"""Communication module for Amazon devices."""

from http import HTTPMethod

from yarl import URL

from aioamazondevices.const.http import COMM_SITE, URI_COMM_PREFERENCES
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonDevice, AmazonDropInStatus


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

    async def _set_communications_state(
        self, preference: str, device: AmazonDevice, state: str
    ) -> None:
        payload = {"state": state}
        url = URL.joinpath(
            COMM_SITE,
            URI_COMM_PREFERENCES.format(
                device_type=device.device_type,
                serial_number=device.serial_number,
            ),
            preference,
        )
        await self._http_wrapper.session_request(
            method=HTTPMethod.PATCH, url=url, input_data=payload, json_data=True
        )

    async def set_communications_enablement(
        self, device: AmazonDevice, state: bool
    ) -> None:
        """Enable / disable communications for device."""
        await self._set_communications_state(
            "communications", device, "ON" if state else "OFF"
        )

    async def set_announcements_enablement(
        self, device: AmazonDevice, state: bool
    ) -> None:
        """Enable / disable announcements for device."""
        await self._set_communications_state(
            "announcements", device, "ON" if state else "OFF"
        )

    async def set_dropin_enablement(
        self, device: AmazonDevice, state: AmazonDropInStatus
    ) -> None:
        """Set allowed dropin state for device."""
        await self._set_communications_state("dropin", device, state.value)

    async def get_communication_preferences(
        self, devices: list[AmazonDevice]
    ) -> dict[str, dict[str, str]]:
        """Get communication preferences for a device."""
        communication_preferences = {}
        for device in devices:
            query_string = {
                "devicePreferences": [
                    "communications",
                    "calling",
                    "messaging",
                    "dropin",
                    "announcements",
                ]
            }
            url = URL.joinpath(
                COMM_SITE,
                URI_COMM_PREFERENCES.format(
                    device_type=device.device_type,
                    serial_number=device.serial_number,
                ),
            )
            url = url.with_query(query_string)
            _, resp = await self._http_wrapper.session_request(
                method=HTTPMethod.GET, url=url
            )
            resp_json = await self._http_wrapper.response_to_json(resp)

            comms_preferences = {}
            for device_prefs in resp_json.get("devicePermissionsPreferences", {}):
                comms_preferences[device_prefs.get("devicePreference")] = (
                    device_prefs.get("state")
                )

            communication_preferences[device.serial_number] = comms_preferences

        return communication_preferences
