# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Do not disturb module for Amazon devices."""

from http import HTTPMethod

from yarl import URL

from aioamazondevices.const.http import URI_DND_STATUS_ALL, URI_DND_STATUS_DEVICE
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonDevice


class AmazonDnDHandler:
    """Class to handle Alexa Do Not Disturb functionality."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize AmazonDnDHandler class."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper
        self._dnd_states: dict[str, bool] = {}

    @property
    def dnd_states(self) -> dict[str, bool]:
        """Return do_not_disturb states."""
        return self._dnd_states

    def update_cached_dnd_state(self, serial: str, enabled: bool) -> None:
        """Update the cached do_not_disturb state for a device."""
        self._dnd_states[serial] = enabled

    async def sync_do_not_disturb_status(self) -> None:
        """Sync do_not_disturb status for all devices."""
        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.GET,
            url=URL.joinpath(
                self._session_state_data.alexa_website_url, URI_DND_STATUS_ALL
            ),
        )

        dnd_data = await self._http_wrapper.response_to_json(raw_resp, "dnd")

        for dnd in dnd_data.get("doNotDisturbDeviceStatusList", {}):
            self._dnd_states[dnd.get("deviceSerialNumber")] = dnd.get("enabled")

    async def set_do_not_disturb(self, device: AmazonDevice, enable: bool) -> None:
        """Set do_not_disturb flag."""
        payload = {
            "deviceSerialNumber": device.serial_number,
            "deviceType": device.device_type,
            "enabled": enable,
        }
        await self._http_wrapper.session_request(
            method=HTTPMethod.PUT,
            url=URL.joinpath(
                self._session_state_data.alexa_website_url, URI_DND_STATUS_DEVICE
            ),
            input_data=payload,
            json_data=True,
        )
