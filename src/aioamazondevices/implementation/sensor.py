# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Sensor module for Amazon devices."""

from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from http import HTTPMethod
from typing import Any

from yarl import URL

from aioamazondevices.const.devices import SPEAKER_GROUP_FAMILY
from aioamazondevices.const.http import REQUEST_AGENT, URI_NEXUS_GRAPHQL
from aioamazondevices.const.queries import QUERY_POLLED_SENSOR_STATE
from aioamazondevices.const.sensors import POLLED_SENSOR_FEATURES
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.implementation.sensor_templates import (
    SensorDefinition,
    resolve_sensor_definition,
)
from aioamazondevices.structures import AmazonDevice, AmazonDeviceSensor
from aioamazondevices.utils import (
    _LOGGER,
    check_and_log_graphql_errors,
    validate_graphql_endpoint_shape,
)

# How Amazon identifies a sensor: (endpoint ID, feature, instance, property)
type SensorId = tuple[str, str, str, str]


@dataclass(frozen=True)
class _TrackedSensor:
    """A sensor we track, resolved once per sync.

    Holds the resolved definition so we don't need to reprocess
    the sensor templates when applying an update.
    """

    serial_number: str
    feature_name: str
    sensor_definition: SensorDefinition


@dataclass(frozen=True)
class SensorValue:
    """A parsed value of a tracked sensor, not yet stored."""

    serial_number: str
    sensor: AmazonDeviceSensor


def _parse_sample_timestamp(
    raw_timestamp: str | None,
    sensor_name: str,
    serial_number: str,
) -> datetime | None:
    """Parse a sensor sample timestamp, if present."""
    if not raw_timestamp:
        return None
    try:
        return datetime.fromisoformat(raw_timestamp)
    except (TypeError, ValueError):
        _LOGGER.warning(
            "Sensor %s [device %s] has an unparsable timeOfSample: %s",
            sensor_name,
            serial_number,
            raw_timestamp,
        )
        return None


