# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for sensor state parsing in AmazonSensorHandler."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.devices import DEVICE_TYPE_AQM, DEVICE_TYPE_THERMOSTAT
from aioamazondevices.const.http import ARRAY_WRAPPER
from aioamazondevices.implementation import feature_property_definitions
from aioamazondevices.structures import AmazonDevice, AmazonDeviceSensor

from .const import TEST_SERIAL_1

TEST_TEMPERATURE = 21.3
TEST_RANGE_VALUE = 42


def _temperature_endpoint(value_key: str) -> dict[str, Any]:
    """Build a temperature value under the given property key."""
    return {
        "features": [
            {
                "name": "temperatureSensor",
                "instance": None,
                "properties": [
                    {
                        "name": "temperature",
                        "type": "RETRIEVABLE",
                        "error": None,
                        "__typename": "TemperatureSensor",
                        value_key: {"value": TEST_TEMPERATURE, "scale": "CELSIUS"},
                    }
                ],
            }
        ]
    }


@pytest.mark.anyio
async def test_sensor_value_is_read(
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., dict[str, AmazonDeviceSensor]],
) -> None:
    """A value under the expected key is parsed."""
    sensors = sync_sensors(_temperature_endpoint("value"), make_device(TEST_SERIAL_1))

    assert sensors["temperature"].value == TEST_TEMPERATURE
    assert sensors["temperature"].scale == "CELSIUS"
    assert not sensors["temperature"].error


def _empty_temperature_endpoint() -> dict[str, Any]:
    """Build a temperature property without a value."""
    endpoint = _temperature_endpoint("value")
    endpoint["features"][0]["properties"][0]["value"] = None
    return endpoint


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("endpoint", "message"),
    [
        pytest.param(
            _temperature_endpoint("temperatureValue"),
            "ignored due to errors in feature",
            id="unreadable",
        ),
        pytest.param(
            _empty_temperature_endpoint(), "ignored due to empty value", id="empty"
        ),
    ],
)
async def test_unusable_sensor_value_is_skipped(
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., dict[str, AmazonDeviceSensor]],
    caplog: pytest.LogCaptureFixture,
    endpoint: dict[str, Any],
    message: str,
) -> None:
    """A value we cannot use is dropped, not reported as a valid 'n/a'."""
    sensors = sync_sensors(endpoint, make_device(TEST_SERIAL_1))

    assert sensors == {}
    assert message in caplog.text


def _make_typed_device(
    make_device: Callable[..., AmazonDevice], device_type: str
) -> AmazonDevice:
    """Build a test device with the given device type."""
    device = make_device(TEST_SERIAL_1)
    device.device_type = device_type
    return device


def _range_endpoint(instance: str) -> dict[str, Any]:
    """Build a range value for the given instance."""
    return {
        "features": [
            {
                "name": "range",
                "instance": instance,
                "properties": [
                    {
                        "name": "rangeValue",
                        "type": "RETRIEVABLE",
                        "error": None,
                        "__typename": "RangeValue",
                        "rangeValue": {"value": TEST_RANGE_VALUE},
                    }
                ],
            }
        ]
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("endpoint", "device_type"),
    [
        pytest.param(
            {"features": [{"name": "unknownFeature", "properties": []}]},
            "A1B2C3",
            id="unknown-feature",
        ),
        pytest.param(_range_endpoint("99"), DEVICE_TYPE_AQM, id="unknown-instance"),
        pytest.param(_range_endpoint("4"), "A1B2C3", id="other-device-type"),
    ],
)
async def test_untemplated_sensor_is_skipped(
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., dict[str, AmazonDeviceSensor]],
    endpoint: dict[str, Any],
    device_type: str,
) -> None:
    """Features, instances and device types without a template are ignored."""
    sensors = sync_sensors(endpoint, _make_typed_device(make_device, device_type))

    assert sensors == {}


@pytest.mark.anyio
async def test_device_specific_sensor_uses_override(
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., dict[str, AmazonDeviceSensor]],
) -> None:
    """A device type specific instance takes its name and scale from the override."""
    sensors = sync_sensors(
        _range_endpoint("4"),
        _make_typed_device(make_device, DEVICE_TYPE_AQM),
    )

    assert sensors["Humidity"].value == TEST_RANGE_VALUE
    assert sensors["Humidity"].scale == "%"
    assert sensors["Humidity"].feature_name == "range"
    assert sensors["Humidity"].property_name == "rangeValue"
    assert sensors["Humidity"].instance == "4"


def _setpoint(name: str, value: float) -> dict[str, Any]:
    """Build a thermostat setpoint property."""
    return {
        "name": name,
        "error": None,
        "__typename": "Setpoint",
        "value": {"value": value, "scale": "FAHRENHEIT"},
    }


