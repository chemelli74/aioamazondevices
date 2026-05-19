"""Todo list module for Amazon devices."""

from http import HTTPMethod

from aioamazondevices.const.http import URI_TODO
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import ListInfo, ListItem, ListItemStatus, ListType


def is_item_complete(list_item: ListItem) -> bool:
    """Check if a list item is complete.

    Args:
        list_item: The list item to check.

    Returns:
        True if the list item is complete, False otherwise.

    """
    return list_item.status == ListItemStatus.COMPLETE


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

    async def get_lists(self) -> list[ListInfo]:
        """Fetch all available Alexa shopping lists.

        Returns:
            A list of shopping list information objects.

        Raises:
            Exception: If the API request fails.

        """
        _, raw_resp = await self._http_wrapper.session_request(
            HTTPMethod.POST,
            f"{self._base_url}{URI_TODO}/fetch",
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
                name=list_info["listName"]
                if list_info["listType"] == ListType.CUSTOM
                else list_info["listType"].capitalize(),
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
            A list of list items.

        """
        _, raw_resp = await self._http_wrapper.session_request(
            HTTPMethod.POST,
            f"{self._base_url}{URI_TODO}/{list_id}/items/fetch?limit={limit}",
            input_data={},
            json_data=True,
        )

        response_json = await self._http_wrapper.response_to_json(raw_resp)

        item_info_list = response_json.get("itemInfoList", [])

        return [
            ListItem(
                id=item_info["itemId"],
                name=(item_info["itemName"][0].upper() + item_info["itemName"][1:])
                if item_info["itemName"]
                else "",
                status=ListItemStatus(item_info["itemStatus"]),
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
        await self._http_wrapper.session_request(
            HTTPMethod.PUT,
            f"{self._base_url}{URI_TODO}/{list_id}/items/{item_id}?version={version}",
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
            f"{self._base_url}{URI_TODO}/{list_id}/items",
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
            f"{self._base_url}{URI_TODO}/{list_id}/items/{item_id}?version={version}",
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
            f"{self._base_url}{URI_TODO}/{list_id}/items/{item_id}?version={version}",
            input_data={
                "itemAttributesToUpdate": [{"type": "itemName", "value": new_name}],
                "itemAttributesToRemove": [],
            },
            json_data=True,
        )

    async def update_lists(self) -> None:
        """Update the lists."""
        self.lists = await self.get_lists()

    async def sync_all_items(self, list_id: str | None = None) -> None:
        """Update all items of all lists or a single list."""
        list_ids = (
            [list_info.id for list_info in self.lists] if list_id is None else [list_id]
        )

        for current_list_id in list_ids:
            self.all_items[current_list_id] = await self.get_list_items(current_list_id)
