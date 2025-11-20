"""aioamazondevices HTTP const."""

HTTP_ERROR_199 = 199
HTTP_ERROR_299 = 299

ARRAY_WRAPPER = "generatedArrayWrapper"

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

REFRESH_ACCESS_TOKEN = "access_token"  # noqa: S105
REFRESH_AUTH_COOKIES = "auth_cookies"

URI_DEVICES = "/api/devices-v2/device"
URI_DND = "/api/dnd/device-status-list"
URI_NOTIFICATIONS = "/api/notifications"
URI_SIGNIN = "/ap/signin"
URI_NEXUS_GRAPHQL = "/nexus/v1/graphql"
