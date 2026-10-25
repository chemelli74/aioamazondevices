# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the volume push-event handling in AmazonEchoApi."""

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonDevice, AmazonVolumeState

from .const import TEST_SERIAL_1, TEST_SERIAL_2

TEST_SERIAL_GROUP = "GROUP-1"


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

    async def sync_device_volumes() -> None:
        await asyncio.sleep(0)
        api._media_handler._device_volumes = {
            TEST_SERIAL_1: AmazonVolumeState(10, False)
        }

    sync = AsyncMock(side_effect=sync_device_volumes)
    monkeypatch.setattr(api._media_handler, "sync_device_volumes", sync)

    await asyncio.gather(
        api._handle_volume_change_event(_volume_payload(TEST_SERIAL_1, 50)),
        api._handle_volume_change_event(_volume_payload(TEST_SERIAL_1, 50)),
    )

    sync.assert_awaited_once()


@pytest.mark.anyio
async def test_volume_event_not_overwritten_by_in_flight_sync(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A push event arriving mid-sync survives the stale full-sync response."""
    api._device_volumes_initialized = True
    api._media_handler._device_volumes = {TEST_SERIAL_1: AmazonVolumeState(10, False)}

    started = asyncio.Event()
    release = asyncio.Event()

    async def sync_device_volumes() -> None:
        started.set()
        await release.wait()
        # Snapshot taken before the push event: old volume.
        api._media_handler._device_volumes = {
            TEST_SERIAL_1: AmazonVolumeState(10, False)
        }

    monkeypatch.setattr(api._media_handler, "sync_device_volumes", sync_device_volumes)
    monkeypatch.setattr(api._media_handler, "sync_media_state", AsyncMock())

    sync_task = asyncio.create_task(api.sync_media_state())
    await started.wait()

    # The push event lands while the full sync response is still in flight.
    event_task = asyncio.create_task(
        api._handle_volume_change_event(_volume_payload(TEST_SERIAL_1, 50))
    )
    await asyncio.sleep(0)

    release.set()
    await asyncio.gather(sync_task, event_task)

    assert api._media_handler._device_volumes == {
        TEST_SERIAL_1: AmazonVolumeState(50, False)
    }


@pytest.mark.anyio
async def test_volume_event_updates_parent_speaker_group(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """A member's volume push recalculates its speaker group's volume."""
    api._device_volumes_initialized = True
    api._media_handler._device_volumes = {
        TEST_SERIAL_1: AmazonVolumeState(10, False),
        TEST_SERIAL_2: AmazonVolumeState(30, False),
    }

    member = make_device(TEST_SERIAL_1)
    member.parent_clusters = [TEST_SERIAL_GROUP, "MISSING_GROUP"]
    group = make_device(TEST_SERIAL_GROUP)
    group.device_cluster_members = {TEST_SERIAL_1: None, TEST_SERIAL_2: None}
    api._device_handler._final_devices = {
        TEST_SERIAL_1: member,
        TEST_SERIAL_GROUP: group,
    }

    await api._handle_volume_change_event(_volume_payload(TEST_SERIAL_1, 50))

    assert api._media_handler._device_volumes[TEST_SERIAL_GROUP] == AmazonVolumeState(
        40, False
    )
    assert "MISSING_GROUP" not in api._media_handler._device_volumes


@pytest.mark.anyio
async def test_volume_event_for_unknown_device_updates_cache_only(
    api: AmazonEchoApi,
) -> None:
    """A push for a serial not in the device list still updates its volume."""
    api._device_volumes_initialized = True

    await api._handle_volume_change_event(_volume_payload(TEST_SERIAL_1, 50))

    assert api._media_handler._device_volumes == {
        TEST_SERIAL_1: AmazonVolumeState(50, False)
    }


@pytest.mark.anyio
async def test_volume_event_without_serial_leaves_cache_unchanged(
    api: AmazonEchoApi,
) -> None:
    """A payload with no device serial changes nothing."""
    api._device_volumes_initialized = True
    api._media_handler._device_volumes = {TEST_SERIAL_1: AmazonVolumeState(10, False)}

    await api._handle_volume_change_event({"volumeSetting": 50, "isMuted": False})

    assert api._media_handler._device_volumes == {
        TEST_SERIAL_1: AmazonVolumeState(10, False)
    }
