# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Metadata constants for Amazon device sensors."""

from aioamazondevices.const.devices import DEVICE_TYPE_AQM

SENSOR_STATE_OFF = "NOT_DETECTED"

# Sensors templates, keyed by feature name and then by property name
# This determines how to parse the feature
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
}

# These templates will be applied to all devices
COMMON_SENSORS: list[str] = [
    "temperatureSensor",
    "motionSensor",
    "lightSensor",
    "connectivity",
]

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
    }
}
