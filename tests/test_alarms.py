# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Alexa alarms handler."""

from collections.abc import Callable
from datetime import UTC, datetime, tzinfo
from http import HTTPMethod
from typing import Any
from unittest.mock import AsyncMock

import pytest
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import REFRESH_ACCESS_TOKEN, REQUEST_AGENT
from aioamazondevices.const.schedules import COUNTRY_GROUPS
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.implementation import alarm, notification
from aioamazondevices.implementation.alarm import AmazonAlarmHandler
from aioamazondevices.structures import AmazonAlarm, AmazonDevice

from .const import TEST_SERIAL_1, TEST_SERIAL_2

TEST_ACCESS_TOKEN = "Atna|token"  # noqa: S105
TEST_ALEXA_API_URL = "https://api.eu.amazonalexa.com"
ALARMS_URL = f"{TEST_ALEXA_API_URL}/v1/alerts/alarms"

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
    """Freeze the time seen by the notification and alarm modules."""
    monkeypatch.setattr(notification, "datetime", FrozenDatetime)
    monkeypatch.setattr(alarm, "datetime", FrozenDatetime)


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


@pytest.fixture(autouse=True)
def refresh_data(api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Return the mock of the access token refresh."""
    refresh_data = AsyncMock(return_value=(True, {}))
    monkeypatch.setattr(api._http_wrapper, "refresh_data", refresh_data)
    return refresh_data


@pytest.fixture
def handler(api: AmazonEchoApi) -> AmazonAlarmHandler:
    """Return the alarm handler with a logged-in access token."""
    api._session_state_data.login_stored_data = {
        REFRESH_ACCESS_TOKEN: TEST_ACCESS_TOKEN
    }
    return api._alarm_handler


@pytest.fixture
def session_request(
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> AsyncMock:
    """Return the session_request mock, with the endpoints naming the API host."""
    return mock_json_response({"alexaApiUrl": TEST_ALEXA_API_URL})


def _alarm_calls(session_request: AsyncMock) -> list[tuple[str, str, Any]]:
    """Return method, URL and payload of the calls to the alarms API."""
    return [
        (call.kwargs["method"], str(call.kwargs["url"]), call.kwargs["input_data"])
        for call in session_request.call_args_list
        if str(call.kwargs["url"]).startswith(ALARMS_URL)
    ]


def _make_alarm(
    handler: AmazonAlarmHandler, raw_data: dict[str, Any] | None = None
) -> AmazonAlarm:
    """Build an AmazonAlarm the way get_alarms does."""
    raw_data = raw_data or _alarm()
    return AmazonAlarm(
        id=raw_data["id"],
        status=raw_data["status"],
        label=None,
        repeat_days=handler._parse_repeat_days(raw_data),
        next_occurrence=None,
        raw_data=raw_data,
    )


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


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("repeat_days", "trigger"),
    [
        pytest.param(None, {"scheduledTime": "2026-10-29T07:30:00"}, id="one-off"),
        pytest.param(
            ["FR", "MO"],
            {
                "scheduledTime": "2026-10-29T07:30:00",
                "recurrence": {"freq": "WEEKLY", "byDay": ["MO", "FR"], "interval": 1},
            },
            id="weekly",
        ),
        pytest.param(
            ["MO", "TU", "WE", "TH", "FR", "SA", "SU"],
            {
                "scheduledTime": "2026-10-29T07:30:00",
                "recurrence": {"freq": "DAILY", "byDay": [], "interval": 1},
            },
            id="daily",
        ),
    ],
)
async def test_create_alarm(
    handler: AmazonAlarmHandler,
    make_device: Callable[..., AmazonDevice],
    session_request: AsyncMock,
    repeat_days: list[str] | None,
    trigger: dict[str, Any],
) -> None:
    """An alarm is created on the Alexa API host named by the endpoints."""
    await handler.create_alarm(
        make_device(TEST_SERIAL_1),
        datetime.fromisoformat("2026-10-29T07:30"),
        repeat_days,
    )

    assert _alarm_calls(session_request) == [
        (
            HTTPMethod.POST,
            ALARMS_URL,
            {
                "trigger": trigger,
                "extensions": [],
                "endpointId": f"{TEST_SERIAL_1}@A1B2C3",
            },
        )
    ]


@pytest.mark.anyio
async def test_create_alarm_request(
    handler: AmazonAlarmHandler,
    make_device: Callable[..., AmazonDevice],
    session_request: AsyncMock,
    refresh_data: AsyncMock,
) -> None:
    """Alarms are sent with a fresh access token and are not retried."""
    await handler.create_alarm(
        make_device(TEST_SERIAL_1), datetime.fromisoformat("2026-10-29T07:30")
    )

    kwargs = session_request.call_args.kwargs
    assert kwargs["json_data"] is True
    assert kwargs["fail_fast"] is True
    assert kwargs["extended_headers"] == {
        "Authorization": f"Bearer {TEST_ACCESS_TOKEN}",
        "User-Agent": REQUEST_AGENT["Amazon"],
    }
    refresh_data.assert_awaited_once_with(REFRESH_ACCESS_TOKEN)


@pytest.mark.anyio
async def test_create_alarm_invalid_repeat_days(
    handler: AmazonAlarmHandler,
    make_device: Callable[..., AmazonDevice],
    session_request: AsyncMock,
) -> None:
    """Unknown repeat days are rejected before calling Amazon."""
    with pytest.raises(ValueError, match="MONDAY"):
        await handler.create_alarm(
            make_device(TEST_SERIAL_1),
            datetime.fromisoformat("2026-10-29T07:30"),
            ["MONDAY"],
        )

    session_request.assert_not_awaited()


@pytest.mark.anyio
async def test_alexa_api_url_looked_up_once(
    handler: AmazonAlarmHandler,
    session_request: AsyncMock,
) -> None:
    """The Alexa API host is only looked up for the first alarm request."""
    await handler.set_alarm_status(_make_alarm(handler), False)
    await handler.set_alarm_status(_make_alarm(handler), False)

    assert [str(call.kwargs["url"]) for call in session_request.call_args_list] == [
        "https://alexa.amazon.com/api/endpoints",
        f"{ALARMS_URL}/idx-1/cancel",
        f"{ALARMS_URL}/idx-1/cancel",
    ]


@pytest.mark.anyio
async def test_alexa_api_url_missing(
    handler: AmazonAlarmHandler,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """Without an Alexa API host no alarm request is sent."""
    session_request = mock_json_response({})

    with pytest.raises(CannotRetrieveData):
        await handler.set_alarm_status(_make_alarm(handler), False)

    assert _alarm_calls(session_request) == []


@pytest.mark.anyio
async def test_disable_alarm(
    handler: AmazonAlarmHandler,
    session_request: AsyncMock,
) -> None:
    """Disabling an alarm cancels it without a body."""
    await handler.set_alarm_status(_make_alarm(handler), False)

    assert _alarm_calls(session_request) == [
        (HTTPMethod.PUT, f"{ALARMS_URL}/idx-1/cancel", None)
    ]
    assert session_request.call_args.kwargs["json_data"] is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("raw_data", "scheduled_time"),
    [
        pytest.param(_alarm(), "2026-10-29T07:30:00", id="one-off-future"),
        pytest.param(
            _alarm(originalDate="2026-10-01", originalTime="13:00:00.000"),
            "2026-10-28T13:00:00",
            id="one-off-past-later-today",
        ),
        pytest.param(
            _alarm(originalDate="2026-10-01", originalTime="07:30:00.000"),
            "2026-10-29T07:30:00",
            id="one-off-past-tomorrow",
        ),
        pytest.param(
            _alarm(originalDate="2026-10-01", recurringPattern="XXXX-WD"),
            "2026-10-29T07:30:00",
            id="weekdays",
        ),
        pytest.param(
            _alarm(originalDate="2026-10-01", recurringPattern="XXXX-WE"),
            "2026-10-31T07:30:00",
            id="weekend",
        ),
        pytest.param(
            _alarm(originalDate="2026-10-28", originalTime="11:59:30.000"),
            "2026-10-29T11:59:30",
            id="one-off-just-rung",
        ),
        pytest.param(
            _alarm(
                originalDate="2026-10-01",
                originalTime="11:59:30.000",
                recurringPattern="XXXX-WD",
            ),
            "2026-10-29T11:59:00",
            id="weekdays-just-rung",
        ),
    ],
)
async def test_enable_alarm(
    handler: AmazonAlarmHandler,
    session_request: AsyncMock,
    raw_data: dict[str, Any],
    scheduled_time: str,
) -> None:
    """Enabling an alarm schedules its next occurrence."""
    await handler.set_alarm_status(_make_alarm(handler, raw_data), True)

    assert _alarm_calls(session_request) == [
        (
            HTTPMethod.PUT,
            f"{ALARMS_URL}/idx-1/activate",
            {"trigger": {"scheduledTime": scheduled_time}, "extensions": []},
        )
    ]


@pytest.mark.anyio
async def test_enable_alarm_weekend_country(
    handler: AmazonAlarmHandler,
    session_request: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The weekend of the account's country is used."""
    # Saudi Arabia, whatever the case of COUNTRY_GROUPS.
    country_code = next(c for c in COUNTRY_GROUPS["FR-SA"] if c.lower() == "sa")
    monkeypatch.setattr(handler._session_state_data, "_country_code", country_code)
    alarm_1 = _make_alarm(
        handler, _alarm(originalDate="2026-10-01", recurringPattern="XXXX-WE")
    )

    await handler.set_alarm_status(alarm_1, True)

    assert alarm_1.repeat_days == ["FR", "SA"]
    ((_, _, payload),) = _alarm_calls(session_request)
    assert payload["trigger"]["scheduledTime"] == "2026-10-30T07:30:00"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "raw_data",
    [
        pytest.param(_alarm(recurringPattern="XXXX-XX-01"), id="unknown"),
        pytest.param(
            _alarm(
                originalDate="2026-10-28",
                originalTime="11:59:30.000",
                rRuleData={"recurrenceRules": ["FREQ=WEEKLY;INTERVAL=2;BYDAY=WE"]},
            ),
            id="every-other-week-just-rung",
        ),
    ],
)
async def test_enable_alarm_unknown_recurrence(
    handler: AmazonAlarmHandler,
    session_request: AsyncMock,
    raw_data: dict[str, Any],
) -> None:
    """An alarm with a recurrence that can't be read is not enabled."""
    with pytest.raises(ValueError, match="Next occurrence"):
        await handler.set_alarm_status(_make_alarm(handler, raw_data), True)

    session_request.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("raw_data", "repeat_days", "payload"),
    [
        pytest.param(
            _alarm(recurringPattern="XXXX-WD", sound={"id": "system_alerts_01"}),
            None,
            {
                "trigger": {
                    "scheduledTime": "2026-10-30T06:45:00",
                    "recurrence": {
                        "freq": "WEEKLY",
                        "byDay": ["MO", "TU", "WE", "TH", "FR"],
                        "interval": 1,
                    },
                },
                "extensions": [],
                "assets": [{"type": "TONE", "assetId": "system_alerts_01"}],
            },
            id="keeps-repeat-and-tone",
        ),
        pytest.param(
            _alarm(recurringPattern="XXXX-WD", musicAlarmId="music-1"),
            [],
            {
                "trigger": {"scheduledTime": "2026-10-30T06:45:00"},
                "extensions": [],
                "assets": [{"type": "TONE", "assetId": "MUSIC-music-1"}],
            },
            id="one-off-music",
        ),
        pytest.param(
            _alarm(rRuleData={"recurrenceRules": ["FREQ=MONTHLY;BYMONTHDAY=1"]}),
            ["SA", "SU"],
            {
                "trigger": {
                    "scheduledTime": "2026-10-30T06:45:00",
                    "recurrence": {
                        "freq": "WEEKLY",
                        "byDay": ["SA", "SU"],
                        "interval": 1,
                    },
                },
                "extensions": [],
            },
            id="new-repeat",
        ),
    ],
)
async def test_update_alarm(
    handler: AmazonAlarmHandler,
    session_request: AsyncMock,
    raw_data: dict[str, Any],
    repeat_days: list[str] | None,
    payload: dict[str, Any],
) -> None:
    """Changing an alarm sends its schedule and tone back."""
    await handler.update_alarm(
        _make_alarm(handler, raw_data),
        datetime.fromisoformat("2026-10-30T06:45"),
        repeat_days,
    )

    assert _alarm_calls(session_request) == [
        (HTTPMethod.PUT, f"{ALARMS_URL}/idx-1", payload)
    ]


