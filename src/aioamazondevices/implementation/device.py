# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Implementation of device handling for Amazon devices."""

from http import HTTPMethod
from typing import Any

from yarl import URL

from aioamazondevices.const.devices import (
    DEVICE_TYPE_AQM,
    DEVICE_TYPES_HARDCODED_METADATA,
    DEVICE_TYPES_TO_IGNORE,
    SPEAKER_GROUP_FAMILY,
)
from aioamazondevices.const.http import (
    REFRESH_ACCESS_TOKEN,
    REQUEST_AGENT,
    URI_DEVICES,
    URI_NEXUS_GRAPHQL,
    URI_REBOOT,
)
from aioamazondevices.const.queries import QUERY_DEVICE_DATA
from aioamazondevices.exceptions import CannotRestartDevice, CannotRetrieveData
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonDevice
from aioamazondevices.utils import _LOGGER, format_graphql_error, parse_device_details


def _endpoint_text(endpoint: dict[str, Any], key: str) -> str | None:
    """Return the text of a GraphQL endpoint attribute."""
    return ((endpoint.get(key) or {}).get("value") or {}).get("text")


def _endpoint_device_type(endpoint: dict[str, Any]) -> str | None:
    """Return the legacy device type of a GraphQL endpoint."""
    legacy_identifiers = endpoint.get("legacyIdentifiers") or {}
    return _endpoint_text(legacy_identifiers.get("dmsIdentifier") or {}, "deviceType")


def _endpoint_entity_id(endpoint: dict[str, Any]) -> str | None:
    """Return the legacy entity ID of a GraphQL endpoint."""
    legacy_identifiers = endpoint.get("legacyIdentifiers") or {}
    return (legacy_identifiers.get("chrsIdentifier") or {}).get("entityId")


def _resolve_model_details(
    device_type: str, account_name: str, model: str | None, manufacturer: str | None
) -> tuple[str | None, str | None, str | None]:
    """Normalize a model and split its hardware revision off.

    Returns the model, its hardware version and the manufacturer, falling back
    to hardcoded metadata for devices that report no usable model.
    """
    hardcoded_data = DEVICE_TYPES_HARDCODED_METADATA.get(device_type, {})

    if not model:
        _LOGGER.debug(
            "Looking hardcoded model for device type %s [%s]",
            device_type,
            account_name,
        )
        model = hardcoded_data.get("model")

    device_model, hardware_version = parse_device_details(model)

    if not device_model:
        _LOGGER.warning(
            "Unknown device type '%s' for %s: please read https://github.com/chemelli74/aioamazondevices/wiki/Unknown-Device-Types",
            device_type,
            account_name,
        )
        return model, None, manufacturer

    return (
        device_model,
        hardware_version,
        manufacturer or hardcoded_data.get("manufacturer"),
    )


