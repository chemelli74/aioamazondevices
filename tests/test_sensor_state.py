# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for sensor state parsing in AmazonSensorHandler."""

import re
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.devices import DEVICE_TYPE_AQM
from aioamazondevices.const.http import ARRAY_WRAPPER
from aioamazondevices.const.queries import QUERY_SENSOR_STATE
from aioamazondevices.const.sensors import SENSOR_TEMPLATES
from aioamazondevices.implementation import sensor as sensor_module
from aioamazondevices.implementation.sensor import parse_graphql_feature_to_sensor
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1

TEST_TEMPERATURE = 21.3
TEST_RANGE_VALUE = 42


def _temperature_endpoint(value_key: str) -> dict[str, Any]:
    """Build a temperature reading under the given property key."""
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
) -> None:
    """A reading under the expected key is parsed."""
    sensors = parse_graphql_feature_to_sensor(
        _temperature_endpoint("value"), make_device(TEST_SERIAL_1)
    )

    assert sensors["temperature"].value == TEST_TEMPERATURE
    assert sensors["temperature"].scale == "CELSIUS"
    assert not sensors["temperature"].error


@pytest.mark.anyio
async def test_unreadable_sensor_is_skipped(
    make_device: Callable[..., AmazonDevice],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A reading we cannot parse is dropped, not reported as a valid 'n/a'."""
    sensors = parse_graphql_feature_to_sensor(
        _temperature_endpoint("temperatureValue"), make_device(TEST_SERIAL_1)
    )

    assert sensors == {}
    assert "ignored due to errors in feature" in caplog.text


def _make_typed_device(
    make_device: Callable[..., AmazonDevice], device_type: str
) -> AmazonDevice:
    """Build a test device with the given device type."""
    device = make_device(TEST_SERIAL_1)
    device.device_type = device_type
    return device


def _range_endpoint(instance: str) -> dict[str, Any]:
    """Build a range reading for the given instance."""
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


@pytest.mark.parametrize(
    "value_key",
    sorted(
        {
            template["key"]
            for properties in SENSOR_TEMPLATES.values()
            for template in properties.values()
            if template["key"]
        }
    ),
)
def test_sensor_template_key_is_queried(value_key: str) -> None:
    """Every sensor template value key is requested by the sensor state query."""
    assert re.search(rf"\b{value_key}\b", QUERY_SENSOR_STATE)


@pytest.mark.anyio
async def test_motion_sensor_properties_are_read(
    make_device: Callable[..., AmazonDevice],
) -> None:
    """All motion sensor properties are parsed, using the API property names."""
    values = {
        ("detectionState", "DetectionState"): "DETECTED",
        ("detectionSensitivity", "DetectionSensitivity"): "MEDIUM",
        ("enablement", "EnablementState"): "ENABLED",
        ("detectionRange", "DetectionRange"): "HIGH",
        ("detectionTechnology", "DetectionTechnology"): "ULTRASONIC_BASIC",
    }
    endpoint = {
        "features": [
            {
                "name": "motionSensor",
                "instance": None,
                "properties": [
                    {
                        "name": name,
                        "type": "RETRIEVABLE",
                        "error": None,
                        "__typename": typename,
                        f"{typename[0].lower()}{typename[1:]}Value": value,
                    }
                    for (name, typename), value in values.items()
                ],
            }
        ]
    }

    sensors = parse_graphql_feature_to_sensor(endpoint, make_device(TEST_SERIAL_1))

    assert {name: sensor.value for name, sensor in sensors.items()} == {
        name: value for (name, _), value in values.items()
    }


@pytest.mark.anyio
async def test_aqm_led_toggle_is_read(
    make_device: Callable[..., AmazonDevice],
) -> None:
    """The AQM LED toggle instance is exposed as a named sensor."""
    endpoint = {
        "features": [
            {
                "name": "toggle",
                "instance": "11",
                "properties": [
                    {
                        "name": "toggleState",
                        "type": "RETRIEVABLE",
                        "error": None,
                        "__typename": "ToggleState",
                        "toggleStateValue": "ON",
                    }
                ],
            }
        ]
    }

    sensors = parse_graphql_feature_to_sensor(
        endpoint, _make_typed_device(make_device, DEVICE_TYPE_AQM)
    )

    assert sensors["LED"].value == "ON"
    assert sensors["LED"].feature_name == "toggle"
    assert sensors["LED"].instance == "11"


@pytest.mark.anyio
async def test_unknown_feature_is_skipped(
    make_device: Callable[..., AmazonDevice],
) -> None:
    """A feature with no sensor template is ignored."""
    endpoint = {"features": [{"name": "unknownFeature", "properties": []}]}

    sensors = parse_graphql_feature_to_sensor(endpoint, make_device(TEST_SERIAL_1))

    assert sensors == {}


@pytest.mark.anyio
async def test_device_specific_sensor_uses_override(
    make_device: Callable[..., AmazonDevice],
) -> None:
    """A device type specific instance takes its name and scale from the override."""
    sensors = parse_graphql_feature_to_sensor(
        _range_endpoint("4"),
        _make_typed_device(make_device, DEVICE_TYPE_AQM),
    )

    assert sensors["Humidity"].value == TEST_RANGE_VALUE
    assert sensors["Humidity"].scale == "%"
    assert sensors["Humidity"].feature_name == "range"
    assert sensors["Humidity"].instance == "4"


@pytest.mark.anyio
async def test_device_specific_sensor_unknown_instance_is_skipped(
    make_device: Callable[..., AmazonDevice],
) -> None:
    """An instance not listed for the device type is ignored."""
    sensors = parse_graphql_feature_to_sensor(
        _range_endpoint("99"),
        _make_typed_device(make_device, DEVICE_TYPE_AQM),
    )

    assert sensors == {}


@pytest.mark.anyio
async def test_device_specific_sensor_other_device_type_is_skipped(
    make_device: Callable[..., AmazonDevice],
) -> None:
    """A non generic feature is ignored on device types that do not enable it."""
    sensors = parse_graphql_feature_to_sensor(
        _range_endpoint("4"), make_device(TEST_SERIAL_1)
    )

    assert sensors == {}


@pytest.mark.anyio
async def test_device_specific_sensor_without_name_uses_fallback(
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An override without a name is keyed by property name and instance."""
    monkeypatch.setitem(
        sensor_module.SPECIFIC_SENSORS,
        "TESTTYPE",
        {"range": {"1": {"scale": "ppm"}}},
    )

    sensors = parse_graphql_feature_to_sensor(
        _range_endpoint("1"),
        _make_typed_device(make_device, "TESTTYPE"),
    )

    assert sensors["rangeValue-1"].value == TEST_RANGE_VALUE
    assert sensors["rangeValue-1"].scale == "ppm"


@pytest.mark.anyio
async def test_endpoint_states_graphql_errors_return_nothing(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """GraphQL errors are logged and no sensor states are returned."""
    handler = api._sensor_handler
    device = make_device(TEST_SERIAL_1)
    device.endpoint_id = "endpoint-1"
    handler._final_devices = {TEST_SERIAL_1: device}
    response = {"errors": [{"message": "Boom", "path": ["listEndpoints"]}]}
    handler._http_wrapper.session_request = AsyncMock(return_value=(None, None))  # type: ignore[method-assign]
    handler._http_wrapper.response_to_json = AsyncMock(return_value=response)  # type: ignore[method-assign]

    assert await handler._get_endpoint_states() == {}
    assert "Error running query: QUERY_SENSOR_STATE - Boom" in caplog.text


@pytest.mark.anyio
async def test_endpoint_states_malformed_returns_nothing(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A response without endpoints is logged as malformed."""
    handler = api._sensor_handler
    device = make_device(TEST_SERIAL_1)
    device.endpoint_id = "endpoint-1"
    handler._final_devices = {TEST_SERIAL_1: device}
    response = {ARRAY_WRAPPER: [{"data": {"listEndpoints": None}}]}
    handler._http_wrapper.session_request = AsyncMock(return_value=(None, None))  # type: ignore[method-assign]
    handler._http_wrapper.response_to_json = AsyncMock(return_value=response)  # type: ignore[method-assign]

    assert await handler._get_endpoint_states() == {}
    assert "Malformed endpoint data received in QUERY_SENSOR_STATE" in caplog.text


@pytest.mark.anyio
async def test_endpoint_states_are_keyed_by_endpoint_id(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
) -> None:
    """Endpoint states are keyed by endpoint ID, skipping those without one."""
    handler = api._sensor_handler
    device = make_device(TEST_SERIAL_1)
    device.endpoint_id = "endpoint-1"
    handler._final_devices = {TEST_SERIAL_1: device}
    endpoint = {"endpointId": "endpoint-1", "features": []}
    response = {
        ARRAY_WRAPPER: [
            {"data": {"listEndpoints": {"endpoints": [endpoint, {"features": []}]}}}
        ]
    }
    handler._http_wrapper.session_request = AsyncMock(return_value=(None, None))  # type: ignore[method-assign]
    handler._http_wrapper.response_to_json = AsyncMock(return_value=response)  # type: ignore[method-assign]

    assert await handler._get_endpoint_states() == {"endpoint-1": endpoint}
