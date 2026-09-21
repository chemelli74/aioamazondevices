# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the notification change push-event handling in AmazonEchoApi."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.schedules import NOTIFICATION_TIMER
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonPushMessage,
    AmazonSchedule,
)

SERIAL = "SERIAL"
OTHER_SERIAL = "OTHER_SERIAL"

TIMER = AmazonSchedule(
    type=NOTIFICATION_TIMER,
    status="ON",
    label="pasta",
    next_occurrence=datetime(2026, 1, 1, tzinfo=UTC),
)


def _payload(serial: str | None) -> dict[str, object]:
    """Build a NotificationChange push payload."""
    if serial is None:
        return {}
    return {"dopplerId": {"deviceSerialNumber": serial}}


@pytest.fixture
def fast_debounce(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the debounce window so tests do not wait on real time."""
    monkeypatch.setattr("aioamazondevices.api.NOTIFICATION_DEBOUNCE_DELAY", 0.01)


@pytest.fixture
def notified_api(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> AmazonEchoApi:
    """Build an API with two timer-capable devices already loaded."""
    devices = {}
    for serial in (SERIAL, OTHER_SERIAL):
        device = make_device(serial, capabilities=["TIMERS_AND_ALARMS"])
        device.notifications_supported = True
        devices[serial] = device
    api._device_handler._final_devices = devices
    api._sensor_handler._final_devices = devices
    return api


async def _settle(api: AmazonEchoApi) -> None:
    """Wait for any pending debounced sync to finish."""
    if task := api._notification_debounce_task:
        await asyncio.gather(task, return_exceptions=True)
    # The task clears itself before fetching, so give the fetch a chance to land.
    await asyncio.sleep(0.05)


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_burst_collapses_into_single_fetch(
    notified_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A burst of push events hits the notifications endpoint only once."""
    fetch = AsyncMock(return_value={SERIAL: {NOTIFICATION_TIMER: TIMER}})
    monkeypatch.setattr(
        notified_api._notification_handler, "_fetch_notifications", fetch
    )

    for _ in range(3):
        await notified_api._handle_notification_change_event()

    fetch.assert_not_awaited()
    await _settle(notified_api)

    fetch.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_push_event_dispatches_through_handler(
    notified_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A NotificationChange event refreshes every device, not just the sender."""
    devices = notified_api._device_handler.devices
    # Stale entry on a device the push event does not name.
    devices[OTHER_SERIAL].notifications = {NOTIFICATION_TIMER: TIMER}
    monkeypatch.setattr(
        notified_api._notification_handler,
        "_fetch_notifications",
        AsyncMock(return_value={SERIAL: {NOTIFICATION_TIMER: TIMER}}),
    )

    await notified_api._http2_push_event_handler(
        AmazonPushMessage.NotificationChange.value, _payload(SERIAL)
    )
    await _settle(notified_api)

    assert devices[SERIAL].notifications == {NOTIFICATION_TIMER: TIMER}
    # The endpoint returns every device, so the whole snapshot is applied.
    assert devices[OTHER_SERIAL].notifications == {}


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_debounced_sync_updates_devices_and_emits(
    notified_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The collapsed sync applies notifications and emits the map."""
    notifications = {SERIAL: {NOTIFICATION_TIMER: TIMER}}
    monkeypatch.setattr(
        notified_api._notification_handler,
        "_fetch_notifications",
        AsyncMock(return_value=notifications),
    )

    received: list[dict[str, dict[str, AmazonSchedule]]] = []

    async def on_notification(data: dict[str, dict[str, AmazonSchedule]]) -> None:
        received.append(data)

    notified_api.on_notification_event.append(on_notification)
    notified_api.on_notification_event.freeze()

    await notified_api._handle_notification_change_event()
    await _settle(notified_api)

    devices = notified_api._device_handler.devices
    assert devices[SERIAL].notifications == {NOTIFICATION_TIMER: TIMER}
    assert received == [notifications]


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_sync_updates_every_device(
    notified_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One sync applies the fetched snapshot to every device."""
    notifications = {
        SERIAL: {NOTIFICATION_TIMER: TIMER},
        OTHER_SERIAL: {NOTIFICATION_TIMER: TIMER},
    }
    monkeypatch.setattr(
        notified_api._notification_handler,
        "_fetch_notifications",
        AsyncMock(return_value=notifications),
    )

    await notified_api._handle_notification_change_event()
    await notified_api._handle_notification_change_event()
    await _settle(notified_api)

    devices = notified_api._device_handler.devices
    assert devices[SERIAL].notifications == {NOTIFICATION_TIMER: TIMER}
    assert devices[OTHER_SERIAL].notifications == {NOTIFICATION_TIMER: TIMER}


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_cancelled_notification_is_cleared(
    notified_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A device whose notification disappeared has its cache cleared."""
    notified_api._device_handler.devices[SERIAL].notifications = {
        NOTIFICATION_TIMER: TIMER
    }
    monkeypatch.setattr(
        notified_api._notification_handler,
        "_fetch_notifications",
        AsyncMock(return_value={}),
    )

    await notified_api._handle_notification_change_event()
    await _settle(notified_api)

    assert notified_api._device_handler.devices[SERIAL].notifications == {}


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_event_before_devices_loaded_is_skipped(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No devices means no fetch and no scheduled sync."""
    fetch = AsyncMock(return_value={})
    monkeypatch.setattr(api._notification_handler, "_fetch_notifications", fetch)

    await api._handle_notification_change_event()
    await _settle(api)

    fetch.assert_not_awaited()
    assert api._notification_debounce_task is None


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_failed_fetch_leaves_notifications_untouched(
    notified_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A None response from the endpoint does not wipe cached notifications."""
    notified_api._device_handler.devices[SERIAL].notifications = {
        NOTIFICATION_TIMER: TIMER
    }
    monkeypatch.setattr(
        notified_api._notification_handler,
        "_fetch_notifications",
        AsyncMock(return_value=None),
    )

    await notified_api._handle_notification_change_event()
    await _settle(notified_api)

    assert notified_api._device_handler.devices[SERIAL].notifications == {
        NOTIFICATION_TIMER: TIMER
    }


@pytest.mark.anyio
async def test_stop_http2_processing_cancels_pending_sync(
    notified_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shutting down drops a debounce still waiting to fire."""
    fetch = AsyncMock(return_value={})
    monkeypatch.setattr(
        notified_api._notification_handler, "_fetch_notifications", fetch
    )

    await notified_api._handle_notification_change_event()
    pending = notified_api._notification_debounce_task
    assert pending is not None

    await notified_api.stop_http2_processing()
    await asyncio.gather(pending, return_exceptions=True)

    fetch.assert_not_awaited()
    assert notified_api._notification_debounce_task is None
