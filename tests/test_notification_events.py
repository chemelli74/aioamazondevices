# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the notification change push-event handling in AmazonEchoApi."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.schedules import NOTIFICATION_TIMER
from aioamazondevices.exceptions import CannotConnect
from aioamazondevices.implementation.http2 import _process_rendering_update
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
    monkeypatch.setattr(api._notification_handler, "get_notifications", fetch)
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
        # Let the debounce start sleeping, so the next event cancels it mid-wait.
        await asyncio.sleep(0)

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
async def test_sync_notifications_without_subscribers(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sync with no subscribers fetches but has nobody to emit to."""
    fetch = _mock_fetch(api, monkeypatch, {SERIAL: {NOTIFICATION_TIMER: TIMER}})

    await api.sync_notifications()

    fetch.assert_awaited_once()


@pytest.mark.anyio
async def test_sync_notifications_survives_failed_fetch(
    notified_api: AmazonEchoApi,
    received: list[NotificationMap],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed initial sync emits nothing, raises nothing and is retried."""
    _mock_fetch(notified_api, monkeypatch, None)

    await notified_api.sync_notifications()

    assert received == []
    assert notified_api._notification_resync_required

    _mock_fetch(notified_api, monkeypatch, {})

    await notified_api.sync_notifications()

    assert received == [{}]
    assert not notified_api._notification_resync_required


@pytest.mark.anyio
async def test_sync_notifications_connection_error_is_retried(
    notified_api: AmazonEchoApi,
    received: list[NotificationMap],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A connection error raised by the fetch still marks the sync for retry."""
    monkeypatch.setattr(
        notified_api._notification_handler,
        "get_notifications",
        AsyncMock(side_effect=CannotConnect("Connection error during GET")),
    )

    with pytest.raises(CannotConnect):
        await notified_api.sync_notifications()

    assert received == []
    assert notified_api._notification_resync_required


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
        notified_api._notification_handler, "get_notifications", slow_fetch
    )

    await notified_api._handle_notification_change_event()
    await fetch_started.wait()
    assert notified_api._notification_tasks

    await notified_api.stop_http2_processing()

    assert fetch_finished
    assert not notified_api._notification_tasks


def _gated_fetch(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> list[asyncio.Event]:
    """Block each fetch until its gate, in call order, is set."""
    gates: list[asyncio.Event] = []

    async def fetch() -> NotificationMap:
        gate = asyncio.Event()
        gates.append(gate)
        await gate.wait()
        return {}

    monkeypatch.setattr(api._notification_handler, "get_notifications", fetch)
    return gates


async def _push_past_debounce(api: AmazonEchoApi) -> None:
    """Send a push event and wait until its debounce window has passed."""
    await api._handle_notification_change_event()
    await asyncio.sleep(0.05)


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_pushes_during_slow_fetch_queue_one_follow_up(
    notified_api: AmazonEchoApi,
    received: list[NotificationMap],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pushes during a fetch queue a single follow-up fetch, not one each."""
    gates = _gated_fetch(notified_api, monkeypatch)

    await _push_past_debounce(notified_api)
    for _ in range(3):
        await _push_past_debounce(notified_api)

    gates[0].set()
    await asyncio.sleep(0.01)
    assert [gate.is_set() for gate in gates] == [True, False]
    assert not notified_api._notification_sync_queued

    # A push during the follow-up fetch is not covered by it, so queues another.
    await _push_past_debounce(notified_api)
    gates[1].set()
    await asyncio.sleep(0.01)
    gates[2].set()
    await asyncio.gather(*notified_api._notification_tasks)

    assert [gate.is_set() for gate in gates] == [True, True, True]
    assert received == [{}, {}, {}]


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_stop_http2_processing_cancels_queued_sync(
    notified_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A queued sync cancelled while waiting does not block later ones."""
    gates = _gated_fetch(notified_api, monkeypatch)

    await _push_past_debounce(notified_api)
    await _push_past_debounce(notified_api)

    await notified_api.stop_http2_processing()

    assert [gate.is_set() for gate in gates] == [False]
    assert not notified_api._notification_sync_queued
    assert not notified_api._notification_lock.locked()


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
    monkeypatch.setattr(api._notification_handler, "get_notifications", fetch)

    await asyncio.gather(api.sync_notifications(), api.sync_notifications())

    assert applied == [older, newer]


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_debounce")
async def test_stop_http2_processing_ignores_pushes_during_shutdown(
    notified_api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A push arriving mid-shutdown cannot leave a sync running afterwards."""
    fetch_started = asyncio.Event()

    async def slow_fetch() -> NotificationMap:
        fetch_started.set()
        try:
            await asyncio.sleep(10)
        finally:
            # slow cleanup, leaving a window for more pushes to arrive
            await asyncio.sleep(0.05)
        return {}

    monkeypatch.setattr(
        notified_api._notification_handler, "get_notifications", slow_fetch
    )

    class FakeHttp2Client:
        """Stands in for the push producer."""

        stopped = False

        async def stop_processing(self) -> None:
            self.stopped = True

    client = FakeHttp2Client()
    monkeypatch.setattr(notified_api, "_http2_client", client)

    async def producer() -> None:
        while not client.stopped:
            await notified_api._handle_notification_change_event()
            await asyncio.sleep(0.001)

    await notified_api._handle_notification_change_event()
    await fetch_started.wait()
    producer_task = asyncio.create_task(producer())

    await notified_api.stop_http2_processing()
    await producer_task

    assert not notified_api._notification_tasks


@pytest.mark.parametrize(
    ("notification_id", "version", "event_type"),
    [
        pytest.param("timer-id", 2, "UPDATE", id="timer-create-first-write"),
        pytest.param("timer-id", 3, "UPDATE", id="timer-create-second-write"),
        pytest.param("reminder-id_REMINDER", 2, "UPDATE", id="reminder-create"),
        pytest.param("reminder-id", 2, "DELETE", id="reminder-delete"),
        pytest.param("alarm-id", 4, "UPDATE", id="alarm-update"),
        pytest.param("alarm-id", 4, "DELETE", id="alarm-delete"),
    ],
)
def test_notification_change_is_never_dropped(
    notification_id: str, version: int, event_type: str
) -> None:
    """Every NotificationChange is a real change, whatever its version."""
    payload = {
        "dopplerId": {"deviceSerialNumber": SERIAL, "deviceType": "TYPE"},
        "notificationId": notification_id,
        "notificationVersion": version,
        "eventType": event_type,
    }
    rendering_update = {
        "route": "EventBus:tcomm::message",
        "resourceId": AmazonPushMessage.NotificationChange.value,
        "resourceMetadata": {
            "command": AmazonPushMessage.NotificationChange.value,
            "payload": payload,
        },
    }

    assert _process_rendering_update(rendering_update) == (
        AmazonPushMessage.NotificationChange.value,
        payload,
    )
