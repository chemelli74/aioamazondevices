"""Constants for Amazon devices."""

import logging

_LOGGER = logging.getLogger(__package__)

DEFAULT_ASSOC_HANDLE = "amzn_dp_project_dee_ios"

DOMAIN_BY_COUNTRY = {
    "us": {
        "domain": "com",
        "openid.assoc_handle": DEFAULT_ASSOC_HANDLE,
    },
    "uk": {
        "domain": "co.uk",
    },
    "au": {
        "domain": "com.au",
    },
    "jp": {
        "domain": "co.jp",
        "openid.assoc_handle": "jpflex",
    },
    "br": {
        "domain": "com.br",
    },
}

# Amazon APP info
AMAZON_APP_BUNDLE_ID = "com.amazon.echo"
AMAZON_APP_ID = "MAPiOSLib/6.0/ToHideRetailLink"
AMAZON_APP_NAME = "AioAmazonDevices"
AMAZON_APP_VERSION = "2.2.556530.0"
AMAZON_DEVICE_SOFTWARE_VERSION = "35602678"
AMAZON_DEVICE_TYPE = "A2IVLV5VM2W81"
AMAZON_CLIENT_OS = "16.6"

DEFAULT_HEADERS = {
    "User-Agent": (
        f"Mozilla/5.0 (iPhone; CPU iPhone OS {AMAZON_CLIENT_OS.replace('.', '_')} like Mac OS X) "  # noqa: E501
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    ),
    "Accept-Language": "en-US",
    "Accept-Encoding": "gzip",
}

DEVICES = "devices"
URI_QUERIES = {
    DEVICES: "/api/devices-v2/device",
    "doNotDisturbDeviceStatusList": "/api/dnd/device-status-list",
    "devicePreferences": "/api/device-preferences",
    "bluetoothStates": "/api/bluetooth",
}

# File extensions
SAVE_PATH = "out"
HTML_EXTENSION = ".html"
JSON_EXTENSION = ".json"

DEVICE_TYPE_TO_MODEL = {
    "A1RABVCI4QCIKC": "Echo Dot (Gen3)",
    "A2DS1Q2TPDJ48U": "Echo Dot Clock (Gen5)",
    "A2H4LV5GIZ1JFT": "Echo Dot Clock (Gen4)",
    "A2U21SRK4QGSE1": "Echo Dot Clock (Gen4)",
    "A32DDESGESSHZA": "Echo Dot (Gen3)",
    "A32DOYMUN6DTXA": "Echo Dot (Gen3)",
    "A3RMGO6LYLH7YN": "Echo Dot (Gen4)",
    "A3S5BH2HU6VAYF": "Echo Dot (Gen2)",
    "A4ZXE0RM7LQ7A": "Echo Dot (Gen5)",
    "AKNO1N0KSFN8L": "Echo Dot (Gen1)",
}
