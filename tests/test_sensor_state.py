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
from aioamazondevices.implementation.sensor import (
    AmazonSensorHandler,
    parse_graphql_feature_to_sensor,
)
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


@pytest.mark.anyio
async def test_sensor_template_name_override(
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A template name replaces the property name as the sensor name."""
    monkeypatch.setitem(
        feature_property_definitions.SENSOR_TEMPLATES,
        "temperatureSensor",
        {
            "temperature": {
                "key": "value",
                "subkey": "value",
                "scale": "scale",
                "name": "Room Temperature",
            }
        },
    )

    sensors = parse_graphql_feature_to_sensor(
        _temperature_endpoint("value"), make_device(TEST_SERIAL_1)
    )

    assert list(sensors) == ["Room Temperature"]
    assert sensors["Room Temperature"].name == "Room Temperature"
    assert sensors["Room Temperature"].value == TEST_TEMPERATURE
    assert sensors["Room Temperature"].property_name == "temperature"


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
def test_untemplated_sensor_is_skipped(
    make_device: Callable[..., AmazonDevice],
    endpoint: dict[str, Any],
    device_type: str,
) -> None:
    """Features, instances and device types without a template are ignored."""
    sensors = parse_graphql_feature_to_sensor(
        endpoint, _make_typed_device(make_device, device_type)
    )

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
    assert sensors["Humidity"].property_name == "rangeValue"
    assert sensors["Humidity"].instance == "4"


@pytest.mark.anyio
async def test_device_specific_sensor_without_name_uses_fallback(
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An override without a name is keyed by property name and instance."""
    monkeypatch.setitem(
        feature_property_definitions.SPECIFIC_SENSORS,
        "TESTTYPE",
        {"range": {"1": {"scale": "ppm"}}},
    )

    sensors = parse_graphql_feature_to_sensor(
        _range_endpoint("1"),
        _make_typed_device(make_device, "TESTTYPE"),
    )

    assert sensors["rangeValue-1"].value == TEST_RANGE_VALUE
    assert sensors["rangeValue-1"].scale == "ppm"


@pytest.fixture
def endpoint_handler(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> AmazonSensorHandler:
    """Return a sensor handler with one device on endpoint-1."""
    handler = api._sensor_handler
    device = make_device(TEST_SERIAL_1)
    device.endpoint_id = "endpoint-1"
    handler._final_devices = {TEST_SERIAL_1: device}
    return handler


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "message"),
    [
        pytest.param(
            {"errors": [{"message": "Boom", "path": ["listEndpoints"]}]},
            "Error running query: QUERY_SENSOR_STATE - Boom",
            id="graphql-errors",
        ),
        pytest.param(
            {ARRAY_WRAPPER: [{"data": {"listEndpoints": None}}]},
            "Malformed endpoint data received in QUERY_SENSOR_STATE",
            id="malformed",
        ),
    ],
)
async def test_bad_endpoint_states_response_returns_nothing(
    endpoint_handler: AmazonSensorHandler,
    caplog: pytest.LogCaptureFixture,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    response: dict[str, Any],
    message: str,
) -> None:
    """GraphQL errors and malformed responses are logged, returning no states."""
    mock_json_response(response)

    assert await endpoint_handler._get_endpoint_states() == {}
    assert message in caplog.text


@pytest.mark.anyio
async def test_endpoint_states_are_keyed_by_endpoint_id(
    endpoint_handler: AmazonSensorHandler,
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

    assert await endpoint_handler._get_endpoint_states() == {"endpoint-1": endpoint}
