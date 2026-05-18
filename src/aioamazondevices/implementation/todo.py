"""Todo list module for Amazon devices."""

from http import HTTPMethod

from aioamazondevices.const.http import URI_LISTS
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import ListInfo, ListItem, ListItemStatus, ListType


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

        self.lists: list[ListInfo] = []
        self.all_items: dict[str, list[ListItem]] = {}
        self.all_items_lookup: dict[str, dict[str, ListItem]] = {}

    async def get_lists(self) -> list[ListInfo]:
        """Fetch all available Alexa shopping lists.

        Returns:
            A list of shopping list information objects.

        Raises:
            Exception: If the API request fails.

        """
        _, raw_resp = await self._http_wrapper.session_request(
            HTTPMethod.POST,
            f"{self._base_url}{URI_LISTS}/fetch",
            input_data={},
            json_data=True,
        )

        response_json = await self._http_wrapper.response_to_json(
            raw_resp, "listInfoList"
        )
        list_info_list = response_json["listInfoList"]

        return [
            ListInfo(
                id=list_info["listId"],
                list_type=ListType(list_info["listType"]),
                custom_list_name=list_info.get("listName"),
            )
            for list_info in list_info_list
        ]

    async def get_list_items(self, list_id: str, limit: int = 100) -> list[ListItem]:
        """Fetch all items from a specified Alexa shopping list.

        Args:
            list_id: The ID of the list to fetch items from.
            limit: The number of items to fetch in each batch.
                   Defaults to 100 which is the maximum allowed by the API.

        Returns:
            A list of shopping list items.

        """
        list_items, _ = await self.get_list_items_check_has_more(list_id, limit)
        return list_items

    async def get_list_items_check_has_more(
        self, list_id: str, limit: int = 100
    ) -> tuple[list[ListItem], bool]:
        """Fetch all items from a specified Alexa shopping list.

        Args:
            list_id: The ID of the list to fetch items from.
            limit: The number of items to fetch in each batch.
                   Defaults to 100 which is the maximum allowed by the API.

        Returns:
            A tuple of the list of shopping list items and a boolean indicating
            whether there are more items.

        """
        _, raw_resp = await self._http_wrapper.session_request(
            HTTPMethod.POST,
            f"{self._base_url}{URI_LISTS}/{list_id}/items/fetch?limit={limit}",
            input_data={},
            json_data=True,
        )

        response_json = await self._http_wrapper.response_to_json(raw_resp)

        item_info_list = response_json.get("itemInfoList", [])

        list_items = [
            ListItem(
                id=item_info["itemId"],
                original_name=item_info["itemName"],
                status=ListItemStatus(item_info["itemStatus"]),
                version=item_info["version"],
            )
            for item_info in item_info_list
        ]

        return list_items, response_json.get("nextToken") is not None

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
        await self._http_wrapper.session_request(
            HTTPMethod.PUT,
            f"{self._base_url}{URI_LISTS}/{list_id}/items/{item_id}?version={version}",
            input_data={
                "itemAttributesToUpdate": [
                    {
                        "type": "itemStatus",
                        "value": ListItemStatus.COMPLETE.value
                        if checked
                        else ListItemStatus.ACTIVE.value,
                    }
                ],
                "itemAttributesToRemove": [],
            },
            json_data=True,
        )

    async def add_item(self, list_id: str, name: str) -> None:
        """Add a new item to a shopping list.

        Args:
            list_id: The ID of the list to add the item to.
            name: The name of the item to add.

        """
        await self._http_wrapper.session_request(
            HTTPMethod.POST,
            f"{self._base_url}{URI_LISTS}/{list_id}/items",
            input_data={
                "items": [
                    {
                        "itemType": "KEYWORD",
                        "itemName": name,
                    }
                ]
            },
            json_data=True,
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
        await self._http_wrapper.session_request(
            HTTPMethod.DELETE,
            f"{self._base_url}{URI_LISTS}/{list_id}/items/{item_id}?version={version}",
            input_data={},
            json_data=True,
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
        await self._http_wrapper.session_request(
            HTTPMethod.PUT,
            f"{self._base_url}{URI_LISTS}/{list_id}/items/{item_id}?version={version}",
            input_data={
                "itemAttributesToUpdate": [{"type": "itemName", "value": new_name}],
                "itemAttributesToRemove": [],
            },
            json_data=True,
        )

    async def update_lists(self) -> None:
        """Update the lists."""
        self.lists = await self.get_lists()

    async def update_all_items(self, list_id: str | None = None) -> None:
        """Update all items of all lists or a single list."""
        list_ids = (
            [list_info.id for list_info in self.lists] if list_id is None else [list_id]
        )

        for current_list_id in list_ids:
            self.all_items[current_list_id] = await self.get_list_items(current_list_id)
            self.all_items_lookup[current_list_id] = {
                item.id: item for item in self.all_items[current_list_id]
            }
