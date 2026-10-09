# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Metadata constants for Amazon device sensors."""

from aioamazondevices.const.devices import DEVICE_TYPE_AQM

SENSOR_STATE_OFF = "NOT_DETECTED"

# Sensors templates, keyed by feature name and then by property name

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
        "enablement": {
            "key": "enablementStateValue",
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
    "toggle": {
        "toggleState": {
            "key": "toggleStateValue",
            "subkey": None,
            "scale": None,
        },
    },
}

# These templates will be applied to all devices
GENERIC_SENSORS: list[str] = [
    "temperatureSensor",
    "motionSensor",
    "lightSensor",
    "connectivity",
]

DEVICE_TYPE_SENSORS: dict[str, dict[str, list[str]]] = {
    DEVICE_TYPE_AQM: {
        "range": [
            "4",  # Humidity
            "5",  # VOC
            "6",  # PM25
            "7",  # PM10
            "8",  # CO
            "9",  # Air Quality
        ],
        "toggle": [
            "11",  # LED toggle
        ],
    }
}
