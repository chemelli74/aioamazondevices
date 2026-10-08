# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for sensor state parsing in AmazonSensorHandler."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.implementation.sensor import parse_graphql_feature_to_sensor
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1

TEST_ENDPOINT_ID = "endpoint-1"
TEST_TEMPERATURE = 21.3


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
async def test_update_sensor_data_parses_endpoint_state(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
) -> None:
    """Endpoint states are matched to devices by endpoint ID and parsed."""
    device = make_device(TEST_SERIAL_1)
    device.endpoint_id = TEST_ENDPOINT_ID
    handler = api._sensor_handler

    with patch.object(
        handler,
        "_get_endpoint_states",
        AsyncMock(return_value={TEST_ENDPOINT_ID: _temperature_endpoint("value")}),
    ):
        await handler.update_sensor_data({TEST_SERIAL_1: device}, None, {})

    assert device.sensors["temperature"].value == TEST_TEMPERATURE


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
