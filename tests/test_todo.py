# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Amazon todo list handler."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from aioamazondevices.implementation.todo import AmazonToDoHandler
from aioamazondevices.structures import AmazonListItemStatus


def _make_handler(item_names: list[str]) -> AmazonToDoHandler:
    """Build a handler whose items fetch returns the given item names."""
    http_wrapper = MagicMock()
    http_wrapper.response_to_json = AsyncMock(
        return_value={
            "itemInfoList": [
                {
                    "itemId": f"id-{index}",
                    "itemName": name,
                    "itemStatus": "ACTIVE",
                    "version": 1,
                }
                for index, name in enumerate(item_names)
            ]
        }
    )
    handler = AmazonToDoHandler(http_wrapper, MagicMock())
    handler._call_lists_api = AsyncMock()  # type: ignore[method-assign]
    return handler


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("stored_name", "expected_name"),
    [
        pytest.param("milk", "Milk", id="first-letter-is-capitalized"),
        pytest.param("Riz Tang Frère", "Riz Tang Frère", id="inner-capitals-kept"),
        pytest.param(
            "@boissons@ Café grains",
            "@boissons@ Café grains",
            id="text-after-prefix-keeps-its-case",
        ),
        pytest.param("", "", id="empty-name-unchanged"),
    ],
)
async def test_get_list_items_only_capitalizes_first_character(
    stored_name: str, expected_name: str
) -> None:
    """The first character is capitalized and the rest is left untouched."""
    handler = _make_handler([stored_name])

    items = await handler.get_list_items("list-id")

    assert [item.name for item in items] == [expected_name]
    assert items[0].status == AmazonListItemStatus.ACTIVE
