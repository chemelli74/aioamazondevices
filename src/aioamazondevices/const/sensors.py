# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Metadata constants for Amazon device sensors."""

from aioamazondevices.const.devices import DEVICE_TYPE_AQM, DEVICE_TYPE_GLOW

SENSOR_STATE_OFF = "NOT_DETECTED"

# Sensors templates, keyed by feature name and then by property name
# This determines how to parse the feature
# An optional "name" replaces the property name as the sensor name
SENSOR_TEMPLATES: dict[str, dict[str, dict[str, str | None]]] = {
    "temperatureSensor": {
        "temperature": {
            "key": "value",
            "subkey": "value",
            "scale": "scale",
        },
    },
    "motionSensor": {
        "detectionState": {
            "key": "detectionStateValue",
            "subkey": None,
            "scale": None,
        },
        "detectionSensitivity": {
            "key": "detectionSensitivityValue",
            "subkey": None,
            "scale": None,
        },
        "detectionRange": {
            "key": "detectionRangeValue",
            "subkey": None,
            "scale": None,
        },
        "detectionTechnology": {
            "key": "detectionTechnologyValue",
            "subkey": None,
            "scale": None,
        },
        "enablement": {
            "name": "motionSensor-enabled",
            "key": "enablementStateValue",
            "subkey": None,
            "scale": None,
        },
    },
    "lightSensor": {
        "illuminance": {
            "key": "illuminanceValue",
            "subkey": "value",
            "scale": None,
        },
    },
    "connectivity": {
        "reachability": {
            "key": "reachabilityStatusValue",
            "subkey": None,
            "scale": None,
        },
    },
    "range": {
        "rangeValue": {
            "key": "rangeValue",
            "subkey": "value",
            "scale": None,
        },
    },
    "power": {
        "powerState": {
            "key": "powerStateValue",
            "subkey": None,
            "scale": None,
        },
    },
    "brightness": {
        "brightness": {
            "key": "brightnessStateValue",
            "subkey": None,
            "scale": None,
        },
    },
    "color": {
        "color": {
            "key": "colorStateValue",
            "subkey": None,
            "scale": None,
        },
    },
    "mode": {
        "mode": {
            "key": "modeValue",
            "subkey": "value",
            "scale": None,
        },
    },
    "toggle": {
        "toggleState": {
            "key": "toggleStateValue",
            "subkey": None,
            "scale": None,
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
SPECIFIC_SENSORS: dict[str, dict[str, dict[str, dict[str, str | None]]]] = {
    DEVICE_TYPE_AQM: {
        "range": {
            "4": {
                "name": "Humidity",
                "scale": "%",
            },
            "5": {
                "name": "VOC",
                "scale": None,
            },
            "6": {
                "name": "PM25",
                "scale": "MicroGramsPerCubicMeter",
            },
            "7": {
                "name": "PM10",
                "scale": "MicroGramsPerCubicMeter",
            },
            "8": {
                "name": "CO",
                "scale": "ppm",
            },
            "9": {
                "name": "Air Quality",
                "scale": None,
            },
        },
        "toggle": {
            "11": {
                "name": "LED",
                "scale": None,
            }
        },
    },
    DEVICE_TYPE_GLOW: {
        "power": {
            "": {
                "name": "Power",
                "device_grouping": "LIGHT",
            }
        },
        "brightness": {
            "": {
                "name": "Brightness",
                "scale": "%",
                "device_grouping": "LIGHT",
            }
        },
        "color": {
            "": {
                "name": "Color",
                "device_grouping": "LIGHT",
            }
        },
        "mode": {
            "1": {
                "name": "mode",
            }
        },
        "toggle": {
            "3": {
                "name": "Tap to change",
            }
        },
    },
}
