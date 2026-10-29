# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Todo list module for Amazon devices."""

import asyncio
from collections.abc import Callable, Coroutine
from http import HTTPMethod
from typing import Any

from aiohttp import ClientResponse
from yarl import URL

from aioamazondevices.const.http import URI_TODO_BASE
from aioamazondevices.const.metadata import TODO_DEBOUNCE_DELAY
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import (
    AmazonListEvent,
    AmazonListEventType,
    AmazonListInfo,
    AmazonListItem,
    AmazonListItemStatus,
    AmazonListType,
)
from aioamazondevices.utils import _LOGGER


class AmazonToDoHandler:
    """Class to handle Amazon sensor functionality."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
        *,
        on_list_event: Callable[[AmazonListEvent], Coroutine[Any, Any, None]],
    ) -> None:
        """Initialize AmazonToDoHandler class."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper
        self._on_list_event = on_list_event

        self._lists: list[AmazonListInfo] = []
        # debounced item changes, keyed by list id then item id
        self._changes: dict[str, dict[str, AmazonListEventType]] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def lists(self) -> list[AmazonListInfo]:
        """Return the cached list of ListInfo objects."""
        return self._lists

    async def _call_lists_api(
        self,
        method: HTTPMethod,
        path: str,
        query: dict[str, Any] | None = None,
        input_data: dict[str, Any] | None = None,
    ) -> ClientResponse:
        """Call the Alexa lists API."""
        url = URL.joinpath(
            self._session_state_data.retail_site_url, URI_TODO_BASE, path
        )
        url = url.with_query(query)
        _, raw_response = await self._http_wrapper.session_request(
            method=method,
            url=url,
            input_data=input_data or {},  # API doesn't allow 'None'
            json_data=True,
        )

        return raw_response

    async def update_lists(self) -> None:
        """Fetch all available Alexa shopping lists and stores it."""
        raw_resp = await self._call_lists_api(HTTPMethod.POST, "fetch")
        response_json = await self._http_wrapper.response_to_json(
            raw_resp, "(todo)fetch"
        )
        list_info_list = response_json["listInfoList"]

        self._lists = [
            AmazonListInfo(
                id=list_info["listId"],
                list_type=AmazonListType(list_info["listType"]),
                name=list_info.get("listName", None),
            )
            for list_info in list_info_list
        ]

    async def get_list_items(
        self, list_id: str, limit: int = 100
    ) -> list[AmazonListItem]:
        """Fetch all items from a specified Alexa shopping list."""
        raw_resp = await self._call_lists_api(
            method=HTTPMethod.POST,
            path=f"{list_id}/items/fetch",
            query={"limit": limit},
        )

        response_json = await self._http_wrapper.response_to_json(
            raw_resp, "(todo)ItemsFetch"
        )

        item_info_list = response_json.get("itemInfoList", [])

        return [
            AmazonListItem(
                id=item_info["itemId"],
                name=(item_info["itemName"]).capitalize(),
                status=AmazonListItemStatus(item_info["itemStatus"]),
                version=item_info["version"],
            )
            for item_info in item_info_list
        ]

    def queue_item_change(
        self, list_id: str, item_id: str, event_type: AmazonListEventType
    ) -> None:
        """Queue an item change, to be emitted once the list changes settle."""
        changes = self._changes.setdefault(list_id, {})
        # an item created within the debounce window is still new to subscribers
        if not (
            event_type == AmazonListEventType.UPDATED
            and changes.get(item_id) == AmazonListEventType.CREATED
        ):
            changes[item_id] = event_type

        # every change restarts the debounce window
        if timer := self._timers.get(list_id):
            timer.cancel()
        self._timers[list_id] = asyncio.get_running_loop().call_later(
            TODO_DEBOUNCE_DELAY, self._flush_changes, list_id
        )

    def _flush_changes(self, list_id: str) -> None:
        """Process the settled changes of a list in the background."""
        # changes arriving from now on start a new debounce window
        del self._timers[list_id]
        changes = self._changes.pop(list_id)

        task = asyncio.create_task(
            self._process_changes(list_id, changes),
            name=f"aioamazondevices_todo_{list_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process_changes(
        self, list_id: str, changes: dict[str, AmazonListEventType]
    ) -> None:
        """Fetch a list once for its settled changes, then emit them."""
        list_items: dict[str, AmazonListItem] = {}
        if any(
            event_type != AmazonListEventType.DELETED for event_type in changes.values()
        ):
            try:
                list_items = {
                    item.id: item for item in await self.get_list_items(list_id)
                }
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Fetching todo list %s failed: %s", list_id, err)
                return

        for item_id, event_type in changes.items():
            # an item removed again before the fetch is reported as deleted
            items = list_items.get(item_id)
            # a failing subscriber must not drop the remaining events
            try:
                await self._on_list_event(
                    AmazonListEvent(
                        list_id,
                        item_id,
                        AmazonListEventType.DELETED if items is None else event_type,
                        items=items,
                    )
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "Emitting todo event for item %s of list %s failed",
                    item_id,
                    list_id,
                )

    async def cancel_pending(self) -> None:
        """Drop queued changes and cancel any fetch in progress."""
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()
        self._changes.clear()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                if (t := asyncio.current_task()) and t.cancelling():
                    raise

    async def set_item_checked_status(
        self, list_id: str, item_id: str, checked: bool, version: int
    ) -> None:
        """Update the checked status of an item in a shopping list."""
        await self._call_lists_api(
            method=HTTPMethod.PUT,
            path=f"{list_id}/items/{item_id}",
            query={"version": version},
            input_data={
                "itemAttributesToUpdate": [
                    {
                        "type": "itemStatus",
                        "value": AmazonListItemStatus.COMPLETE.value
                        if checked
                        else AmazonListItemStatus.ACTIVE.value,
                    }
                ],
                "itemAttributesToRemove": [],
            },
        )

    async def add_item(self, list_id: str, name: str) -> None:
        """Add a new item to a shopping list."""
        await self._call_lists_api(
            method=HTTPMethod.POST,
            path=f"{list_id}/items",
            input_data={
                "items": [
                    {
                        "itemType": "KEYWORD",
                        "itemName": name,
                    }
                ]
            },
        )

    async def delete_item(self, list_id: str, item_id: str, version: int) -> None:
        """Delete an item from a shopping list."""
        await self._call_lists_api(
            method=HTTPMethod.DELETE,
            path=f"{list_id}/items/{item_id}",
            query={"version": version},
        )

    async def rename_item(
        self, list_id: str, item_id: str, new_name: str, version: int
    ) -> None:
        """Rename an item in a shopping list."""
        await self._call_lists_api(
            method=HTTPMethod.PUT,
            path=f"{list_id}/items/{item_id}",
            query={"version": version},
            input_data={
                "itemAttributesToUpdate": [{"type": "itemName", "value": new_name}],
                "itemAttributesToRemove": [],
            },
        )
