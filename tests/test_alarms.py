# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Alexa alarms handler."""

from collections.abc import Callable
from datetime import UTC, datetime, tzinfo
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.implementation import notification
from aioamazondevices.implementation.alarm import AmazonAlarmHandler
from aioamazondevices.structures import AmazonAlarm, AmazonDevice

from .const import TEST_SERIAL_1, TEST_SERIAL_2

# A Wednesday.
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


class FrozenDatetime(datetime):
    """A datetime whose now() always returns NOW."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> "FrozenDatetime":
        """Return NOW in the given timezone."""
        return cls.fromtimestamp(NOW.timestamp(), tz=tz or UTC)

    def astimezone(self, tz: tzinfo | None = None) -> "FrozenDatetime":
        """Treat UTC as the host's local timezone."""
        return super().astimezone(tz or UTC)


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the time seen by the notification module."""
    monkeypatch.setattr(notification, "datetime", FrozenDatetime)


def _alarm(
    notification_index: str = "idx-1",
    *,
    serial: str = TEST_SERIAL_1,
    **fields: object,
) -> dict[str, Any]:
    """Build an alarm as returned by the notifications API."""
    return {
        "id": f"A1B2C3-{serial}-{notification_index}",
        "notificationIndex": notification_index,
        "type": "Alarm",
        "deviceType": "A1B2C3",
        "deviceSerialNumber": serial,
        "status": "ON",
        "alarmLabel": None,
        "originalDate": "2026-10-29",
        "originalTime": "07:30:00.000",
        **fields,
    }


@pytest.fixture
def handler(api: AmazonEchoApi) -> AmazonAlarmHandler:
    """Return the alarm handler."""
    return api._alarm_handler


@pytest.mark.anyio
async def test_get_alarms(
    handler: AmazonAlarmHandler,
    make_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """All alarms of the device are returned, enabled or not."""
    music_alarm = _alarm("idx-2", type="MusicAlarm", status="OFF")
    mock_json_response(
        {
            "notifications": [
                _alarm(alarmLabel="Work"),
                music_alarm,
                _alarm("idx-3", serial=TEST_SERIAL_2),
                _alarm("idx-4", type="Timer"),
            ]
        }
    )

    alarms = await handler.get_alarms(make_device(TEST_SERIAL_1))

    assert alarms == [
        AmazonAlarm(
            id=f"A1B2C3-{TEST_SERIAL_1}-idx-1",
            status="ON",
            label="Work",
            repeat_days=[],
            next_occurrence=datetime(2026, 10, 29, 7, 30, tzinfo=UTC),
            raw_data=_alarm(alarmLabel="Work"),
        ),
        AmazonAlarm(
            id=f"A1B2C3-{TEST_SERIAL_1}-idx-2",
            status="OFF",
            label=None,
            repeat_days=[],
            next_occurrence=datetime(2026, 10, 29, 7, 30, tzinfo=UTC),
            raw_data=music_alarm,
        ),
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        pytest.param({}, [], id="one-off"),
        pytest.param(
            {"recurringPattern": "P1D"},
            ["MO", "TU", "WE", "TH", "FR", "SA", "SU"],
            id="daily",
        ),
        pytest.param(
            {"recurringPattern": "XXXX-WD"},
            ["MO", "TU", "WE", "TH", "FR"],
            id="weekdays",
        ),
        pytest.param(
            {"recurringPattern": "XXXX-WXX-6"},
            ["SA"],
            id="one-day",
        ),
        pytest.param(
            {"rRuleData": {"recurrenceRules": ["FREQ=WEEKLY;BYDAY=WE,MO;"]}},
            ["MO", "WE"],
            id="rrule",
        ),
        pytest.param(
            {"rRuleData": {"recurrenceRules": ["FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"]}},
            None,
            id="every-other-week",
        ),
        pytest.param(
            {"rRuleData": {"recurrenceRules": ["FREQ=MONTHLY;BYMONTHDAY=1"]}},
            None,
            id="monthly",
        ),
        pytest.param({"recurringPattern": "XXXX-XX-01"}, None, id="unknown"),
        pytest.param(
            {"rRuleData": {"recurrenceRules": ["FREQ=WEEKLY"]}},
            None,
            id="weekly-without-days",
        ),
        pytest.param(
            {"rRuleData": {"recurrenceRules": ["FREQ=WEEKLY;BYDAY=+1MO"]}},
            None,
            id="unknown-day",
        ),
    ],
)
async def test_parse_repeat_days(
    handler: AmazonAlarmHandler,
    fields: dict[str, Any],
    expected: list[str] | None,
) -> None:
    """Repeat days are read from Amazon's recurrence."""
    assert handler._parse_repeat_days(_alarm(**fields)) == expected


@pytest.mark.anyio
async def test_get_alarms_keeps_raw_data(
    handler: AmazonAlarmHandler,
    make_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """Reading an alarm leaves the notification as Amazon sent it."""
    raw_alarm = _alarm(
        rRuleData={"recurrenceRules": ["FREQ=WEEKLY;BYDAY=MO"]},
        recurringPattern="XXXX-WXX-1",
    )
    mock_json_response({"notifications": [raw_alarm]})

    (alarm_1,) = await handler.get_alarms(make_device(TEST_SERIAL_1))

    assert alarm_1.raw_data["rRuleData"]["recurrenceRules"] == ["FREQ=WEEKLY;BYDAY=MO"]


@pytest.mark.anyio
async def test_get_alarms_empty_response(
    handler: AmazonAlarmHandler,
    make_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """An empty response means no alarms."""
    mock_json_response({})

    assert await handler.get_alarms(make_device(TEST_SERIAL_1)) == []
