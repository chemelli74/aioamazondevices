# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for Alexa vocal history parsing."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from http import HTTPMethod
from typing import Any
from unittest.mock import AsyncMock

import pytest
from bs4 import BeautifulSoup
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import (
    CSRF_A2Z,
    REFRESH_ACCESS_TOKEN,
    URI_HISTORY_DATA,
    URI_HISTORY_FRONTEND,
)
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.implementation import history as history_module
from aioamazondevices.implementation.history import AmazonHistoryHandler
from aioamazondevices.structures import AmazonVocalRecord

from .const import TEST_CSRF, TEST_SERIAL_1, TEST_SERIAL_2

TEST_BEARER = "access-token"
NEW_CSRF = "new-csrf"

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
def handler(monkeypatch: pytest.MonkeyPatch) -> AmazonHistoryHandler:
    """Return a history handler that skips the backend refresh wait."""
    monkeypatch.setattr(history_module, "BACKEND_REFRESH_WAIT_SECONDS", 0)
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recognised speaker is taken from personsInfo, absent when unknown."""
    monkeypatch.setattr(
        handler,
        "_vocal_history_json",
        AsyncMock(return_value={"alexaHistoryRecords": [_record(persons_info)]}),
    )

    records = await handler.get_vocal_history()

    record = records[TEST_SERIAL_1]
    assert (record.person_first_name, record.person_type) == expected
    # personId is in the payload but account-scoped, so it is deliberately not exposed
    assert not hasattr(record, "person_id")


def _history_record(
    serial: str | None, timestamp: int, **fields: object
) -> dict[str, Any]:
    """Build a vocal history record for a device, overriding any fields."""
    return {
        "timestamp": timestamp,
        "utteranceType": "GENERAL",
        "intent": "PlayMusicIntent",
        "title": f"record {timestamp}",
        "subTitle": "Echo Dot",
        "deviceInfo": {"deviceSerialNumber": serial},
        **fields,
    }


@pytest.fixture
def history_api(api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch) -> AmazonEchoApi:
    """Return a logged in API that skips the backend refresh wait."""
    monkeypatch.setattr(history_module, "BACKEND_REFRESH_WAIT_SECONDS", 0)
    api._session_state_data.login_stored_data = {REFRESH_ACCESS_TOKEN: TEST_BEARER}
    monkeypatch.setattr(
        api._http_wrapper, "refresh_data", AsyncMock(return_value=(True, {}))
    )
    return api


@pytest.fixture
def csrf_page(
    history_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> Callable[[str], AsyncMock]:
    """Return a setter making every request return the given HTML page."""

    def _csrf_page(html: str) -> AsyncMock:
        session_request = AsyncMock(
            return_value=(BeautifulSoup(html, "html.parser"), None)
        )
        monkeypatch.setattr(
            history_api._http_wrapper, "session_request", session_request
        )
        return session_request

    return _csrf_page


@pytest.mark.anyio
async def test_vocal_history_keeps_latest_record_per_device(
    handler: AmazonHistoryHandler, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the latest record linked to a device is kept for each device."""
    records = [
        _history_record(TEST_SERIAL_1, 2),
        _history_record(TEST_SERIAL_1, 3),
        _history_record(TEST_SERIAL_1, 1),
        _history_record(
            TEST_SERIAL_2,
            5,
            deviceInfo=[{"deviceSerialNumber": TEST_SERIAL_2}],
            utteranceType=None,
            recordType="VOICE_HISTORY",
            intent=None,
        ),
        _history_record(TEST_SERIAL_2, 4, utteranceType=None),
    ]
    monkeypatch.setattr(
        handler,
        "_vocal_history_json",
        AsyncMock(return_value={"alexaHistoryRecords": records}),
    )

    assert await handler.get_vocal_history() == {
        TEST_SERIAL_1: AmazonVocalRecord(
            timestamp=3,
            history_type="GENERAL",
            intent="PlayMusicIntent",
            title="record 3",
            sub_title="Echo Dot",
        ),
        TEST_SERIAL_2: AmazonVocalRecord(
            timestamp=5,
            history_type="VOICE_HISTORY",
            intent="Unknown",
            title="record 5",
            sub_title="Echo Dot",
        ),
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({"utteranceType": "ASR_TIMEOUT"}, id="asr-timeout"),
        pytest.param({"utteranceType": "DEVICE_ARBITRATION"}, id="arbitration"),
        pytest.param({"utteranceType": "NO_EXPRESSED_INTENT"}, id="no-intent"),
        pytest.param({"utteranceType": "WAKE_WORD_ONLY"}, id="wake-word-only"),
        pytest.param({"deviceInfo": None}, id="no-device"),
        pytest.param({"deviceInfo": []}, id="empty-device-list"),
        pytest.param({"deviceInfo": "Echo"}, id="device-not-a-dict"),
    ],
)
async def test_vocal_history_skips_records(
    handler: AmazonHistoryHandler,
    monkeypatch: pytest.MonkeyPatch,
    fields: dict[str, Any],
) -> None:
    """Records with nothing said or no linked device are skipped."""
    monkeypatch.setattr(
        handler,
        "_vocal_history_json",
        AsyncMock(
            return_value={
                "alexaHistoryRecords": [_history_record(TEST_SERIAL_1, 1, **fields)]
            }
        ),
    )

    assert await handler.get_vocal_history() == {}


