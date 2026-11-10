# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Alexa lists handler and the API calls that use it."""

import asyncio
from collections.abc import Awaitable, Callable
from http import HTTPMethod
from typing import Any
from unittest.mock import AsyncMock, call

import pytest
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import URI_TODO_BASE
from aioamazondevices.implementation import todo as todo_module
from aioamazondevices.implementation.todo import AmazonToDoHandler
from aioamazondevices.structures import (
    AmazonListEvent,
    AmazonListEventType,
    AmazonListInfo,
    AmazonListItem,
    AmazonListItemStatus,
    AmazonListType,
)

TEST_LIST_ID = "LIST-1"
TEST_OTHER_LIST_ID = "LIST-2"
TEST_ITEM_ID = "ITEM-1"
DEBOUNCE_DELAY = 0.05  # seconds

ITEM = AmazonListItem(
    id=TEST_ITEM_ID, status=AmazonListItemStatus.ACTIVE, name="Milk", version=3
)


def _lists_url(api: AmazonEchoApi, path: str, query: dict[str, Any] | None) -> URL:
    """Return the lists API URL for the path and query."""
    return URL.joinpath(
        api._session_state_data.retail_site_url, URI_TODO_BASE, path
    ).with_query(query)


def _set_checked(checked: bool) -> Callable[[AmazonEchoApi], Awaitable[None]]:
    """Return a call setting the test item's checked status."""
    return lambda api: api.set_todo_list_item_checked_status(
        TEST_LIST_ID, TEST_ITEM_ID, checked, 3
    )


def _item_status(status: AmazonListItemStatus) -> dict[str, Any]:
    """Return the update body setting an item's status."""
    return {
        "itemAttributesToUpdate": [{"type": "itemStatus", "value": status.value}],
        "itemAttributesToRemove": [],
    }


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


@pytest.fixture
def get_list_items(
    handler: AmazonToDoHandler, monkeypatch: pytest.MonkeyPatch
) -> AsyncMock:
    """Stub the list fetch, returning items a and b, and return the mock."""
    get_list_items = AsyncMock(return_value=[_item("a"), _item("b")])
    monkeypatch.setattr(handler, "get_list_items", get_list_items)
    return get_list_items


async def _settle(handler: AmazonToDoHandler) -> None:
    """Wait for all debounced todo changes to be processed."""
    await asyncio.sleep(DEBOUNCE_DELAY * 2)
    assert not handler._timers
    await asyncio.gather(*handler._tasks)


