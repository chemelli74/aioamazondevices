"""aioamazondevices Common const."""

import logging

_LOGGER = logging.getLogger(__package__)

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
