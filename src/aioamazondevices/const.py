"""Constants for Amazon devices."""

import logging
from typing import Any

_LOGGER = logging.getLogger(__package__)

DEFAULT_ASSOC_HANDLE = "amzn_dp_project_dee_ios"

HTTP_ERROR_199 = 199
HTTP_ERROR_299 = 299

TO_REDACT = {
    "address",
    "address1",
    "address2",
    "address3",
    "city",
    "county",
    "customerId",
    "deviceAccountId",
    "deviceAddress",
    "deviceOwnerCustomerId",
    "given_name",
    "name",
    "password",
    "postalCode",
    "searchCustomerId",
    "state",
    "street",
    "user_id",
}

AMAZON_DE_OVERRIDE: dict[str, str] = {
    "domain": "de",
    "openid.assoc_handle": f"{DEFAULT_ASSOC_HANDLE}_de",
}
AMAZON_US_OVERRIDE: dict[str, str] = {
    "domain": "com",
    "openid.assoc_handle": DEFAULT_ASSOC_HANDLE,
}

DOMAIN_BY_ISO3166_COUNTRY: dict[str, dict[str, Any]] = {
    "ar": AMAZON_US_OVERRIDE,
    "at": AMAZON_DE_OVERRIDE,
    "au": {
        "domain": "com.au",
        "openid.assoc_handle": f"{DEFAULT_ASSOC_HANDLE}_au",
    },
    "be": {
        "domain": "com.be",
    },
    "br": AMAZON_US_OVERRIDE | {"market": "https://www.amazon.com.br"},
    "gb": {
        "domain": "co.uk",
        "openid.assoc_handle": f"{DEFAULT_ASSOC_HANDLE}_uk",
    },
    "il": AMAZON_US_OVERRIDE,
    "jp": {
        "domain": "co.jp",
    },
    "mx": {
        "domain": "com.mx",
    },
    "nl": {
        "domain": "nl",
        "market": "https://www.amazon.co.uk",
    },
    "no": AMAZON_DE_OVERRIDE,
    "nz": {
        "domain": "com.au",
        "openid.assoc_handle": f"{DEFAULT_ASSOC_HANDLE}_au",
    },
    "tr": {
        "domain": "com.tr",
    },
    "us": AMAZON_US_OVERRIDE,
    "za": {
        "domain": "co.za",
    },
}

# Amazon APP info
AMAZON_APP_BUNDLE_ID = "com.amazon.echo"
AMAZON_APP_ID = "MAPiOSLib/6.0/ToHideRetailLink"
AMAZON_APP_NAME = "AioAmazonDevices"
AMAZON_APP_VERSION = "2.2.663733.0"
AMAZON_DEVICE_SOFTWARE_VERSION = "35602678"
AMAZON_DEVICE_TYPE = "A2IVLV5VM2W81"
AMAZON_CLIENT_OS = "18.5"

DEFAULT_HEADERS = {
    "User-Agent": (
        f"AmazonWebView/AmazonAlexa/{AMAZON_APP_VERSION}/iOS/{AMAZON_CLIENT_OS}/iPhone"
    ),
    "Accept-Charset": "utf-8",
    "Accept-Encoding": "gzip",
    "Connection": "keep-alive",
}
DEFAULT_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"  # noqa: E501
CSRF_COOKIE = "csrf"

REFRESH_ACCESS_TOKEN = "access_token"  # noqa: S105
REFRESH_AUTH_COOKIES = "auth_cookies"

NODE_DEVICES = "devices"
NODE_DO_NOT_DISTURB = "doNotDisturbDeviceStatusList"
NODE_PREFERENCES = "devicePreferences"
NODE_BLUETOOTH = "bluetoothStates"
NODE_IDENTIFIER = "identifier"
NODE_SENSORS = "sensors"

URI_QUERIES = {
    NODE_DEVICES: "/api/devices-v2/device",
    NODE_DO_NOT_DISTURB: "/api/dnd/device-status-list",
    NODE_PREFERENCES: "/api/device-preferences",
    NODE_BLUETOOTH: "/api/bluetooth",
    # "/api/ping"
    # "/api/np/command"
    # "/api/np/player"
    # "/api/device-wifi-details"
    # "/api/activities"
    # "/api/behaviors/v2/automations"
    # "/api/notifications"
}

URI_SIGNIN = "/ap/signin"
URI_IDS = "/api/phoenix"
URI_SENSORS = "/api/phoenix/state"

SENSORS = [
    "babyCryDetectionState",
    "beepingApplianceDetectionState",
    "coughDetectionState",
    "dogBarkDetectionState",
    "humanPresenceDetectionState",
    "illuminance",
    "temperature",
    "waterSoundsDetectionState",
]
SENSOR_STATE_OFF = "NOT_DETECTED"

# File extensions
SAVE_PATH = "out"
HTML_EXTENSION = ".html"
JSON_EXTENSION = ".json"
BIN_EXTENSION = ".bin"

