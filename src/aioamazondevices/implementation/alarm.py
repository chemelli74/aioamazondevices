# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Alarm module for Amazon devices."""

from http import HTTPMethod
from typing import Any

from yarl import URL

from aioamazondevices.const.http import REQUEST_AGENT, URI_NOTIFICATIONS
from aioamazondevices.const.schedules import (
    ALARM_DAYS,
    NOTIFICATION_ALARM,
    NOTIFICATION_MUSIC_ALARM,
)
from aioamazondevices.implementation.notification import AmazonNotificationHandler
from aioamazondevices.structures import AmazonAlarm, AmazonDevice

ALARM_RULE_PARTS = {"FREQ", "INTERVAL", "BYDAY", "BYHOUR", "BYMINUTE"}


class AmazonAlarmHandler(AmazonNotificationHandler):
    """Class to handle Alexa alarms."""

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
            for schedule in notifications["notifications"]
            if schedule["type"] in (NOTIFICATION_ALARM, NOTIFICATION_MUSIC_ALARM)
            and schedule["deviceSerialNumber"] == device.serial_number
        ]

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
