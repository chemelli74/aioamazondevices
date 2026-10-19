# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for sensor template resolution."""

import pytest

from aioamazondevices.const.devices import DEVICE_TYPE_AQM
from aioamazondevices.const.sensors import SENSOR_TEMPLATES
from aioamazondevices.implementation import sensor_templates
from aioamazondevices.implementation.sensor_templates import sensor_spec


def test_common_sensor_is_keyed_by_property() -> None:
    """A common sensor has no override and is keyed by its property name."""
    spec = sensor_spec("ANYTYPE", "temperatureSensor", "", "temperature")

    assert spec is not None
    assert spec.key == "temperature"
    assert spec.template == SENSOR_TEMPLATES["temperatureSensor"]["temperature"]
    assert spec.override is None


def test_specific_sensor_uses_override_name() -> None:
    """A device specific instance is keyed by its override name."""
    spec = sensor_spec(DEVICE_TYPE_AQM, "range", "4", "rangeValue")

    assert spec is not None
    assert spec.key == "Humidity"
    assert spec.override == {"name": "Humidity", "scale": "%"}


def test_specific_sensor_without_name_uses_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An override without a name is keyed by property name and instance."""
    monkeypatch.setitem(
        sensor_templates.SPECIFIC_SENSORS, "TESTTYPE", {"range": {"1": {}}}
    )

    spec = sensor_spec("TESTTYPE", "range", "1", "rangeValue")

    assert spec is not None
    assert spec.key == "rangeValue-1"


@pytest.mark.parametrize(
    ("device_type", "feature_name", "instance", "property_name"),
    [
        # feature without a template
        ("ANYTYPE", "power", "", "powerState"),
        # property without a template
        ("ANYTYPE", "motionSensor", "", "sensitivity"),
        # specific feature on a device type that does not enable it
        ("ANYTYPE", "range", "4", "rangeValue"),
        # specific feature on an instance that is not enabled
        (DEVICE_TYPE_AQM, "range", "99", "rangeValue"),
    ],
)
def test_untemplated_property_has_no_spec(
    device_type: str, feature_name: str, instance: str, property_name: str
) -> None:
    """Properties without a template for the device type have no spec."""
    assert sensor_spec(device_type, feature_name, instance, property_name) is None
