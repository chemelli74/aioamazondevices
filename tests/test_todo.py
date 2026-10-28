# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Alexa lists handler and the API calls that use it."""

from collections.abc import Awaitable, Callable
from http import HTTPMethod
from typing import Any
from unittest.mock import AsyncMock

import pytest
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import URI_TODO_BASE
from aioamazondevices.structures import (
    AmazonListEvent,
    AmazonListEventType,
    AmazonListInfo,
    AmazonListItem,
    AmazonListItemStatus,
    AmazonListType,
)

TEST_LIST_ID = "LIST-1"
TEST_ITEM_ID = "ITEM-1"

ITEM = AmazonListItem(
    id=TEST_ITEM_ID, status=AmazonListItemStatus.ACTIVE, name="Milk", version=3
)


def _lists_url(api: AmazonEchoApi, path: str, query: dict[str, Any] | None) -> URL:
    """Return the lists API URL for the path and query."""
    return URL.joinpath(
        api._session_state_data.retail_site_url, URI_TODO_BASE, path
    ).with_query(query)


@pytest.fixture
def on_todo_event(api: AmazonEchoApi) -> AsyncMock:
    """Subscribe to list events and return the subscriber mock."""
    on_todo_event = AsyncMock()
    api.on_todo_event.append(on_todo_event)
    api.on_todo_event.freeze()
    return on_todo_event


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
@pytest.mark.parametrize(
    ("event_type", "fetches_item"),
    [
        pytest.param(AmazonListEventType.CREATED, True, id="created"),
        pytest.param(AmazonListEventType.UPDATED, True, id="updated"),
        pytest.param(AmazonListEventType.DELETED, False, id="deleted"),
    ],
)
async def test_item_change_event_emits_list_event(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
    on_todo_event: AsyncMock,
    event_type: AmazonListEventType,
    fetches_item: bool,
) -> None:
    """A list push event emits the change, with the item unless it was deleted."""
    get_list_items = AsyncMock(return_value=[ITEM])
    monkeypatch.setattr(api._todo_handler, "get_list_items", get_list_items)

    await api._handle_item_change_event(
        {
            "listId": TEST_LIST_ID,
            "listItemId": TEST_ITEM_ID,
            "eventName": event_type.value,
        }
    )

    on_todo_event.assert_awaited_once_with(
        AmazonListEvent(
            TEST_LIST_ID, TEST_ITEM_ID, event_type, items=ITEM if fetches_item else None
        )
    )
    assert get_list_items.await_args_list == (
        [((TEST_LIST_ID,),)] if fetches_item else []
    )


@pytest.mark.anyio
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
    on_todo_event: AsyncMock,
    payload: dict[str, Any],
    message: str,
) -> None:
    """Malformed and unsupported list push events are logged and dropped."""
    await api._handle_item_change_event(payload)

    assert message in caplog.text
    on_todo_event.assert_not_awaited()
