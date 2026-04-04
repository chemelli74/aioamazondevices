"""Implementation of device handling for Amazon devices."""

from http import HTTPMethod
from typing import Any

from aioamazondevices.const.devices import (
    DEVICE_TYPE_AQM,
    DEVICE_TYPES_HARDCODED_METADATA,
    DEVICE_TYPES_TO_IGNORE,
)
from aioamazondevices.const.http import REQUEST_AGENT, URI_DEVICES, URI_NEXUS_GRAPHQL
from aioamazondevices.const.queries import QUERY_DEVICE_DATA
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonDevice
from aioamazondevices.utils import _LOGGER, format_graphql_error, parse_device_details


class AmazonDeviceHandler:
    """Class to handle Amazon device functionality."""

    def __init__(
        self,
        session_state_data: AmazonSessionStateData,
        http_wrapper: AmazonHttpWrapper,
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

    async def get_base_devices(self) -> None:
        """Get a list of devices we are interested in.

        This will not include AQM devices which will be added later.
        """
        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.GET,
            url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_DEVICES}",
        )

        json_data = await self._http_wrapper.response_to_json(raw_resp, "devices")

        final_devices_list: dict[str, AmazonDevice] = {}
        serial_to_device_type: dict[str, str] = {}
        for device in json_data["devices"]:
            # Remove stale, orphaned and virtual devices
            if not device or (device.get("deviceType") in DEVICE_TYPES_TO_IGNORE):
                continue

            account_name: str = device["accountName"]
            capabilities: list[str] = device["capabilities"]
            # Skip devices that cannot be used with voice features
            if "MICROPHONE" not in capabilities:
                _LOGGER.debug(
                    "Skipping device without microphone capabilities: %s", account_name
                )
                continue

            serial_number: str = device["serialNumber"]

            _has_notification_capability = any(
                capability in capabilities
                for capability in ["REMINDERS", "TIMERS_AND_ALARMS"]
            )

            final_devices_list[serial_number] = AmazonDevice(
                account_name=account_name,
                capabilities=capabilities,
                device_family=device["deviceFamily"],
                device_type=device["deviceType"],
                device_owner_customer_id=device["deviceOwnerCustomerId"],
                household_device=device["deviceOwnerCustomerId"]
                == self._session_state_data.account_customer_id,
                device_cluster_members=dict.fromkeys(
                    device["clusterMembers"] or [serial_number]
                ),
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
            )

            serial_to_device_type[serial_number] = device["deviceType"]

        # backfill device types for cluster members
        for device in final_devices_list.values():
            for member_serial in device.device_cluster_members:
                device.device_cluster_members[member_serial] = (
                    serial_to_device_type.get(member_serial)
                )

        self._final_devices = final_devices_list

    async def set_device_endpoints_data(self) -> None:
        """Set device endpoint data."""
        devices_endpoints = await self._get_devices_endpoint_data()
        for serial_number in self._final_devices:
            device_endpoint = devices_endpoints.get(serial_number, {})
            endpoint_device = self._final_devices[serial_number]
            hardcoded_data = DEVICE_TYPES_HARDCODED_METADATA.get(
                endpoint_device.device_type, {}
            )
            endpoint_device.entity_id = (
                device_endpoint["legacyIdentifiers"]["chrsIdentifier"]["entityId"]
                if device_endpoint
                else None
            )
            endpoint_device.endpoint_id = (
                device_endpoint["endpointId"] if device_endpoint else None
            )

            model_value: str | None = (
                (device_endpoint.get("model") or {}).get("value", {}).get("text")
            )
            model: str | None = (
                model_value
                if model_value and "Alexa Voice" not in model_value
                else endpoint_device.model
            )

            if not model:
                _LOGGER.debug(
                    "Looking hardcoded model for device type %s [%s]",
                    endpoint_device.device_type,
                    endpoint_device.account_name,
                )
                model = hardcoded_data.get("model")

            manufacturer = (
                manufacturer_key.get("value", {}).get("text")
                if (manufacturer_key := device_endpoint.get("manufacturer"))
                else hardcoded_data.get("manufacturer")
            )

            device_model, device_hw_version = parse_device_details(model)

            if not device_model:
                _LOGGER.warning(
                    "Unknown device type '%s' for %s: please read https://github.com/chemelli74/aioamazondevices/wiki/Unknown-Device-Types",
                    endpoint_device.device_type,
                    endpoint_device.account_name,
                )
            else:
                endpoint_device.model = device_model
                endpoint_device.hardware_version = device_hw_version
                endpoint_device.manufacturer = manufacturer

    async def _get_devices_endpoint_data(self) -> dict[str, dict[str, Any]]:
        """Get Devices endpoint data."""
        payload = {
            "operationName": "getDevicesBaseData",
            "query": QUERY_DEVICE_DATA,
        }

        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_NEXUS_GRAPHQL}",
            input_data=payload,
            json_data=True,
            extended_headers={"User-Agent": REQUEST_AGENT["Amazon"]},
        )

        endpoint_data = await self._http_wrapper.response_to_json(raw_resp, "endpoint")

        if not (data := endpoint_data.get("data")) or not data.get("alexaVoiceDevices"):
            await format_graphql_error(endpoint_data)
            return {}

        devices_endpoints: dict[str, dict[str, Any]] = {}

        # Process Alexa Voice Enabled devices
        # Just map endpoint ID to serial number to facilitate sensor lookup
        for endpoint in data.get("alexaVoiceDevices", {}).get("endpoints", []):
            # save looking up sensor data on apps
            if (endpoint.get("alexaEnabledMetadata") or {}).get("category") == "APP":
                continue

            if endpoint.get("serialNumber"):
                serial_number = endpoint["serialNumber"]["value"]["text"]
                devices_endpoints[serial_number] = endpoint
                self._endpoints[endpoint["endpointId"]] = serial_number

        # Process Air Quality Monitors if present
        # map endpoint ID to serial number to facilitate sensor lookup but also
        # create AmazonDevice as these are not present in api/devices-v2/device endpoint
        for aqm_endpoint in data.get("airQualityMonitors", {}).get("endpoints", {}):
            if (
                aqm_endpoint.get("manufacturer", {})
                .get("value", {})
                .get("text", "Unknown")
                != "Amazon"
            ):
                _LOGGER.debug(
                    "Skipping non-Amazon Air Quality Monitor: %s",
                    aqm_endpoint,
                )
                continue
            aqm_serial_number: str = aqm_endpoint["serialNumber"]["value"]["text"]
            devices_endpoints[aqm_serial_number] = aqm_endpoint
            self._endpoints[aqm_endpoint["endpointId"]] = aqm_serial_number

            self._final_devices[aqm_serial_number] = AmazonDevice(
                account_name=aqm_endpoint["friendlyNameObject"]["value"]["text"],
                capabilities=[],
                device_family="AIR_QUALITY_MONITOR",
                device_type=aqm_endpoint["legacyIdentifiers"]["dmsIdentifier"][
                    "deviceType"
                ]["value"]["text"],
                device_owner_customer_id=self._session_state_data.account_customer_id
                or "n/a",
                household_device=False,
                device_cluster_members={aqm_serial_number: DEVICE_TYPE_AQM},
                online=True,
                serial_number=aqm_serial_number,
                software_version=aqm_endpoint["softwareVersion"]["value"]["text"],
                manufacturer="Amazon",
                model=None,
                hardware_version=None,
                entity_id=None,
                endpoint_id=aqm_endpoint.get("endpointId"),
                sensors={},
                notifications_supported=False,
                notifications={},
                media_player_supported=False,
            )

        return devices_endpoints
