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
    "de": {
        "domain": "de",
    }
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

AMAZON_APP_BUNDLE_ID = "com.audible.iphone"
AMAZON_APP_ID = "MAPiOSLib/6.0/ToHideRetailLink"
AMAZON_APP_VERSION = "3.56.2"
AMAZON_SOFTWARE_VERSION = "35602678"
AMAZON_SERIAL_NUMBER = b"#A2CZJZGLK2JJVM"
