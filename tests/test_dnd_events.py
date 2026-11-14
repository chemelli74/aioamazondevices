# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Do Not Disturb push-event handling in AmazonEchoApi."""

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1, TEST_SERIAL_2


def _dnd_payload(serial: str, enabled: bool) -> dict[str, object]:
    """Build a DND push payload."""
    return {"dopplerId": {"deviceSerialNumber": serial}, "enabled": enabled}


@pytest.mark.anyio
async def test_dnd_event_triggers_initial_sync_once(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent push events perform the initial full sync only once."""

    async def sync_do_not_disturb_status() -> None:
        await asyncio.sleep(0)
        api._dnd_handler._dnd_states = {TEST_SERIAL_1: False}

    sync = AsyncMock(side_effect=sync_do_not_disturb_status)
    monkeypatch.setattr(api._dnd_handler, "sync_do_not_disturb_status", sync)

    await asyncio.gather(
        api._handle_dnd_event(_dnd_payload(TEST_SERIAL_1, True)),
        api._handle_dnd_event(_dnd_payload(TEST_SERIAL_1, True)),
    )

    sync.assert_awaited_once()


@pytest.mark.anyio
async def test_dnd_event_not_overwritten_by_in_flight_sync(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A push event arriving mid-sync survives the stale full-sync response."""
    api._dnd_initialized = True
    api._dnd_handler._dnd_states = {TEST_SERIAL_1: False}

    started = asyncio.Event()
    release = asyncio.Event()

    async def sync_do_not_disturb_status() -> None:
        started.set()
        await release.wait()
        # Snapshot taken before the push event: DND still disabled.
        api._dnd_handler._dnd_states = {TEST_SERIAL_1: False}

    monkeypatch.setattr(
        api._dnd_handler, "sync_do_not_disturb_status", sync_do_not_disturb_status
    )

    sync_task = asyncio.create_task(api.sync_dnd_state())
    await started.wait()

    # The push event lands while the full sync response is still in flight.
    event_task = asyncio.create_task(
        api._handle_dnd_event(_dnd_payload(TEST_SERIAL_1, True))
    )
    await asyncio.sleep(0)

    release.set()
    await asyncio.gather(sync_task, event_task)

    assert api._dnd_handler.dnd_states == {TEST_SERIAL_1: True}


@pytest.mark.anyio
async def test_dnd_event_without_enabled_is_ignored(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A payload with no boolean 'enabled' triggers neither sync nor update."""
    sync = AsyncMock()
    monkeypatch.setattr(api._dnd_handler, "sync_do_not_disturb_status", sync)

    await api._handle_dnd_event({"dopplerId": {"deviceSerialNumber": TEST_SERIAL_1}})

    sync.assert_not_awaited()
    assert api._dnd_handler.dnd_states == {}


@pytest.mark.anyio
async def test_dnd_set_survives_push_for_other_device(
    api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    make_device: Callable[..., AmazonDevice],
) -> None:
    """A set without its own push event is kept when another device pushes."""
    mock_json_response({})
    api._dnd_initialized = True
    api._dnd_handler._dnd_states = {TEST_SERIAL_1: False, TEST_SERIAL_2: False}
    on_dnd_event = AsyncMock()
    api.on_dnd_event.append(on_dnd_event)
    api.on_dnd_event.freeze()

    # Amazon sends no push for this device, e.g. an Echo Show
    await api.set_do_not_disturb(make_device(TEST_SERIAL_1), True)
    await api._handle_dnd_event(_dnd_payload(TEST_SERIAL_2, True))

    on_dnd_event.assert_awaited_with({TEST_SERIAL_1: True, TEST_SERIAL_2: True})