TEST_ALLOWED_TEMPERATURE_RANGE = {
    "heating": {
        "minimum": {"value": 40.0, "scale": "FAHRENHEIT"},
        "maximum": {"value": 87.0, "scale": "FAHRENHEIT"},
    },
    "cooling": {
        "minimum": {"value": 43.0, "scale": "FAHRENHEIT"},
        "maximum": {"value": 90.0, "scale": "FAHRENHEIT"},
    },
}


def _thermostat_endpoint() -> dict[str, Any]:
    """Build the thermostat features of an Amazon Smart Thermostat."""
    return {
        "features": [
            {
                "name": "thermostat",
                "instance": None,
                "properties": [
                    _setpoint("upperSetpoint", 73.0),
                    # properties without a template are ignored
                    {
                        "name": "adaptiveRecoveryStatus",
                        "error": None,
                        "__typename": "AdaptiveRecoveryStatus",
                    },
                    _setpoint("targetSetpoint", 62.0),
                    _setpoint("lowerSetpoint", 65.0),
                    {
                        "name": "thermostatMode",
                        "error": None,
                        "__typename": "ThermostatMode",
                        "thermostatModeValue": "AUTO",
                    },
                ],
            },
            {
                "name": "thermostatConfiguration",
                "instance": None,
                "properties": [
                    {
                        "name": "allowedTemperatureRange",
                        "error": None,
                        "__typename": "ThermostatConfigurationAllowedTemperatureRange",
                        "thermostatAllowedTemperatureRangeValue": (
                            TEST_ALLOWED_TEMPERATURE_RANGE
                        ),
                    },
                ],
            },
        ]
    }


@pytest.mark.anyio
async def test_thermostat_sensors_are_read(
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., dict[str, AmazonDeviceSensor]],
) -> None:
    """Thermostat properties are keyed by property name, scale read from value."""
    sensors = sync_sensors(
        _thermostat_endpoint(),
        _make_typed_device(make_device, DEVICE_TYPE_THERMOSTAT),
    )

    assert {key: (sensor.value, sensor.scale) for key, sensor in sensors.items()} == {
        "upperSetpoint": (73.0, "FAHRENHEIT"),
        "targetSetpoint": (62.0, "FAHRENHEIT"),
        "lowerSetpoint": (65.0, "FAHRENHEIT"),
        "thermostatMode": ("AUTO", None),
        "allowedTemperatureRange": (TEST_ALLOWED_TEMPERATURE_RANGE, None),
    }


@pytest.mark.anyio
async def test_device_specific_sensor_without_name_uses_fallback(
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., dict[str, AmazonDeviceSensor]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An override without a name is keyed by property name and instance."""
    monkeypatch.setitem(
        feature_property_definitions.SPECIFIC_SENSORS,
        "TESTTYPE",
        {"range": {"1": {"scale": "ppm"}}},
    )

    sensors = sync_sensors(
        _range_endpoint("1"),
        _make_typed_device(make_device, "TESTTYPE"),
    )

    assert sensors["rangeValue-1"].value == TEST_RANGE_VALUE
    assert sensors["rangeValue-1"].scale == "ppm"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "message"),
    [
        pytest.param(
            {"errors": [{"message": "Boom", "path": ["listEndpoints"]}]},
            "Error running query: QUERY_POLLED_SENSOR_STATE - Boom",
            id="graphql-errors",
        ),
        pytest.param(
            {ARRAY_WRAPPER: [{"data": {"listEndpoints": None}}]},
            "Malformed endpoint data received in QUERY_POLLED_SENSOR_STATE",
            id="malformed",
        ),
    ],
)
async def test_bad_endpoint_states_response_returns_nothing(
    api: AmazonEchoApi,
    caplog: pytest.LogCaptureFixture,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    response: dict[str, Any],
    message: str,
) -> None:
    """GraphQL errors and malformed responses are logged, returning no states."""
    mock_json_response(response)

    assert await api._sensor_handler._get_polled_sensor_states(["endpoint-1"]) == {}
    assert message in caplog.text


@pytest.mark.anyio
async def test_endpoint_states_are_keyed_by_endpoint_id(
    api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """Endpoint states are keyed by endpoint ID, skipping those without one."""
    endpoint = {"endpointId": "endpoint-1", "features": []}
    response = {
        ARRAY_WRAPPER: [
            {"data": {"listEndpoints": {"endpoints": [endpoint, {"features": []}]}}}
        ]
    }
    mock_json_response(response)

    assert await api._sensor_handler._get_polled_sensor_states(["endpoint-1"]) == {
        "endpoint-1": endpoint
    }