def _iter_endpoint_properties(
    endpoint: dict[str, Any],
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield (feature name, instance, property) for every property of an endpoint."""
    for feature in endpoint.get("features") or []:
        feature_name: str = feature.get("name") or ""
        instance: str = feature.get("instance") or ""
        for feature_property in feature.get("properties") or []:
            yield feature_name, instance, feature_property


def _parse_property(
    feature_property: dict[str, Any],
    *,
    feature_name: str,
    instance: str,
    sensor_definition: SensorDefinition,
    serial_number: str,
) -> AmazonDeviceSensor | None:
    """Parse a single GraphQL property into a sensor, None if it cannot be used."""
    property_name: str = feature_property.get("name") or ""
    template = sensor_definition.template
    value: str | int | float = "n/a"
    scale: str | None = None
    time_of_sample = _parse_sample_timestamp(
        feature_property.get("timeOfSample"),
        property_name,
        serial_number,
    )

    # "error" can be None, missing, or a dict
    api_error = feature_property.get("error") or {}
    error = bool(api_error)
    error_type = api_error.get("type")
    error_msg = api_error.get("message")
    if not error:
        try:
            value_raw = feature_property[template["key"] or ""]
            if not value_raw:
                _LOGGER.warning(
                    "Sensor %s [device %s] ignored due to empty value",
                    property_name,
                    serial_number,
                )
                return None
            scale = (
                value_raw[scale_template]
                if (scale_template := template["scale"])
                else None
            )
            value = (
                value_raw[subkey_template]
                if (subkey_template := template["subkey"])
                else value_raw
            )

        except (KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Sensor %s [device %s] ignored due to errors in feature %s: %s",
                property_name,
                serial_number,
                feature_property,
                repr(exc),
            )
            return None
    if error:
        _LOGGER.debug(
            "error in sensor %s - %s - %s",
            property_name,
            error_type,
            error_msg,
        )

    if sensor_definition.override is not None:
        scale = sensor_definition.override.get("scale")

    return AmazonDeviceSensor(
        sensor_definition.key,
        value,
        error,
        error_type,
        error_msg,
        scale,
        feature_name=feature_name,
        property_name=property_name,
        instance=instance,
        time_of_sample=time_of_sample,
    )


def _tracked_sensors(device: AmazonDevice) -> Iterator[tuple[SensorId, _TrackedSensor]]:
    """Yield (sensor ID, tracked sensor) for each supported feature property.

    Support comes from the device features, not from the current values, so a
    sensor without a value or with a NOT_FOUND error is still tracked.
    """
    for feature_name, instances in device.features.items():
        for instance, feature in instances.items():
            for property_name in feature.sensor_keys:
                if (
                    sensor_definition := resolve_sensor_definition(
                        device.device_type, feature_name, instance, property_name
                    )
                ) is None:
                    continue
                sensor_id: SensorId = (
                    device.endpoint_id or "",
                    feature_name,
                    instance,
                    property_name,
                )
                yield (
                    sensor_id,
                    _TrackedSensor(
                        device.serial_number, feature_name, sensor_definition
                    ),
                )


def _parse_tracked_values(
    endpoint_id: str,
    endpoint_state: dict[str, Any],
    tracked_sensors: dict[SensorId, _TrackedSensor],
) -> list[SensorValue]:
    """Parse the values of tracked sensors from an endpoint state."""
    sensor_values: list[SensorValue] = []
    for feature_name, instance, feature_property in _iter_endpoint_properties(
        endpoint_state
    ):
        sensor_id: SensorId = (
            endpoint_id,
            feature_name,
            instance,
            feature_property.get("name") or "",
        )
        if (tracked := tracked_sensors.get(sensor_id)) is None:
            continue
        if (
            sensor := _parse_property(
                feature_property,
                feature_name=feature_name,
                instance=instance,
                sensor_definition=tracked.sensor_definition,
                serial_number=tracked.serial_number,
            )
        ) is None:
            continue
        sensor_values.append(SensorValue(tracked.serial_number, sensor))
    return sensor_values


def _is_older(sensor: AmazonDeviceSensor, current: AmazonDeviceSensor | None) -> bool:
    """Return True if a value was sampled before the one already held."""
    return bool(
        current is not None
        and sensor.time_of_sample
        and current.time_of_sample
        and sensor.time_of_sample < current.time_of_sample
    )


def _is_change(sensor: AmazonDeviceSensor, current: AmazonDeviceSensor | None) -> bool:
    """Return True if a value differs from the one already held.

    A newer sample of the same value is not a change, and an older sample
    is never stored, so it is not one either.
    """
    if current is None:
        return True
    if _is_older(sensor, current):
        return False
    return replace(sensor, time_of_sample=current.time_of_sample) != current


class AmazonSensorHandler:
    """Class to handle Amazon sensor functionality."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize AmazonSensorHandler class."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper

        self._sensors: dict[str, dict[str, AmazonDeviceSensor]] = {}
        # sensors we track, keyed by how Amazon identifies them
        self._tracked_sensors: dict[SensorId, _TrackedSensor] = {}
        # endpoints with at least one tracked sensor, to drop push events early
        self._endpoints: frozenset[str] = frozenset()
        # endpoints with at least one sensor Amazon does not push
        self._polled_endpoints: frozenset[str] = frozenset()

    @property
    def sensors(self) -> dict[str, dict[str, AmazonDeviceSensor]]:
        """Return sensors keyed by serial number, then sensor key."""
        return self._sensors

    def full_sensor_sync(
        self,
        devices: dict[str, AmazonDevice],
        endpoint_states: dict[str, dict[str, Any]],
    ) -> None:
        """Rebuild the sensors and tracked sensors from full endpoint states.

        Tracked sensors are the supported features of each device, values are
        filled in from the endpoint states.
        """
        sensors: dict[str, dict[str, AmazonDeviceSensor]] = {}
        tracked_sensors: dict[SensorId, _TrackedSensor] = {}
        missing: list[str] = []
        for serial_number, device in devices.items():
            if not device.endpoint_id:
                continue
            if (endpoint_state := endpoint_states.get(device.endpoint_id)) is None:
                missing.append(serial_number)
                continue

            device_tracked = dict(_tracked_sensors(device))
            tracked_sensors.update(device_tracked)

            previous = self._sensors.get(serial_number, {})
            device_sensors: dict[str, AmazonDeviceSensor] = {}
            for sensor_value in _parse_tracked_values(
                device.endpoint_id, endpoint_state, device_tracked
            ):
                sensor = sensor_value.sensor
                current = previous.get(sensor.name)
                device_sensors[sensor.name] = (
                    current if current and _is_older(sensor, current) else sensor
                )
            if device_sensors:
                sensors[serial_number] = device_sensors

        if missing:
            _LOGGER.error("Devices missing from sensor sync: %s", missing)

        self._sensors = sensors
        self._tracked_sensors = tracked_sensors
        self._endpoints = frozenset(sensor_id[0] for sensor_id in tracked_sensors)
        self._polled_endpoints = frozenset(
            sensor_id[0]
            for sensor_id, tracked in tracked_sensors.items()
            if tracked.feature_name in POLLED_SENSOR_FEATURES
        )

    async def update_polled_sensors(self) -> None:
        """Update the sensors Amazon does not push."""
        if not (polled_endpoints := self._polled_endpoints):
            return

        endpoint_states = await self._get_polled_sensor_states(list(polled_endpoints))
        polled: set[tuple[str, str]] = set()
        for endpoint_id, endpoint_state in endpoint_states.items():
            sensor_values = self.parse_endpoint_state(endpoint_id, endpoint_state)
            self.store_values(sensor_values)
            polled.update((v.serial_number, v.sensor.name) for v in sensor_values)

        if missing := self._polled_sensors() - polled:
            _LOGGER.warning("Sensors missing from poll: %s", sorted(missing))
            for serial_number, sensor_key in missing:
                if sensor := self._sensors.get(serial_number, {}).get(sensor_key):
                    sensor.error = True

    def _polled_sensors(self) -> set[tuple[str, str]]:
        """Return (serial number, sensor key) of every polled sensor."""
        return {
            (tracked.serial_number, tracked.sensor_definition.key)
            for tracked in self._tracked_sensors.values()
            if tracked.feature_name in POLLED_SENSOR_FEATURES
        }

    def is_tracked_endpoint(self, endpoint_id: str) -> bool:
        """Return True if the endpoint has at least one tracked sensor."""
        return endpoint_id in self._endpoints

    def parse_endpoint_state(
        self, endpoint_id: str, endpoint_state: dict[str, Any]
    ) -> list[SensorValue]:
        """Parse the values of tracked sensors from an endpoint state."""
        return _parse_tracked_values(endpoint_id, endpoint_state, self._tracked_sensors)

    def _stored(self, sensor_value: SensorValue) -> AmazonDeviceSensor | None:
        """Return the sensor currently held for a value."""
        return self._sensors.get(sensor_value.serial_number, {}).get(
            sensor_value.sensor.name
        )

    def has_changes(self, sensor_values: list[SensorValue]) -> bool:
        """Return True if any value differs from the sensor currently held."""
        return any(
            _is_change(sensor_value.sensor, self._stored(sensor_value))
            for sensor_value in sensor_values
        )

    def store_values(self, sensor_values: list[SensorValue]) -> None:
        """Store values, skipping any sampled before the sensor currently held."""
        for sensor_value in sensor_values:
            if _is_older(sensor_value.sensor, self._stored(sensor_value)):
                continue
            self._sensors.setdefault(sensor_value.serial_number, {})[
                sensor_value.sensor.name
            ] = sensor_value.sensor

    def update_device_online_statuses(self, devices: dict[str, AmazonDevice]) -> None:
        """Derive device online status from the reachability sensors."""
        for serial_number, device in devices.items():
            if reachability := self._sensors.get(serial_number, {}).get("reachability"):
                device.online = reachability.value == "OK"

        # base online status of speaker groups on their members
        for device in devices.values():
            if device.device_family == SPEAKER_GROUP_FAMILY:
                device.online = all(
                    d.online
                    for d in devices.values()
                    if d.serial_number in device.device_cluster_members
                )

    async def _get_polled_sensor_states(
        self, endpoint_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Retrieve the polled sensor states of the given endpoints, keyed by ID."""
        payload = [
            {
                "operationName": "getPolledSensorState",
                "variables": {
                    "endpointIds": endpoint_ids,
                },
                "query": QUERY_POLLED_SENSOR_STATE,
            }
        ]

        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=URL.joinpath(
                self._session_state_data.alexa_website_url, URI_NEXUS_GRAPHQL
            ),
            input_data=payload,
            json_data=True,
            extended_headers={"User-Agent": REQUEST_AGENT["Amazon"]},
        )

        sensors_state = await self._http_wrapper.response_to_json(raw_resp, "sensors")

        if check_and_log_graphql_errors("QUERY_POLLED_SENSOR_STATE", sensors_state):
            # Explicit error in returned data
            return {}

        if not (
            endpoints := validate_graphql_endpoint_shape(
                "QUERY_POLLED_SENSOR_STATE", sensors_state
            )
        ):
            return {}

        return {
            endpoint["endpointId"]: endpoint
            for endpoint in endpoints
            if endpoint.get("endpointId")
        }