@pytest.mark.anyio
async def test_update_lists(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """All lists are fetched and cached, a missing name is None."""
    session_request = mock_json_response(
        {
            "listInfoList": [
                {"listId": "SHOP-1", "listType": "SHOP", "listName": "Shopping"},
                {"listId": "TODO-1", "listType": "TODO"},
                {"listId": "CUSTOM-1", "listType": "CUSTOM", "listName": "Garden"},
            ]
        }
    )

    await api._todo_handler.update_lists()

    assert api.todo_lists == [
        AmazonListInfo("SHOP-1", AmazonListType.SHOP, "Shopping"),
        AmazonListInfo("TODO-1", AmazonListType.TODO, None),
        AmazonListInfo("CUSTOM-1", AmazonListType.CUSTOM, "Garden"),
    ]
    session_request.assert_awaited_once_with(
        method=HTTPMethod.POST,
        url=_lists_url(api, "fetch", None),
        input_data={},
        json_data=True,
    )


@pytest.mark.anyio
async def test_get_list_items(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """Items are fetched with a limit, keyed by id, with capitalised names."""
    session_request = mock_json_response(
        {
            "itemInfoList": [
                {
                    "itemId": TEST_ITEM_ID,
                    "itemName": "milk",
                    "itemStatus": "ACTIVE",
                    "version": 3,
                },
                {
                    "itemId": "ITEM-2",
                    "itemName": "BREAD rolls",
                    "itemStatus": "COMPLETE",
                    "version": 1,
                },
            ]
        }
    )

    items = await api.get_todo_list_items(TEST_LIST_ID)

    assert items == {
        TEST_ITEM_ID: ITEM,
        "ITEM-2": AmazonListItem(
            id="ITEM-2",
            status=AmazonListItemStatus.COMPLETE,
            name="Bread rolls",
            version=1,
        ),
    }
    session_request.assert_awaited_once_with(
        method=HTTPMethod.POST,
        url=_lists_url(api, f"{TEST_LIST_ID}/items/fetch", {"limit": 100}),
        input_data={},
        json_data=True,
    )


@pytest.mark.anyio
async def test_get_list_items_without_items(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """A response with no item list returns no items."""
    mock_json_response({})

    assert await api.get_todo_list_items(TEST_LIST_ID) == {}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("api_call", "expected"),
    [
        pytest.param(
            _set_checked(True),
            (
                HTTPMethod.PUT,
                f"{TEST_LIST_ID}/items/{TEST_ITEM_ID}",
                {"version": 3},
                _item_status(AmazonListItemStatus.COMPLETE),
            ),
            id="check",
        ),
        pytest.param(
            _set_checked(False),
            (
                HTTPMethod.PUT,
                f"{TEST_LIST_ID}/items/{TEST_ITEM_ID}",
                {"version": 3},
                _item_status(AmazonListItemStatus.ACTIVE),
            ),
            id="uncheck",
        ),
        pytest.param(
            lambda api: api.add_todo_list_item(TEST_LIST_ID, "Eggs"),
            (
                HTTPMethod.POST,
                f"{TEST_LIST_ID}/items",
                None,
                {"items": [{"itemType": "KEYWORD", "itemName": "Eggs"}]},
            ),
            id="add",
        ),
        pytest.param(
            lambda api: api.delete_todo_list_item(TEST_LIST_ID, TEST_ITEM_ID, 3),
            (
                HTTPMethod.DELETE,
                f"{TEST_LIST_ID}/items/{TEST_ITEM_ID}",
                {"version": 3},
                {},
            ),
            id="delete",
        ),
        pytest.param(
            lambda api: api.rename_todo_list_item(
                TEST_LIST_ID, TEST_ITEM_ID, "Oat milk", 3
            ),
            (
                HTTPMethod.PUT,
                f"{TEST_LIST_ID}/items/{TEST_ITEM_ID}",
                {"version": 3},
                {
                    "itemAttributesToUpdate": [
                        {"type": "itemName", "value": "Oat milk"}
                    ],
                    "itemAttributesToRemove": [],
                },
            ),
            id="rename",
        ),
    ],
)
async def test_item_changes(
    api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    api_call: Callable[[AmazonEchoApi], Awaitable[None]],
    expected: tuple[HTTPMethod, str, dict[str, Any] | None, dict[str, Any]],
) -> None:
    """Each item change sends its own request to the lists API."""
    method, path, query, input_data = expected
    session_request = mock_json_response({})

    await api_call(api)

    session_request.assert_awaited_once_with(
        method=method,
        url=_lists_url(api, path, query),
        input_data=input_data,
        json_data=True,
    )


@pytest.mark.anyio
@pytest.mark.usefixtures("events")
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        pytest.param(
            {"listId": TEST_LIST_ID, "eventName": "itemCreated"},
            "Received malformed ItemChange payload",
            id="malformed",
        ),
        pytest.param(
            {
                "listId": TEST_LIST_ID,
                "listItemId": TEST_ITEM_ID,
                "eventName": "itemMoved",
            },
            "Received unsupported list event type: itemMoved",
            id="unsupported",
        ),
    ],
)
async def test_item_change_event_rejected(
    api: AmazonEchoApi,
    caplog: pytest.LogCaptureFixture,
    handler: AmazonToDoHandler,
    payload: dict[str, Any],
    message: str,
) -> None:
    """Malformed and unsupported list push events are logged and dropped."""
    await api._handle_item_change_event(payload)

    assert message in caplog.text
    assert not handler._changes
    assert not handler._timers


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("event_name", "expected"),
    [
        pytest.param(
            "itemCreated",
            (
                AmazonListEvent(
                    TEST_LIST_ID, "a", AmazonListEventType.CREATED, _item("a")
                ),
                [call(TEST_LIST_ID)],
            ),
            id="created",
        ),
        pytest.param(
            "itemUpdated",
            (
                AmazonListEvent(
                    TEST_LIST_ID, "a", AmazonListEventType.UPDATED, _item("a")
                ),
                [call(TEST_LIST_ID)],
            ),
            id="updated",
        ),
        pytest.param(
            "itemDeleted",
            (AmazonListEvent(TEST_LIST_ID, "a", AmazonListEventType.DELETED), []),
            id="deleted",
        ),
    ],
)
async def test_single_change_emits_event(
    api: AmazonEchoApi,
    events: list[AmazonListEvent],
    get_list_items: AsyncMock,
    event_name: str,
    expected: tuple[AmazonListEvent, list[Any]],
) -> None:
    """A change emits its event, with the item unless it was deleted."""
    expected_event, expected_fetches = expected

    await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", event_name))
    await _settle(api._todo_handler)

    assert events == [expected_event]
    assert get_list_items.await_args_list == expected_fetches


