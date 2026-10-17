# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Sensor template resolution for Amazon devices."""

from dataclasses import dataclass

from aioamazondevices.const.sensors import (
    COMMON_SENSORS,
    SENSOR_TEMPLATES,
    SPECIFIC_SENSORS,
)

type SensorTemplate = dict[str, str | None]
type SensorOverride = dict[str, str | None] | None


@dataclass(frozen=True)
class SensorSpec:
    """How a templated property is parsed and stored."""

    key: str
    template: SensorTemplate
    override: SensorOverride


def sensor_spec(
    device_type: str, feature_name: str, instance: str, property_name: str
) -> SensorSpec | None:
    """Return the spec of a property, None if it has no template for the device type.

    A property has a spec when its feature is common to all devices, or is
    enabled for this device type and instance.
    """
    if (template := SENSOR_TEMPLATES.get(feature_name, {}).get(property_name)) is None:
        return None

    if feature_name in COMMON_SENSORS:
        return SensorSpec(template.get("name") or property_name, template, None)

    instances = SPECIFIC_SENSORS.get(device_type, {}).get(feature_name, {})
    if (override := instances.get(instance)) is None:
        return None
    return SensorSpec(
        override.get("name") or f"{property_name}-{instance}", template, override
    )
