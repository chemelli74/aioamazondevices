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


@pytest.mark.anyio
async def test_sensor_template_name_override(
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A template name replaces the property name as the sensor name."""
    monkeypatch.setitem(
        sensor_module.SENSOR_TEMPLATES,
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
    assert sensors["Humidity"].property_name == "rangeValue"
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
