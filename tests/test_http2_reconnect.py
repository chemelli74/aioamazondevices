# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for resyncing pushed state after the HTTP2 stream reconnects."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import REFRESH_ACCESS_TOKEN
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.implementation.http2 import AmazonHTTP2Client, _TaskAction

pytestmark = pytest.mark.anyio


def _http2_client() -> AmazonHTTP2Client:
    """Build an HTTP2 client whose stream opens and closes straight away."""
    session_state_data = MagicMock()
    session_state_data.login_stored_data = {
        "customer_info": {"home_region": "eu"},
        REFRESH_ACCESS_TOKEN: "token",
    }

    async def _no_chunks() -> AsyncIterator[bytes]:
        for chunk in list[bytes]():
            yield chunk

    response = MagicMock(
        status_code=200,
        http_version="HTTP/2",
        headers={"content-type": 'multipart/related; boundary="b"'},
    )
    response.aiter_bytes = _no_chunks

    @contextlib.asynccontextmanager
    async def _stream(*_args: object, **_kwargs: object) -> AsyncIterator[MagicMock]:
        yield response

    httpx_client = MagicMock()
    httpx_client.stream = _stream
    return AmazonHTTP2Client(MagicMock(), session_state_data, httpx_client)


@pytest.fixture
def synced_api(api: AmazonEchoApi) -> AmazonEchoApi:
    """Return an API with the DnD and media syncs stubbed."""
    api._dnd_handler.sync_do_not_disturb_status = AsyncMock()  # type: ignore[method-assign]
    api._media_handler.sync_device_volumes = AsyncMock()  # type: ignore[method-assign]
    api._media_handler.sync_media_state = AsyncMock()  # type: ignore[method-assign]
    return api


async def _resync(api: AmazonEchoApi) -> None:
    """Signal a reconnect and wait for the resync it starts."""
    await api._http2_reconnected_handler()
    assert api._resync_task is not None
    await api._resync_task


async def test_reconnected_is_only_sent_after_first_connect() -> None:
    """Opening the stream for the first time is not a reconnect."""
    client = _http2_client()
    reconnects = 0

    async def _on_reconnected() -> None:
        nonlocal reconnects
        reconnects += 1

    client.on_reconnected.append(_on_reconnected)
    client.on_reconnected.freeze()

    await client._stream_and_process()
    assert reconnects == 0

    await client._stream_and_process()
    await client._stream_and_process()
    assert reconnects == 2  # noqa: PLR2004


async def test_restarted_processing_is_not_a_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stop and start of processing resets the first connect."""
    client = _http2_client()
    client._has_connected = True

    async def _stop_after_one_run(_delay: float) -> _TaskAction:
        client._stop_event.set()
        return _TaskAction.RECONNECT_IMMEDIATE

    monkeypatch.setattr(client, "_run_tasks", _stop_after_one_run)
    await client._orchestrate_tasks()

    assert not client._has_connected


async def test_start_and_stop_http2_processing(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Starting subscribes to reconnects, stopping drops the client."""
    api._session_state_data.login_stored_data = {"customer_info": {"home_region": "eu"}}
    monkeypatch.setattr(AmazonHTTP2Client, "start_processing", AsyncMock())
    monkeypatch.setattr(AmazonHTTP2Client, "stop_processing", AsyncMock())

    await api.start_http2_processing(MagicMock())
    client = api._http2_client
    # starting again reuses the client, without subscribing twice
    await api.start_http2_processing(MagicMock())

    assert client is not None
    assert api._http2_client is client
    assert list(client.on_reconnected) == [api._http2_reconnected_handler]
    assert client.on_reconnected.frozen

    await api.stop_http2_processing()

    assert api._http2_client is None


async def test_reconnect_resyncs_pushed_state(synced_api: AmazonEchoApi) -> None:
    """A reconnect resyncs DnD and media."""
    await _resync(synced_api)

    synced_api._dnd_handler.sync_do_not_disturb_status.assert_awaited_once()  # type: ignore[attr-defined]
    synced_api._media_handler.sync_device_volumes.assert_awaited_once()  # type: ignore[attr-defined]
    synced_api._media_handler.sync_media_state.assert_awaited_once()  # type: ignore[attr-defined]
    assert synced_api._dnd_initialized
    assert synced_api._device_volumes_initialized


async def test_reconnect_during_resync_runs_once_more(
    synced_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reconnects while a resync is running are coalesced into one more resync."""
    release = asyncio.Event()
    syncs = 0

    async def _sync_dnd() -> None:
        nonlocal syncs
        syncs += 1
        await release.wait()

    monkeypatch.setattr(
        synced_api._dnd_handler, "sync_do_not_disturb_status", _sync_dnd
    )

    await synced_api._http2_reconnected_handler()
    task = synced_api._resync_task
    await asyncio.sleep(0)
    await synced_api._http2_reconnected_handler()
    await synced_api._http2_reconnected_handler()
    assert synced_api._resync_task is task

    release.set()
    assert task is not None
    await task

    assert syncs == 2  # noqa: PLR2004


async def test_failed_dnd_resync_falls_back_to_push(
    synced_api: AmazonEchoApi,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed DnD resync is logged, media still resyncs, push does the sync."""
    synced_api._dnd_initialized = True
    synced_api._dnd_handler.sync_do_not_disturb_status = AsyncMock(  # type: ignore[method-assign]
        side_effect=CannotRetrieveData("Boom")
    )

    await _resync(synced_api)

    assert "sync_dnd_state after HTTP2 reconnect failed" in caplog.text
    assert not synced_api._dnd_initialized
    synced_api._media_handler.sync_media_state.assert_awaited_once()  # type: ignore[attr-defined]


async def test_stop_cancels_resync(
    synced_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stopping HTTP2 processing cancels an in-flight resync."""
    started = asyncio.Event()

    async def _sync_dnd() -> None:
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(
        synced_api._dnd_handler, "sync_do_not_disturb_status", _sync_dnd
    )

    await synced_api._http2_reconnected_handler()
    task = synced_api._resync_task
    await started.wait()

    await synced_api.stop_http2_processing()

    assert task is not None
    assert task.cancelled()
    assert synced_api._resync_task is None


async def test_cancelled_stop_is_propagated(
    synced_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancelling the stop itself is not swallowed while waiting for the resync."""
    holding = asyncio.Event()

    async def _sync_dnd() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # ignore the stop's cancel, so the stop is left waiting
            holding.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(
        synced_api._dnd_handler, "sync_do_not_disturb_status", _sync_dnd
    )

    await synced_api._http2_reconnected_handler()
    await asyncio.sleep(0)
    stop = asyncio.create_task(synced_api.stop_http2_processing())
    await holding.wait()

    stop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stop
