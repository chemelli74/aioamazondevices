"""Todo list module for Amazon devices."""

from http import HTTPMethod
from typing import Any

from aiohttp import ClientResponse
from yarl import URL

from aioamazondevices.const.http import URI_TODO
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import (
    AmazonListInfo,
    AmazonListItem,
    AmazonListItemStatus,
    AmazonListType,
)


class AmazonToDoHandler:
    """Class to handle Amazon sensor functionality."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize AmazonToDoHandler class."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper

        self._lists: list[AmazonListInfo] = []

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
        url = URL.joinpath(self._session_state_data.www_url, URI_TODO, path)
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
            raw_resp, "listInfoList"
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

        response_json = await self._http_wrapper.response_to_json(raw_resp)

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
