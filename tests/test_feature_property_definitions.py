# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for sensor template resolution."""

import pytest

from aioamazondevices.const.devices import DEVICE_TYPE_AQM
from aioamazondevices.const.sensors import SENSOR_TEMPLATES
from aioamazondevices.implementation import feature_property_definitions
from aioamazondevices.implementation.feature_property_definitions import (
    FeaturePropertyDefinition,
    resolve_feature_property_definition,
)


@pytest.mark.parametrize(
    ("device_type", "feature_name", "instance", "property_name", "expected"),
    [
        pytest.param(
            "ANYTYPE",
            "temperatureSensor",
            "",
            "temperature",
            FeaturePropertyDefinition(
                "temperature",
                SENSOR_TEMPLATES["temperatureSensor"]["temperature"],
                None,
            ),
            id="common-keyed-by-property",
        ),
        pytest.param(
            DEVICE_TYPE_AQM,
            "range",
            "4",
            "rangeValue",
            FeaturePropertyDefinition(
                "Humidity",
                SENSOR_TEMPLATES["range"]["rangeValue"],
                {"name": "Humidity", "scale": "%"},
            ),
            id="specific-keyed-by-override-name",
        ),
    ],
)
def test_templated_property_definition(
    device_type: str,
    feature_name: str,
    instance: str,
    property_name: str,
    expected: FeaturePropertyDefinition,
) -> None:
    """Common sensors are keyed by property, specific ones by their override."""
    assert (
        resolve_feature_property_definition(
            device_type, feature_name, instance, property_name
        )
        == expected
    )


def test_specific_sensor_without_name_uses_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An override without a name is keyed by property name and instance."""
    monkeypatch.setitem(
        feature_property_definitions.SPECIFIC_SENSORS, "TESTTYPE", {"range": {"1": {}}}
    )

    definition = resolve_feature_property_definition(
        "TESTTYPE", "range", "1", "rangeValue"
    )

    assert definition is not None
    assert definition.key == "rangeValue-1"


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
def test_untemplated_property_has_no_definition(
    device_type: str, feature_name: str, instance: str, property_name: str
) -> None:
    """Properties without a template for the device type have no definition."""
    assert (
        resolve_feature_property_definition(
            device_type, feature_name, instance, property_name
        )
        is None
    )
