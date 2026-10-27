# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for resyncing pushed state after the HTTP2 stream reconnects."""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import REFRESH_ACCESS_TOKEN
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.implementation.http2 import AmazonHTTP2Client, _TaskAction
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1

SYNCED_TEMPERATURE = 20.0
RESYNCED_TEMPERATURE = 23.0


def _http2_client() -> AmazonHTTP2Client:
    """Build an HTTP2 client whose stream opens and closes straight away."""
    session_state_data = MagicMock()
    session_state_data.login_stored_data = {
        "customer_info": {"home_region": "eu"},
        REFRESH_ACCESS_TOKEN: "token",
    }

    async def aiter_bytes() -> AsyncIterator[bytes]:
        for chunk in list[bytes]():
            yield chunk

    response = MagicMock(
        status_code=200,
        http_version="HTTP/2",
        headers={"content-type": 'multipart/related; boundary="b"'},
    )
    response.aiter_bytes = aiter_bytes

    @contextlib.asynccontextmanager
    async def stream(*_args: object, **_kwargs: object) -> AsyncIterator[MagicMock]:
        yield response

    httpx_client = MagicMock()
    httpx_client.stream = stream
    return AmazonHTTP2Client(MagicMock(), session_state_data, httpx_client)


def _temperature(value: float) -> dict[str, Any]:
    """Build a temperature sensor feature with the given value."""
    return {
        "name": "temperatureSensor",
        "instance": None,
        "properties": [
            {"name": "temperature", "value": {"value": value, "scale": "CELSIUS"}}
        ],
    }


@dataclass
class _SyncMocks:
    """The stubbed endpoint features lookup, DnD and media syncs."""

    endpoints_features: AsyncMock = field(default_factory=AsyncMock)
    dnd: AsyncMock = field(default_factory=AsyncMock)
    volumes: AsyncMock = field(default_factory=AsyncMock)
    media: AsyncMock = field(default_factory=AsyncMock)


@pytest.fixture
def sync_mocks() -> _SyncMocks:
    """Return the mocks the syncs are stubbed with."""
    return _SyncMocks()


@pytest.fixture
def synced_api(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., Any],
    sync_mocks: _SyncMocks,
    monkeypatch: pytest.MonkeyPatch,
) -> AmazonEchoApi:
    """Return an API with a temperature sensor synced and other syncs stubbed."""
    device = make_device(TEST_SERIAL_1)
    sync_sensors({"features": [_temperature(SYNCED_TEMPERATURE)]}, device)
    api._device_handler._final_devices = {TEST_SERIAL_1: device}
    sync_mocks.endpoints_features.return_value = {
        device.endpoint_id: {
            "endpointId": device.endpoint_id,
            "features": [_temperature(RESYNCED_TEMPERATURE)],
        }
    }
    monkeypatch.setattr(
        api._device_handler, "_get_endpoints_features", sync_mocks.endpoints_features
    )
    monkeypatch.setattr(api._dnd_handler, "sync_do_not_disturb_status", sync_mocks.dnd)
    monkeypatch.setattr(api._media_handler, "sync_device_volumes", sync_mocks.volumes)
    monkeypatch.setattr(api._media_handler, "sync_media_state", sync_mocks.media)
    return api


async def _resync(api: AmazonEchoApi) -> None:
    """Signal a reconnect and wait for the resync it starts."""
    await api._http2_reconnected_handler()
    assert api._resync_task is not None
    await api._resync_task


@pytest.mark.anyio
async def test_reconnected_is_only_sent_after_first_connect() -> None:
    """Opening the stream for the first time is not a reconnect."""
    client = _http2_client()
    on_reconnected = AsyncMock()
    client.on_reconnected.append(on_reconnected)
    client.on_reconnected.freeze()

    await client._stream_and_process()
    on_reconnected.assert_not_awaited()

    await client._stream_and_process()
    await client._stream_and_process()
    assert on_reconnected.await_args_list == [call(), call()]


@pytest.mark.anyio
async def test_restarted_processing_is_not_a_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stop and start of processing resets the first connect."""
    client = _http2_client()
    client._has_connected = True

    async def run_tasks(_delay: float) -> _TaskAction:
        client._stop_event.set()
        return _TaskAction.RECONNECT_IMMEDIATE

    monkeypatch.setattr(client, "_run_tasks", run_tasks)
    await client._orchestrate_tasks()

    assert not client._has_connected


@pytest.mark.anyio
async def test_start_and_stop_http2_processing(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Starting subscribes to reconnects, stopping drops the client."""
    api._session_state_data.login_stored_data = {"customer_info": {"home_region": "eu"}}
    monkeypatch.setattr(AmazonHTTP2Client, "start_processing", AsyncMock())
    monkeypatch.setattr(AmazonHTTP2Client, "stop_processing", AsyncMock())

    await api.start_http2_processing(MagicMock())
    client = api._http2_client
    # Starting again reuses the client, without subscribing twice.
    await api.start_http2_processing(MagicMock())

    assert client is not None
    assert api._http2_client is client
    assert list(client.on_reconnected) == [api._http2_reconnected_handler]
    assert client.on_reconnected.frozen

    await api.stop_http2_processing()

    assert api._http2_client is None


