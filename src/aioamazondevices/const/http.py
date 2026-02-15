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
REQUEST_AGENT = {
    "Amazon": f"AmazonWebView/AmazonAlexa/{AMAZON_APP_VERSION}/iOS/{AMAZON_CLIENT_OS}/iPhone",  # noqa: E501
    "Browser": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",  # noqa: E501
}

REFRESH_ACCESS_TOKEN = "access_token"  # noqa: S105
REFRESH_AUTH_COOKIES = "auth_cookies"

URI_DEVICES = "/api/devices-v2/device"
URI_DND_STATUS_ALL = "/api/dnd/device-status-list"
URI_DND_STATUS_DEVICE = "/api/dnd/status"
URI_NEXUS_GRAPHQL = "/nexus/v1/graphql"
URI_NOTIFICATIONS = "/api/notifications"
URI_SIGNIN = "/ap/signin"

LOGIN_EXCEPTIONS = {
    "default": {
        "oauth_assoc_handle": "amzn_dp_project_dee_ios",
        "oauth_and_register_domain": ".com",
    },
    "co.jp": {
        "oauth_assoc_handle": "jpflex",
        "oauth_and_register_domain": ".co.jp",
    },
}
