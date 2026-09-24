# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the notification change push-event handling in AmazonEchoApi."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.schedules import NOTIFICATION_TIMER
from aioamazondevices.structures import AmazonPushMessage, AmazonSchedule

SERIAL = "SERIAL"
OTHER_SERIAL = "OTHER_SERIAL"

TIMER = AmazonSchedule(
    type=NOTIFICATION_TIMER,
    status="ON",
    label="pasta",
    next_occurrence=datetime(2026, 1, 1, tzinfo=UTC),
)

NotificationMap = dict[str, dict[str, AmazonSchedule]]


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
def received() -> list[NotificationMap]:
    """Collect every notification map emitted to subscribers."""
    return []


@pytest.fixture
def notified_api(api: AmazonEchoApi, received: list[NotificationMap]) -> AmazonEchoApi:
    """Build an API with a notification subscriber attached."""

    async def on_notification(data: NotificationMap) -> None:
        received.append(data)

    api.on_notification_event.append(on_notification)
    api.on_notification_event.freeze()
    return api


def _mock_fetch(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
    notifications: NotificationMap | None,
) -> AsyncMock:
    """Replace the notifications endpoint call with a canned response."""
    fetch = AsyncMock(return_value=notifications)
    monkeypatch.setattr(api._notification_handler, "_fetch_notifications", fetch)
    return fetch


async def _settle(api: AmazonEchoApi) -> None:
    """Wait for any pending debounced sync to finish."""
    if task := api._notification_debounce_task:
        await asyncio.gather(task, return_exceptions=True)
    # The task clears itself before fetching, so give the fetch a chance to land.
    await asyncio.sleep(0.05)


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_burst_collapses_into_single_fetch(
    notified_api: AmazonEchoApi,
    received: list[NotificationMap],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A burst of push events hits the notifications endpoint only once."""
    fetch = _mock_fetch(
        notified_api, monkeypatch, {SERIAL: {NOTIFICATION_TIMER: TIMER}}
    )

    for _ in range(3):
        await notified_api._handle_notification_change_event()

    fetch.assert_not_awaited()
    await _settle(notified_api)

    fetch.assert_awaited_once()
    assert len(received) == 1


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_push_event_dispatches_through_handler(
    notified_api: AmazonEchoApi,
    received: list[NotificationMap],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A NotificationChange push event emits the full fetched snapshot."""
    notifications = {
        SERIAL: {NOTIFICATION_TIMER: TIMER},
        OTHER_SERIAL: {NOTIFICATION_TIMER: TIMER},
    }
    _mock_fetch(notified_api, monkeypatch, notifications)

    await notified_api._http2_push_event_handler(
        AmazonPushMessage.NotificationChange.value, _payload(SERIAL)
    )
    await _settle(notified_api)

    # The endpoint returns every device, not just the one that sent the event.
    assert received == [notifications]


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_cancelled_notification_emits_empty_map(
    notified_api: AmazonEchoApi,
    received: list[NotificationMap],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When nothing is scheduled any more, subscribers get an empty map."""
    _mock_fetch(notified_api, monkeypatch, {})

    await notified_api._handle_notification_change_event()
    await _settle(notified_api)

    assert received == [{}]


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_event_without_subscribers_is_skipped(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No subscribers means no fetch and no scheduled sync."""
    fetch = _mock_fetch(api, monkeypatch, {})

    await api._handle_notification_change_event()
    await _settle(api)

    fetch.assert_not_awaited()
    assert api._notification_debounce_task is None


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_failed_fetch_emits_nothing(
    notified_api: AmazonEchoApi,
    received: list[NotificationMap],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A None response from the endpoint is not passed on to subscribers."""
    _mock_fetch(notified_api, monkeypatch, None)

    await notified_api._handle_notification_change_event()
    await _settle(notified_api)

    assert received == []


@pytest.mark.anyio
async def test_stop_http2_processing_cancels_pending_sync(
    notified_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shutting down drops a debounce still waiting to fire."""
    fetch = _mock_fetch(notified_api, monkeypatch, {})

    await notified_api._handle_notification_change_event()
    pending = notified_api._notification_debounce_task
    assert pending is not None

    await notified_api.stop_http2_processing()
    await asyncio.gather(pending, return_exceptions=True)

    fetch.assert_not_awaited()
    assert notified_api._notification_debounce_task is None


@pytest.mark.anyio
async def test_sync_notifications_primes_initial_state(
    notified_api: AmazonEchoApi,
    received: list[NotificationMap],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public sync emits the current state without a push event."""
    _mock_fetch(notified_api, monkeypatch, {SERIAL: {NOTIFICATION_TIMER: TIMER}})

    await notified_api.sync_notifications()

    assert received == [{SERIAL: {NOTIFICATION_TIMER: TIMER}}]
    assert notified_api._notification_debounce_task is None


@pytest.mark.anyio
async def test_sync_notifications_survives_failed_fetch(
    notified_api: AmazonEchoApi,
    received: list[NotificationMap],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed initial sync emits nothing and raises nothing."""
    _mock_fetch(notified_api, monkeypatch, None)

    await notified_api.sync_notifications()

    assert received == []


@pytest.mark.anyio
async def test_notifications_are_not_filtered(
    notified_api: AmazonEchoApi,
    received: list[NotificationMap],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Notifications are emitted as fetched, even for unknown devices."""
    notifications = {"PLAIN": {NOTIFICATION_TIMER: TIMER}}
    _mock_fetch(notified_api, monkeypatch, notifications)

    await notified_api.sync_notifications()

    assert received == [notifications]


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_stop_http2_processing_waits_for_running_sync(
    notified_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shutting down does not return while a fetch is still in flight."""
    fetch_started = asyncio.Event()
    fetch_finished = False

    async def slow_fetch() -> NotificationMap:
        nonlocal fetch_finished
        fetch_started.set()
        try:
            await asyncio.sleep(10)
        finally:
            fetch_finished = True
        return {}

    monkeypatch.setattr(
        notified_api._notification_handler, "_fetch_notifications", slow_fetch
    )

    await notified_api._handle_notification_change_event()
    await fetch_started.wait()
    assert notified_api._notification_tasks

    await notified_api.stop_http2_processing()

    assert fetch_finished
    assert not notified_api._notification_tasks


@pytest.mark.anyio
async def test_overlapping_syncs_emit_in_fetch_order(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow subscriber cannot let an older snapshot land after a newer one."""
    applied: list[NotificationMap] = []

    async def slow_subscriber(data: NotificationMap) -> None:
        # Yield before applying, as a subscriber doing its own I/O would
        await asyncio.sleep(0.01 if not data else 0)
        applied.append(data)

    api.on_notification_event.append(slow_subscriber)
    api.on_notification_event.freeze()

    older: NotificationMap = {}
    newer: NotificationMap = {SERIAL: {NOTIFICATION_TIMER: TIMER}}
    fetch = AsyncMock(side_effect=[older, newer])
    monkeypatch.setattr(api._notification_handler, "_fetch_notifications", fetch)

    await asyncio.gather(api.sync_notifications(), api.sync_notifications())

    assert applied == [older, newer]
