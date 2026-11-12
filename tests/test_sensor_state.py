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

from .const import TEST_DEVICE_TYPE, TEST_SERIAL_1

TEST_TEMPERATURE = 21.3
TEST_RANGE_VALUE = 42


def _temperature_endpoint(
    value_key: str,
    value: float = TEST_TEMPERATURE,
    scale: str = "CELSIUS",
) -> dict[str, Any]:
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
                        value_key: {"value": value, "scale": scale},
                    }
                ],
            }
        ]
    }


def _empty_temperature_endpoint() -> dict[str, Any]:
    """Build a temperature property without a value."""
    endpoint = _temperature_endpoint("value")
    endpoint["features"][0]["properties"][0]["value"] = None
    return endpoint


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
async def test_sensor_value_is_read(
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., dict[str, AmazonDeviceSensor]],
) -> None:
    """A value under the expected key is parsed."""
    sensors = sync_sensors(_temperature_endpoint("value"), make_device(TEST_SERIAL_1))

    assert sensors["temperature"].value == TEST_TEMPERATURE
    assert sensors["temperature"].scale == "CELSIUS"
    assert not sensors["temperature"].error


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("value", "scale", "expected"),
    [
        pytest.param(19, "CELSIUS", (False, None), id="19-celsius"),
        pytest.param(70, "FAHRENHEIT", (False, None), id="70-fahrenheit"),
        pytest.param(-279, "CELSIUS", (False, None), id="minus-279-celsius"),
        pytest.param(
            -280, "CELSIUS", (True, "INVALID_TEMPERATURE"), id="minus-280-celsius"
        ),
        pytest.param(
            -300, "CELSIUS", (True, "INVALID_TEMPERATURE"), id="minus-300-celsius"
        ),
        pytest.param(
            -280, "FAHRENHEIT", (True, "INVALID_TEMPERATURE"), id="minus-280-fahrenheit"
        ),
    ],
)
async def test_temperature_calibration_value_is_an_error(
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., dict[str, AmazonDeviceSensor]],
    value: float,
    scale: str,
    expected: tuple[bool, str | None],
) -> None:
    """Temperatures at or below the calibration placeholder are errors.

    The raw value is kept either way.
    """
    sensors = sync_sensors(
        _temperature_endpoint("value", value, scale), make_device(TEST_SERIAL_1)
    )

    sensor = sensors["temperature"]
    assert sensor.value == value
    assert (sensor.error, sensor.error_type) == expected


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


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("endpoint", "device_type"),
    [
        pytest.param(
            {"features": [{"name": "unknownFeature", "properties": []}]},
            TEST_DEVICE_TYPE,
            id="unknown-feature",
        ),
        pytest.param(_range_endpoint("99"), DEVICE_TYPE_AQM, id="unknown-instance"),
        pytest.param(_range_endpoint("4"), TEST_DEVICE_TYPE, id="other-device-type"),
    ],
)
async def test_untemplated_sensor_is_skipped(
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., dict[str, AmazonDeviceSensor]],
    endpoint: dict[str, Any],
    device_type: str,
) -> None:
    """Features, instances and device types without a template are ignored."""
    sensors = sync_sensors(
        endpoint, make_device(TEST_SERIAL_1, device_type=device_type)
    )

    assert sensors == {}


@pytest.mark.anyio
async def test_device_specific_sensor_uses_override(
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., dict[str, AmazonDeviceSensor]],
) -> None:
    """A device type specific instance takes its name and scale from the override."""
    sensors = sync_sensors(
        _range_endpoint("4"),
        make_device(TEST_SERIAL_1, device_type=DEVICE_TYPE_AQM),
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
        make_device(TEST_SERIAL_1, device_type="TESTTYPE"),
    )

    assert sensors["rangeValue-1"].value == TEST_RANGE_VALUE
    assert sensors["rangeValue-1"].scale == "ppm"


@pytest.mark.anyio
async def test_device_specific_sensor_without_scale_keeps_value_scale(
    make_device: Callable[..., AmazonDevice],
    sync_sensors: Callable[..., dict[str, AmazonDeviceSensor]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An override without a scale keeps the scale read from the value."""
    monkeypatch.setitem(
        feature_property_definitions.SENSOR_TEMPLATES,
        "testSensor",
        feature_property_definitions.SENSOR_TEMPLATES["temperatureSensor"],
    )
    monkeypatch.setitem(
        feature_property_definitions.SPECIFIC_SENSORS,
        "TESTTYPE",
        {"testSensor": {"": {}}},
    )
    endpoint = _temperature_endpoint("value")
    endpoint["features"][0]["name"] = "testSensor"

    sensors = sync_sensors(endpoint, make_device(TEST_SERIAL_1, device_type="TESTTYPE"))

    assert sensors["temperature"].value == TEST_TEMPERATURE
    assert sensors["temperature"].scale == "CELSIUS"


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
