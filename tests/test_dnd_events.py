# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Do Not Disturb push-event handling in AmazonEchoApi."""

import asyncio

import pytest

from aioamazondevices.api import AmazonEchoApi

SERIAL = "SERIAL"


def _dnd_payload(serial: str, enabled: bool) -> dict[str, object]:
    """Build a DND push payload."""
    return {"dopplerId": {"deviceSerialNumber": serial}, "enabled": enabled}


@pytest.mark.anyio
async def test_dnd_event_triggers_initial_sync_once(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent push events perform the initial full sync only once."""
    syncs = 0

    async def sync_do_not_disturb_status() -> None:
        nonlocal syncs
        syncs += 1
        await asyncio.sleep(0)
        api._dnd_handler._dnd_states = {SERIAL: False}

    monkeypatch.setattr(
        api._dnd_handler, "sync_do_not_disturb_status", sync_do_not_disturb_status
    )

    await asyncio.gather(
        api._handle_dnd_event(_dnd_payload(SERIAL, True)),
        api._handle_dnd_event(_dnd_payload(SERIAL, True)),
    )

    assert syncs == 1


@pytest.mark.anyio
async def test_dnd_event_not_overwritten_by_in_flight_sync(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A push event arriving mid-sync survives the stale full-sync response."""
    api._dnd_initialized = True
    api._dnd_handler._dnd_states = {SERIAL: False}

    started = asyncio.Event()
    release = asyncio.Event()

    async def sync_do_not_disturb_status() -> None:
        started.set()
        await release.wait()
        # Snapshot taken before the push event: DND still disabled.
        api._dnd_handler._dnd_states = {SERIAL: False}

    monkeypatch.setattr(
        api._dnd_handler, "sync_do_not_disturb_status", sync_do_not_disturb_status
    )

    sync_task = asyncio.create_task(api.sync_dnd_state())
    await started.wait()

    # The push event lands while the full sync response is still in flight.
    event_task = asyncio.create_task(api._handle_dnd_event(_dnd_payload(SERIAL, True)))
    await asyncio.sleep(0)

    release.set()
    await asyncio.gather(sync_task, event_task)

    assert api._dnd_handler.dnd_states == {SERIAL: True}


@pytest.mark.anyio
async def test_dnd_event_without_enabled_is_ignored(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A payload with no boolean 'enabled' triggers neither sync nor update."""
    syncs = 0

    async def sync_do_not_disturb_status() -> None:
        nonlocal syncs
        syncs += 1

    monkeypatch.setattr(
        api._dnd_handler, "sync_do_not_disturb_status", sync_do_not_disturb_status
    )

    await api._handle_dnd_event({"dopplerId": {"deviceSerialNumber": SERIAL}})

    assert syncs == 0
    assert api._dnd_handler.dnd_states == {}
