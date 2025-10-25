"""Constants for Amazon devices."""

import logging

_LOGGER = logging.getLogger(__package__)

ARRAY_WRAPPER = "generatedArrayWrapper"

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
    "Accept-Charset": "utf-8",
    "Accept-Encoding": "gzip",
    "Connection": "keep-alive",
}
CSRF_COOKIE = "csrf"
REQUEST_AGENT = {
    "Amazon": f"AmazonWebView/AmazonAlexa/{AMAZON_APP_VERSION}/iOS/{AMAZON_CLIENT_OS}/iPhone",  # noqa: E501
    "Browser": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",  # noqa: E501
}

REFRESH_ACCESS_TOKEN = "access_token"  # noqa: S105
REFRESH_AUTH_COOKIES = "auth_cookies"

URI_DEVICES = "/api/devices-v2/device"
URI_DND = "/api/dnd/device-status-list"
URI_NOTIFICATIONS = "/api/notifications"
URI_SIGNIN = "/ap/signin"
URI_NEXUS_GRAPHQL = "/nexus/v1/graphql"

SENSOR_STATE_OFF = "NOT_DETECTED"

# File extensions
SAVE_PATH = "out"
HTML_EXTENSION = ".html"
JSON_EXTENSION = ".json"
BIN_EXTENSION = ".bin"

SPEAKER_GROUP_DEVICE_TYPE = "A3C9PE6TNYLTCH"
SPEAKER_GROUP_FAMILY = "WHA"
SPEAKER_GROUP_MODEL = "Speaker Group"

SENSORS: dict[str, dict[str, str | None]] = {
    "temperatureSensor": {
        "name": "temperature",
        "key": "value",
        "subkey": "value",
        "scale": "scale",
    },
    "motionSensor": {
        "name": "detectionState",
        "key": "detectionStateValue",
        "subkey": None,
        "scale": None,
    },
    "lightSensor": {
        "name": "illuminance",
        "key": "illuminanceValue",
        "subkey": "value",
        "scale": None,
    },
}

ALEXA_INFO_SKILLS = [
    "Alexa.Calendar.PlayToday",
    "Alexa.Calendar.PlayTomorrow",
    "Alexa.Calendar.PlayNext",
    "Alexa.Date.Play",
    "Alexa.Time.Play",
    "Alexa.News.NationalNews",
    "Alexa.FlashBriefing.Play",
    "Alexa.Traffic.Play",
    "Alexa.Weather.Play",
    "Alexa.CleanUp.Play",
    "Alexa.GoodMorning.Play",
    "Alexa.SingASong.Play",
    "Alexa.FunFact.Play",
    "Alexa.Joke.Play",
    "Alexa.TellStory.Play",
    "Alexa.ImHome.Play",
    "Alexa.GoodNight.Play",
]

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
    "A2Y04QPFCANLPQ",  # Bose QuietComfort 35 II - issue #476
    "AYHO3NTIQQ04G",  # Nextbase 622GW Dash Cam - issue #477
    "AHL4H6CKH3AUP",  # BMW Car System - issue #478
    "A3BW5ZVFHRCQPO",  # BMW Mini Car System - issue #479
    "A133UZ2CB0IB8",  # Sony Soundbar Sony HT-A5000 - issue #486
    "A2M9HB23M9MSSM",  # Smartwatch Amazfit Bip U Pro - issue #507
    "A1P7E7V3FCZKU6",  # Toshiba Corporation TV 32LF221U19 - issue #531
]


RECURRING_PATTERNS: dict[str, str] = {
    "XXXX-WD": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    "XXXX-WE": "FREQ=WEEKLY;BYDAY=SA,SU",
    "XXXX-WXX-1": "FREQ=WEEKLY;BYDAY=MO",
    "XXXX-WXX-2": "FREQ=WEEKLY;BYDAY=TU",
    "XXXX-WXX-3": "FREQ=WEEKLY;BYDAY=WE",
    "XXXX-WXX-4": "FREQ=WEEKLY;BYDAY=TH",
    "XXXX-WXX-5": "FREQ=WEEKLY;BYDAY=FR",
    "XXXX-WXX-6": "FREQ=WEEKLY;BYDAY=SA",
    "XXXX-WXX-7": "FREQ=WEEKLY;BYDAY=SU",
}

WEEKEND_EXCEPTIONS = {
    "TH-FR": {
        "XXXX-WD": "FREQ=WEEKLY;BYDAY=MO,TU,WE,SA,SU",
        "XXXX-WE": "FREQ=WEEKLY;BYDAY=TH,FR",
    },
    "FR-SA": {
        "XXXX-WD": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,SU",
        "XXXX-WE": "FREQ=WEEKLY;BYDAY=FR,SA",
    },
}

# Countries grouped by their weekend type
COUNTRY_GROUPS = {
    "TH-FR": ["IR"],
    "FR-SA": [
        "AF",
        "BD",
        "BH",
        "DZ",
        "EG",
        "IL",
        "IQ",
        "JO",
        "KW",
        "LY",
        "MV",
        "MY",
        "OM",
        "PS",
        "QA",
        "SA",
        "SD",
        "SY",
        "YE",
    ],
}

NOTIFICATION_ALARM = "Alarm"
NOTIFICATION_MUSIC_ALARM = "MusicAlarm"
NOTIFICATION_REMINDER = "Reminder"
NOTIFICATION_TIMER = "Timer"
