"""Constants for Amazon devices."""

import logging

_LOGGER = logging.getLogger(__package__)

DOMAIN_BY_COUNTRY = {
    "us": {
        "domain": "com",
        "openid.assoc_handle": "amzn_dp_project_dee_ios",
    },
    "uk": {
        "domain": "co.uk",
    },
    "au": {
        "domain": "com.au",
    },
    "jp": {
        "domain": "co.jp",
    },
    "br": {
        "domain": "com.br",
    },
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    ),
    "Accept-Language": "en-US",
    "Accept-Encoding": "gzip",
}

URI_QUERIES = {
    "base": "/api/devices-v2/device",
    "status": "/api/dnd/device-status-list",
    "preferences": "/api/device-preferences",
    "automations": "/api/behaviors/v2/automations",
    "bluetooth": "/api/bluetooth",
}

# Amazon APP info
AMAZON_APP_BUNDLE_ID = "com.amazon.echo"
AMAZON_APP_ID = "MAPiOSLib/6.0/ToHideRetailLink"
AMAZON_APP_NAME = "AioAmazonDevices"
AMAZON_APP_VERSION = "2.2.556530.0"
AMAZON_DEVICE_SOFTWARE_VERSION = "35602678"
AMAZON_DEVICE_TYPE = "A2IVLV5VM2W81"
AMAZON_CLIENT_OS = "16.6"