class AmazonDeviceHandler:
    """Class to handle Amazon device functionality."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize AmazonDeviceHandler class."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper
        self._final_devices: dict[str, AmazonDevice] = {}

    @property
    def devices(self) -> dict[str, AmazonDevice]:
        """Return the final devices list."""
        return self._final_devices

    async def update_devices(self) -> None:
        """Build the list of devices we are interested in.

        GraphQL endpoint data is the driving side: every device is built from
        its endpoint and enriched with `api/devices-v2/device` data when there
        is some. Speaker groups are the exception, as they only exist in the
        devices-v2 data.
        """
        devices_endpoints = await self._get_devices_endpoint_data()
        base_devices = await self._get_base_devices_data()

        devices: dict[str, AmazonDevice] = {}

        for serial_number, endpoint in devices_endpoints.items():
            # Devices without devices-v2 data are built from their endpoint
            # alone, one branch per device type we support that way
            if base_device := base_devices.get(serial_number):
                device = self._build_device(endpoint, base_device)
            elif _endpoint_device_type(endpoint) == DEVICE_TYPE_AQM:
                device = self._build_device(endpoint)
            else:
                _LOGGER.debug(
                    "Skipping endpoint without devices-v2 data: %s",
                    _endpoint_text(endpoint, "friendlyNameObject"),
                )
                continue

            devices[serial_number] = device

        # Speaker groups are not exposed as endpoints by GraphQL
        for serial_number, base_device in base_devices.items():
            if (
                serial_number in devices
                or base_device["deviceFamily"] != SPEAKER_GROUP_FAMILY
            ):
                continue

            devices[serial_number] = self._build_device({}, base_device)

        # backfill device types for cluster members, now that they are all built
        for device in devices.values():
            for member_serial in device.device_cluster_members:
                member = devices.get(member_serial)
                device.device_cluster_members[member_serial] = (
                    member.device_type if member else None
                )

        self._final_devices = devices

    def _build_device(
        self,
        endpoint: dict[str, Any],
        base_device: dict[str, Any] | None = None,
    ) -> AmazonDevice:
        """Build a device from its GraphQL endpoint and devices-v2 data.

        The endpoint is the primary source and devices-v2 provides what it does
        not have, so a device without devices-v2 data (e.g. an air quality
        monitor) is built from its endpoint alone, and a speaker group, which
        has no endpoint, from its devices-v2 data alone.
        """
        base = base_device or {}
        account_customer_id = self._session_state_data.account_customer_id
        capabilities: list[str] = base.get("capabilities") or []
        owner_customer_id: str | None = base.get("deviceOwnerCustomerId")

        account_name = _endpoint_text(endpoint, "friendlyNameObject") or base.get(
            "accountName", ""
        )
        serial_number = _endpoint_text(endpoint, "serialNumber") or base.get(
            "serialNumber", ""
        )
        device_type = _endpoint_device_type(endpoint) or base.get("deviceType", "")
        # devices-v2 is the only source of a device family, so a device that
        # has no devices-v2 data at all is a different case to one whose data
        # does not name a family
        family = (base.get("deviceFamily") or "Unknown") if base else "Endpoint Only"

        model, hardware_version, manufacturer = _resolve_model_details(
            device_type,
            account_name,
            _endpoint_text(endpoint, "model") or base.get("deviceTypeFriendlyName"),
            _endpoint_text(endpoint, "manufacturer"),
        )

        return AmazonDevice(
            account_name=account_name,
            capabilities=capabilities,
            device_family=family,
            device_type=device_type,
            device_owner_customer_id=owner_customer_id or account_customer_id or "n/a",
            household_device=bool(owner_customer_id)
            and owner_customer_id == account_customer_id,
            device_cluster_members=dict.fromkeys(
                base.get("clusterMembers") or [serial_number]
            ),
            parent_clusters=base.get("parentClusters") or [],
            online=base.get("online", True),
            serial_number=serial_number,
            software_version=_endpoint_text(endpoint, "softwareVersion")
            or (
                base.get("softwareVersion")
                if "SUPPORTS_SOFTWARE_VERSION" in capabilities
                else None
            ),
            manufacturer=manufacturer,
            model=model,
            hardware_version=hardware_version,
            entity_id=_endpoint_entity_id(endpoint),
            endpoint_id=endpoint.get("endpointId"),
            sensors={},
            notifications_supported=any(
                capability in capabilities
                for capability in ["REMINDERS", "TIMERS_AND_ALARMS"]
            ),
            notifications={},
            media_player_supported="AUDIO_PLAYER" in capabilities,
            communication_settings={},
            # only devices-v2 devices can be spoken to, speaker groups aside
            voice_control_supported=bool(base) and family != SPEAKER_GROUP_FAMILY,
        )

    async def _get_base_devices_data(self) -> dict[str, dict[str, Any]]:
        """Get the raw devices-v2 data, keyed by serial number.

        This will not include devices that exist in the GraphQL data only,
        like AQM devices.
        """
        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.GET,
            url=URL.joinpath(self._session_state_data.alexa_website_url, URI_DEVICES),
        )

        json_data = await self._http_wrapper.response_to_json(raw_resp, "devices")

        base_devices: dict[str, dict[str, Any]] = {}
        for device in json_data["devices"]:
            # Remove stale, orphaned and virtual devices
            if not device or (device.get("deviceType") in DEVICE_TYPES_TO_IGNORE):
                continue

            # Skip devices that cannot be used with voice features
            if "MICROPHONE" not in device["capabilities"]:
                _LOGGER.debug(
                    "Skipping device without microphone capabilities: %s",
                    device["accountName"],
                )
                continue

            base_devices[device["serialNumber"]] = device

        return base_devices

    async def _get_devices_endpoint_data(self) -> dict[str, dict[str, Any]]:
        """Get devices endpoint data, keyed by serial number."""
        payload = {
            "operationName": "getDevicesBaseData",
            "query": QUERY_DEVICE_DATA,
        }

        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=URL.joinpath(
                self._session_state_data.alexa_website_url, URI_NEXUS_GRAPHQL
            ),
            input_data=payload,
            json_data=True,
            extended_headers={"User-Agent": REQUEST_AGENT["Amazon"]},
        )

        endpoint_data = await self._http_wrapper.response_to_json(raw_resp, "endpoint")

        if (
            not (data := endpoint_data.get("data"))
            or not (endpoints_list := data.get("listEndpoints"))
            or not (raw_endpoints := endpoints_list.get("endpoints"))
        ):
            format_graphql_error(endpoint_data)
            return {}

        devices_endpoints: dict[str, dict[str, Any]] = {}
        for endpoint in raw_endpoints:
            # save looking up sensor data on apps
            if (endpoint.get("alexaEnabledMetadata") or {}).get("category") == "APP":
                continue

            if not (serial_number := _endpoint_text(endpoint, "serialNumber")):
                continue

            devices_endpoints[serial_number] = endpoint

        return devices_endpoints

    async def restart_device(self, device: AmazonDevice) -> None:
        """Restart a device."""
        url = URL.joinpath(
            self._session_state_data.alexa_website_url,
            URI_REBOOT.format(
                device_type=device.device_type, serial_number=device.serial_number
            ),
        )
        payload = {
            "deviceSerialNumber": device.serial_number,
            "deviceType": device.device_type,
        }

        access_token = self._session_state_data.login_stored_data[REFRESH_ACCESS_TOKEN]

        try:
            await self._http_wrapper.session_request(
                method=HTTPMethod.POST,
                url=url,
                input_data=payload,
                json_data=True,
                extended_headers={
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": REQUEST_AGENT["Amazon"],
                },
            )
        except CannotRetrieveData as exc:
            # Reraise standard exception with more context
            raise CannotRestartDevice(
                f"Failed to restart device {device.account_name}"
            ) from exc
