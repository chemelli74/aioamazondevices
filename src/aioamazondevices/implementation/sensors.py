"""Support for Amazon sensors."""

from http import HTTPMethod
from typing import Any

from aioamazondevices.const.devices import SPEAKER_GROUP_FAMILY
from aioamazondevices.const.http import ARRAY_WRAPPER, REQUEST_AGENT, URI_NEXUS_GRAPHQL
from aioamazondevices.const.metadata import SENSORS
from aioamazondevices.const.queries import QUERY_SENSOR_STATE
from aioamazondevices.const.schedules import (
    NOTIFICATION_ALARM,
    NOTIFICATION_REMINDER,
    NOTIFICATION_TIMER,
)
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonDevice, AmazonDeviceSensor
from aioamazondevices.utils import _LOGGER, format_graphql_error


class AmazonSensorHandler:
    """Class to handle Amazon sensor functionality."""

    def __init__(
        self,
        session_state_data: AmazonSessionStateData,
        http_wrapper: AmazonHttpWrapper,
    ) -> None:
        """Initialize AmazonSensorHandler class."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper
        self._final_devices: dict[str, AmazonDevice] = {}
        self._endpoints: dict[str, str] = {}

    async def update_sensor_data(
        self,
        devices: dict[str, AmazonDevice],
        endpoints: dict[str, str],
        dnd_sensors: dict[str, AmazonDeviceSensor],
        notifications: dict[str, dict[str, Any]] | None,
    ) -> None:
        """Update sensors data for all devices."""
        self._final_devices = devices
        self._endpoints = endpoints
        devices_sensors = await self._get_sensor_data()

        for device in self._final_devices.values():
            # Update sensors
            sensors = devices_sensors.get(device.serial_number, {})
            if sensors:
                device.sensors = sensors
            else:
                for device_sensor in device.sensors.values():
                    device_sensor.error = True
            if (
                device_dnd := dnd_sensors.get(device.serial_number)
            ) and device.device_family != SPEAKER_GROUP_FAMILY:
                device.sensors["dnd"] = device_dnd

            if notifications is None:
                continue  # notifications were not obtained, do not update

            # Clear old notifications to handle cancelled ones
            device.notifications = {}

            # Update notifications
            device_notifications = notifications.get(device.serial_number, {})

            # Add only supported notification types
            for capability, notification_type in [
                ("REMINDERS", NOTIFICATION_REMINDER),
                ("TIMERS_AND_ALARMS", NOTIFICATION_ALARM),
                ("TIMERS_AND_ALARMS", NOTIFICATION_TIMER),
            ]:
                if (
                    capability in device.capabilities
                    and notification_type in device_notifications
                    and (
                        notification_object := device_notifications.get(
                            notification_type
                        )
                    )
                ):
                    device.notifications[notification_type] = notification_object

    async def _get_sensor_data(self) -> dict[str, dict[str, AmazonDeviceSensor]]:
        """Retrieve devices sensors states."""
        devices_sensors: dict[str, dict[str, AmazonDeviceSensor]] = {}

        if not self._endpoints:
            return {}

        endpoint_ids = list(self._endpoints.keys())
        payload = [
            {
                "operationName": "getEndpointState",
                "variables": {
                    "endpointIds": endpoint_ids,
                },
                "query": QUERY_SENSOR_STATE,
            }
        ]

        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_NEXUS_GRAPHQL}",
            input_data=payload,
            json_data=True,
            extended_headers={"User-Agent": REQUEST_AGENT["Amazon"]},
        )

        sensors_state = await self._http_wrapper.response_to_json(raw_resp, "sensors")

        if await format_graphql_error(sensors_state):
            # Explicit error in returned data
            return {}

        if (
            not (arr := sensors_state.get(ARRAY_WRAPPER))
            or not (data := arr[0].get("data"))
            or not (endpoints_list := data.get("listEndpoints"))
            or not (endpoints := endpoints_list.get("endpoints"))
        ):
            _LOGGER.error("Malformed sensor state data received: %s", sensors_state)
            return {}

        for endpoint in endpoints:
            serial_number = self._endpoints[endpoint.get("endpointId")]

            if serial_number in self._final_devices:
                devices_sensors[serial_number] = self._process_sensor_data(
                    endpoint, serial_number
                )

        return devices_sensors

    def _process_sensor_data(
        self, endpoint: dict[str, Any], serial_number: str
    ) -> dict[str, AmazonDeviceSensor]:
        device_sensors: dict[str, AmazonDeviceSensor] = {}
        for feature in endpoint.get("features", {}):
            if (sensor_template := SENSORS.get(feature["name"])) is None:
                # Skip sensors that are not in the predefined list
                continue

            if not (name := sensor_template["name"]):
                raise CannotRetrieveData("Unable to read sensor template")

            for feature_property in feature.get("properties"):
                if sensor_template["name"] != feature_property.get("name"):
                    continue

                value: str | int | float = "n/a"
                scale: str | None = None

                # "error" can be None, missing, or a dict
                api_error = feature_property.get("error") or {}
                error = bool(api_error)
                error_type = api_error.get("type")
                error_msg = api_error.get("message")
                if not error:
                    try:
                        value_raw = feature_property[sensor_template["key"]]
                        if not value_raw:
                            _LOGGER.warning(
                                "Sensor %s [device %s] ignored due to empty value",
                                name,
                                serial_number,
                            )
                            continue
                        scale = (
                            value_raw[scale_template]
                            if (scale_template := sensor_template["scale"])
                            else None
                        )
                        value = (
                            value_raw[subkey_template]
                            if (subkey_template := sensor_template["subkey"])
                            else value_raw
                        )

                    except (KeyError, ValueError) as exc:
                        _LOGGER.warning(
                            "Sensor %s [device %s] ignored due to errors in feature %s: %s",  # noqa: E501
                            name,
                            serial_number,
                            feature_property,
                            repr(exc),
                        )
                if error:
                    _LOGGER.debug(
                        "error in sensor %s - %s - %s", name, error_type, error_msg
                    )

                if error_type != "NOT_FOUND":
                    device_sensors[name] = AmazonDeviceSensor(
                        name,
                        value,
                        error,
                        error_type,
                        error_msg,
                        scale,
                    )

        return device_sensors
