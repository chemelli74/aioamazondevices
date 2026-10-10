# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the to-do list handler."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.implementation import todo as todo_module
from aioamazondevices.structures import AmazonListItemStatus

PAGE = 100
TOTAL = 268


def _items(start: int, count: int) -> list[dict[str, Any]]:
    return [
        {
            "itemId": f"id-{n}",
            "itemName": f"item {n}",
            "itemStatus": "ACTIVE" if n % 3 else "COMPLETE",
            "version": 1,
        }
        for n in range(start, start + count)
    ]


def _wire(api: AmazonEchoApi, pages: list[dict[str, Any]]) -> AsyncMock:
    handler = api._todo_handler
    call = AsyncMock(return_value=object())
    handler._call_lists_api = call  # type: ignore[method-assign]
    handler._http_wrapper.response_to_json = AsyncMock(  # type: ignore[method-assign]
        side_effect=pages
    )
    return call


@pytest.mark.anyio
async def test_get_list_items_single_page(api: AmazonEchoApi) -> None:
    """A list below the page size is read with one call."""
    pages = [{"itemInfoList": _items(0, 5)}]
    call = _wire(api, pages)

    items = await api.get_todo_list_items("list")

    assert len(items) == len(pages[0]["itemInfoList"])
    assert call.await_count == len(pages)
    first = call.await_args_list[0].kwargs
    assert first["query"] == {"limit": PAGE}
    assert first["input_data"] == {}


@pytest.mark.anyio
async def test_get_list_items_follows_next_token(api: AmazonEchoApi) -> None:
    """All pages are read until no nextToken is returned (268 items)."""
    pages: list[dict[str, Any]] = [
        {"itemInfoList": _items(0, PAGE), "nextToken": "t1"},
        {"itemInfoList": _items(PAGE, PAGE), "nextToken": "t2"},
        {"itemInfoList": _items(2 * PAGE, TOTAL - 2 * PAGE), "nextToken": None},
    ]
    call = _wire(api, pages)

    items = await api.get_todo_list_items("list")

    assert len(items) == TOTAL
    assert call.await_count == len(pages)
    second = call.await_args_list[1].kwargs
    assert second["query"] == {"limit": PAGE, "nextToken": "t1"}
    assert second["input_data"] == {"nextToken": "t1"}
    assert items["id-0"].status == AmazonListItemStatus.COMPLETE
    assert items["id-1"].name == "Item 1"


@pytest.mark.anyio
async def test_get_list_items_stops_on_repeated_token(api: AmazonEchoApi) -> None:
    """A repeated token or an empty page ends the loop, duplicates collapse."""
    pages = [
        {"itemInfoList": _items(0, PAGE), "nextToken": "t1"},
        {"itemInfoList": _items(PAGE // 2, PAGE), "nextToken": "t1"},
    ]
    call = _wire(api, pages)

    items = await api.get_todo_list_items("list")

    assert len(items) == PAGE + PAGE // 2
    assert call.await_count == len(pages)


@pytest.mark.anyio
async def test_get_list_items_page_limit(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Endless tokens stop after MAX_LIST_PAGES calls."""
    max_pages, size = 3, 10
    monkeypatch.setattr(todo_module, "MAX_LIST_PAGES", max_pages)
    pages = [
        {"itemInfoList": _items(n * size, size), "nextToken": f"t{n}"}
        for n in range(max_pages + 2)
    ]
    call = _wire(api, pages)

    items = await api.get_todo_list_items("list")

    assert len(items) == max_pages * size
    assert call.await_count == max_pages
