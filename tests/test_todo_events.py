# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the debounced todo list push-event handling."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.implementation import todo as todo_module
from aioamazondevices.implementation.todo import AmazonToDoHandler
from aioamazondevices.structures import (
    AmazonListEvent,
    AmazonListEventType,
    AmazonListItem,
    AmazonListItemStatus,
)

LIST_ID = "list-1"
OTHER_LIST_ID = "list-2"
DEBOUNCE_DELAY = 0.05  # seconds


def _item(item_id: str) -> AmazonListItem:
    """Build a list item."""
    return AmazonListItem(item_id, AmazonListItemStatus.ACTIVE, item_id.title(), 1)


def _payload(list_id: str, item_id: str, event_name: str) -> dict[str, str]:
    """Build an ItemChange push payload."""
    return {"listId": list_id, "listItemId": item_id, "eventName": event_name}


@pytest.fixture
def handler(api: AmazonEchoApi) -> AmazonToDoHandler:
    """Return the todo handler of the API."""
    return api._todo_handler


@pytest.fixture
def events(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> list[AmazonListEvent]:
    """Collect emitted todo events, with a short debounce delay."""
    monkeypatch.setattr(todo_module, "TODO_DEBOUNCE_DELAY", DEBOUNCE_DELAY)
    received: list[AmazonListEvent] = []

    async def on_todo_event(list_event: AmazonListEvent) -> None:
        received.append(list_event)

    api.on_todo_event.append(on_todo_event)
    api.on_todo_event.freeze()
    return received


async def _settle(handler: AmazonToDoHandler) -> None:
    """Wait for all debounced todo changes to be processed."""
    await asyncio.sleep(DEBOUNCE_DELAY * 2)
    assert not handler._timers
    await asyncio.gather(*handler._tasks)


@pytest.mark.anyio
async def test_burst_of_changes_fetches_list_once(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changes within the debounce window share a single list fetch."""
    fetch = AsyncMock(return_value=[_item("a"), _item("b")])
    monkeypatch.setattr(handler, "get_list_items", fetch)

    await api._handle_item_change_event(_payload(LIST_ID, "a", "itemUpdated"))
    await asyncio.sleep(0.03)
    # This restarts the window, so the first change is not flushed on its own.
    await api._handle_item_change_event(_payload(LIST_ID, "b", "itemUpdated"))
    await asyncio.sleep(0.03)
    fetch.assert_not_awaited()

    await _settle(handler)

    fetch.assert_awaited_once_with(LIST_ID)
    assert events == [
        AmazonListEvent(LIST_ID, "a", AmazonListEventType.UPDATED, _item("a")),
        AmazonListEvent(LIST_ID, "b", AmazonListEventType.UPDATED, _item("b")),
    ]
    assert not handler._tasks
    assert not handler._changes


@pytest.mark.anyio
async def test_lists_are_debounced_separately(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each list is fetched for its own changes."""
    fetch = AsyncMock(return_value=[_item("a")])
    monkeypatch.setattr(handler, "get_list_items", fetch)

    await api._handle_item_change_event(_payload(LIST_ID, "a", "itemCreated"))
    await api._handle_item_change_event(_payload(OTHER_LIST_ID, "a", "itemCreated"))
    await _settle(handler)

    assert sorted(call.args[0] for call in fetch.await_args_list) == [
        LIST_ID,
        OTHER_LIST_ID,
    ]
    assert sorted(event.list_id for event in events) == [LIST_ID, OTHER_LIST_ID]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("event_names", "expected_type"),
    [
        pytest.param(
            ["itemCreated", "itemUpdated"],
            AmazonListEventType.CREATED,
            id="created-then-updated",
        ),
        pytest.param(
            ["itemUpdated", "itemUpdated"],
            AmazonListEventType.UPDATED,
            id="updated-twice",
        ),
        pytest.param(
            ["itemCreated", "itemDeleted"],
            AmazonListEventType.DELETED,
            id="created-then-deleted",
        ),
        pytest.param(
            ["itemUpdated", "itemDeleted"],
            AmazonListEventType.DELETED,
            id="updated-then-deleted",
        ),
    ],
)
async def test_changes_to_one_item_are_merged(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    event_names: list[str],
    expected_type: AmazonListEventType,
) -> None:
    """Several changes to one item emit a single event."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            handler, "get_list_items", AsyncMock(return_value=[_item("a")])
        )

        for event_name in event_names:
            await api._handle_item_change_event(_payload(LIST_ID, "a", event_name))
        await _settle(handler)

    assert [(event.item_id, event.type) for event in events] == [("a", expected_type)]


@pytest.mark.anyio
async def test_only_deletions_skip_fetch(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deleted items need no list fetch."""
    fetch = AsyncMock()
    monkeypatch.setattr(handler, "get_list_items", fetch)

    await api._handle_item_change_event(_payload(LIST_ID, "a", "itemDeleted"))
    await _settle(handler)

    fetch.assert_not_awaited()
    assert events == [AmazonListEvent(LIST_ID, "a", AmazonListEventType.DELETED)]


@pytest.mark.anyio
async def test_item_missing_from_fetch_is_deleted(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An item removed again before the fetch is reported as deleted."""
    monkeypatch.setattr(handler, "get_list_items", AsyncMock(return_value=[]))

    await api._handle_item_change_event(_payload(LIST_ID, "a", "itemCreated"))
    await _settle(handler)

    assert events == [AmazonListEvent(LIST_ID, "a", AmazonListEventType.DELETED)]


@pytest.mark.anyio
async def test_fetch_failure_is_logged(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed fetch emits nothing and does not block later changes."""
    monkeypatch.setattr(
        handler, "get_list_items", AsyncMock(side_effect=RuntimeError("boom"))
    )

    await api._handle_item_change_event(_payload(LIST_ID, "a", "itemUpdated"))
    await _settle(handler)

    assert not events
    assert not handler._tasks
    assert "Fetching todo list list-1 failed: boom" in caplog.text


@pytest.mark.anyio
async def test_stop_http2_processing_cancels_pending_changes(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stopping drops changes still waiting for the debounce window."""
    fetch = AsyncMock()
    monkeypatch.setattr(handler, "get_list_items", fetch)

    await api._handle_item_change_event(_payload(LIST_ID, "a", "itemUpdated"))
    timer = handler._timers[LIST_ID]

    await api.stop_http2_processing()

    assert timer.cancelled()
    assert not handler._timers
    assert not handler._changes
    fetch.assert_not_awaited()
    assert not events


@pytest.mark.anyio
async def test_stop_http2_processing_cancels_in_flight_fetch(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stopping cancels a list fetch already in progress."""
    started = asyncio.Event()

    async def get_list_items(_list_id: str) -> list[AmazonListItem]:
        started.set()
        await asyncio.Event().wait()
        return []

    monkeypatch.setattr(handler, "get_list_items", get_list_items)

    await api._handle_item_change_event(_payload(LIST_ID, "a", "itemUpdated"))
    await started.wait()
    (task,) = handler._tasks

    await api.stop_http2_processing()

    assert task.cancelled()
    assert not handler._tasks
    assert not events
