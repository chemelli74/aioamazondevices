# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for Alexa vocal history parsing."""

from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPMethod
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const import history as history_constants
from aioamazondevices.const.http import CSRF_A2Z, REFRESH_ACCESS_TOKEN
from aioamazondevices.implementation.history import AmazonHistoryHandler
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1, TEST_SERIAL_2

PersonsInfo = dict[str, str] | list[dict[str, str]] | None


class _Absent:
    """Marker for a payload that carries no `personsInfo` key at all."""


ABSENT = _Absent()

TEST_PERSON = {
    "personId": "amzn1.actor.person.oid.PERSON_ID",
    "personFirstName": "Alice",
    "personType": "ADULT",
}


def _record(persons_info: PersonsInfo | _Absent) -> dict[str, Any]:
    """Build a minimal vocal history record, shaped like the Amazon payload."""
    record: dict[str, Any] = {
        "timestamp": 1757000000000,
        "utteranceType": "GENERAL",
        "intent": "PlayMusicIntent",
        "title": "play some music",
        "subTitle": "Echo Dot",
        "deviceInfo": {"deviceSerialNumber": TEST_SERIAL_1},
    }
    if not isinstance(persons_info, _Absent):
        record["personsInfo"] = persons_info
    return record


@pytest.fixture
def handler() -> AmazonHistoryHandler:
    """Return a history handler with mocked HTTP dependencies."""
    return AmazonHistoryHandler(AsyncMock(), AsyncMock())


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("persons_info", "expected"),
    [
        pytest.param(
            TEST_PERSON,
            ("Alice", "ADULT"),
            id="recognised-speaker",
        ),
        pytest.param(
            [TEST_PERSON],
            ("Alice", "ADULT"),
            id="recognised-speaker-as-list",
        ),
        pytest.param(None, (None, None), id="voice-not-recognised"),
        pytest.param([], (None, None), id="empty-list"),
        pytest.param(ABSENT, (None, None), id="personsinfo-key-absent"),
    ],
)
async def test_vocal_history_exposes_speaker(
    handler: AmazonHistoryHandler,
    persons_info: PersonsInfo | _Absent,
    expected: tuple[str | None, str | None],
) -> None:
    """The recognised speaker is taken from personsInfo, absent when unknown."""
    handler._request_voice_history = AsyncMock(  # type: ignore[method-assign]
        return_value={"customerHistoryRecords": [_record(persons_info)]}
    )
    handler._update_vocal_history_token = AsyncMock()  # type: ignore[method-assign]

    records = await handler.get_vocal_history()

    record = records[TEST_SERIAL_1]
    assert (record.person_first_name, record.person_type) == expected
    # personId is in the payload but account-scoped, so it is deliberately not exposed
    assert not hasattr(record, "person_id")


def _api_record(
    serial: str,
    timestamp: int,
    *,
    command: str = "",
    reply: str = "",
    history_type: str = "GENERAL",
) -> dict[str, Any]:
    """Build an RVH record, also usable as a RAH record via activityKey."""
    items = []
    if command:
        items.append(
            {"recordItemType": "CUSTOMER_TRANSCRIPT", "transcriptText": command}
        )
    if reply:
        items.append({"recordItemType": "ALEXA_RESPONSE", "transcriptText": reply})
    return {
        "recordKey": f"customer#{timestamp}#type#{serial}",
        "activityKey": f"customer#{timestamp}#type#{serial}",
        "timestamp": timestamp,
        "utteranceType": history_type,
        "voiceHistoryRecordItems": items,
        "personsInfo": [TEST_PERSON],
    }


def test_rvh_parser_keeps_commands_replies_and_amazon_timestamps() -> None:
    """The newest usable record per device can contain only a reply."""
    newest_timestamp = 200
    reply_timestamp = 150
    records = AmazonHistoryHandler._parse_voice_history(
        {
            "customerHistoryRecords": [
                _api_record(TEST_SERIAL_1, 100, command="Alexa, what time is it"),
                _api_record(
                    TEST_SERIAL_1,
                    newest_timestamp,
                    command="Echo what's the date",
                    reply="It's Wednesday",
                ),
                _api_record(
                    TEST_SERIAL_2, reply_timestamp, reply="Home Assistant has started"
                ),
                _api_record(TEST_SERIAL_2, 160, history_type="DEVICE_ARBITRATION"),
            ]
        }
    )

    assert records[TEST_SERIAL_1].timestamp == newest_timestamp
    assert records[TEST_SERIAL_1].title == "what's the date"
    assert records[TEST_SERIAL_1].sub_title == "It's Wednesday"
    assert records[TEST_SERIAL_1].person_first_name == "Alice"
    assert records[TEST_SERIAL_2].timestamp == reply_timestamp
    assert records[TEST_SERIAL_2].title == ""
    assert records[TEST_SERIAL_2].sub_title == "Home Assistant has started"


