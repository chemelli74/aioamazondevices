"""Communication module for Amazon devices."""

from http import HTTPMethod

from aioamazondevices.const.http import COMM_SITE
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonDevice


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
        url = f"https://{COMM_SITE}/devicesTypes/{device.device_type}/deviceId/{device.serial_number}/preferences/${preference}"
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

    async def set_dropin_enablement(self, device: AmazonDevice, state: str) -> None:
        """Set allowed dropin state for device.

        State values are All, Home and Off
        """
        await self._set_communications_state("dropin", device, state)

    async def get_communication_preferences(
        self, devices: list[AmazonDevice]
    ) -> dict[str, dict[str, str]]:
        """Get communication preferences for a device."""
        communication_preferences = {}
        for device in devices:
            url = f"https://{COMM_SITE}/devicesTypes/{device.device_type}/deviceId/{device.serial_number}/preferences?devicePreferences=communications&devicePreferences=calling&devicePreferences=messaging&devicePreferences=dropin&devicePreferences=announcements"
            _, resp = await self._http_wrapper.session_request(
                method=HTTPMethod.GET, url=url
            )
            resp_json = await self._http_wrapper.response_to_json(resp)

            comms_preferences = {}
            for device_prefs in resp_json.get("devicePermissionsPreferences", {}):
                comms_preferences[device_prefs.get("devicePreference")] = (
                    device_prefs.get("state", "n/a")
                )

            communication_preferences[device.serial_number] = comms_preferences

        return communication_preferences
