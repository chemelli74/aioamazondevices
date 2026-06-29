"""Communication module for Amazon devices."""

from http import HTTPMethod

from yarl import URL

from aioamazondevices.const.devices import DEVICE_TYPE_AQM, SPEAKER_GROUP_FAMILY
from aioamazondevices.const.http import COMM_SITE, URI_COMM_PREFERENCES
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonDevice, AmazonDropInStatus
from aioamazondevices.utils import _LOGGER


class AlexaCommunicationsHandler:
    """Class to handle Alexa communications."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize AlexaCommunicationsHandler class."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper
        self._communication_site = URL(COMM_SITE)
        self._communication_preferences: dict[str, dict[str, str]] = {}

    async def _set_communications_state(
        self, preference: str, device: AmazonDevice, state: str
    ) -> None:
        payload = {"state": state}
        url = URL.joinpath(
            self._communication_site,
            URI_COMM_PREFERENCES.format(
                device_type=device.device_type,
                serial_number=device.serial_number,
            ),
            preference,
        )
        await self._http_wrapper.session_request(
            method=HTTPMethod.PATCH, url=url, input_data=payload, json_data=True
        )

    async def set_communication_status(self, device: AmazonDevice, state: bool) -> None:
        """Enable / disable communications for device."""
        await self._set_communications_state(
            "communications", device, "ON" if state else "OFF"
        )

    async def set_announcement_status(self, device: AmazonDevice, state: bool) -> None:
        """Enable / disable announcements for device."""
        await self._set_communications_state(
            "announcements", device, "ON" if state else "OFF"
        )

    async def set_dropin_status(
        self, device: AmazonDevice, state: AmazonDropInStatus
    ) -> None:
        """Set allowed dropin state for device."""
        await self._set_communications_state("dropin", device, state.value)

    async def get_communication_preferences(
        self, devices: list[AmazonDevice]
    ) -> dict[str, dict[str, str]]:
        """Get communication preferences for a device."""
        failed_updates: list[str] = []
        for device in devices:
            if (
                device.device_family == SPEAKER_GROUP_FAMILY
                or device.device_type == DEVICE_TYPE_AQM
            ):
                # avoid unnecessary call for devices that don't support communications
                continue

            query_string = {
                "devicePreferences": [
                    "communications",
                    "dropin",
                    "announcements",
                ]
            }
            url = URL.joinpath(
                self._communication_site,
                URI_COMM_PREFERENCES.format(
                    device_type=device.device_type,
                    serial_number=device.serial_number,
                ),
            )
            url = url.with_query(query_string)
            try:
                _, resp = await self._http_wrapper.session_request(
                    method=HTTPMethod.GET, url=url
                )
            except CannotRetrieveData:
                failed_updates.append(device.account_name)
                continue
            resp_json = await self._http_wrapper.response_to_json(
                resp, "devicesTypes(preferences)"
            )

            device_communication_preferences: dict[str, str] = {}
            for device_permissions_pref in resp_json.get(
                "devicePermissionsPreferences", {}
            ):
                device_pref = device_permissions_pref["devicePreference"]
                pref_state = device_permissions_pref.get("state")
                pref_allowed = device_permissions_pref.get("allowed")

                if pref_allowed is True:
                    device_communication_preferences[device_pref] = pref_state

            self._communication_preferences[device.serial_number] = (
                device_communication_preferences
            )

        if failed_updates:
            _LOGGER.warning(
                "Failed to refresh communications settings for [%s], will use cached values.",  # noqa: E501
                ", ".join(failed_updates),
            )
        return self._communication_preferences