@pytest.mark.anyio
@pytest.mark.parametrize(
    "fetched",
    [
        pytest.param([_item("b")], id="deleted-item-gone"),
        pytest.param([_item("a"), _item("b")], id="deleted-item-still-fetched"),
    ],
)
async def test_deletion_batched_with_update(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    get_list_items: AsyncMock,
    fetched: list[AmazonListItem],
) -> None:
    """A deletion in a fetched batch is emitted without an item, even if stale."""
    get_list_items.return_value = fetched

    await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", "itemDeleted"))
    await api._handle_item_change_event(_payload(TEST_LIST_ID, "b", "itemUpdated"))
    await _settle(handler)

    get_list_items.assert_awaited_once_with(TEST_LIST_ID)
    assert events == [
        AmazonListEvent(TEST_LIST_ID, "a", AmazonListEventType.DELETED),
        AmazonListEvent(TEST_LIST_ID, "b", AmazonListEventType.UPDATED, _item("b")),
    ]


@pytest.mark.anyio
async def test_burst_of_changes_fetches_list_once(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    get_list_items: AsyncMock,
) -> None:
    """Changes within the debounce window share a single list fetch."""
    await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", "itemUpdated"))
    first_timer = handler._timers[TEST_LIST_ID]
    # This restarts the window, so the first change is not flushed on its own.
    await api._handle_item_change_event(_payload(TEST_LIST_ID, "b", "itemUpdated"))

    assert first_timer.cancelled()
    assert handler._timers[TEST_LIST_ID] is not first_timer
    assert handler._changes == {
        TEST_LIST_ID: {
            "a": AmazonListEventType.UPDATED,
            "b": AmazonListEventType.UPDATED,
        }
    }

    await _settle(handler)

    get_list_items.assert_awaited_once_with(TEST_LIST_ID)
    assert events == [
        AmazonListEvent(TEST_LIST_ID, "a", AmazonListEventType.UPDATED, _item("a")),
        AmazonListEvent(TEST_LIST_ID, "b", AmazonListEventType.UPDATED, _item("b")),
    ]
    assert not handler._tasks
    assert not handler._changes


@pytest.mark.anyio
async def test_lists_are_debounced_separately(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    get_list_items: AsyncMock,
) -> None:
    """Each list is fetched for its own changes."""
    await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", "itemCreated"))
    await api._handle_item_change_event(
        _payload(TEST_OTHER_LIST_ID, "a", "itemCreated")
    )
    await _settle(handler)

    assert sorted(call.args[0] for call in get_list_items.await_args_list) == [
        TEST_LIST_ID,
        TEST_OTHER_LIST_ID,
    ]
    assert sorted(event.list_id for event in events) == [
        TEST_LIST_ID,
        TEST_OTHER_LIST_ID,
    ]


