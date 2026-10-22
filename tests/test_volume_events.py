# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the volume push-event handling in AmazonEchoApi."""

import asyncio

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonVolumeState

SERIAL = "SERIAL"


def _volume_payload(serial: str, volume: int) -> dict[str, object]:
    """Build a volume push payload."""
    return {
        "dopplerId": {"deviceSerialNumber": serial},
        "volumeSetting": volume,
        "isMuted": False,
    }


@pytest.mark.anyio
async def test_volume_event_triggers_initial_sync_once(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent push events perform the initial full sync only once."""
    syncs = 0

    async def sync_device_volumes() -> None:
        nonlocal syncs
        syncs += 1
        await asyncio.sleep(0)
        api._media_handler._device_volumes = {SERIAL: AmazonVolumeState(10, False)}

    monkeypatch.setattr(api._media_handler, "sync_device_volumes", sync_device_volumes)

    await asyncio.gather(
        api._handle_volume_change_event(_volume_payload(SERIAL, 50)),
        api._handle_volume_change_event(_volume_payload(SERIAL, 50)),
    )

    assert syncs == 1


@pytest.mark.anyio
async def test_volume_event_not_overwritten_by_in_flight_sync(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A push event arriving mid-sync survives the stale full-sync response."""
    api._device_volumes_initialized = True
    api._media_handler._device_volumes = {SERIAL: AmazonVolumeState(10, False)}

    started = asyncio.Event()
    release = asyncio.Event()

    async def sync_device_volumes() -> None:
        started.set()
        await release.wait()
        # Snapshot taken before the push event: old volume.
        api._media_handler._device_volumes = {SERIAL: AmazonVolumeState(10, False)}

    async def sync_media_state(_devices: object) -> None:
        return

    monkeypatch.setattr(api._media_handler, "sync_device_volumes", sync_device_volumes)
    monkeypatch.setattr(api._media_handler, "sync_media_state", sync_media_state)

    sync_task = asyncio.create_task(api.sync_media_state())
    await started.wait()

    # The push event lands while the full sync response is still in flight.
    event_task = asyncio.create_task(
        api._handle_volume_change_event(_volume_payload(SERIAL, 50))
    )
    await asyncio.sleep(0)

    release.set()
    await asyncio.gather(sync_task, event_task)

    assert api._media_handler._device_volumes == {SERIAL: AmazonVolumeState(50, False)}
