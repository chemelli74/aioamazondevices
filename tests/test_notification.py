# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Alexa notifications handler."""

from collections.abc import Callable
from datetime import UTC, datetime, tzinfo
from http import HTTPMethod
from typing import Any
from unittest.mock import AsyncMock

import pytest
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.devices import DEVICE_TYPES_TO_IGNORE
from aioamazondevices.const.http import REQUEST_AGENT, URI_NOTIFICATIONS
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.implementation import notification
from aioamazondevices.structures import AmazonDevice, AmazonSchedule

from .const import TEST_SERIAL_1, TEST_SERIAL_2

# A Wednesday, so weekday and weekend rules land on different days.
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
NOW_MS = int(NOW.timestamp() * 1000)
HOUR_MS = 3_600_000


class FrozenDatetime(datetime):
    """A datetime whose now() always returns NOW."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> "FrozenDatetime":
        """Return NOW in the given timezone."""
        return cls.fromtimestamp(NOW.timestamp(), tz=tz or UTC)


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the time seen by the notification module."""
    monkeypatch.setattr(notification, "datetime", FrozenDatetime)


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    """Return a UTC datetime in the same month as NOW."""
    return datetime(2026, 10 if day >= NOW.day else 11, day, hour, minute, tzinfo=UTC)


def _schedule(
    schedule_type: str,
    *,
    serial: str = TEST_SERIAL_1,
    device_type: str = "A1B2C3",
    status: str = "ON",
    label: str = "",
    **fields: object,
) -> dict[str, Any]:
    """Build a notification as returned by the notifications API."""
    label_type = "Alarm" if schedule_type == "MusicAlarm" else schedule_type
    return {
        "type": schedule_type,
        "deviceType": device_type,
        "deviceSerialNumber": serial,
        "status": status,
        f"{label_type.lower()}Label": label,
        **fields,
    }


def _timer(
    offset_ms: int, label: str, *, status: str = "ON", device_type: str = "A1B2C3"
) -> dict[str, Any]:
    """Build a timer that fires offset_ms after NOW."""
    return _schedule(
        "Timer",
        label=label,
        status=status,
        device_type=device_type,
        triggerTime=NOW_MS + offset_ms,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("schedule", "expected"),
    [
        pytest.param(
            {
                "type": "Alarm",
                "originalDate": "2026-10-28",
                "originalTime": "18:30:00.000",
            },
            _at(28, 18, 30),
            id="single-alarm",
        ),
        pytest.param(
            {
                "type": "Alarm",
                "originalDate": "2026-10-28",
                "originalTime": "07:00:00.000",
            },
            None,
            id="single-alarm-in-past",
        ),
        pytest.param(
            {"type": "Timer", "triggerTime": NOW_MS + HOUR_MS},
            _at(28, 13),
            id="timer",
        ),
        pytest.param(
            {"type": "Reminder", "alarmTime": NOW_MS + 2 * HOUR_MS},
            _at(28, 14),
            id="reminder",
        ),
        pytest.param(
            {"type": "Reminder", "alarmTime": NOW_MS - HOUR_MS},
            None,
            id="reminder-in-past",
        ),
        pytest.param(
            {"type": "Alarm", "recurringPattern": "P1D", "originalTime": "13:00"},
            _at(28, 13),
            id="daily-later-today",
        ),
        pytest.param(
            {"type": "Alarm", "recurringPattern": "P1D", "originalTime": "07:00"},
            _at(29, 7),
            id="daily-tomorrow",
        ),
        pytest.param(
            {"type": "Alarm", "recurringPattern": "XXXX-WD", "originalTime": "07:00"},
            _at(29, 7),
            id="weekdays",
        ),
        pytest.param(
            {"type": "Alarm", "recurringPattern": "XXXX-WE", "originalTime": "09:00"},
            _at(31, 9),
            id="weekends",
        ),
        pytest.param(
            {
                "type": "Alarm",
                "recurringPattern": "XXXX-WXX-1",
                "originalTime": "06:45",
            },
            _at(2, 6, 45),
            id="mondays",
        ),
        pytest.param(
            {
                "type": "Alarm",
                "rRuleData": {"recurrenceRules": ["FREQ=WEEKLY;BYDAY=FR;"]},
                "originalTime": "08:15",
            },
            _at(30, 8, 15),
            id="rfc5545-adds-time",
        ),
        pytest.param(
            {
                "type": "Reminder",
                "rRuleData": {"recurrenceRules": ["FREQ=DAILY;BYHOUR=6;BYMINUTE=30"]},
                "originalTime": "09:00",
            },
            _at(29, 6, 30),
            id="rfc5545-keeps-own-time",
        ),
        pytest.param(
            {"type": "Reminder", "rRuleData": {"recurrenceRules": ["FREQ=DAILY"]}},
            _at(29, 0),
            id="rfc5545-without-time",
        ),
        pytest.param(
            {
                "type": "Alarm",
                "rRuleData": {"recurrenceRules": ["FREQ=WEEKLY;BYDAY=SA"]},
                "recurringPattern": "XXXX-WXX-5",
                "originalTime": "10:00",
            },
            _at(30, 10),
            id="earliest-of-several-rules",
        ),
        pytest.param(
            {
                "type": "Alarm",
                "rRuleData": {"recurrenceRules": ["FREQ=DAILY;COUNT=3"]},
                "originalDate": "2026-10-01",
                "originalTime": "07:00",
            },
            None,
            id="rfc5545-finished",
        ),
    ],
)
async def test_parse_next_occurrence(
    api: AmazonEchoApi, schedule: dict[str, Any], expected: datetime | None
) -> None:
    """The next occurrence is found for single and recurring schedules."""
    assert api._notification_handler._parse_next_occurrence(schedule) == expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("schedule", "message"),
    [
        pytest.param(
            {"type": "Alarm", "recurringPattern": "XXXX-WXX-9"},
            "Unknown recurring rule <XXXX-WXX-9> for schedule type <Alarm>",
            id="unknown-recurring-rule",
        ),
        pytest.param(
            {"type": "Birthday"},
            "Unknown schedule type: Birthday",
            id="unknown-type",
        ),
    ],
)
async def test_parse_next_occurrence_unknown_schedule_warns(
    api: AmazonEchoApi,
    caplog: pytest.LogCaptureFixture,
    schedule: dict[str, Any],
    message: str,
) -> None:
    """Schedules that cannot be understood have no next occurrence."""
    assert api._notification_handler._parse_next_occurrence(schedule) is None
    assert message in caplog.text