@pytest.mark.anyio
async def test_vocal_history_request(
    history_api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """The last week of history is requested with the access and CSRF tokens."""
    session_request = mock_json_response({"alexaHistoryRecords": []})
    handler = history_api._history_handler
    handler._csrf_a2z_token = TEST_CSRF
    handler._csrf_a2z_refresh_time = datetime.now(UTC)
    week_ago_noon = datetime.now(UTC).replace(
        hour=12, minute=0, second=0, microsecond=0
    ) - timedelta(days=7)

    assert await handler._vocal_history_json() == {"alexaHistoryRecords": []}

    (request,) = session_request.await_args_list
    kwargs = dict(request.kwargs)
    url = kwargs.pop("url")
    assert kwargs == {
        "method": HTTPMethod.POST,
        "input_data": {"previousRequestToken": None},
        "json_data": True,
        "extended_headers": {
            "Authorization": f"Bearer {TEST_BEARER}",
            CSRF_A2Z: TEST_CSRF,
        },
    }
    assert url.with_query(None) == URL.joinpath(
        history_api._session_state_data.retail_site_url, URI_HISTORY_DATA
    )
    assert int(url.query["startTime"]) == int(week_ago_noon.timestamp() * 1000)
    assert int(url.query["startTime"]) < int(url.query["endTime"])


@pytest.mark.anyio
async def test_vocal_history_request_warns_on_refresh_failure(
    history_api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed token refresh is logged and the stored token is still used."""
    mock_json_response({"alexaHistoryRecords": []})
    monkeypatch.setattr(
        history_api._http_wrapper, "refresh_data", AsyncMock(return_value=(False, {}))
    )
    history_api._history_handler._csrf_a2z_refresh_time = datetime.now(UTC)

    await history_api._history_handler._vocal_history_json()

    assert "Access token refresh failed" in caplog.text


@pytest.mark.anyio
async def test_csrf_token_is_read_and_cached(
    history_api: AmazonEchoApi, csrf_page: Callable[[str], AsyncMock]
) -> None:
    """The CSRF token is read from the history page and reused for 12 hours."""
    session_request = csrf_page(f'<meta name="csrf-token" content="{TEST_CSRF}">')
    handler = history_api._history_handler

    await handler._update_vocal_history_token()
    await handler._update_vocal_history_token()

    assert handler._csrf_a2z_token == TEST_CSRF
    session_request.assert_awaited_once_with(
        method=HTTPMethod.GET,
        url=URL.joinpath(
            history_api._session_state_data.retail_site_url, URI_HISTORY_FRONTEND
        ),
    )


@pytest.mark.anyio
async def test_csrf_token_is_refreshed_when_stale(
    history_api: AmazonEchoApi, csrf_page: Callable[[str], AsyncMock]
) -> None:
    """A token older than 12 hours is read again."""
    session_request = csrf_page(f'<meta name="csrf-token" content="{NEW_CSRF}">')
    handler = history_api._history_handler
    handler._csrf_a2z_token = TEST_CSRF
    handler._csrf_a2z_refresh_time = datetime.now(UTC) - timedelta(hours=13)

    await handler._update_vocal_history_token()

    session_request.assert_awaited_once()
    assert handler._csrf_a2z_token == NEW_CSRF


@pytest.mark.anyio
@pytest.mark.parametrize(
    "html",
    [
        pytest.param("<html></html>", id="no-meta"),
        pytest.param('<meta name="csrf-token">', id="no-content"),
        pytest.param('<meta name="csrf-token" content="">', id="empty-content"),
    ],
)
async def test_csrf_token_missing_raises(
    history_api: AmazonEchoApi, csrf_page: Callable[[str], AsyncMock], html: str
) -> None:
    """A history page without a CSRF token cannot be used."""
    csrf_page(html)

    with pytest.raises(CannotRetrieveData, match="Cannot find anti-csrftoken-a2z"):
        await history_api._history_handler._update_vocal_history_token()