def test_rvh_parser_ignores_false_wakes_and_empty_records() -> None:
    """Wake-only records cannot replace a real event from that device."""
    valid_timestamp = 100
    records = AmazonHistoryHandler._parse_voice_history(
        {
            "customerHistoryRecords": [
                _api_record(TEST_SERIAL_1, valid_timestamp, command="what time is it"),
                _api_record(
                    TEST_SERIAL_1, 200, command="Alexa", history_type="WAKE_WORD_ONLY"
                ),
                _api_record(
                    TEST_SERIAL_1, 300, command="noise", history_type="FALSE_WAKE_WORD"
                ),
                _api_record(TEST_SERIAL_1, 400),
                _api_record(
                    TEST_SERIAL_2,
                    500,
                    reply="Announcement completed",
                    history_type="NO_EXPRESSED_INTENT",
                ),
            ]
        }
    )

    assert records[TEST_SERIAL_1].timestamp == valid_timestamp
    assert records[TEST_SERIAL_2].sub_title == "Announcement completed"


@pytest.mark.anyio
async def test_rah_request_uses_bearer_and_pagination_token(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RAH pages use the access token and pass Amazon's pagination token."""
    request = AsyncMock(return_value=(None, object()))
    monkeypatch.setattr(api._http_wrapper, "session_request", request)
    monkeypatch.setattr(
        api._http_wrapper, "response_to_json", AsyncMock(return_value={})
    )
    api._history_handler._csrf_a2z_token = "csrf-test"  # noqa: S105

    await api._history_handler._request_rah_history(
        100, 200, "access-test", "next-page"
    )

    assert request.await_args is not None
    kwargs = request.await_args.kwargs
    assert kwargs["method"] == HTTPMethod.POST
    assert kwargs["url"].path.endswith("/rah/alexa-history-records-v2")
    assert dict(kwargs["url"].query) == {"startTime": "100", "endTime": "200"}
    assert kwargs["input_data"] == {"previousRequestToken": "next-page"}
    assert kwargs["extended_headers"] == {
        "Authorization": "Bearer access-test",
        CSRF_A2Z: "csrf-test",
    }


@pytest.mark.anyio
async def test_startup_history_pages_keep_newest_valid_event_per_device(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RAH's overlapping pages seed each Echo with its latest Amazon timestamp."""
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    old = now_ms - 20_000
    newest = now_ms - 10_000
    reply_time = now_ms - 30_000
    api._device_handler._final_devices = {
        TEST_SERIAL_1: make_device(TEST_SERIAL_1),
        TEST_SERIAL_2: make_device(TEST_SERIAL_2),
        "NO_VOICE": make_device("NO_VOICE", voice_control_supported=False),
    }
    api._session_state_data.login_stored_data[REFRESH_ACCESS_TOKEN] = "access-test"
    monkeypatch.setattr(
        api._history_handler, "_update_vocal_history_token", AsyncMock()
    )
    monkeypatch.setattr(
        api._http_wrapper, "refresh_data", AsyncMock(return_value=(True, None))
    )
    page = AsyncMock(
        side_effect=[
            {
                "alexaHistoryRecords": [
                    _api_record(TEST_SERIAL_1, newest, command="newest"),
                    _api_record(
                        TEST_SERIAL_2,
                        now_ms - history_constants.HISTORY_STARTUP_LOOKBACK_MS - 1000,
                        reply="outside the window",
                    ),
                ],
                "paginationToken": "page-two",
            },
            {
                "alexaHistoryRecords": [
                    _api_record(TEST_SERIAL_1, newest, command="overlap"),
                    _api_record(TEST_SERIAL_1, old, command="older"),
                    _api_record(
                        TEST_SERIAL_2, reply_time, reply="Home Assistant has started"
                    ),
                ],
                "paginationToken": "page-three",
            },
        ]
    )
    monkeypatch.setattr(api._history_handler, "_request_rah_history", page)

    records = await api.sync_history_state()

    expected_tokens = [None, "page-two"]
    assert page.await_count == len(expected_tokens)
    assert [call.args[3] for call in page.await_args_list] == expected_tokens
    assert records[TEST_SERIAL_1].timestamp == newest
    assert records[TEST_SERIAL_1].title == "newest"
    assert records[TEST_SERIAL_2].timestamp == reply_time
    assert records[TEST_SERIAL_2].sub_title == "Home Assistant has started"
    assert api._last_emitted_history == {
        TEST_SERIAL_1: newest,
        TEST_SERIAL_2: reply_time,
    }


@pytest.mark.anyio
async def test_rvh_request_parameters(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live history requests use RVH's voice filter and null page token."""
    request = AsyncMock(return_value=(None, object()))
    monkeypatch.setattr(api._http_wrapper, "session_request", request)
    monkeypatch.setattr(
        api._http_wrapper, "response_to_json", AsyncMock(return_value={})
    )

    await api._history_handler._request_voice_history(100, 200)

    assert request.await_args is not None
    kwargs = request.await_args.kwargs
    assert kwargs["method"] == HTTPMethod.POST
    assert kwargs["url"].path.endswith("/rvh/customer-history-records-v2")
    assert dict(kwargs["url"].query) == {
        "startTime": "100",
        "endTime": "200",
        "recordType": "VOICE_HISTORY",
        "maxRecordSize": str(history_constants.HISTORY_MAX_RECORD_SIZE),
    }
    assert kwargs["input_data"] == {"previousRequestToken": None}
    assert kwargs["json_data"] is True
