# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for timeOfSample handling in AmazonSensorHandler."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from aioamazondevices.implementation.sensor import parse_graphql_feature_to_sensor
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


@pytest.mark.parametrize(
    ("time_of_sample", "expected", "logged"),
    [
        pytest.param(
            "2026-09-12T08:09:17.922Z",
            datetime(2026, 9, 12, 8, 9, 17, 922000, tzinfo=UTC),
            False,
            id="parsed",
        ),
        pytest.param(None, None, False, id="missing"),
        pytest.param("not-a-timestamp", None, True, id="unparsable"),
        pytest.param(12345, None, True, id="non-string"),
    ],
)
def test_time_of_sample(
    make_device: Callable[..., AmazonDevice],
    caplog: pytest.LogCaptureFixture,
    time_of_sample: str | int | None,
    expected: datetime | None,
    logged: bool,
) -> None:
    """A valid timeOfSample is parsed, anything else is unset and logged."""
    sensors = parse_graphql_feature_to_sensor(
        _illuminance_endpoint(time_of_sample), make_device(TEST_SERIAL_1)
    )

    assert sensors["illuminance"].time_of_sample == expected
    assert ("unparsable timeOfSample" in caplog.text) is logged