@pytest.mark.anyio
async def test_batches_of_one_list_are_processed_in_order(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later batch waits for a slow earlier batch of the same list."""
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    fetched: list[str] = []

    async def get_list_items(_list_id: str) -> list[AmazonListItem]:
        if not fetched:
            fetched.append("first")
            first_started.set()
            await release_first.wait()
        else:
            fetched.append("second")
        return [_item("a"), _item("b")]

    monkeypatch.setattr(handler, "get_list_items", get_list_items)

    await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", "itemUpdated"))
    await first_started.wait()
    await api._handle_item_change_event(_payload(TEST_LIST_ID, "b", "itemUpdated"))
    await asyncio.sleep(DEBOUNCE_DELAY * 2)

    # The second batch is flushed but must not fetch before the first finishes.
    assert not handler._timers
    first_task, second_task = handler._tasks
    assert not first_task.done()
    assert not second_task.done()
    assert fetched == ["first"]

    release_first.set()
    await _settle(handler)

    assert fetched == ["first", "second"]
    assert [event.item_id for event in events] == ["a", "b"]


@pytest.mark.anyio
@pytest.mark.usefixtures("get_list_items")
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
    for event_name in event_names:
        await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", event_name))
    await _settle(handler)

    assert [(event.item_id, event.type) for event in events] == [("a", expected_type)]


@pytest.mark.anyio
async def test_only_deletions_skip_fetch(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    get_list_items: AsyncMock,
) -> None:
    """Deleted items need no list fetch."""
    await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", "itemDeleted"))
    await _settle(handler)

    get_list_items.assert_not_awaited()
    assert events == [AmazonListEvent(TEST_LIST_ID, "a", AmazonListEventType.DELETED)]


@pytest.mark.anyio
async def test_item_missing_from_fetch_is_deleted(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    get_list_items: AsyncMock,
) -> None:
    """An item removed again before the fetch is reported as deleted."""
    get_list_items.return_value = []

    await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", "itemCreated"))
    await _settle(handler)

    assert events == [AmazonListEvent(TEST_LIST_ID, "a", AmazonListEventType.DELETED)]


@pytest.mark.anyio
async def test_fetch_failure_is_logged(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    get_list_items: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed fetch emits nothing and does not block later changes."""
    get_list_items.side_effect = RuntimeError("boom")

    await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", "itemUpdated"))
    await _settle(handler)

    assert not events
    assert not handler._tasks
    assert f"Fetching todo list {TEST_LIST_ID} failed: boom" in caplog.text


@pytest.mark.anyio
@pytest.mark.usefixtures("events", "get_list_items")
async def test_failing_subscriber_does_not_drop_other_events(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A subscriber raising for one event still receives the rest of the batch."""
    on_list_event = AsyncMock(side_effect=[RuntimeError("boom"), None])
    monkeypatch.setattr(handler, "_on_list_event", on_list_event)

    await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", "itemDeleted"))
    await api._handle_item_change_event(_payload(TEST_LIST_ID, "b", "itemDeleted"))
    await _settle(handler)

    assert on_list_event.await_args_list == [
        call(AmazonListEvent(TEST_LIST_ID, "a", AmazonListEventType.DELETED)),
        call(AmazonListEvent(TEST_LIST_ID, "b", AmazonListEventType.DELETED)),
    ]
    assert (
        f"Emitting todo event for item a of list {TEST_LIST_ID} failed" in caplog.text
    )


@pytest.mark.anyio
async def test_changes_without_subscribers_skip_fetch(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    get_list_items: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without subscribers changes are not queued, so the list is not fetched."""
    monkeypatch.setattr(todo_module, "TODO_DEBOUNCE_DELAY", DEBOUNCE_DELAY)

    await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", "itemUpdated"))
    await _settle(handler)

    get_list_items.assert_not_awaited()
    assert not handler._changes


@pytest.mark.anyio
async def test_stop_http2_processing_cancels_pending_changes(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    get_list_items: AsyncMock,
) -> None:
    """Stopping drops changes still waiting for the debounce window."""
    await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", "itemUpdated"))
    timer = handler._timers[TEST_LIST_ID]

    await api.stop_http2_processing()

    assert timer.cancelled()
    assert not handler._timers
    assert not handler._changes
    get_list_items.assert_not_awaited()
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

    await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", "itemUpdated"))
    await started.wait()
    (task,) = handler._tasks

    await api.stop_http2_processing()

    assert task.cancelled()
    assert not handler._tasks
    assert not events


@pytest.mark.anyio
async def test_cancelled_stop_is_propagated(
    api: AmazonEchoApi,
    handler: AmazonToDoHandler,
    events: list[AmazonListEvent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling the stop itself is not swallowed while waiting for a fetch."""
    holding = asyncio.Event()

    async def get_list_items(_list_id: str) -> list[AmazonListItem]:
        """Simulate a fetch that never finishes and ignores being cancelled."""
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Swallow the stop's cancel, so the stop is left waiting.
            holding.set()
            await asyncio.Event().wait()
        return []

    monkeypatch.setattr(handler, "get_list_items", get_list_items)

    await api._handle_item_change_event(_payload(TEST_LIST_ID, "a", "itemUpdated"))
    await asyncio.sleep(DEBOUNCE_DELAY * 2)
    (task,) = handler._tasks
    stop = asyncio.create_task(api.stop_http2_processing())
    await holding.wait()

    stop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stop

    # Cancel the fetch again, so it does not outlive the test.
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not events
