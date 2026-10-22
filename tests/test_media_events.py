# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the media state sync in AmazonMediaHandler."""

import asyncio
import dataclasses
from collections.abc import Callable
from typing import Any

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonDevice

SERIAL = "SERIAL"


def _media_sessions(state: str) -> dict[str, Any]:
    """Build a media sessions response with the given player state."""
    return {SERIAL: {"nowPlayingData": {"playerState": state}}}


@pytest.mark.anyio
async def test_media_state_not_overwritten_by_in_flight_sync(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sync started mid-sync survives the stale response of the first one."""
    device = dataclasses.replace(make_device(SERIAL), media_player_supported=True)
    devices = {SERIAL: device}

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
    assert media_states[SERIAL].player_state == "PLAYING"
