# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Metadata constants for Amazon device sensors."""

from typing import NotRequired, TypedDict

from aioamazondevices.const.devices import (
    DEVICE_TYPE_AQM,
    DEVICE_TYPE_GLOW,
    DEVICE_TYPE_THERMOSTAT,
)

SENSOR_STATE_OFF = "NOT_DETECTED"

# Value Amazon reports while a temperature sensor calibrates (e.g. after a reboot)
# It is always -280, whatever the scale set on the device
TEMPERATURE_CALIBRATION_VALUE = -280


class SensorTemplate(TypedDict):
    """How to read a sensor value from a feature property."""

    # field in graphQL response holding the value
    value_key: str
    # optional subkey if required value is nested
    value_subkey: NotRequired[str]
    # optional field in graphQL response holding the scale
    value_scale_key: NotRequired[str]


# Sensors templates, keyed by feature name and then by property name
# This determines how to parse the feature
# the property name will be used as sensor key for these
SENSOR_TEMPLATES: dict[str, dict[str, SensorTemplate]] = {
    "temperatureSensor": {
        "temperature": {
            "value_key": "value",
            "value_subkey": "value",
            "value_scale_key": "scale",
        },
    },
    "motionSensor": {
        "detectionState": {
            "value_key": "detectionStateValue",
        },
    },
    "lightSensor": {
        "illuminance": {
            "value_key": "illuminanceValue",
            "value_subkey": "value",
        },
    },
    "connectivity": {
        "reachability": {
            "value_key": "reachabilityStatusValue",
        },
    },
    "range": {
        "rangeValue": {
            "value_key": "rangeValue",
            "value_subkey": "value",
        },
    },
    "power": {
        "powerState": {
            "value_key": "powerStateValue",
        },
    },
    "brightness": {
        "brightness": {
            "value_key": "brightnessStateValue",
        },
    },
    "color": {
        "color": {
            "value_key": "colorStateValue",
        },
    },
    "mode": {
        "mode": {
            "value_key": "modeValue",
            "value_subkey": "value",
        },
    },
    "toggle": {
        "toggleState": {
            "value_key": "toggleStateValue",
        },
    },
    "thermostat": {
        "targetSetpoint": {
            "value_key": "value",
            "value_subkey": "value",
            "value_scale_key": "scale",
        },
        "upperSetpoint": {
            "value_key": "value",
            "value_subkey": "value",
            "value_scale_key": "scale",
        },
        "lowerSetpoint": {
            "value_key": "value",
            "value_subkey": "value",
            "value_scale_key": "scale",
        },
        "thermostatMode": {
            "value_key": "thermostatModeValue",
        },
    },
    "hvac": {
        "coolerStage": {
            "value_key": "coolerStageValue",
            "value_subkey": "value",
        },
        "primaryHeaterStage": {
            "value_key": "primaryHeaterStageValue",
            "value_subkey": "value",
        },
        "fanStage": {
            "value_key": "fanStageValue",
            "value_subkey": "value",
        },
    },
    "thermostatConfiguration": {
        "allowedTemperatureRange": {
            "value_key": "thermostatAllowedTemperatureRangeValue",
        },
    },
}

# These templates will be applied to all devices
COMMON_SENSORS: list[str] = [
    "temperatureSensor",
    "motionSensor",
    "lightSensor",
    "connectivity",
]

# Features Amazon does not push over HTTP2, so they need polling
POLLED_SENSOR_FEATURES: frozenset[str] = frozenset(
    {
        "connectivity",
        "hvac",
        "lightSensor",
        "motionSensor",
    }
)


class SpecificSensor(TypedDict):
    """Per instance settings for a device type specific sensor."""

    # Override the sensor key used to identify the sensor
    # particularly useful for range sensors, where the default key
    # is the property name (plus instance if set) which is not sufficient
    # to identify the sensor (e.g. range-3 on one device can be a completely
    # different sensor than range-3 on another device)
    sensor_key_override: NotRequired[str]
    # Optional scale literal, defaults to the scale reported by the device (if any)
    # Setting to None will force the sensor to have no scale, even if the device
    # reports one
    scale: NotRequired[str | None]


# Device type specific sensors, keyed by device type, feature name and then instance
SPECIFIC_SENSORS: dict[str, dict[str, dict[str, SpecificSensor]]] = {
    DEVICE_TYPE_AQM: {
        "range": {
            "4": {
                "sensor_key_override": "Humidity",
                "scale": "%",
            },
            "5": {
                "sensor_key_override": "VOC",
                "scale": None,
            },
            "6": {
                "sensor_key_override": "PM25",
                "scale": "MicroGramsPerCubicMeter",
            },
            "7": {
                "sensor_key_override": "PM10",
                "scale": "MicroGramsPerCubicMeter",
            },
            "8": {
                "sensor_key_override": "CO",
                "scale": "ppm",
            },
            "9": {
                "sensor_key_override": "Air Quality",
                "scale": None,
            },
        },
        "toggle": {
            "11": {
                "sensor_key_override": "aqm_led",
                "scale": None,
            }
        },
    },
    DEVICE_TYPE_GLOW: {
        "power": {
            "": {
                "sensor_key_override": "light_power",
                "scale": None,
            }
        },
        "brightness": {
            "": {
                "sensor_key_override": "brightness",
                "scale": "%",
            }
        },
        "color": {
            "": {
                "sensor_key_override": "color",
                "scale": None,
            }
        },
        "mode": {
            "1": {
                "sensor_key_override": "light_mode",
            }
        },
        "toggle": {
            "3": {
                "sensor_key_override": "glow_tap",
            }
        },
    },
    DEVICE_TYPE_THERMOSTAT: {
        "mode": {
            "5": {
                "sensor_key_override": "fan_mode",
            }
        },
        "thermostat": {"": {}},
        "thermostatConfiguration": {"": {}},
        "hvac": {"": {}},
    },
}