@pytest.mark.anyio
async def test_reconnect_resyncs_pushed_state(
    synced_api: AmazonEchoApi, sync_mocks: _SyncMocks
) -> None:
    """A reconnect resyncs sensors, DnD and media, and notifies subscribers."""
    on_sensor_event = AsyncMock()
    synced_api.on_sensor_event.append(on_sensor_event)
    synced_api.on_sensor_event.freeze()

    await _resync(synced_api)

    sensor = synced_api.sensors[TEST_SERIAL_1]["temperature"]
    assert sensor.value == RESYNCED_TEMPERATURE
    on_sensor_event.assert_awaited_once()
    sync_mocks.dnd.assert_awaited_once()
    sync_mocks.volumes.assert_awaited_once()
    sync_mocks.media.assert_awaited_once()
    assert synced_api._dnd_initialized
    assert synced_api._device_volumes_initialized


@pytest.mark.anyio
async def test_reconnect_during_resync_runs_once_more(
    synced_api: AmazonEchoApi, sync_mocks: _SyncMocks
) -> None:
    """Reconnects while a resync is running are coalesced into one more resync."""
    release = asyncio.Event()
    sync_mocks.dnd.side_effect = release.wait

    await synced_api._http2_reconnected_handler()
    task = synced_api._resync_task
    await asyncio.sleep(0)
    await synced_api._http2_reconnected_handler()
    await synced_api._http2_reconnected_handler()
    assert synced_api._resync_task is task

    release.set()
    assert task is not None
    await task

    assert sync_mocks.dnd.await_args_list == [call(), call()]


@pytest.mark.anyio
async def test_failed_sensor_resync_is_retried_on_next_poll(
    synced_api: AmazonEchoApi,
    sync_mocks: _SyncMocks,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed sensor resync is logged, the rest still runs, the poll retries."""
    resynced_features = sync_mocks.endpoints_features
    monkeypatch.setattr(
        synced_api._device_handler,
        "_get_endpoints_features",
        AsyncMock(side_effect=CannotRetrieveData("Boom")),
    )

    await _resync(synced_api)

    assert "Sensor resync after HTTP2 reconnect failed" in caplog.text
    sync_mocks.dnd.assert_awaited_once()
    sync_mocks.media.assert_awaited_once()

    monkeypatch.setattr(
        synced_api._device_handler, "_get_endpoints_features", resynced_features
    )
    # The daily refresh is not due, so only the retry can resync the sensors.
    synced_api._last_daily_refresh = datetime.now(UTC)
    synced_api._default_device_serial = TEST_SERIAL_1
    monkeypatch.setattr(
        synced_api._notification_handler,
        "get_notifications",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        synced_api._communication_handler,
        "get_communication_preferences",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        synced_api._sensor_handler, "update_polled_sensors", AsyncMock()
    )

    await synced_api.get_devices_data()

    assert not synced_api._sensor_resync_required
    sensor = synced_api.sensors[TEST_SERIAL_1]["temperature"]
    assert sensor.value == RESYNCED_TEMPERATURE

    # Once resynced, later polls do not resync again.
    await synced_api.get_devices_data()
    resynced_features.assert_awaited_once()


@pytest.mark.anyio
async def test_sensor_resync_waits_for_sync_lock(
    synced_api: AmazonEchoApi, sync_mocks: _SyncMocks
) -> None:
    """A resync does not query endpoint states while a device refresh holds the lock."""
    async with synced_api._sensor_sync_lock:
        task = asyncio.create_task(synced_api._resync_sensors())
        await asyncio.sleep(0)
        sync_mocks.endpoints_features.assert_not_awaited()

    await task
    sync_mocks.endpoints_features.assert_awaited_once()


@pytest.mark.anyio
async def test_failed_dnd_resync_falls_back_to_push(
    synced_api: AmazonEchoApi,
    sync_mocks: _SyncMocks,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed DnD resync is logged, media still resyncs, push does the sync."""
    synced_api._dnd_initialized = True
    sync_mocks.dnd.side_effect = CannotRetrieveData("Boom")

    await _resync(synced_api)

    assert "sync_dnd_state after HTTP2 reconnect failed" in caplog.text
    assert not synced_api._dnd_initialized
    sync_mocks.media.assert_awaited_once()


@pytest.mark.anyio
async def test_stop_cancels_resync(
    synced_api: AmazonEchoApi, sync_mocks: _SyncMocks
) -> None:
    """Stopping HTTP2 processing cancels an in-flight resync."""
    started = asyncio.Event()

    async def sync_do_not_disturb_status() -> None:
        started.set()
        await asyncio.Event().wait()

    sync_mocks.dnd.side_effect = sync_do_not_disturb_status

    await synced_api._http2_reconnected_handler()
    task = synced_api._resync_task
    await started.wait()

    await synced_api.stop_http2_processing()

    assert task is not None
    assert task.cancelled()
    assert synced_api._resync_task is None


@pytest.mark.anyio
async def test_cancelled_stop_is_propagated(
    synced_api: AmazonEchoApi, sync_mocks: _SyncMocks
) -> None:
    """Cancelling the stop itself is not swallowed while waiting for the resync."""
    holding = asyncio.Event()

    async def sync_do_not_disturb_status() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Swallow the stop's cancel, so the stop is left waiting.
            holding.set()
            await asyncio.Event().wait()

    sync_mocks.dnd.side_effect = sync_do_not_disturb_status

    await synced_api._http2_reconnected_handler()
    await asyncio.sleep(0)
    stop = asyncio.create_task(synced_api.stop_http2_processing())
    await holding.wait()

    stop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stop
