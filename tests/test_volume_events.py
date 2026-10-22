# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the volume push-event handling in AmazonEchoApi."""

import asyncio
from collections.abc import Callable

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonDevice, AmazonVolumeState

SERIAL = "SERIAL"
GROUP_SERIAL = "GROUP_SERIAL"


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


@pytest.mark.anyio
async def test_volume_event_updates_parent_speaker_group(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """A member's volume push recalculates its speaker group's volume."""
    api._device_volumes_initialized = True
    api._media_handler._device_volumes = {
        SERIAL: AmazonVolumeState(10, False),
        "OTHER": AmazonVolumeState(30, False),
    }

    member = make_device(SERIAL)
    member.parent_clusters = [GROUP_SERIAL, "MISSING_GROUP"]
    group = make_device(GROUP_SERIAL)
    group.device_cluster_members = {SERIAL: None, "OTHER": None}
    api._device_handler._final_devices = {SERIAL: member, GROUP_SERIAL: group}

    await api._handle_volume_change_event(_volume_payload(SERIAL, 50))

    assert api._media_handler._device_volumes[GROUP_SERIAL] == AmazonVolumeState(
        40, False
    )
    assert "MISSING_GROUP" not in api._media_handler._device_volumes


@pytest.mark.anyio
async def test_volume_event_for_unknown_device_updates_cache_only(
    api: AmazonEchoApi,
) -> None:
    """A push for a serial not in the device list still updates its volume."""
    api._device_volumes_initialized = True

    await api._handle_volume_change_event(_volume_payload(SERIAL, 50))

    assert api._media_handler._device_volumes == {SERIAL: AmazonVolumeState(50, False)}


@pytest.mark.anyio
async def test_volume_event_without_serial_leaves_cache_unchanged(
    api: AmazonEchoApi,
) -> None:
    """A payload with no device serial changes nothing."""
    api._device_volumes_initialized = True
    api._media_handler._device_volumes = {SERIAL: AmazonVolumeState(10, False)}

    await api._handle_volume_change_event({"volumeSetting": 50, "isMuted": False})

    assert api._media_handler._device_volumes == {SERIAL: AmazonVolumeState(10, False)}
