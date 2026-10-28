# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the media state sync in AmazonMediaHandler."""

import asyncio
import dataclasses
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonMediaState,
    AmazonVolumeState,
)

from .const import TEST_SERIAL_1

VOLUME = AmazonVolumeState(30, False)


def _media_sessions(state: str) -> dict[str, Any]:
    """Build a media sessions response with the given player state."""
    return {TEST_SERIAL_1: {"nowPlayingData": {"playerState": state}}}


@pytest.mark.anyio
async def test_media_state_not_overwritten_by_in_flight_sync(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sync started mid-sync survives the stale response of the first one."""
    device = dataclasses.replace(
        make_device(TEST_SERIAL_1), media_player_supported=True
    )
    devices = {TEST_SERIAL_1: device}

    started = asyncio.Event()
    release = asyncio.Event()
    responses = iter(("PAUSED", "PLAYING"))

    async def get_media_states(_device: AmazonDevice) -> dict[str, Any]:
        state = next(responses)
        if state == "PAUSED":
            # Snapshot taken before the push event: old state.
            started.set()
            await release.wait()
        return _media_sessions(state)

    monkeypatch.setattr(api._media_handler, "_get_media_states", get_media_states)

    sync_task = asyncio.create_task(api._media_handler.sync_media_state(devices))
    await started.wait()

    # The push event lands while the first sync response is still in flight.
    event_task = asyncio.create_task(api._media_handler.sync_media_state(devices))
    await asyncio.sleep(0)

    release.set()
    await asyncio.gather(sync_task, event_task)

    media_states = await api._media_handler.media_states
    assert media_states[TEST_SERIAL_1].player_state == "PLAYING"


@pytest.mark.anyio
async def test_audio_player_event_skipped_before_devices_load(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A push event before the device list is loaded does not sync media state."""
    sync = AsyncMock()
    monkeypatch.setattr(api._media_handler, "sync_media_state", sync)

    await api._handle_audio_player_state_event()

    sync.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "subscribed",
    [
        pytest.param(False, id="no-subscribers"),
        pytest.param(True, id="subscribed"),
    ],
)
async def test_audio_player_event_syncs_and_emits(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
    subscribed: bool,
) -> None:
    """A push event resyncs media state and emits it only to subscribers."""
    devices = {
        TEST_SERIAL_1: dataclasses.replace(
            make_device(TEST_SERIAL_1), media_player_supported=True
        )
    }
    api._device_handler._final_devices = devices
    monkeypatch.setattr(
        api._media_handler,
        "_get_media_states",
        AsyncMock(return_value=_media_sessions("PLAYING")),
    )
    sync = AsyncMock(wraps=api._media_handler.sync_media_state)
    monkeypatch.setattr(api._media_handler, "sync_media_state", sync)

    received: list[dict[str, AmazonMediaState]] = []

    async def on_media_state(media_states: dict[str, AmazonMediaState]) -> None:
        received.append(media_states)

    if subscribed:
        api.on_media_state_event.append(on_media_state)
        api.on_media_state_event.freeze()

    await api._handle_audio_player_state_event()

    sync.assert_awaited_once_with(devices)
    media_states = await api._media_handler.media_states
    assert media_states[TEST_SERIAL_1].player_state == "PLAYING"
    assert received == ([media_states] if subscribed else [])


@pytest.mark.anyio
async def test_sync_media_state_emits_volumes_and_media_states(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full sync emits the device volumes and then the media states."""

    async def sync_device_volumes() -> None:
        api._media_handler.update_cached_device_volume(TEST_SERIAL_1, VOLUME)

    monkeypatch.setattr(api._media_handler, "sync_device_volumes", sync_device_volumes)
    monkeypatch.setattr(api._media_handler, "sync_media_state", AsyncMock())

    received: list[tuple[str, dict[str, Any]]] = []

    async def on_volume_state(volumes: dict[str, AmazonVolumeState]) -> None:
        received.append(("volume", volumes))

    async def on_media_state(media_states: dict[str, AmazonMediaState]) -> None:
        received.append(("media", media_states))

    api.on_volume_state_event.append(on_volume_state)
    api.on_volume_state_event.freeze()
    api.on_media_state_event.append(on_media_state)
    api.on_media_state_event.freeze()

    await api.sync_media_state()

    assert api._device_volumes_initialized
    assert received == [("volume", {TEST_SERIAL_1: VOLUME}), ("media", {})]