@pytest.mark.anyio
async def test_get_notifications_request(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """Notifications are requested with a browser user agent."""
    session_request = mock_json_response({"notifications": []})

    assert await api._notification_handler.get_notifications() == {}

    session_request.assert_awaited_once_with(
        HTTPMethod.GET,
        url=URL.joinpath(api._session_state_data.alexa_website_url, URI_NOTIFICATIONS),
        extended_headers={"User-Agent": REQUEST_AGENT["Browser"]},
    )


@pytest.mark.anyio
async def test_get_notifications_request_failure_returns_none(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed request returns None, so device notifications are kept."""
    monkeypatch.setattr(
        api._http_wrapper,
        "session_request",
        AsyncMock(side_effect=CannotRetrieveData("boom")),
    )

    assert await api._notification_handler.get_notifications() is None
    assert "Failed to obtain notification data" in caplog.text


@pytest.mark.anyio
async def test_get_notifications_keeps_next_of_each_type(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """Each device keeps the next active notification of each supported type."""
    mock_json_response(
        {
            "notifications": [
                _timer(2 * HOUR_MS, label="later"),
                _timer(HOUR_MS, label="sooner"),
                _timer(3 * HOUR_MS, label="latest"),
                _timer(HOUR_MS // 2, label="off", status="OFF"),
                _timer(-HOUR_MS, label="expired"),
                _timer(
                    HOUR_MS // 2,
                    label="ignored device",
                    device_type=DEVICE_TYPES_TO_IGNORE[0],
                ),
                _schedule(
                    "MusicAlarm",
                    label="wake up",
                    originalDate="2026-10-29",
                    originalTime="07:00:00.000",
                ),
                _schedule("Reminder", serial=TEST_SERIAL_2, alarmTime=NOW_MS + HOUR_MS),
                _schedule("Birthday"),
            ]
        }
    )

    notifications = await api._notification_handler.get_notifications()

    assert notifications == {
        TEST_SERIAL_1: {
            "Timer": AmazonSchedule("Timer", "ON", "sooner", _at(28, 13)),
            "Alarm": AmazonSchedule("Alarm", "ON", "wake up", _at(29, 7)),
        },
        TEST_SERIAL_2: {
            "Reminder": AmazonSchedule("Reminder", "ON", "", _at(28, 13)),
        },
    }


@pytest.mark.anyio
async def test_update_device_notifications_by_capability(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """Devices get only the notification types their capabilities support."""
    alarm = AmazonSchedule("Alarm", "ON", "", _at(29, 7))
    timer = AmazonSchedule("Timer", "ON", "", _at(28, 13))
    reminder = AmazonSchedule("Reminder", "ON", "", _at(28, 14))
    all_types = {"Alarm": alarm, "Timer": timer, "Reminder": reminder}
    reminders_only = make_device(TEST_SERIAL_1, capabilities=["REMINDERS"])
    timers_and_alarms = make_device(TEST_SERIAL_2, capabilities=["TIMERS_AND_ALARMS"])
    no_notifications = make_device("9999", capabilities=["REMINDERS"])
    no_notifications.notifications = {"Reminder": reminder}

    api._notification_handler.update_device_notifications(
        {
            TEST_SERIAL_1: reminders_only,
            TEST_SERIAL_2: timers_and_alarms,
            "9999": no_notifications,
        },
        {TEST_SERIAL_1: all_types, TEST_SERIAL_2: all_types},
    )

    assert reminders_only.notifications == {"Reminder": reminder}
    assert timers_and_alarms.notifications == {"Alarm": alarm, "Timer": timer}
    assert no_notifications.notifications == {}


@pytest.mark.anyio
async def test_update_device_notifications_without_data_keeps_existing(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """When notifications could not be fetched, devices keep their old ones."""
    reminder = AmazonSchedule("Reminder", "ON", "", _at(28, 14))
    device = make_device(TEST_SERIAL_1, capabilities=["REMINDERS"])
    device.notifications = {"Reminder": reminder}

    api._notification_handler.update_device_notifications({TEST_SERIAL_1: device}, None)

    assert device.notifications == {"Reminder": reminder}
