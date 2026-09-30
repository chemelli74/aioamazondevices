# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the vocal history push-event proxy in AmazonEchoApi."""

import asyncio
from http import HTTPMethod
from unittest.mock import AsyncMock

import pytest

from aioamazondevices import api as api_module
from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonVocalRecord

from .const import TEST_SERIAL_1, TEST_SERIAL_2


def _record(timestamp: int, *, reply: str = "") -> AmazonVocalRecord:
    """Build a history record using an Amazon timestamp."""
    return AmazonVocalRecord(
        timestamp=timestamp,
        history_type="UTTERANCE",
        intent="Unknown",
        title="what time is it" if not reply else "",
        sub_title=reply,
    )


def _subscribe(api: AmazonEchoApi) -> list[dict[str, AmazonVocalRecord]]:
    """Capture emitted history signals."""
    received: list[dict[str, AmazonVocalRecord]] = []

    async def on_history(history: dict[str, AmazonVocalRecord]) -> None:
        received.append(history)

    api.on_history_event.append(on_history)
    api.on_history_event.freeze()
    return received


@pytest.mark.anyio
async def test_eq_event_skips_history_fetch_without_subscribers(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No subscribers means no probe is scheduled."""
    probe = AsyncMock()
    monkeypatch.setattr(api, "_probe_vocal_history", probe)

    await api._handle_eq_event_as_history_proxy(
        {"dopplerId": {"deviceSerialNumber": TEST_SERIAL_1}}
    )

    probe.assert_not_awaited()
    assert not api._history_probe_tasks


@pytest.mark.anyio
async def test_eq_event_probes_only_the_pushing_device(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A push probes its serial and ignores a push with no serial."""
    _subscribe(api)
    probe = AsyncMock()
    monkeypatch.setattr(api, "_probe_vocal_history", probe)

    await api._handle_eq_event_as_history_proxy({"dopplerId": {}})
    assert not api._history_probe_tasks

    await api._handle_eq_event_as_history_proxy(
        {"dopplerId": {"deviceSerialNumber": TEST_SERIAL_1}}
    )
    task = api._history_probe_tasks[TEST_SERIAL_1]
    await task

    probe.assert_awaited_once()
    assert probe.await_args.args[0] == TEST_SERIAL_1


@pytest.mark.anyio
async def test_probe_retries_until_matching_reply_and_deduplicates(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a fresh record from the pushing Echo is emitted, including replies."""
    received = _subscribe(api)
    old = _record(989_999)
    fresh = _record(1_000_100, reply="The current time is 3:31 a.m.")
    fetch = AsyncMock(
        side_effect=[
            {TEST_SERIAL_1: old, TEST_SERIAL_2: fresh},
            {TEST_SERIAL_1: fresh},
        ]
    )
    monkeypatch.setattr(api, "_shared_vocal_history_fetch", fetch)
    monkeypatch.setattr(api_module, "HISTORY_PROBE_DELAY_SECONDS", 0)
    monkeypatch.setattr(api_module, "HISTORY_RETRY_DELAY_SECONDS", 0)

    await api._probe_vocal_history(TEST_SERIAL_1, 1_000_000)
    initial_fetches = 2
    assert fetch.await_count == initial_fetches
    fetch.return_value = {TEST_SERIAL_1: fresh}
    fetch.side_effect = None
    await api._probe_vocal_history(TEST_SERIAL_1, 1_000_000)

    assert received == [{TEST_SERIAL_1: fresh}]
    assert fetch.await_count == initial_fetches + api_module.HISTORY_PROBE_ATTEMPTS
    assert api._last_emitted_history[TEST_SERIAL_1] == fresh.timestamp


@pytest.mark.anyio
async def test_simultaneous_probes_share_history_request(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent Echo probes await one in-flight RVH fetch."""
    started = asyncio.Event()
    release = asyncio.Event()
    record = _record(100)

    async def fetch() -> dict[str, AmazonVocalRecord]:
        started.set()
        await release.wait()
        return {TEST_SERIAL_1: record}

    mock_fetch = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(api, "_fetch_voice_history", mock_fetch)
    first = asyncio.create_task(api._shared_vocal_history_fetch())
    await started.wait()
    second = asyncio.create_task(api._shared_vocal_history_fetch())
    await asyncio.sleep(0)
    release.set()

    assert await asyncio.gather(first, second) == [
        {TEST_SERIAL_1: record},
        {TEST_SERIAL_1: record},
    ]
    mock_fetch.assert_awaited_once()


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

    await api._request_voice_history(100, 200)

    kwargs = request.await_args.kwargs
    assert kwargs["method"] == HTTPMethod.POST
    assert kwargs["url"].path.endswith("/rvh/customer-history-records-v2")
    assert dict(kwargs["url"].query) == {
        "startTime": "100",
        "endTime": "200",
        "recordType": "VOICE_HISTORY",
        "maxRecordSize": str(api_module.HISTORY_MAX_RECORD_SIZE),
    }
    assert kwargs["input_data"] == {"previousRequestToken": None}
    assert kwargs["json_data"] is True
