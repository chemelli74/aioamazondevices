"""Todo list module for Amazon devices."""

from http import HTTPMethod
from typing import Any

from aiohttp import ClientResponse

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

        self._base_url = f"https://www.amazon.{self._session_state_data.domain}"

        self._lists: list[AmazonListInfo] = []

    @property
    def lists(self) -> list[AmazonListInfo]:
        """Return the cached list of ListInfo objects."""
        return self._lists

    async def _call_lists_api(
        self, method: HTTPMethod, url: str, input_data: dict[str, Any] | None = None
    ) -> ClientResponse:
        """Call the Alexa lists API.

        Args:
            url: The relative URL for the API call.
            method: The HTTP method to use.
            input_data: Optional dictionary containing input data for the request.
                        Defaults to an empty dictionary if not provided, as required
                        by the Amazon API.

        Returns:
            The raw response from the API.

        """
        _, raw_response = await self._http_wrapper.session_request(
            method,
            f"{self._base_url}{URI_TODO}/{url}",
            input_data=input_data or {},  # API doesn't allow 'None'
            json_data=True,
        )

        return raw_response

    async def update_lists(self) -> None:
        """Fetch all available Alexa shopping lists and stores it.

        Raises:
            Exception: If the API request fails.

        """
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
        """Fetch all items from a specified Alexa shopping list.

        Args:
            list_id: The ID of the list to fetch items from.
            limit: The number of items to fetch in each batch.
                   Defaults to 100 which is the maximum allowed by the API.

        Returns:
            A list of list items.

        """
        raw_resp = await self._call_lists_api(
            HTTPMethod.POST, f"{list_id}/items/fetch?limit={limit}"
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
        """Update the checked status of an item in a shopping list.

        Args:
            list_id: The ID of the list containing the item.
            item_id: The ID of the item to update.
            checked: True to mark as complete, False to mark as active.
            version: The current version of the item.
                     The value is included in the get_list_items response and is
                     required by the Amazon API.

        """
        await self._call_lists_api(
            HTTPMethod.PUT,
            f"{list_id}/items/{item_id}?version={version}",
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
        """Add a new item to a shopping list.

        Args:
            list_id: The ID of the list to add the item to.
            name: The name of the item to add.

        """
        await self._call_lists_api(
            HTTPMethod.POST,
            f"{list_id}/items",
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
        """Delete an item from a shopping list.

        Args:
            list_id: The ID of the list containing the item.
            item_id: The ID of the item to delete.
            version: The current version of the item.
                     The value is included in the get_list_items response and is
                     required by the Amazon API.

        """
        await self._call_lists_api(
            HTTPMethod.DELETE, f"{list_id}/items/{item_id}?version={version}"
        )

    async def rename_item(
        self, list_id: str, item_id: str, new_name: str, version: int
    ) -> None:
        """Rename an item in a shopping list.

        Args:
            list_id: The ID of the list containing the item.
            item_id: The ID of the item to rename.
            new_name: The new name for the item.
            version: The current version of the item.
                     The value is included in the get_list_items response and is
                     required by the Amazon API.

        """
        await self._call_lists_api(
            HTTPMethod.PUT,
            f"{list_id}/items/{item_id}?version={version}",
            input_data={
                "itemAttributesToUpdate": [{"type": "itemName", "value": new_name}],
                "itemAttributesToRemove": [],
            },
        )
