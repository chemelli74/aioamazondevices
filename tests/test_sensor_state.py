# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for sensor state parsing in AmazonSensorHandler."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.devices import DEVICE_TYPE_AQM
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


def _motion_property(
    name: str, typename: str, value_key: str, value: str
) -> dict[str, Any]:
    """Build a motion sensor property."""
    return {
        "name": name,
        "type": "RETRIEVABLE",
        "error": None,
        "__typename": typename,
        value_key: value,
    }


@pytest.mark.anyio
async def test_motion_sensor_properties_are_read(
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., dict[str, AmazonDeviceSensor]],
) -> None:
    """Every templated motion sensor property is parsed into its own sensor."""
    endpoint = {
        "features": [
            {
                "name": "motionSensor",
                "instance": None,
                "properties": [
                    _motion_property(
                        "detectionState",
                        "DetectionState",
                        "detectionStateValue",
                        "NOT_DETECTED",
                    ),
                    _motion_property(
                        "detectionRange",
                        "DetectionRange",
                        "detectionRangeValue",
                        "HIGH",
                    ),
                    _motion_property(
                        "detectionSensitivity",
                        "DetectionSensitivity",
                        "detectionSensitivityValue",
                        "MEDIUM",
                    ),
                    _motion_property(
                        "detectionTechnology",
                        "DetectionTechnology",
                        "detectionTechnologyValue",
                        "ULTRASONIC_BASIC",
                    ),
                    _motion_property(
                        "enablement",
                        "EnablementState",
                        "enablementStateValue",
                        "DISABLED",
                    ),
                ],
            }
        ]
    }

    sensors = sync_sensors(endpoint, make_device(TEST_SERIAL_1))

    assert {key: sensor.value for key, sensor in sensors.items()} == {
        "detectionState": "NOT_DETECTED",
        "detectionRange": "HIGH",
        "detectionSensitivity": "MEDIUM",
        "detectionTechnology": "ULTRASONIC_BASIC",
        "enablement": "DISABLED",
    }


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
