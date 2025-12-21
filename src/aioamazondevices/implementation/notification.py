"""Module to handle Alexa notifications."""

from datetime import datetime, timedelta
from http import HTTPMethod
from typing import Any

from dateutil.parser import parse
from dateutil.rrule import rrulestr

from aioamazondevices.const.devices import DEVICE_TO_IGNORE
from aioamazondevices.const.http import REQUEST_AGENT, URI_NOTIFICATIONS
from aioamazondevices.const.schedules import (
    COUNTRY_GROUPS,
    NOTIFICATION_ALARM,
    NOTIFICATION_MUSIC_ALARM,
    NOTIFICATION_REMINDER,
    NOTIFICATION_TIMER,
    NOTIFICATIONS_SUPPORTED,
    RECURRING_PATTERNS,
    WEEKEND_EXCEPTIONS,
)
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonSchedule
from aioamazondevices.utils import _LOGGER


class AmazonNotificationHandler:
    """Class to handle Alexa notifications."""

    def __init__(
        self,
        session_state_data: AmazonSessionStateData,
        http_wrapper: AmazonHttpWrapper,
    ) -> None:
        """Initialize AmazonNotificationHandler class."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper

    async def get_notifications(self) -> dict[str, dict[str, AmazonSchedule]] | None:
        """Get all notifications (alarms, timers, reminders)."""
        final_notifications: dict[str, dict[str, AmazonSchedule]] = {}

        try:
            _, raw_resp = await self._http_wrapper.session_request(
                HTTPMethod.GET,
                url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_NOTIFICATIONS}",
                extended_headers={"User-Agent": REQUEST_AGENT["Browser"]},
            )
        except CannotRetrieveData:
            _LOGGER.warning(
                "Failed to obtain notification data.  Timers and alarms have not been updated"  # noqa: E501
            )
            return None

        notifications = await self._http_wrapper.response_to_json(
            raw_resp, "notifications"
        )

        for schedule in notifications["notifications"]:
            schedule_type: str = schedule["type"]
            schedule_device_type = schedule["deviceType"]
            schedule_device_serial = schedule["deviceSerialNumber"]

            if schedule_device_type in DEVICE_TO_IGNORE:
                continue

            if schedule_type not in NOTIFICATIONS_SUPPORTED:
                _LOGGER.debug(
                    "Unsupported schedule type %s for device %s",
                    schedule_type,
                    schedule_device_serial,
                )
                continue

            if schedule_type == NOTIFICATION_MUSIC_ALARM:
                # Structure is the same as standard Alarm
                schedule_type = NOTIFICATION_ALARM
                schedule["type"] = NOTIFICATION_ALARM
            label_desc = schedule_type.lower() + "Label"
            if (schedule_status := schedule["status"]) == "ON" and (
                next_occurrence := await self._parse_next_occurrence(schedule)
            ):
                schedule_notification_list = final_notifications.get(
                    schedule_device_serial, {}
                )
                schedule_notification_by_type = schedule_notification_list.get(
                    schedule_type
                )
                # Replace if no existing notification
                # or if existing.next_occurrence is None
                # or if new next_occurrence is earlier
                if (
                    not schedule_notification_by_type
                    or schedule_notification_by_type.next_occurrence is None
                    or next_occurrence < schedule_notification_by_type.next_occurrence
                ):
                    final_notifications.update(
                        {
                            schedule_device_serial: {
                                **schedule_notification_list
                                | {
                                    schedule_type: AmazonSchedule(
                                        type=schedule_type,
                                        status=schedule_status,
                                        label=schedule[label_desc],
                                        next_occurrence=next_occurrence,
                                    ),
                                }
                            }
                        }
                    )

        return final_notifications

    async def _parse_next_occurrence(
        self,
        schedule: dict[str, Any],
    ) -> datetime | None:
        """Parse RFC5545 rule set for next iteration."""
        # Local timezone
        tzinfo = datetime.now().astimezone().tzinfo
        # Current time
        actual_time = datetime.now(tz=tzinfo)
        # Reference start date
        today_midnight = actual_time.replace(hour=0, minute=0, second=0, microsecond=0)
        # Reference time (1 minute ago to avoid edge cases)
        now_reference = actual_time - timedelta(minutes=1)

        # Schedule data
        original_date = schedule.get("originalDate")
        original_time = schedule.get("originalTime")

        recurring_rules: list[str] = []
        if schedule.get("rRuleData"):
            recurring_rules = schedule["rRuleData"]["recurrenceRules"]
        if schedule.get("recurringPattern"):
            recurring_rules.append(schedule["recurringPattern"])

        # Recurring events
        if recurring_rules:
            next_candidates: list[datetime] = []
            for recurring_rule in recurring_rules:
                # Already in RFC5545 format
                if "FREQ=" in recurring_rule:
                    rule = await self._add_hours_minutes(recurring_rule, original_time)

                    # Add date to candidates list
                    next_candidates.append(
                        rrulestr(rule, dtstart=today_midnight).after(
                            now_reference, True
                        ),
                    )
                    continue

                if recurring_rule not in RECURRING_PATTERNS:
                    _LOGGER.warning(
                        "Unknown recurring rule <%s> for schedule type <%s>",
                        recurring_rule,
                        schedule["type"],
                    )
                    return None

                # Adjust recurring rules for country specific weekend exceptions
                recurring_pattern = RECURRING_PATTERNS.copy()
                for group, countries in COUNTRY_GROUPS.items():
                    if self._session_state_data.country_code in countries:
                        recurring_pattern |= WEEKEND_EXCEPTIONS[group]
                        break

                rule = await self._add_hours_minutes(
                    recurring_pattern[recurring_rule], original_time
                )

                # Add date to candidates list
                next_candidates.append(
                    rrulestr(rule, dtstart=today_midnight).after(now_reference, True),
                )

            return min(next_candidates) if next_candidates else None

        # Single events
        if schedule["type"] == NOTIFICATION_ALARM:
            timestamp = parse(f"{original_date} {original_time}").replace(tzinfo=tzinfo)

        elif schedule["type"] == NOTIFICATION_TIMER:
            # API returns triggerTime in milliseconds since epoch
            timestamp = datetime.fromtimestamp(
                schedule["triggerTime"] / 1000, tz=tzinfo
            )

        elif schedule["type"] == NOTIFICATION_REMINDER:
            # API returns alarmTime in milliseconds since epoch
            timestamp = datetime.fromtimestamp(schedule["alarmTime"] / 1000, tz=tzinfo)

        else:
            _LOGGER.warning(("Unknown schedule type: %s"), schedule["type"])
            return None

        if timestamp > now_reference:
            return timestamp

        return None

    async def _add_hours_minutes(
        self,
        recurring_rule: str,
        original_time: str | None,
    ) -> str:
        """Add hours and minutes to a RFC5545 string."""
        rule = recurring_rule.removesuffix(";")

        if not original_time:
            return rule

        # Add missing BYHOUR, BYMINUTE if needed (Alarms only)
        if "BYHOUR=" not in recurring_rule:
            hour = int(original_time.split(":")[0])
            rule += f";BYHOUR={hour}"
        if "BYMINUTE=" not in recurring_rule:
            minute = int(original_time.split(":")[1])
            rule += f";BYMINUTE={minute}"

        return rule
