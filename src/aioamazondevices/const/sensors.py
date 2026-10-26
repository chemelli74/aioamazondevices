# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Metadata constants for Amazon device sensors."""

from aioamazondevices.const.devices import DEVICE_TYPE_AQM, DEVICE_TYPE_GLOW

SENSOR_STATE_OFF = "NOT_DETECTED"

# Sensors templates, keyed by feature name and then by property name
# This determines how to parse the feature
# the property name will be used as sensor key for these
SENSOR_TEMPLATES: dict[str, dict[str, dict[str, str | None]]] = {
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
            "value_subkey": None,
            "value_scale_key": None,
        },
    },
    "lightSensor": {
        "illuminance": {
            "value_key": "illuminanceValue",
            "value_subkey": "value",
            "value_scale_key": None,
        },
    },
    "connectivity": {
        "reachability": {
            "value_key": "reachabilityStatusValue",
            "value_subkey": None,
            "value_scale_key": None,
        },
    },
    "range": {
        "rangeValue": {
            "value_key": "rangeValue",
            "value_subkey": "value",
            "value_scale_key": None,
        },
    },
    "power": {
        "powerState": {
            "value_key": "powerStateValue",
            "value_subkey": None,
            "value_scale_key": None,
        },
    },
    "brightness": {
        "brightness": {
            "value_key": "brightnessStateValue",
            "value_subkey": None,
            "value_scale_key": None,
        },
    },
    "color": {
        "color": {
            "value_key": "colorStateValue",
            "value_subkey": None,
            "value_scale_key": None,
        },
    },
    "mode": {
        "mode": {
            "value_key": "modeValue",
            "value_subkey": "value",
            "value_scale_key": None,
        },
    },
    "toggle": {
        "toggleState": {
            "value_key": "toggleStateValue",
            "value_subkey": None,
            "value_scale_key": None,
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
        "lightSensor",
        "motionSensor",
    }
)

# Device type specific sensors, keyed by device type, feature name and then instance
# The property name will be used for sensor key unless sensor_key_override is set
SPECIFIC_SENSORS: dict[str, dict[str, dict[str, dict[str, str | None]]]] = {
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
                "sensor_key_override": "AQM-LED",
                "scale": None,
            }
        },
    },
    DEVICE_TYPE_GLOW: {
        "power": {
            "": {
                "sensor_key_override": "Light-Power",
                "scale": None,
            }
        },
        "brightness": {
            "": {
                "sensor_key_override": "Brightness",
                "scale": "%",
            }
        },
        "color": {
            "": {
                "sensor_key_override": "Color",
                "scale": None,
            }
        },
        "mode": {
            "1": {
                "sensor_key_override": "Light-Mode",
            }
        },
        "toggle": {
            "3": {
                "sensor_key_override": "Glow-Tap",
            }
        },
    },
}
