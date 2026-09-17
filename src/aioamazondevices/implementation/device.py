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

APP_CATEGORY = "APP"
AQM_DEVICE_FAMILY = "AIR_QUALITY_MONITOR"


def _endpoint_text(endpoint: dict[str, Any], key: str) -> str | None:
    """Return the text of a GraphQL endpoint attribute."""
    return ((endpoint.get(key) or {}).get("value") or {}).get("text")


def _endpoint_device_type(endpoint: dict[str, Any]) -> str | None:
    """Return the legacy device type of a GraphQL endpoint."""
    legacy_identifiers = endpoint.get("legacyIdentifiers") or {}
    return _endpoint_text(legacy_identifiers.get("dmsIdentifier") or {}, "deviceType")


def _graphql_endpoints(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the endpoints of a device data GraphQL response.

    The query returns every device as a single list, wrapped in whatever key
    the query uses for it.
    """
    if isinstance(endpoints := data.get("endpoints"), list):
        return endpoints

    for value in data.values():
        if isinstance(value, dict) and isinstance(
            endpoints := value.get("endpoints"), list
        ):
            return endpoints

    return []


def _build_base_device(
    device: dict[str, Any], account_customer_id: str | None
) -> AmazonDevice:
    """Build an AmazonDevice from `api/devices-v2/device` data."""
    capabilities: list[str] = device["capabilities"]
    serial_number: str = device["serialNumber"]

    _has_notification_capability = any(
        capability in capabilities for capability in ["REMINDERS", "TIMERS_AND_ALARMS"]
    )

    return AmazonDevice(
        account_name=device["accountName"],
        capabilities=capabilities,
        device_family=device["deviceFamily"],
        device_type=device["deviceType"],
        device_owner_customer_id=device["deviceOwnerCustomerId"],
        household_device=device["deviceOwnerCustomerId"] == account_customer_id,
        device_cluster_members=dict.fromkeys(
            device["clusterMembers"] or [serial_number]
        ),
        parent_clusters=device.get("parentClusters") or [],
        online=device["online"],
        serial_number=serial_number,
        software_version=device["softwareVersion"]
        if "SUPPORTS_SOFTWARE_VERSION" in capabilities
        else None,
        entity_id=None,
        model=device.get("deviceTypeFriendlyName"),
        manufacturer=None,
        hardware_version=None,
        endpoint_id=None,
        sensors={},
        notifications_supported=_has_notification_capability,
        notifications={},
        media_player_supported="AUDIO_PLAYER" in capabilities,
        communication_settings={},
        voice_control_supported=device["deviceFamily"] != SPEAKER_GROUP_FAMILY,
    )


def _build_endpoint_device(  # noqa: PLR0913 - a device just has many fields
    *,
    account_name: str,
    device_family: str,
    device_type: str,
    serial_number: str,
    customer_id: str | None,
    online: bool,
    manufacturer: str | None = None,
    model: str | None = None,
    software_version: str | None = None,
    entity_id: str | None = None,
    endpoint_id: str | None = None,
) -> AmazonDevice:
    """Build an AmazonDevice for a GraphQL-discovered endpoint.

    Devices like air quality monitors are not returned by
    ``api/devices-v2/device``, so the voice-device fields are left empty.
    """
    return AmazonDevice(
        account_name=account_name,
        capabilities=[],
        device_family=device_family,
        device_type=device_type,
        device_owner_customer_id=customer_id or "n/a",
        household_device=False,
        device_cluster_members={serial_number: device_type},
        parent_clusters=[],
        online=online,
        serial_number=serial_number,
        software_version=software_version,
        manufacturer=manufacturer,
        model=model,
        hardware_version=None,
        entity_id=entity_id,
        endpoint_id=endpoint_id,
        sensors={},
        notifications_supported=False,
        notifications={},
        media_player_supported=False,
        communication_settings={},
        voice_control_supported=False,
    )


def _build_endpoint_only_device(
    endpoint: dict[str, Any],
    account_customer_id: str | None,
    *,
    device_family: str,
) -> AmazonDevice:
    """Build a device from its GraphQL endpoint alone.

    For devices that `api/devices-v2/device` does not return, the device
    family is the only thing the endpoint cannot tell us.
    """
    return _build_endpoint_device(
        account_name=_endpoint_text(endpoint, "friendlyNameObject") or "",
        device_family=device_family,
        device_type=_endpoint_device_type(endpoint) or "",
        serial_number=_endpoint_text(endpoint, "serialNumber") or "",
        customer_id=account_customer_id,
        online=True,
        manufacturer=_endpoint_text(endpoint, "manufacturer"),
        software_version=_endpoint_text(endpoint, "softwareVersion"),
        endpoint_id=endpoint.get("endpointId"),
    )


def _add_endpoint_data(device: AmazonDevice, endpoint: dict[str, Any]) -> None:
    """Enrich a device with the data of its GraphQL endpoint.

    Speaker groups have no endpoint, so an empty one is passed for them.
    """
    hardcoded_data = DEVICE_TYPES_HARDCODED_METADATA.get(device.device_type, {})

    device.entity_id = (
        endpoint["legacyIdentifiers"]["chrsIdentifier"]["entityId"]
        if endpoint
        else None
    )
    device.endpoint_id = endpoint["endpointId"] if endpoint else None

    model_value = _endpoint_text(endpoint, "model")
    model: str | None = (
        model_value
        if model_value and "Alexa Voice" not in model_value
        else device.model
    )

    if not model:
        _LOGGER.debug(
            "Looking hardcoded model for device type %s [%s]",
            device.device_type,
            device.account_name,
        )
        model = hardcoded_data.get("model")

    manufacturer = _endpoint_text(endpoint, "manufacturer") or hardcoded_data.get(
        "manufacturer"
    )

    device_model, device_hw_version = parse_device_details(model)

    if not device_model:
        _LOGGER.warning(
            "Unknown device type '%s' for %s: please read https://github.com/chemelli74/aioamazondevices/wiki/Unknown-Device-Types",
            device.device_type,
            device.account_name,
        )
    else:
        device.model = device_model
        device.hardware_version = device_hw_version
        device.manufacturer = manufacturer


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
        self._endpoints: dict[str, str] = {}  # endpoint ID to serial number map

    @property
    def devices(self) -> dict[str, AmazonDevice]:
        """Return the final devices list."""
        return self._final_devices

    @property
    def endpoints(self) -> dict[str, str]:
        """Return the endpoints mapping."""
        return self._endpoints

    async def update_devices(self) -> None:
        """Build the list of devices we are interested in.

        GraphQL endpoint data is the driving side: a device is built from its
        `api/devices-v2/device` data when it has some, otherwise from the
        endpoint alone (e.g. air quality monitors). Speaker groups are the
        exception, as they only exist in the devices-v2 data.
        """
        devices_endpoints = await self._get_devices_endpoint_data()
        base_devices = await self._get_base_devices_data()
        account_customer_id = self._session_state_data.account_customer_id

        devices: dict[str, AmazonDevice] = {}
        endpoints: dict[str, str] = {}
        serial_to_device_type: dict[str, str | None] = {
            serial_number: base_device["deviceType"]
            for serial_number, base_device in base_devices.items()
        }

        for serial_number, endpoint in devices_endpoints.items():
            # Devices without devices-v2 data are built from their endpoint
            # alone, one branch per device type we support that way
            if base_device := base_devices.get(serial_number):
                device = _build_base_device(base_device, account_customer_id)
            elif _endpoint_device_type(endpoint) == DEVICE_TYPE_AQM:
                device = _build_endpoint_only_device(
                    endpoint, account_customer_id, device_family=AQM_DEVICE_FAMILY
                )
            else:
                _LOGGER.debug(
                    "Skipping endpoint without devices-v2 data: %s",
                    _endpoint_text(endpoint, "friendlyNameObject"),
                )
                continue

            _add_endpoint_data(device, endpoint)
            devices[serial_number] = device
            endpoints[endpoint["endpointId"]] = serial_number
            serial_to_device_type.setdefault(serial_number, device.device_type)

        # Speaker groups are not exposed as endpoints by GraphQL
        for serial_number, base_device in base_devices.items():
            if (
                serial_number in devices
                or base_device["deviceFamily"] != SPEAKER_GROUP_FAMILY
            ):
                continue

            device = _build_base_device(base_device, account_customer_id)
            _add_endpoint_data(device, {})
            devices[serial_number] = device

        # backfill device types for cluster members
        for device in devices.values():
            for member_serial in device.device_cluster_members:
                device.device_cluster_members[member_serial] = (
                    serial_to_device_type.get(member_serial)
                )

        self._final_devices = devices
        self._endpoints = endpoints

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

        if not (data := endpoint_data.get("data")) or not (
            raw_endpoints := _graphql_endpoints(data)
        ):
            format_graphql_error(endpoint_data)
            return {}

        devices_endpoints: dict[str, dict[str, Any]] = {}
        for endpoint in raw_endpoints:
            # save looking up sensor data on apps
            if (endpoint.get("alexaEnabledMetadata") or {}).get(
                "category"
            ) == APP_CATEGORY:
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