@pytest.mark.anyio
async def test_update_alarm_unknown_repeat_days(
    handler: AmazonAlarmHandler,
    session_request: AsyncMock,
) -> None:
    """An alarm repeating in an unknown way needs its repeat days."""
    raw_data = _alarm(rRuleData={"recurrenceRules": ["FREQ=MONTHLY;BYMONTHDAY=1"]})

    with pytest.raises(ValueError, match="Repeat days"):
        await handler.update_alarm(
            _make_alarm(handler, raw_data), datetime(2026, 10, 30, 6, 45, tzinfo=UTC)
        )

    session_request.assert_not_awaited()


@pytest.mark.anyio
async def test_delete_alarm(
    handler: AmazonAlarmHandler,
    session_request: AsyncMock,
) -> None:
    """Deleting an alarm sends it back to the notifications endpoint."""
    alarm_1 = _make_alarm(handler)

    await handler.delete_alarm(alarm_1)

    session_request.assert_awaited_once_with(
        method=HTTPMethod.DELETE,
        url=URL(f"https://alexa.amazon.com/api/notifications/{alarm_1.id}"),
        input_data=alarm_1.raw_data,
        json_data=True,
    )


@pytest.mark.anyio
async def test_create_alarm_aware_time(
    handler: AmazonAlarmHandler,
    make_device: Callable[..., AmazonDevice],
    session_request: AsyncMock,
) -> None:
    """An aware time is sent as the local time of the host."""
    scheduled_time = datetime(2026, 10, 29, 7, 30, tzinfo=UTC)

    await handler.create_alarm(make_device(TEST_SERIAL_1), scheduled_time)

    ((_, _, payload),) = _alarm_calls(session_request)
    assert payload["trigger"]["scheduledTime"] == (
        scheduled_time.astimezone().strftime("%Y-%m-%dT%H:%M:%S")
    )
