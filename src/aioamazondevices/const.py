"""Constants for Amazon devices."""

import logging

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

# Amazon APP info
AMAZON_APP_BUNDLE_ID = "com.amazon.echo"
AMAZON_APP_ID = "MAPiOSLib/6.0/ToHideRetailLink"
AMAZON_APP_NAME = "AioAmazonDevices"
AMAZON_APP_VERSION = "2.2.663733.0"
AMAZON_DEVICE_SOFTWARE_VERSION = "35602678"
AMAZON_DEVICE_TYPE = "A2IVLV5VM2W81"
AMAZON_CLIENT_OS = "18.5"

DEFAULT_SITE = "https://www.amazon.com"
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

URI_DEVICES = "/api/devices-v2/device"
URI_SIGNIN = "/ap/signin"
URI_NEXUS_GRAPHQL = "/nexus/v1/graphql"

SENSOR_STATE_MOTION_DETECTED = "DETECTED"

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
    "A3PAHYZLPKL73D",  # EERO 6 Wifi AP - issue #426
    "A3KOTUS4DKHU1W",  # Samsung Fridge - issue #429
    "AN630UQPG2CA4",  # Insignia TV - issue #430
    "A3SSG6GR8UU7SN",  # Amazon Echo Sub - issue #437
]

CONFIRMED_DEVICES: list[str] = [
    "A10A33FOX2NUBK",  # Echo Spot / Gen1
    "A11QM4H9HGV71H",  # Echo Show 5 /Gen3
    "A13W6HQIHKEN3Z",  # Echo Auto / Gen2
    "A15996VY63BQ2D",  # Echo Show 8/ Gen2
    "A18O6U1UQFJ0XK",  # Echo Plus / Gen2
    "A1C66CX2XD756O",  # Fire Tablet HD 8 /Gen8
    "A1EIANJ7PNB0Q7",  # Echo Show 15 / Gen1
    "A1NL4BVLQ4L3N3",  # Echo Show /Gen1
    "A1Q6UGEXJZWJQ0",  # Fire TV Stick 4K / Gen2
    "A1Q7QCGNMXAKYW",  # Fire Tablet 7 / Gen9
    "A1RABVCI4QCIKC",  # Echo Dot / Gen3
    "A1TD5Z1R8IWBHA",  # Fire Tablet HD 8 / Gen12
    "A1VGB7MHSIEYFK",  # Fire TV Cube / Gen3
    "A1WAR447VT003J",  # Yamaha / RX A4 Aventage
    "A1WZKXFLI43K86",  # FireTV 4k MAX / Gen2
    "A1XWJRHALS1REP",  # Echo Show 5 / Gen2
    "A1Z88NGR2BK6A2",  # Echo Show 8 / Gen1
    "A265XOI9586NML",  # Fire TV Stick with Alexa Voice Remote
    "A271DR1789MXDS",  # Fire Tablet 7 / Gen12
    "A2DS1Q2TPDJ48U",  # Echo Dot Clock / Gen5
    "A2E0SNTXJVT7WK",  # Fire TV Stick / Gen2
    "A2F7IJUT32OLN4",  # Samsung Electronics Co., Ltd. / Soundbar Q990D
    "A2GFL5ZMWNE0PX",  # Fire TV Stick / Gen3
    "A2H4LV5GIZ1JFT",  # Echo Dot Clock / Gen4
    "A2JKHJ0PX4J3L3",  # Fire TV Cube / Gen2
    "A2LWARUGJLBYEW",  # Fire TV Stick / Gen2
    "A2M35JJZWCQOMZ",  # Echo Plus / Gen1
    "A2M4YX06LWP8WI",  # Fire Tablet 7 / Gen5
    "A2N49KXGVA18AR",  # Fire Tablet HD 10 Plus / Gen11
    "A2OSP3UA4VC85F",  # Sonos Inc. / Sonos One / Gen1
    "A2RG3FY1YV97SS",  # Sonos Inc. / Sonos Move / Gen1
    "A2RU4B77X9R9NZ",  # Echo Link Amp
    "A2U21SRK4QGSE1",  # Echo Dot / Gen4
    "A2UONLFQW0PADH",  # Echo Show 8 / Gen3
    "A2Z8O30CD35N8F",  # Sonos Inc. / Sonos Arc / Gen1
    "A303PJF6ISQ7IC",  # Echo Auto / Gen1
    "A30YDR2MK8HMRV",  # Echo Dot / Gen3
    "A31DTMEEVDDOIV",  # Fire TV Stick Lite / Gen1
    "A32DDESGESSHZA",  # Echo Dot / Gen3
    "A32DOYMUN6DTXA",  # Echo Dot / Gen3
    "A33S43L213VSHQ ",  # Smart TV 4K / 4 Series
    "A38949IHXHRQ5P",  # Echo Tap / Gen1
    "A39OV95SPFQ9YG",  # Sonos Inc. / Sonos Era 100
    "A3C9PE6TNYLTCH",  # Speaker Group
    "A3EH2E0YZ30OD6",  # Echo Spot/  Gen2
    "A3EVMLQTU6WL1W",  # FireTV 4k MAX / Gen1
    "A3FX4UWTP28V1P",  # Echo / Gen3
    "A3HF4YRA2L7XGC",  # Fire TV Cube / Gen1
    "A3HND3J60V1OXX",  # Echo Loop
    "A3NPD82ABCPIDP",  # Sonos Inc. / Sonos Beam
    "A3RBAYBE7VM004",  # Echo Studio
    "A3RMGO6LYLH7YN",  # Echo Dot / Gen4
    "A3S5BH2HU6VAYF",  # Echo Dot / Gen2
    "A3VRME03NAXFUB",  # Echo Flex
    "A4ZP7ZC4PI6TO",  # Echo Show 5 / Gen1
    "A4ZXE0RM7LQ7A",  # Echo Dot / Gen5
    "A50R5P5LEX87M",  # JBL / JBL BAR 500
    "A7WXQPH584YP",  # Echo / Gen2
    "AB72C64C86AW2",  # Echo / Gen2
    "ADOUDFQX2QVX0",  # Fire TV Omni QLED
    "ADVBD696BHNV5",  # Fire TV Stick / Gen1
    "AECNEXTDY5AD9",  # Cozyla / Frame with Alexa
    "AIPK7MM90V7TB",  # Echo Show 10 / Gen3
    "AKNO1N0KSFN8L",  # Echo Dot / Gen1
    "AKPGW064GI9HE",  # Fire TV Stick 4K / Gen1
    "AP1F6KUH00XPV",  # Echo Stereo Pair / Virtual
    "AQ24620N8QD5Q",  # Echo Show 15 / Gen2
    "ASQZWP4GPYUT7",  # Echo pop / Gen1
    "ATNLRCEBX3W4P",  # Fire Tablet HD 10 / Gen11
    "AUPUQSVCVHXP0",  # ecobee Inc. / ecobee Switch+
    "AVD3HM0HOJAAL",  # Sonos Inc. / Sonos One / Gen2
    "AVU7CPPF2ZRAS",  # Fire Tablet HD 8 Plus / Gen10
    "AWZZ5CVHX2CD",  # Echo Show / Gen2
    "G2A0V704840708AP",  # Echo Plus / Gen2
]
