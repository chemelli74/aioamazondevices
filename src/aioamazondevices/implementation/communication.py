# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Communication module for Amazon devices."""

from http import HTTPMethod

from yarl import URL

from aioamazondevices.const.http import (
    COMM_SITE,
    URI_COMM_IDENTITY,
    URI_COMM_PREFERENCES,
    URI_HOMEGROUP_DEVICES,
)
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
        self._homegroup_id: str | None = None

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

    async def get_communication_preferences(self) -> dict[str, dict[str, str]]:
        """Get communication preferences for a device."""
        if not self._homegroup_id:
            self._homegroup_id = await self.get_homegroup_id()
        url = URL.joinpath(
            self._communication_site,
            URI_HOMEGROUP_DEVICES.format(homegroup_id=self._homegroup_id),
        )
        _, resp = await self._http_wrapper.session_request(
            method=HTTPMethod.GET, url=url
        )
        resp_json = await self._http_wrapper.response_to_json(resp, "homegroup-devices")
        for hg_dev in resp_json.get("devices", []):
            dev_serial = hg_dev.get("deviceSerialNumber")
            dev_type = hg_dev.get("deviceType")
            dev_name = hg_dev.get("deviceName")
            dev_status = hg_dev.get("deviceStatus", {})

            if dev_serial not in self._communication_preferences:
                self._communication_preferences[dev_serial] = {
                    "announcements": dev_status.get("announcementAvailability"),
                }

            self._communication_preferences[dev_serial].update(
                {
                    "communications": dev_status.get("deviceCommsAvailability"),
                    "dropin": dev_status.get("deviceDropInAvailability"),
                }
            )

            query_string = {"devicePreferences": ["announcements"]}
            url = URL.joinpath(
                self._communication_site,
                URI_COMM_PREFERENCES.format(
                    device_type=dev_type,
                    serial_number=dev_serial,
                ),
            )
            url = url.with_query(query_string)
            try:
                _, resp = await self._http_wrapper.session_request(
                    method=HTTPMethod.GET, url=url, fail_fast=True
                )
            except CannotRetrieveData:
                _LOGGER.warning(
                    "Failed to refresh communications settings for device %s, used cached values.",  # noqa: E501
                    dev_name,
                )
                continue
            resp_json = await self._http_wrapper.response_to_json(
                resp, "devicesTypes(preferences)"
            )

            for device_permissions_pref in resp_json.get(
                "devicePermissionsPreferences", {}
            ):
                device_pref = device_permissions_pref["devicePreference"]
                pref_state = device_permissions_pref.get("state")
                pref_allowed = device_permissions_pref.get("allowed")

                if pref_allowed is True:
                    self._communication_preferences[dev_serial][device_pref] = (
                        pref_state
                    )

        return self._communication_preferences

    async def get_homegroup_id(self) -> str | None:
        """Get homegroup id for the user."""
        if self._homegroup_id is not None:
            return self._homegroup_id

        url = URL.joinpath(
            self._communication_site,
            URI_COMM_IDENTITY.format(user_id=self._session_state_data.user_id),
        )
        _, resp = await self._http_wrapper.session_request(
            method=HTTPMethod.GET, url=url
        )
        resp_json = await self._http_wrapper.response_to_json(resp, "comms-identity")
        self._homegroup_id = resp_json.get("homeGroupId")
        return self._homegroup_id
