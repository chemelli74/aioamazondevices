# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for resyncing pushed state after the HTTP2 stream reconnects."""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import REFRESH_ACCESS_TOKEN
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.implementation.http2 import AmazonHTTP2Client, _TaskAction
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1

pytestmark = pytest.mark.anyio

ENDPOINT = "endpoint-1"
SYNCED_TEMPERATURE = 20.0
RESYNCED_TEMPERATURE = 23.0


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


def _temperature(value: float) -> dict[str, Any]:
    return {
        "name": "temperatureSensor",
        "instance": None,
        "properties": [
            {"name": "temperature", "value": {"value": value, "scale": "CELSIUS"}}
        ],
    }


@pytest.fixture
def synced_api(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., Any],
) -> AmazonEchoApi:
    """Return an API with a temperature sensor synced and other syncs stubbed."""
    device = make_device(TEST_SERIAL_1)
    sync_sensors({"features": [_temperature(SYNCED_TEMPERATURE)]}, device)
    api._device_handler._final_devices = {TEST_SERIAL_1: device}
    api._device_handler._get_endpoints_features = AsyncMock(  # type: ignore[method-assign]
        return_value={
            device.endpoint_id: {
                "endpointId": device.endpoint_id,
                "features": [_temperature(RESYNCED_TEMPERATURE)],
            }
        }
    )
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
        return _TaskAction.STOP

    monkeypatch.setattr(client, "_run_tasks", _stop_after_one_run)
    await client._orchestrate_tasks()

    assert not client._has_connected


async def test_reconnect_resyncs_pushed_state(synced_api: AmazonEchoApi) -> None:
    """A reconnect resyncs sensors, DnD and media, and notifies subscribers."""
    events = 0

    async def _on_sensor_event() -> None:
        nonlocal events
        events += 1

    synced_api.on_sensor_event.append(_on_sensor_event)
    synced_api.on_sensor_event.freeze()

    await _resync(synced_api)

    sensor = synced_api.sensors[TEST_SERIAL_1]["temperature"]
    assert sensor.value == RESYNCED_TEMPERATURE
    assert events == 1
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

    async def _get_endpoints_features(_ids: list[str]) -> dict[str, Any]:
        nonlocal syncs
        syncs += 1
        await release.wait()
        return {}

    monkeypatch.setattr(
        synced_api._device_handler, "_get_endpoints_features", _get_endpoints_features
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


async def test_failed_sensor_resync_is_retried_on_next_poll(
    synced_api: AmazonEchoApi,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed sensor resync is logged, the rest still runs, the poll retries."""
    get_features = AsyncMock(side_effect=CannotRetrieveData("Boom"))
    resynced_features = synced_api._device_handler._get_endpoints_features
    synced_api._device_handler._get_endpoints_features = get_features  # type: ignore[method-assign]

    await _resync(synced_api)

    assert "Sensor resync after HTTP2 reconnect failed" in caplog.text
    synced_api._dnd_handler.sync_do_not_disturb_status.assert_awaited_once()  # type: ignore[attr-defined]
    synced_api._media_handler.sync_media_state.assert_awaited_once()  # type: ignore[attr-defined]

    synced_api._device_handler._get_endpoints_features = resynced_features  # type: ignore[method-assign]
    # daily refresh not due, so only the retry can resync the sensors
    synced_api._last_daily_refresh = datetime.now(UTC)
    synced_api._default_device_serial = TEST_SERIAL_1
    synced_api._notification_handler.get_notifications = AsyncMock(return_value=None)  # type: ignore[method-assign]
    synced_api._communication_handler.get_communication_preferences = AsyncMock(  # type: ignore[method-assign]
        return_value={}
    )
    synced_api._sensor_handler.update_polled_sensors = AsyncMock()  # type: ignore[method-assign]

    await synced_api.get_devices_data()

    assert not synced_api._sensor_resync_required
    sensor = synced_api.sensors[TEST_SERIAL_1]["temperature"]
    assert sensor.value == RESYNCED_TEMPERATURE


async def test_failed_dnd_resync_falls_back_to_push(
    synced_api: AmazonEchoApi,
) -> None:
    """A failed DnD resync leaves the next push event to do the full sync."""
    synced_api._dnd_initialized = True
    synced_api._dnd_handler.sync_do_not_disturb_status = AsyncMock(  # type: ignore[method-assign]
        side_effect=CannotRetrieveData("Boom")
    )

    await _resync(synced_api)

    assert not synced_api._dnd_initialized


async def test_stop_cancels_resync(
    synced_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stopping HTTP2 processing cancels an in-flight resync."""
    started = asyncio.Event()

    async def _get_endpoints_features(_ids: list[str]) -> dict[str, Any]:
        started.set()
        await asyncio.Event().wait()
        return {}

    monkeypatch.setattr(
        synced_api._device_handler, "_get_endpoints_features", _get_endpoints_features
    )

    await synced_api._http2_reconnected_handler()
    task = synced_api._resync_task
    await started.wait()

    await synced_api.stop_http2_processing()

    assert task is not None
    assert task.cancelled()
    assert synced_api._resync_task is None
