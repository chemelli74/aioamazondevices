# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for sensor state parsing in AmazonSensorHandler."""

from collections.abc import Callable
from typing import Any

import pytest

from aioamazondevices.implementation.sensor import _get_device_sensor_state
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1

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
    sensors = _get_device_sensor_state(
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
    sensors = _get_device_sensor_state(
        _temperature_endpoint("temperatureValue"), make_device(TEST_SERIAL_1)
    )

    assert sensors == {}
    assert "ignored due to errors in feature" in caplog.text
