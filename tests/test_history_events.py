# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the vocal history push-event proxy in AmazonEchoApi."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

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
    assert probe.await_args is not None
    assert probe.await_args.args[0] == TEST_SERIAL_1


@pytest.mark.anyio
async def test_probe_retries_until_matching_reply_and_deduplicates(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a fresh record from the pushing Echo is emitted, including replies."""
    received = _subscribe(api)
    old = _record(989_999)
    fresh = _record(1_000_100, reply="The current time is 3:31 a.m.")
    api._last_emitted_history[TEST_SERIAL_1] = old.timestamp
    fetch = AsyncMock(
        side_effect=[
            {TEST_SERIAL_1: old, TEST_SERIAL_2: fresh},
            {TEST_SERIAL_1: fresh},
        ]
    )
    monkeypatch.setattr(api, "_shared_vocal_history_fetch", fetch)
    monkeypatch.setattr(api_module, "HISTORY_RETRY_DELAY_SECONDS", 0)

    await api._probe_vocal_history(TEST_SERIAL_1)
    initial_fetches = 2
    assert fetch.await_count == initial_fetches
    fetch.return_value = {TEST_SERIAL_1: fresh}
    fetch.side_effect = None
    await api._probe_vocal_history(TEST_SERIAL_1)

    assert received == [{TEST_SERIAL_1: fresh}]
    assert fetch.await_count == initial_fetches + api_module.HISTORY_PROBE_ATTEMPTS
    assert api._last_emitted_history[TEST_SERIAL_1] == fresh.timestamp


@pytest.mark.anyio
async def test_simultaneous_probes_share_history_request(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent Echo probes await one in-flight RAH fetch."""
    started = asyncio.Event()
    release = asyncio.Event()
    record = _record(100)

    async def fetch() -> dict[str, AmazonVocalRecord]:
        started.set()
        await release.wait()
        return {TEST_SERIAL_1: record}

    mock_fetch = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(api._history_handler, "get_vocal_history", mock_fetch)
    first = asyncio.create_task(api._shared_vocal_history_fetch())
    await started.wait()
    second = asyncio.create_task(api._shared_vocal_history_fetch())
    await asyncio.sleep(0)
    release.set()

    results = list(await asyncio.gather(first, second))
    assert results == [
        {TEST_SERIAL_1: record},
        {TEST_SERIAL_1: record},
    ]
    mock_fetch.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("first_has_record", [True, False])
async def test_push_during_probe_runs_again_for_latest_activity(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
    first_has_record: bool,
) -> None:
    """A second push survives an active probe, whether it succeeds or expires."""
    received = _subscribe(api)
    started = asyncio.Event()
    release = asyncio.Event()
    old = _record(1_000_100)
    newer = _record(1_020_100)
    fetch_count = 0

    async def fetch() -> dict[str, AmazonVocalRecord]:
        nonlocal fetch_count
        fetch_count += 1
        if fetch_count == 1:
            started.set()
            await release.wait()
            return {TEST_SERIAL_1: old} if first_has_record else {}
        return {TEST_SERIAL_1: newer}

    clock = Mock()
    clock.now.side_effect = [
        datetime.fromtimestamp(1000, UTC),
        datetime.fromtimestamp(1020, UTC),
    ]
    monkeypatch.setattr(api_module, "datetime", clock)
    monkeypatch.setattr(api_module, "HISTORY_PROBE_ATTEMPTS", 1)
    monkeypatch.setattr(api._history_handler, "get_vocal_history", fetch)
    probe = AsyncMock(wraps=api._probe_vocal_history)
    monkeypatch.setattr(api, "_probe_vocal_history", probe)
    payload = {"dopplerId": {"deviceSerialNumber": TEST_SERIAL_1}}

    await api._handle_eq_event_as_history_proxy(payload)
    task = api._history_probe_tasks[TEST_SERIAL_1]
    await started.wait()
    await api._handle_eq_event_as_history_proxy(payload)
    assert api._history_probe_tasks[TEST_SERIAL_1] is task
    release.set()
    await task

    expected_fetches = 2
    assert fetch_count == expected_fetches
    assert [call.args for call in probe.await_args_list] == [
        (TEST_SERIAL_1,),
        (TEST_SERIAL_1,),
    ]
    assert received == (
        [{TEST_SERIAL_1: old}, {TEST_SERIAL_1: newer}]
        if first_has_record
        else [{TEST_SERIAL_1: newer}]
    )
    assert not api._history_probe_tasks
    assert not api._history_activity_timestamps


@pytest.mark.anyio
async def test_stop_cancels_pending_history_activity(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shutdown cancels both the probe and its shared history request."""
    received = _subscribe(api)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fetch() -> dict[str, AmazonVocalRecord]:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return {}

    monkeypatch.setattr(api._history_handler, "get_vocal_history", fetch)
    payload = {"dopplerId": {"deviceSerialNumber": TEST_SERIAL_1}}
    await api._handle_eq_event_as_history_proxy(payload)
    task = api._history_probe_tasks[TEST_SERIAL_1]
    await started.wait()
    await api._handle_eq_event_as_history_proxy(payload)
    await api.stop_http2_processing()

    assert task.cancelled()
    assert cancelled.is_set()
    assert not received
    assert not api._history_probe_tasks
    assert not api._history_activity_timestamps
    assert api._history_fetch_task is None


@pytest.mark.anyio
async def test_unexpected_probe_error_is_logged_and_task_cleaned_up(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unexpected background failures are logged with the originating serial."""
    received = _subscribe(api)
    monkeypatch.setattr(
        api._history_handler,
        "get_vocal_history",
        AsyncMock(side_effect=RuntimeError("unexpected history failure")),
    )

    await api._handle_eq_event_as_history_proxy(
        {"dopplerId": {"deviceSerialNumber": TEST_SERIAL_1}}
    )
    task = api._history_probe_tasks[TEST_SERIAL_1]
    await task

    assert task.exception() is None
    assert not received
    assert not api._history_probe_tasks
    assert not api._history_activity_timestamps
    assert (
        f"Unexpected history probe failure for EQ serial={TEST_SERIAL_1}" in caplog.text
    )
    assert "RuntimeError: unexpected history failure" in caplog.text


@pytest.mark.anyio
async def test_probe_expires_without_fresh_history(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing or stale history is retried a bounded number of times."""
    received = _subscribe(api)
    api._last_emitted_history[TEST_SERIAL_1] = 1
    fetch = AsyncMock(side_effect=[{}, {TEST_SERIAL_1: _record(1)}] * 2)
    monkeypatch.setattr(api, "_shared_vocal_history_fetch", fetch)
    monkeypatch.setattr(api_module, "HISTORY_RETRY_DELAY_SECONDS", 0)

    await api._probe_vocal_history(TEST_SERIAL_1)

    assert fetch.await_count == api_module.HISTORY_PROBE_ATTEMPTS
    assert not received
    assert api._last_emitted_history == {TEST_SERIAL_1: 1}


@pytest.mark.anyio
async def test_shutdown_cancels_probe_created_while_stream_stops(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A final push during stream shutdown is included in task cancellation."""
    received = _subscribe(api)
    started = asyncio.Event()

    async def fetch() -> dict[str, AmazonVocalRecord]:
        started.set()
        await asyncio.Event().wait()
        return {}

    async def stop_stream() -> None:
        await api._handle_eq_event_as_history_proxy(
            {"dopplerId": {"deviceSerialNumber": TEST_SERIAL_1}}
        )
        await started.wait()

    monkeypatch.setattr(api._history_handler, "get_vocal_history", fetch)
    client = Mock()
    client.stop_processing = AsyncMock(side_effect=stop_stream)
    monkeypatch.setattr(api, "_http2_client", client)

    await api.stop_http2_processing()

    client.stop_processing.assert_awaited_once()
    assert api._http2_client is None
    assert not api._history_probe_tasks
    assert not api._history_activity_timestamps
    assert api._history_fetch_task is None
    assert not received


@pytest.mark.anyio
async def test_delayed_eq_push_emits_record_newer_than_startup_baseline(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A delayed EQ push accepts new Amazon history older than push receipt."""
    received = _subscribe(api)
    baseline = _record(1_791_238_300_625)
    fresh = _record(1_791_240_542_670)
    fetch = AsyncMock(side_effect=[{TEST_SERIAL_1: baseline}, {TEST_SERIAL_1: fresh}])
    monkeypatch.setattr(api._history_handler, "get_vocal_history", fetch)
    clock = Mock()
    clock.now.return_value = datetime.fromtimestamp(1_791_240_598.671, UTC)
    monkeypatch.setattr(api_module, "datetime", clock)

    assert await api.sync_history_state() == {TEST_SERIAL_1: baseline}
    assert not received
    await api._handle_eq_event_as_history_proxy(
        {"dopplerId": {"deviceSerialNumber": TEST_SERIAL_1}}
    )
    await api._history_probe_tasks[TEST_SERIAL_1]

    assert received == [{TEST_SERIAL_1: fresh}]
    assert api._last_emitted_history[TEST_SERIAL_1] == fresh.timestamp


@pytest.mark.anyio
async def test_startup_baseline_is_not_emitted_again(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing startup history seeds deduplication without publishing events."""
    received = _subscribe(api)
    baseline = _record(100)
    fetch = AsyncMock(return_value={TEST_SERIAL_1: baseline})
    monkeypatch.setattr(api._history_handler, "get_vocal_history", fetch)
    monkeypatch.setattr(api_module, "HISTORY_RETRY_DELAY_SECONDS", 0)

    await api.sync_history_state()
    await api._probe_vocal_history(TEST_SERIAL_1)

    assert not received
    assert api._last_emitted_history == {TEST_SERIAL_1: baseline.timestamp}
    assert fetch.await_count == 1 + api_module.HISTORY_PROBE_ATTEMPTS


@pytest.mark.anyio
async def test_history_sync_does_not_regress_timestamp_baseline(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refresh returning older history cannot roll back an emitted baseline."""
    latest_timestamp = 200
    api._last_emitted_history[TEST_SERIAL_1] = latest_timestamp
    older = _record(100)
    monkeypatch.setattr(
        api._history_handler,
        "get_vocal_history",
        AsyncMock(return_value={TEST_SERIAL_1: older}),
    )

    assert await api.sync_history_state() == {TEST_SERIAL_1: older}
    assert api._last_emitted_history[TEST_SERIAL_1] == latest_timestamp
