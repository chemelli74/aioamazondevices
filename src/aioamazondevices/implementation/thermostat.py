# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Thermostat control module for Amazon devices."""

from http import HTTPMethod
from typing import Any

from yarl import URL

from aioamazondevices.const.http import ARRAY_WRAPPER, REQUEST_AGENT, URI_NEXUS_GRAPHQL
from aioamazondevices.const.queries import MUTATION_SET_ENDPOINT_FEATURE
from aioamazondevices.exceptions import CannotSetThermostat
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonDevice
from aioamazondevices.utils import _LOGGER, format_graphql_error

# Feature "thermostat" carries several differently-named properties at once,
# unlike single-property sensors (see const/metadata.py's SENSORS), so it is
# keyed by property name instead.
THERMOSTAT_SENSORS: dict[str, dict[str, str | None]] = {
    "targetSetpoint": {
        "key": "value",
        "subkey": "value",
        "scale": "scale",
    },
    "upperSetpoint": {
        "key": "value",
        "subkey": "value",
        "scale": "scale",
    },
    "lowerSetpoint": {
        "key": "value",
        "subkey": "value",
        "scale": "scale",
    },
    "thermostatMode": {
        "key": "thermostatModeValue",
        "subkey": None,
        "scale": None,
    },
}


def extract_thermostat_sensors(feature: dict[str, Any]) -> dict[str, Any]:
    """Extract raw setpoint/mode values from a thermostat feature block."""
    data: dict[str, Any] = {}
    for feature_property in feature.get("properties") or []:
        property_name = feature_property.get("name")
        if (sensor_template := THERMOSTAT_SENSORS.get(property_name)) is None:
            continue
        if feature_property.get("error"):
            continue

        value_raw = feature_property.get(sensor_template["key"])
        if not value_raw:
            continue

        if scale_template := sensor_template["scale"]:
            data.setdefault("temperatureScale", value_raw[scale_template])
        data[property_name] = (
            value_raw[subkey_template]
            if (subkey_template := sensor_template["subkey"])
            else value_raw
        )

    supported_modes = (feature.get("configuration") or {}).get("supportedModes")
    if supported_modes:
        data["supportedModes"] = supported_modes

    return data


def extract_thermostat_configuration_sensors(feature: dict[str, Any]) -> dict[str, Any]:
    """Extract the allowed heating/cooling temperature range values."""
    data: dict[str, Any] = {}
    for feature_property in feature.get("properties") or []:
        if feature_property.get("name") != "allowedTemperatureRange":
            continue
        if feature_property.get("error"):
            continue

        allowed_range = (
            feature_property.get("thermostatAllowedTemperatureRangeValue") or {}
        )
        for hvac_mode in ("heating", "cooling"):
            mode_range = allowed_range.get(hvac_mode) or {}
            for bound in ("minimum", "maximum"):
                bound_value = mode_range.get(bound)
                if not bound_value:
                    continue
                data[f"{hvac_mode}{bound.title()}Temperature"] = bound_value["value"]
                data.setdefault("temperatureScale", bound_value.get("scale"))

    return data


class AmazonThermostatHandler:
    """Class to handle Amazon thermostat control functionality."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize AmazonThermostatHandler class."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper

    async def set_thermostat_mode(self, device: AmazonDevice, mode: str) -> None:
        """Set the thermostat's HVAC mode (e.g. HEAT, COOL, AUTO, OFF)."""
        await self._set_endpoint_feature(
            device, "thermostat", "setThermostatMode", {"thermostatMode": mode}
        )

    async def set_target_setpoint(
        self, device: AmazonDevice, value: float, scale: str
    ) -> None:
        """Set a single target temperature (HEAT/COOL mode)."""
        await self._set_endpoint_feature(
            device,
            "thermostat",
            "setTargetSetpoint",
            {"targetSetpoint": {"value": _format_temperature(value), "scale": scale}},
        )

    async def set_setpoint_range(
        self, device: AmazonDevice, lower: float, upper: float, scale: str
    ) -> None:
        """Set the heat/cool target range in one mutation (AUTO mode)."""
        await self._set_endpoint_feature(
            device,
            "thermostat",
            "setTargetSetpoint",
            {
                "lowerSetpoint": {
                    "value": _format_temperature(lower),
                    "scale": scale,
                },
                "upperSetpoint": {
                    "value": _format_temperature(upper),
                    "scale": scale,
                },
            },
        )

    async def _set_endpoint_feature(
        self,
        device: AmazonDevice,
        feature_name: str,
        operation_name: str,
        payload: dict[str, Any],
    ) -> None:
        """Send a setEndpointFeatures mutation and raise on failure."""
        if not device.endpoint_id:
            raise CannotSetThermostat(
                f"No endpoint ID for device {device.account_name}"
            )

        request = {
            "endpointId": device.endpoint_id,
            "featureName": feature_name,
            "featureOperationName": operation_name,
            "payload": payload,
        }
        input_data = [
            {
                "operationName": "setEndpointFeature",
                "variables": {"featureControlRequests": [request]},
                "query": MUTATION_SET_ENDPOINT_FEATURE,
            }
        ]

        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=URL.joinpath(
                self._session_state_data.alexa_website_url, URI_NEXUS_GRAPHQL
            ),
            input_data=input_data,
            json_data=True,
            extended_headers={"User-Agent": REQUEST_AGENT["Amazon"]},
        )
        response = await self._http_wrapper.response_to_json(
            raw_resp, "setEndpointFeature"
        )

        if format_graphql_error(response):
            raise CannotSetThermostat(
                f"Failed to {operation_name} for {device.account_name}"
            )

        arr = response.get(ARRAY_WRAPPER) or []
        errors = (
            arr[0].get("data", {}).get("setEndpointFeatures", {}).get("errors")
            if arr
            else None
        )
        if errors:
            _LOGGER.error(
                "Thermostat control error for %s: %s", device.account_name, errors
            )
            raise CannotSetThermostat(
                f"Amazon rejected {operation_name} for {device.account_name}: {errors}"
            )


def _format_temperature(value: float) -> str:
    """Format a temperature the way Amazon's mutation expects."""
    if float(value).is_integer():
        return str(int(value))
    return str(value)
