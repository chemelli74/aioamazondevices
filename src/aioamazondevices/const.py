"""Constants for Amazon devices."""

import logging

_LOGGER = logging.getLogger(__package__)

DEFAULT_ASSOC_HANDLE = "amzn_dp_project_dee_ios"

DOMAIN_BY_ISO3166_COUNTRY = {
    "us": {
        "domain": "com",
        "openid.assoc_handle": DEFAULT_ASSOC_HANDLE,
    },
    "gb": {
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
CSRF_COOKIE = "csrf"

NODE_DEVICES = "devices"
NODE_DO_NOT_DISTURB = "doNotDisturbDeviceStatusList"
NODE_PREFERENCES = "devicePreferences"
NODE_BLUETOOTH = "bluetoothStates"

URI_QUERIES = {
    NODE_DEVICES: "/api/devices-v2/device",
    NODE_DO_NOT_DISTURB: "/api/dnd/device-status-list",
    NODE_PREFERENCES: "/api/device-preferences",
    NODE_BLUETOOTH: "/api/bluetooth",
}

# File extensions
SAVE_PATH = "out"
HTML_EXTENSION = ".html"
JSON_EXTENSION = ".json"
BIN_EXTENSION = ".bin"

SPEAKER_GROUP_MODEL = "Speaker Group"

DEVICE_TYPE_TO_MODEL: dict[str, dict[str, str | None]] = {
    "A10A33FOX2NUBK": {
        "model": "Echo Spot",
        "hw_version": "Gen1",
    },
    "A11QM4H9HGV71H": {
        "model": "Echo Show 5",
        "hw_version": "Gen3",
    },
    "A1Q6UGEXJZWJQ0": {
        "model": "Fire TV Stick 4K",
        "hw_version": "Gen2",
    },
    "A1RABVCI4QCIKC": {
        "model": "Echo Dot",
        "hw_version": "Gen3",
    },
    "A271DR1789MXDS": {
        "model": "Fire Tablet 7",
        "hw_version": "Gen12",
    },
    "A2DS1Q2TPDJ48U": {
        "model": "Echo Dot Clock",
        "hw_version": "Gen5",
    },
    "A2H4LV5GIZ1JFT": {
        "model": "Echo Dot Clock",
        "hw_version": "Gen4",
    },
    "A2LWARUGJLBYEW": {
        "model": "Fire TV Stick",
        "hw_version": "Gen2",
    },
    "A2M4YX06LWP8WI": {
        "model": "Fire Tablet 7",
        "hw_version": "Gen5",
    },
    "A2U21SRK4QGSE1": {
        "model": "Echo Dot Clock",
        "hw_version": "Gen4",
    },
    "A303PJF6ISQ7IC": {
        "model": "Echo Auto",
        "hw_version": "Gen1",
    },
    "A30YDR2MK8HMRV": {
        "model": "Echo Dot",
        "hw_version": "Gen3",
    },
    "A32DDESGESSHZA": {
        "model": "Echo Dot",
        "hw_version": "Gen3",
    },
    "A32DOYMUN6DTXA": {
        "model": "Echo Dot",
        "hw_version": "Gen3",
    },
    "A3C9PE6TNYLTCH": {
        "model": "Speaker Group",
        "hw_version": "None",
    },
    "A3RMGO6LYLH7YN": {
        "model": "Echo Dot",
        "hw_version": "Gen4",
    },
    "A3S5BH2HU6VAYF": {
        "model": "Echo Dot",
        "hw_version": "Gen2",
    },
    "A3VRME03NAXFUB": {
        "model": "Echo Flex",
        "hw_version": "None",
    },
    "A4ZP7ZC4PI6TO": {
        "model": "Echo Show 3",
        "hw_version": "Gen1",
    },
    "A4ZXE0RM7LQ7A": {
        "model": "Echo Dot",
        "hw_version": "Gen5",
    },
    "A7WXQPH584YP": {
        "model": "Echo Dot",
        "hw_version": "Gen2",
    },
    "AB72C64C86AW2": {
        "model": "Echo Dot",
        "hw_version": "Gen2",
    },
    "AKNO1N0KSFN8L": {
        "model": "Echo Dot",
        "hw_version": "Gen1",
    },
    "AKPGW064GI9HE": {
        "model": " Fire TV Stick 4K",
        "hw_version": "Gen1",
    },
    "ATNLRCEBX3W4P": {
        "model": "Fire Tablet HD 10",
        "hw_version": "Gen11",
    },
    "AVU7CPPF2ZRAS": {
        "model": "Fire Tablet HD 8 Plus",
        "hw_version": "Gen10",
    },
    "G2A0V704840708AP": {
        "model": "Echo Plus",
        "hw_version": "Gen2",
    },
}
