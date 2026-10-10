# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for timeOfSample handling in AmazonSensorHandler."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from aioamazondevices.implementation.sensor import _get_device_sensor_state
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1


def _illuminance_endpoint(time_of_sample: str | int | None = None) -> dict[str, Any]:
    property_data: dict[str, Any] = {
        "name": "illuminance",
        "illuminanceValue": {"value": 42.0},
        "error": None,
    }
    if time_of_sample is not None:
        property_data["timeOfSample"] = time_of_sample

    return {
        "features": [
            {
                "name": "lightSensor",
                "instance": None,
                "properties": [property_data],
            }
        ]
    }


@pytest.mark.anyio
async def test_time_of_sample_is_parsed(
    make_device: Callable[..., AmazonDevice],
) -> None:
    """A well-formed timeOfSample is parsed into an aware datetime."""
    device = make_device(TEST_SERIAL_1)

    sensors = _get_device_sensor_state(
        _illuminance_endpoint(time_of_sample="2026-09-12T08:09:17.922Z"), device
    )

    assert sensors["illuminance"].time_of_sample == datetime(
        2026, 9, 12, 8, 9, 17, 922000, tzinfo=UTC
    )


@pytest.mark.anyio
async def test_missing_time_of_sample_defaults_to_none(
    make_device: Callable[..., AmazonDevice],
) -> None:
    """A response without timeOfSample leaves the field unset."""
    device = make_device(TEST_SERIAL_1)

    sensors = _get_device_sensor_state(_illuminance_endpoint(), device)

    assert sensors["illuminance"].time_of_sample is None


@pytest.mark.anyio
async def test_unparsable_time_of_sample_defaults_to_none(
    make_device: Callable[..., AmazonDevice],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A malformed timeOfSample is logged and does not raise."""
    device = make_device(TEST_SERIAL_1)

    sensors = _get_device_sensor_state(
        _illuminance_endpoint(time_of_sample="not-a-timestamp"), device
    )

    assert sensors["illuminance"].time_of_sample is None
    assert "unparsable timeOfSample" in caplog.text


@pytest.mark.anyio
async def test_non_string_time_of_sample_defaults_to_none(
    make_device: Callable[..., AmazonDevice],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-string timeOfSample is logged and does not raise."""
    device = make_device(TEST_SERIAL_1)

    sensors = _get_device_sensor_state(
        _illuminance_endpoint(time_of_sample=12345), device
    )

    assert sensors["illuminance"].time_of_sample is None
    assert "unparsable timeOfSample" in caplog.text
