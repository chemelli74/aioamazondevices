# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Alarm module for Amazon devices."""

from datetime import datetime, timedelta
from http import HTTPMethod
from typing import Any

from yarl import URL

from aioamazondevices.const.http import (
    REFRESH_ACCESS_TOKEN,
    REQUEST_AGENT,
    URI_ALARMS,
    URI_ENDPOINTS,
    URI_NOTIFICATIONS,
)
from aioamazondevices.const.schedules import (
    ALARM_DAYS,
    NOTIFICATION_ALARM,
    NOTIFICATION_MUSIC_ALARM,
)
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.implementation.notification import AmazonNotificationHandler
from aioamazondevices.structures import AmazonAlarm, AmazonDevice
from aioamazondevices.utils import _LOGGER

ALARM_RULE_PARTS = {"FREQ", "INTERVAL", "BYDAY", "BYHOUR", "BYMINUTE"}


class AmazonAlarmHandler(AmazonNotificationHandler):
    """Class to handle Alexa alarms."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize AmazonAlarmHandler class."""
        super().__init__(http_wrapper, session_state_data)
        self._alexa_api_url: URL | None = None

    async def get_alarms(self, device: AmazonDevice) -> list[AmazonAlarm]:
        """Get all alarms of a device, including disabled ones."""
        _, raw_resp = await self._http_wrapper.session_request(
            HTTPMethod.GET,
            url=URL.joinpath(
                self._session_state_data.alexa_website_url, URI_NOTIFICATIONS
            ),
            extended_headers={"User-Agent": REQUEST_AGENT["Browser"]},
        )
        notifications = await self._http_wrapper.response_to_json(raw_resp, "alarms")

        return [
            AmazonAlarm(
                id=schedule["id"],
                status=schedule["status"],
                label=schedule.get("alarmLabel"),
                repeat_days=self._parse_repeat_days(schedule),
                next_occurrence=self._parse_next_occurrence(
                    schedule | {"type": NOTIFICATION_ALARM}
                ),
                raw_data=schedule,
            )
            for schedule in notifications.get("notifications", [])
            if schedule["type"] in (NOTIFICATION_ALARM, NOTIFICATION_MUSIC_ALARM)
            and schedule["deviceSerialNumber"] == device.serial_number
        ]

    async def create_alarm(
        self,
        device: AmazonDevice,
        scheduled_time: datetime,
        repeat_days: list[str] | None = None,
    ) -> None:
        """Create an alarm."""
        payload = {
            "trigger": self._alarm_trigger(scheduled_time, repeat_days),
            "extensions": [],
            "endpointId": f"{device.serial_number}@{device.device_type}",
        }
        # Not retried, a retry could create a second alarm
        await self._call_alarms_api(HTTPMethod.POST, payload=payload, fail_fast=True)

    async def update_alarm(
        self,
        alarm: AmazonAlarm,
        scheduled_time: datetime,
        repeat_days: list[str] | None = None,
    ) -> None:
        """Change the time of an alarm, keeping its repeat days unless given."""
        # Amazon replaces the schedule, an alarm sent without its repeat
        # days becomes a one-off
        if repeat_days is None:
            if alarm.repeat_days is None:
                raise ValueError(f"Repeat days of alarm {alarm.id} are unknown")
            repeat_days = alarm.repeat_days

        payload = {
            "trigger": self._alarm_trigger(scheduled_time, repeat_days),
            "extensions": [],
            **self._alarm_assets(alarm),
        }
        await self._call_alarms_api(
            HTTPMethod.PUT, alarm.raw_data["notificationIndex"], payload=payload
        )

    async def set_alarm_status(self, alarm: AmazonAlarm, enable: bool) -> None:
        """Enable or disable an alarm."""
        notification_index = alarm.raw_data["notificationIndex"]
        if not enable:
            await self._call_alarms_api(HTTPMethod.PUT, f"{notification_index}/cancel")
            return

        payload = {
            "trigger": {
                "scheduledTime": self._format_alarm_time(self._next_alarm_time(alarm))
            },
            "extensions": [],
            **self._alarm_assets(alarm),
        }
        await self._call_alarms_api(
            HTTPMethod.PUT, f"{notification_index}/activate", payload=payload
        )

    async def delete_alarm(self, alarm: AmazonAlarm) -> None:
        """Delete an alarm."""
        await self._http_wrapper.session_request(
            method=HTTPMethod.DELETE,
            url=URL.joinpath(
                self._session_state_data.alexa_website_url,
                URI_NOTIFICATIONS,
                alarm.id,
            ),
            input_data=alarm.raw_data,
            json_data=True,
        )

    async def _call_alarms_api(
        self,
        method: HTTPMethod,
        path: str = "",
        *,
        payload: dict[str, Any] | None = None,
        fail_fast: bool = False,
    ) -> None:
        """Call the Alexa alarms API."""
        if self._alexa_api_url is None:
            _, raw_resp = await self._http_wrapper.session_request(
                method=HTTPMethod.GET,
                url=URL.joinpath(
                    self._session_state_data.alexa_website_url, URI_ENDPOINTS
                ),
            )
            endpoints = await self._http_wrapper.response_to_json(raw_resp, "endpoints")
            if not (alexa_api_url := endpoints.get("alexaApiUrl")):
                raise CannotRetrieveData("Alexa API URL not found")
            self._alexa_api_url = URL(alexa_api_url)

        refresh_successful, _ = await self._http_wrapper.refresh_data(
            REFRESH_ACCESS_TOKEN
        )
        if not refresh_successful:
            _LOGGER.warning("Access token refresh failed")

        access_token = self._session_state_data.login_stored_data[REFRESH_ACCESS_TOKEN]

        url = URL.joinpath(self._alexa_api_url, URI_ALARMS)
        if path:
            url = URL.joinpath(url, path)

        await self._http_wrapper.session_request(
            method=method,
            url=url,
            input_data=payload,
            json_data=payload is not None,
            extended_headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": REQUEST_AGENT["Amazon"],
            },
            fail_fast=fail_fast,
        )

    def _alarm_trigger(
        self,
        scheduled_time: datetime,
        repeat_days: list[str] | None,
    ) -> dict[str, Any]:
        """Return the trigger of an alarm."""
        if scheduled_time.tzinfo:
            scheduled_time = scheduled_time.astimezone()
        trigger: dict[str, Any] = {
            "scheduledTime": self._format_alarm_time(scheduled_time)
        }
        if not repeat_days:
            return trigger

        if invalid_days := set(repeat_days) - set(ALARM_DAYS):
            raise ValueError(f"Invalid repeat days: {sorted(invalid_days)}")

        if set(repeat_days) == set(ALARM_DAYS):
            trigger["recurrence"] = {"freq": "DAILY", "byDay": [], "interval": 1}
        else:
            trigger["recurrence"] = {
                "freq": "WEEKLY",
                "byDay": [day for day in ALARM_DAYS if day in repeat_days],
                "interval": 1,
            }
        return trigger

    def _alarm_assets(self, alarm: AmazonAlarm) -> dict[str, Any]:
        """Return the tone of an alarm, to keep it when changing the alarm."""
        if music_alarm_id := alarm.raw_data.get("musicAlarmId"):
            asset_id = f"MUSIC-{music_alarm_id}"
        elif sound_id := (alarm.raw_data.get("sound") or {}).get("id"):
            asset_id = sound_id
        else:
            return {}
        return {"assets": [{"type": "TONE", "assetId": asset_id}]}

    def _format_alarm_time(self, scheduled_time: datetime) -> str:
        """Format a time as the device's local time."""
        return scheduled_time.strftime("%Y-%m-%dT%H:%M:%S")

    def _next_alarm_time(self, alarm: AmazonAlarm) -> datetime:
        """Return when an alarm rings next once enabled."""
        repeat_days = alarm.repeat_days
        schedule = alarm.raw_data | {"type": NOTIFICATION_ALARM}
        now = datetime.now().astimezone()
        if not (next_time := self._parse_next_occurrence(schedule)):
            if repeat_days != []:
                raise ValueError(f"Next occurrence of alarm {alarm.id} is unknown")
            # One-off alarm in the past rings at the same time today or tomorrow
            hour, minute = schedule["originalTime"].split(":")[:2]
            next_time = now.replace(
                hour=int(hour), minute=int(minute), second=0, microsecond=0
            )

        # The next occurrence can be up to a minute in the past
        if next_time <= now and repeat_days is None:
            raise ValueError(f"Next occurrence of alarm {alarm.id} is unknown")
        while next_time <= now or (
            repeat_days and ALARM_DAYS[next_time.weekday()] not in repeat_days
        ):
            next_time += timedelta(days=1)
        return next_time

    def _parse_repeat_days(self, schedule: dict[str, Any]) -> list[str] | None:
        """Return the days of the week an alarm repeats on."""
        recurring_rules: list[str] = list(
            (schedule.get("rRuleData") or {}).get("recurrenceRules") or []
        )
        if recurring_pattern := schedule.get("recurringPattern"):
            recurring_rules.append(
                self._recurring_patterns().get(recurring_pattern, recurring_pattern)
            )

        repeat_days: set[str] = set()
        for recurring_rule in recurring_rules:
            rule: dict[str, str] = {}
            for part in recurring_rule.removesuffix(";").split(";"):
                key, _, value = part.partition("=")
                rule[key] = value
            # Only weekly rules can be sent back as repeat days
            if (
                rule.get("FREQ") not in ("DAILY", "WEEKLY")
                or rule.get("INTERVAL", "1") != "1"
                or not rule.keys() <= ALARM_RULE_PARTS
            ):
                return None
            if "BYDAY" in rule:
                days = rule["BYDAY"].split(",")
            elif rule["FREQ"] == "DAILY":
                days = ALARM_DAYS
            else:
                # Weekly on the weekday of a start date we don't know
                return None
            if not set(days) <= set(ALARM_DAYS):
                return None
            repeat_days.update(days)

        return [day for day in ALARM_DAYS if day in repeat_days]
