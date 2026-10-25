# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Feature property definition resolution for Amazon devices."""

from dataclasses import dataclass

from aioamazondevices.const.sensors import (
    COMMON_SENSORS,
    SENSOR_TEMPLATES,
    SPECIFIC_SENSORS,
)

type FeaturePropertyTemplate = dict[str, str | None]
type FeaturePropertyOverride = dict[str, str | None] | None


@dataclass(frozen=True)
class FeaturePropertyDefinition:
    """How a templated property is parsed and stored."""

    key: str
    template: FeaturePropertyTemplate
    override: FeaturePropertyOverride


def resolve_feature_property_definition(
    device_type: str, feature_name: str, instance: str, property_name: str
) -> FeaturePropertyDefinition | None:
    """Return a property's definition, None if it has no template for the device type.

    A property has a definition when its feature is common to all devices, or is
    enabled for this device type and instance.
    """
    if (template := SENSOR_TEMPLATES.get(feature_name, {}).get(property_name)) is None:
        return None

    if feature_name in COMMON_SENSORS:
        return FeaturePropertyDefinition(
            template.get("name") or property_name, template, None
        )

    instances = SPECIFIC_SENSORS.get(device_type, {}).get(feature_name, {})
    if (override := instances.get(instance)) is None:
        return None
    return FeaturePropertyDefinition(
        override.get("name") or f"{property_name}-{instance}", template, override
    )
