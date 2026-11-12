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
                {"sensor_key_override": "Humidity", "scale": "%"},
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


@pytest.mark.parametrize(
    ("instance", "expected_key"),
    [
        pytest.param("1", "rangeValue-1", id="keyed-by-property-and-instance"),
        pytest.param("", "rangeValue", id="without-instance-keyed-by-property"),
    ],
)
def test_specific_sensor_without_name_uses_fallback(
    monkeypatch: pytest.MonkeyPatch, instance: str, expected_key: str
) -> None:
    """An override without a name is keyed by property name and its instance."""
    monkeypatch.setitem(
        feature_property_definitions.SPECIFIC_SENSORS,
        "TESTTYPE",
        {"range": {instance: {}}},
    )

    definition = resolve_feature_property_definition(
        "TESTTYPE", "range", instance, "rangeValue"
    )

    assert definition is not None
    assert definition.key == expected_key


@pytest.mark.parametrize(
    ("device_type", "feature_name", "instance", "property_name"),
    [
        pytest.param("ANYTYPE", "power", "", "powerState", id="feature-untemplated"),
        pytest.param(
            "ANYTYPE", "motionSensor", "", "sensitivity", id="property-untemplated"
        ),
        pytest.param(
            "ANYTYPE", "range", "4", "rangeValue", id="device-type-not-enabled"
        ),
        pytest.param(
            DEVICE_TYPE_AQM, "range", "99", "rangeValue", id="instance-not-enabled"
        ),
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