SPEAKER_GROUP_FAMILY = "WHA"
SPEAKER_GROUP_MODEL = "Speaker Group"

DEVICE_TO_IGNORE: list[str] = [
    AMAZON_DEVICE_TYPE,  # Alexa App for iOS
    "A2TF17PFR55MTB",  # Alexa App for Android
    "A1RTAM01W29CUP",  # Alexa App for PC
    "A18BI6KPKDOEI4",  # ecobee4 Smart Thermostat with Built-in Alexa - issue #199
    "A21Z3CGI8UIP0F",  # Denon AVR-X1600H - issue #253
    "A15ERDAKK5HQQG",  # unsupported Sonos devices - issue #257
    "A3GZUE7F9MEB4U",  # Sony headset WH-1000XM3 - issue #269
    "A23ZD3FSVQM5EE",  # Sony headset WH-1000XM2 - issue #326
    "A7S41FQ5TWBC9",  # Sony headset WH-1000XM4 - issue #327
    "A1L4KDRIILU6N9",  # Sony headset WH-CH700N  - issue #345
    "A2IJJ9QXVOSYK0",  # JBL TUNE770NC - issue #391
    "AKOAGQTKAS9YB",  # Amazon Echo Connect - issue #406
]

DEVICE_TYPE_TO_MODEL: dict[str, dict[str, str | None]] = {
    "A10A33FOX2NUBK": {
        "model": "Echo Spot",
        "hw_version": "Gen1",
    },
    "A11QM4H9HGV71H": {
        "model": "Echo Show 5",
        "hw_version": "Gen3",
    },
    "A13W6HQIHKEN3Z": {
        "model": "Echo Auto",
        "hw_version": "Gen2",
    },
    "A15996VY63BQ2D": {
        "model": "Echo Show 8",
        "hw_version": "Gen2",
    },
    "A18O6U1UQFJ0XK": {
        "model": "Echo Plus",
        "hw_version": "Gen2",
    },
    "A1C66CX2XD756O": {
        "model": "Fire Tablet HD 8",
        "hw_version": "Gen8",
    },
    "A1EIANJ7PNB0Q7": {
        "model": "Echo Show 15",
        "hw_version": "Gen1",
    },
    "A1NL4BVLQ4L3N3": {
        "model": "Echo Show",
        "hw_version": "Gen1",
    },
    "A1Q6UGEXJZWJQ0": {
        "model": "Fire TV Stick 4K",
        "hw_version": "Gen2",
    },
    "A1Q7QCGNMXAKYW": {
        "model": "Fire Tablet 7",
        "hw_version": "Gen9",
    },
    "A1RABVCI4QCIKC": {
        "model": "Echo Dot",
        "hw_version": "Gen3",
    },
    "A1TD5Z1R8IWBHA ": {
        "model": "Fire Tablet HD 8",
        "hw_version": "Gen12",
    },
    "A1VGB7MHSIEYFK": {
        "model": "Fire TV Cube",
        "hw_version": "Gen3",
    },
    "A1WAR447VT003J": {
        "manufacturer": "Yamaha",
        "model": "RX A4 Aventage",
        "hw_version": None,
    },
    "A1WZKXFLI43K86": {
        "model": "FireTV 4k MAX",
        "hw_version": "Gen2",
    },
    "A1XWJRHALS1REP": {
        "model": "Echo Show 5",
        "hw_version": "Gen2",
    },
    "A1Z88NGR2BK6A2": {
        "model": "Echo Show 8",
        "hw_version": "Gen1",
    },
    "A265XOI9586NML": {
        "model": "Fire TV Stick with Alexa Voice Remote",
        "hw_version": None,
    },
    "A271DR1789MXDS": {
        "model": "Fire Tablet 7",
        "hw_version": "Gen12",
    },
    "A2DS1Q2TPDJ48U": {
        "model": "Echo Dot Clock",
        "hw_version": "Gen5",
    },
    "A2F7IJUT32OLN4": {
        "manufacturer": "Samsung Electronics Co., Ltd.",
        "model": "Soundbar Q990D",
        "hw_version": None,
    },
    "A2GFL5ZMWNE0PX": {
        "model": "Fire TV",
        "hw_version": "Gen3",
    },
    "A2H4LV5GIZ1JFT": {
        "model": "Echo Dot Clock",
        "hw_version": "Gen4",
    },
    "A2JKHJ0PX4J3L3": {
        "model": "Fire TV Cube",
        "hw_version": "Gen2",
    },
    "A2LWARUGJLBYEW": {
        "model": "Fire TV Stick",
        "hw_version": "Gen2",
    },
    "A2M35JJZWCQOMZ": {
        "model": "Echo Plus",
        "hw_version": "Gen1",
    },
    "A2M4YX06LWP8WI": {
        "model": "Fire Tablet 7",
        "hw_version": "Gen5",
    },
    "A2N49KXGVA18AR": {
        "model": "Fire Tablet HD 10 Plus",
        "hw_version": "Gen11",
    },
    "A2OSP3UA4VC85F": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos One",
        "hw_version": "Gen1",
    },
    "A2RG3FY1YV97SS": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos Move",
        "hw_version": "Gen1",
    },
    "A2RU4B77X9R9NZ": {
        "model": "Echo Link Amp",
        "hw_version": None,
    },
    "A2U21SRK4QGSE1": {
        "model": "Echo Dot",
        "hw_version": "Gen4",
    },
    "A2UONLFQW0PADH": {
        "model": "Echo Show 8",
        "hw_version": "Gen3",
    },
    "A2Z8O30CD35N8F": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos Arc",
        "hw_version": "Gen1",
    },
    "A303PJF6ISQ7IC": {
        "model": "Echo Auto",
        "hw_version": "Gen1",
    },
    "A30YDR2MK8HMRV": {
        "model": "Echo Dot",
        "hw_version": "Gen3",
    },
    "A31DTMEEVDDOIV": {
        "model": "Fire TV Stick Lite",
        "hw_version": "Gen1",
    },
    "A32DDESGESSHZA": {
        "model": "Echo Dot",
        "hw_version": "Gen3",
    },
    "A32DOYMUN6DTXA": {
        "model": "Echo Dot",
        "hw_version": "Gen3",
    },
    "A33S43L213VSHQ ": {
        "model": "Smart TV 4K",
        "hw_version": "4 Series",
    },
    "A38949IHXHRQ5P": {
        "model": "Echo Tap",
        "hw_version": "Gen1",
    },
    "A39OV95SPFQ9YG": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos Era 100",
        "hw_version": None,
    },
    "A3C9PE6TNYLTCH": {
        "model": "Speaker Group",
        "hw_version": None,
    },
    "A3EH2E0YZ30OD6": {
        "model": "Echo Spot",
        "hw_version": "Gen2",
    },
    "A3EVMLQTU6WL1W": {
        "model": "FireTV 4k MAX",
        "hw_version": "Gen1",
    },
    "A3FX4UWTP28V1P": {
        "model": "Echo",
        "hw_version": "Gen3",
    },
    "A3HF4YRA2L7XGC": {
        "model": "Fire TV Cube",
        "hw_version": "Gen1",
    },
    "A3HND3J60V1OXX": {
        "model": "Echo Loop",
        "hw_version": None,
    },
    "A3NPD82ABCPIDP": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos Beam",
        "hw_version": None,
    },
    "A3RBAYBE7VM004": {
        "model": "Echo Studio",
        "hw_version": None,
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
        "hw_version": None,
    },
    "A4ZP7ZC4PI6TO": {
        "model": "Echo Show 5",
        "hw_version": "Gen1",
    },
    "A4ZXE0RM7LQ7A": {
        "model": "Echo Dot",
        "hw_version": "Gen5",
    },
    "A50R5P5LEX87M ": {
        "manufacturer": "JBL",
        "model": "JBL BAR 500",
        "hw_version": None,
    },
    "A7WXQPH584YP": {
        "model": "Echo",
        "hw_version": "Gen2",
    },
    "AB72C64C86AW2": {
        "model": "Echo",
        "hw_version": "Gen2",
    },
    "ADOUDFQX2QVX0": {
        "model": "Fire TV Omni QLED",
        "hw_version": None,
    },
    "ADVBD696BHNV5": {
        "model": "Fire TV Stick",
        "hw_version": "Gen1",
    },
    "AECNEXTDY5AD9": {
        "manufacturer": "Cozyla",
        "model": "Frame with Alexa",
        "hw_version": None,
    },
    "AIPK7MM90V7TB": {
        "model": "Echo Show 10",
        "hw_version": "Gen3",
    },
    "AKNO1N0KSFN8L": {
        "model": "Echo Dot",
        "hw_version": "Gen1",
    },
    "AKPGW064GI9HE": {
        "model": "Fire TV Stick 4K",
        "hw_version": "Gen1",
    },
    "AP1F6KUH00XPV": {
        "model": "Echo Stereo Pair",
        "hw_version": "Virtual",
    },
    "AQ24620N8QD5Q": {
        "model": "Echo Show 15",
        "hw_version": "Gen2",
    },
    "ASQZWP4GPYUT7": {
        "model": "Echo pop",
        "hw_version": "Gen1",
    },
    "ATNLRCEBX3W4P": {
        "model": "Fire Tablet HD 10",
        "hw_version": "Gen11",
    },
    "AUPUQSVCVHXP0": {
        "manufacturer": "ecobee Inc.",
        "model": "ecobee Switch+",
        "hw_version": None,
    },
    "AVD3HM0HOJAAL": {
        "manufacturer": "Sonos Inc.",
        "model": "Sonos One",
        "hw_version": "Gen2",
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
