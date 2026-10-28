# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Amazon login flow."""

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime
from http import HTTPMethod, HTTPStatus
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from bs4 import BeautifulSoup
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.capabilities import DEVICE_CAPABILITIES
from aioamazondevices.const.http import REFRESH_ACCESS_TOKEN, REFRESH_AUTH_COOKIES
from aioamazondevices.exceptions import (
    CannotAuthenticate,
    CannotRegisterDevice,
    MissingCountryError,
    WrongMethod,
)
from aioamazondevices.login import AmazonLogin

from .const import FIXTURES_DIR, TEST_EMAIL, TEST_PASSWORD

MAPLANDING_URL = URL("https://www.amazon.com/ap/maplanding")


@pytest.mark.anyio
async def test_extract_code_from_url(api: AmazonEchoApi) -> None:
    """The authorization code is read from the post-login redirect query."""
    url = MAPLANDING_URL.with_query(
        {"openid.oa2.authorization_code": "ANabcdef", "openid.mode": "id_res"}
    )

    assert api._login._extract_code_from_url(url) == "ANabcdef"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "url",
    [
        pytest.param(MAPLANDING_URL, id="no_query"),
        pytest.param(
            MAPLANDING_URL.with_query({"openid.mode": "id_res"}), id="missing_code"
        ),
    ],
)
async def test_extract_code_from_url_missing_code(api: AmazonEchoApi, url: URL) -> None:
    """A redirect without an authorization code fails authentication."""
    with pytest.raises(CannotAuthenticate):
        api._login._extract_code_from_url(url)


@pytest.mark.anyio
async def test_get_inputs_from_soup(api: AmazonEchoApi) -> None:
    """Only the hidden inputs of the sign-in form are collected."""
    soup = BeautifulSoup(
        (FIXTURES_DIR / "ap_signin.html").read_text(encoding="utf-8"), "html.parser"
    )

    assert api._login._get_inputs_from_soup(soup) == {
        "appActionToken": "APP_ACTION_TOKEN",
        "appAction": "SIGNIN_PWD_COLLECT",
        "openid.return_to": "ape:aHR0cHM6Ly93d3cuYW1hem9uLmNvbS9hcC9tYXBsYW5kaW5n",
        "prevRID": "ape:UFJFVklPVVNfUkVRVUVTVF9JRA==",
        "workflowState": "WORKFLOW_STATE",
        "anti-csrftoken-a2z": "ANTI_CSRF_TOKEN",
        "useRecyclingRule": "false",
        "subPageType": "SignInClaimCollect",
        "shouldShowPersistentLabels": "true",
    }


@pytest.mark.anyio
async def test_get_inputs_from_soup_without_form(api: AmazonEchoApi) -> None:
    """A page without a form fails authentication."""
    soup = BeautifulSoup("<html><body>No form</body></html>", "html.parser")

    with pytest.raises(CannotAuthenticate):
        api._login._get_inputs_from_soup(soup)


SIGNIN_URL = URL("https://www.amazon.com/ap/signin")
EMAIL_PAGE = """
<form name="signIn" method="post" action="/ax/claim?arb=ARB">
  <input type="hidden" name="appAction" value="SIGNIN_CLAIM_COLLECT" />
  <input type="text" name="email" />
</form>
"""
PASSWORD_PAGE = """
<form name="signIn" method="post" action="https://www.amazon.com/ap/signin">
  <input type="hidden" name="appAction" value="SIGNIN_PWD_COLLECT" />
  <input type="password" name="password" />
</form>
"""  # noqa: S105
MFA_PAGE = """
<form id="auth-mfa-form" method="post" action="https://www.amazon.com/ap/signin">
  <input type="hidden" name="appAction" value="SIGNIN_MFA" />
  <input id="auth-mfa-otpcode" type="tel" name="otpCode" />
</form>
"""
ERROR_BOX = """
<div id="auth-{kind}-message-box">
  <h4>There was a problem</h4>
  <div>{message}</div>
</div>
"""


def _page(html: str, url: URL) -> tuple[BeautifulSoup, MagicMock]:
    """Build a session_request result for a page served from url."""
    resp = MagicMock()
    resp.url = url
    return BeautifulSoup(html, "html.parser"), resp


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("action", "expected"),
    [
        pytest.param(
            "/ax/claim?arb=ARB",
            URL("https://www.amazon.com/ax/claim?arb=ARB"),
            id="relative",
        ),
        pytest.param(
            "https://www.amazon.co.uk/ap/signin",
            URL("https://www.amazon.co.uk/ap/signin"),
            id="absolute",
        ),
    ],
)
async def test_get_request_from_soup(
    api: AmazonEchoApi, action: str, expected: URL
) -> None:
    """Form actions are resolved against the URL of the page serving them."""
    soup = BeautifulSoup(
        f'<form name="signIn" method="post" action="{action}"></form>',
        "html.parser",
    )

    assert api._login._get_request_from_soup(soup, SIGNIN_URL) == ("post", expected)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "html",
    [
        pytest.param("<html><body>No form</body></html>", id="no_form"),
        pytest.param('<form name="signIn" method="post"></form>', id="no_action"),
    ],
)
async def test_get_request_from_soup_without_form(
    api: AmazonEchoApi, html: str
) -> None:
    """A page without a usable form fails authentication."""
    soup = BeautifulSoup(html, "html.parser")

    with pytest.raises(CannotAuthenticate):
        api._login._get_request_from_soup(soup, SIGNIN_URL)


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["error", "warning"])
async def test_check_login_error(api: AmazonEchoApi, kind: str) -> None:
    """An Amazon error or warning box fails authentication with its text."""
    soup = BeautifulSoup(
        ERROR_BOX.format(kind=kind, message="Something is wrong"), "html.parser"
    )

    with pytest.raises(
        CannotAuthenticate, match="There was a problem Something is wrong"
    ):
        api._login._check_login_error(soup)


@pytest.mark.anyio
async def test_check_login_error_without_error(api: AmazonEchoApi) -> None:
    """A page without an error box passes."""
    api._login._check_login_error(BeautifulSoup(MFA_PAGE, "html.parser"))


@pytest.mark.anyio
async def test_login_interactive_oauth(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Email, password and OTP are each submitted to the page asking for them."""
    login = api._login
    session_request = AsyncMock(
        side_effect=[
            _page(EMAIL_PAGE, SIGNIN_URL),
            _page(PASSWORD_PAGE, URL("https://www.amazon.com/ax/claim")),
            _page(MFA_PAGE, SIGNIN_URL),
            _page(
                "",
                MAPLANDING_URL.with_query({"openid.oa2.authorization_code": "AN1"}),
            ),
        ]
    )
    monkeypatch.setattr(login._http_wrapper, "session_request", session_request)

    result = await login._login_mode_interactive_oauth("123456")

    assert result["authorization_code"] == "AN1"
    _, email, password, otp = session_request.await_args_list
    assert email.kwargs["url"] == URL("https://www.amazon.com/ax/claim?arb=ARB")
    assert email.kwargs["input_data"]["email"] == TEST_EMAIL
    assert "password" not in email.kwargs["input_data"]
    assert password.kwargs["url"] == SIGNIN_URL
    assert password.kwargs["input_data"]["password"] == TEST_PASSWORD
    assert otp.kwargs["input_data"]["otpCode"] == "123456"


@pytest.mark.anyio
async def test_login_interactive_oauth_wrong_email(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejected email stops the login before the password is sent."""
    login = api._login
    session_request = AsyncMock(
        side_effect=[
            _page(EMAIL_PAGE, SIGNIN_URL),
            _page(
                ERROR_BOX.format(kind="warning", message="No account found")
                + EMAIL_PAGE,
                SIGNIN_URL,
            ),
        ]
    )
    monkeypatch.setattr(login._http_wrapper, "session_request", session_request)

    with pytest.raises(CannotAuthenticate, match="No account found"):
        await login._login_mode_interactive_oauth("123456")

    # The last request made was the email submission
    assert "email" in session_request.await_args_list[-1].kwargs["input_data"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("final_page", "match"),
    [
        pytest.param(
            ERROR_BOX.format(kind="error", message="The code is not valid") + MFA_PAGE,
            "The code is not valid",
            id="error_box",
        ),
        pytest.param("", "Unable to extract authorization code", id="no_error_box"),
    ],
)
async def test_login_interactive_oauth_no_code(
    api: AmazonEchoApi, final_page: str, match: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without an authorization code, Amazon's message is used when present."""
    login = api._login
    session_request = AsyncMock(
        side_effect=[
            _page(EMAIL_PAGE, SIGNIN_URL),
            _page(PASSWORD_PAGE, URL("https://www.amazon.com/ax/claim")),
            _page(MFA_PAGE, SIGNIN_URL),
            _page(final_page, SIGNIN_URL),
        ]
    )
    monkeypatch.setattr(login._http_wrapper, "session_request", session_request)

    with pytest.raises(CannotAuthenticate, match=match):
        await login._login_mode_interactive_oauth("123456")


@pytest.mark.anyio
async def test_login_interactive_oauth_unexpected_page(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The password is not posted to a page that does not ask for it."""
    login = api._login
    session_request = AsyncMock(
        side_effect=[
            _page(EMAIL_PAGE, SIGNIN_URL),
            _page(
                "<title>Verify it's you</title>"
                '<form id="verify-form" method="post" action="verify"></form>',
                SIGNIN_URL,
            ),
        ]
    )
    monkeypatch.setattr(login._http_wrapper, "session_request", session_request)

    with pytest.raises(
        CannotAuthenticate, match="Unexpected login page 'Verify it's you'"
    ):
        await login._login_mode_interactive_oauth("123456")

    for request in session_request.await_args_list:
        assert "password" not in (request.kwargs.get("input_data") or {})


@pytest.mark.anyio
async def test_login_interactive_oauth_code_with_warning(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An authorization code wins over a warning box on the final page."""
    login = api._login
    session_request = AsyncMock(
        side_effect=[
            _page(EMAIL_PAGE, SIGNIN_URL),
            _page(PASSWORD_PAGE, URL("https://www.amazon.com/ax/claim")),
            _page(MFA_PAGE, SIGNIN_URL),
            _page(
                ERROR_BOX.format(kind="warning", message="Enable cookies"),
                MAPLANDING_URL.with_query({"openid.oa2.authorization_code": "AN1"}),
            ),
        ]
    )
    monkeypatch.setattr(login._http_wrapper, "session_request", session_request)

    result = await login._login_mode_interactive_oauth("123456")

    assert result["authorization_code"] == "AN1"


@pytest.mark.anyio
async def test_login_stored_data_registers_capabilities(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stored-data login re-registers device capabilities."""
    state = api._login._session_state_data
    state.login_stored_data = {"customer_info": {}}
    state.account_customer_id = "CUSTOMER_ID"
    register_device_capabilities = AsyncMock()
    monkeypatch.setattr(
        api._login, "_register_device_capabilities", register_device_capabilities
    )

    await api._login.login_mode_stored_data()

    register_device_capabilities.assert_awaited_once()


@pytest.mark.anyio
async def test_login_stored_data_without_data_raises(api: AmazonEchoApi) -> None:
    """Stored-data login without stored data raises WrongMethod."""
    api._login._session_state_data.login_stored_data = {}

    with pytest.raises(WrongMethod):
        await api._login.login_mode_stored_data()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "expected_customer_id", "expectation"),
    [
        pytest.param(
            {"id": "CUSTOMER_ID", "countryOfResidence": "US"},
            "CUSTOMER_ID",
            nullcontext(),
            id="country_set",
        ),
        pytest.param(
            {"id": "CUSTOMER_ID"},
            None,
            pytest.raises(MissingCountryError),
            id="country_missing",
        ),
        pytest.param(
            {"id": "CUSTOMER_ID", "countryOfResidence": None},
            None,
            pytest.raises(MissingCountryError),
            id="country_none",
        ),
        pytest.param(
            {"id": "CUSTOMER_ID", "countryOfResidence": ""},
            None,
            pytest.raises(MissingCountryError),
            id="country_empty",
        ),
    ],
)
async def test_obtain_account_customer_id(
    api: AmazonEchoApi,
    response: dict[str, str | None],
    expected_customer_id: str | None,
    expectation: AbstractContextManager[object],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """The customer id is stored only when a country of residence is set."""
    login = api._login
    mock_json_response(response)

    with expectation:
        await login.obtain_account_customer_id()

    assert login._session_state_data.account_customer_id == expected_customer_id


@pytest.fixture
def mock_response(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> Callable[[int, dict[str, Any]], AsyncMock]:
    """Return a setter making every request return the given status and JSON.

    The setter returns the session_request mock, to assert on the request.
    """

    def _mock_response(status: int, response: dict[str, Any]) -> AsyncMock:
        session_request = AsyncMock(return_value=(None, MagicMock(status=status)))
        monkeypatch.setattr(api._http_wrapper, "session_request", session_request)
        monkeypatch.setattr(
            api._http_wrapper, "response_to_json", AsyncMock(return_value=response)
        )
        return session_request

    return _mock_response


def _register_response() -> dict[str, Any]:
    """Build a successful device registration response."""
    return {
        "response": {
            "success": {
                "tokens": {
                    "mac_dms": {
                        "adp_token": "ADP_TOKEN",
                        "device_private_key": "PRIVATE_KEY",
                    },
                    "store_authentication_cookie": {"cookie": "STORE_COOKIE"},
                    "bearer": {
                        "access_token": "ACCESS",
                        "refresh_token": "REFRESH",
                        "expires_in": "3600",
                    },
                    "website_cookies": [
                        {"Name": "session-id", "Value": '"SESSION_ID"'},
                        {"Name": "ubid-main", "Value": "UBID"},
                    ],
                },
                "extensions": {
                    "device_info": {"device_serial_number": "SERIAL"},
                    "customer_info": {"home_region": "NA"},
                },
            }
        }
    }


@pytest.mark.anyio
async def test_serial_number_is_loaded_from_stored_data(api: AmazonEchoApi) -> None:
    """A login with stored data reuses the registered device serial number."""
    api._session_state_data.login_stored_data = {
        "device_info": {"device_serial_number": "STORED_SERIAL"}
    }

    login = AmazonLogin(api._http_wrapper, api._session_state_data)

    assert login._serial == "STORED_SERIAL"


@pytest.mark.anyio
async def test_get_inputs_from_soup_skips_unnamed_inputs(api: AmazonEchoApi) -> None:
    """Hidden inputs without a name are not collected."""
    soup = BeautifulSoup(
        '<form><input type="hidden" value="ORPHAN" />'
        '<input type="hidden" name="kept" value="VALUE" /></form>',
        "html.parser",
    )

    assert api._login._get_inputs_from_soup(soup) == {"kept": "VALUE"}


@pytest.mark.anyio
async def test_register_device(
    api: AmazonEchoApi, mock_response: Callable[[int, dict[str, Any]], AsyncMock]
) -> None:
    """A registered device returns its tokens, cookies and account details."""
    session_request = mock_response(HTTPStatus.OK, _register_response())
    api._http_wrapper.cookies["frc"] = "FRC"
    login = api._login
    before = datetime.now(UTC).timestamp()

    login_data = await login._register_device(
        {"authorization_code": "AUTH_CODE", "code_verifier": b"VERIFIER"}
    )

    expires = login_data.pop("expires")
    assert before + 3600 <= expires <= datetime.now(UTC).timestamp() + 3600
    assert login_data == {
        "adp_token": "ADP_TOKEN",
        "device_private_key": "PRIVATE_KEY",
        "access_token": "ACCESS",
        "refresh_token": "REFRESH",
        "website_cookies": {"session-id": "SESSION_ID", "ubid-main": "UBID"},
        "store_authentication_cookie": {"cookie": "STORE_COOKIE"},
        "device_info": {"device_serial_number": "SERIAL"},
        "customer_info": {"home_region": "NA"},
    }
    (request,) = session_request.await_args_list
    assert request.kwargs["method"] == HTTPMethod.POST
    assert request.kwargs["url"] == URL("https://api.amazon.com/auth/register")
    body = request.kwargs["input_data"]
    assert body["auth_data"]["authorization_code"] == "AUTH_CODE"
    assert body["auth_data"]["code_verifier"] == "VERIFIER"
    assert body["auth_data"]["client_id"] == login._build_client_id()
    assert body["registration_data"]["device_serial"] == login._serial
    assert body["user_context_map"] == {"frc": "FRC"}
    assert body["cookies"]["domain"] == ".amazon.com"


@pytest.mark.anyio
async def test_register_device_failure_raises(
    api: AmazonEchoApi, mock_response: Callable[[int, dict[str, Any]], AsyncMock]
) -> None:
    """A rejected registration raises with Amazon's message."""
    mock_response(
        HTTPStatus.BAD_REQUEST,
        {"response": {"error": {"message": "Invalid authorization code"}}},
    )
    api._http_wrapper.cookies["frc"] = "FRC"

    with pytest.raises(
        CannotRegisterDevice, match="Bad Request: Invalid authorization code"
    ):
        await api._login._register_device(
            {"authorization_code": "AUTH_CODE", "code_verifier": b"VERIFIER"}
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "expectation"),
    [
        pytest.param(HTTPStatus.NO_CONTENT, nullcontext(), id="registered"),
        pytest.param(
            HTTPStatus.BAD_REQUEST,
            pytest.raises(CannotRegisterDevice, match="returned 400"),
            id="rejected",
        ),
    ],
)
async def test_register_device_capabilities(
    api: AmazonEchoApi,
    mock_response: Callable[[int, dict[str, Any]], AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
    status: HTTPStatus,
    expectation: AbstractContextManager[object],
) -> None:
    """Capabilities are sent with a fresh access token and must return 204."""
    session_request = mock_response(status, {})
    refresh_data = AsyncMock(return_value=(True, {REFRESH_ACCESS_TOKEN: "FRESH"}))
    monkeypatch.setattr(api._http_wrapper, "refresh_data", refresh_data)

    with expectation:
        await api._login._register_device_capabilities()

    refresh_data.assert_awaited_once_with(REFRESH_ACCESS_TOKEN)
    session_request.assert_awaited_once_with(
        method=HTTPMethod.PUT,
        url=URL("https://api.amazonalexa.com/v1/devices/@self/capabilities"),
        input_data=DEVICE_CAPABILITIES,
        json_data=True,
        extended_headers={"Authorization": "Bearer FRESH"},
    )


@pytest.mark.anyio
async def test_login_interactive_runs_each_step(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interactive login registers the device and stores its login data."""
    login = api._login
    oauth_data = {"authorization_code": "AUTH_CODE", "code_verifier": b"VERIFIER"}
    steps = MagicMock()
    for name, mock in (
        ("_login_mode_interactive_oauth", AsyncMock(return_value=oauth_data)),
        ("_register_device", AsyncMock(return_value={"access_token": "ACCESS"})),
        ("_domain_refresh_auth_cookies", AsyncMock()),
        ("_register_device_capabilities", AsyncMock()),
        ("obtain_account_customer_id", AsyncMock()),
    ):
        monkeypatch.setattr(login, name, mock)
        steps.attach_mock(mock, name)

    login_data = await login.login_mode_interactive("123456")

    assert steps.mock_calls == [
        call._login_mode_interactive_oauth("123456"),
        call._register_device(oauth_data),
        call._domain_refresh_auth_cookies(),
        call._register_device_capabilities(),
        call.obtain_account_customer_id(),
    ]
    assert login_data == {
        "access_token": "ACCESS",
        "site": "https://www.amazon.com",
    }
    assert login._session_state_data.login_stored_data is login_data


@pytest.mark.anyio
async def test_login_interactive_oauth_retries_captcha_in_japanese(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A captcha on the first sign-in is retried with Japanese as the language."""
    login = api._login
    oauth_login = AsyncMock(
        side_effect=[
            (
                SIGNIN_URL,
                BeautifulSoup('<form id="cvf-aamation-challenge-form">', "html.parser"),
            ),
            (SIGNIN_URL, BeautifulSoup(MFA_PAGE, "html.parser")),
        ]
    )
    monkeypatch.setattr(login, "_oauth_login", oauth_login)
    monkeypatch.setattr(
        login._http_wrapper,
        "session_request",
        AsyncMock(
            return_value=_page(
                "", MAPLANDING_URL.with_query({"openid.oa2.authorization_code": "AN1"})
            )
        ),
    )

    result = await login._login_mode_interactive_oauth("123456")

    assert result["authorization_code"] == "AN1"
    first, retry = oauth_login.await_args_list
    assert first.kwargs == {}
    assert retry.kwargs == {"registration_language": "ja_JP"}
    assert retry.args == first.args


@pytest.mark.anyio
async def test_login_stored_data_obtains_missing_customer_id(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stored-data login looks up the customer id when it is not stored."""
    api._session_state_data.login_stored_data = {"customer_info": {}}
    obtain_account_customer_id = AsyncMock()
    monkeypatch.setattr(
        api._login, "obtain_account_customer_id", obtain_account_customer_id
    )
    monkeypatch.setattr(api._login, "_register_device_capabilities", AsyncMock())

    await api._login.login_mode_stored_data()

    obtain_account_customer_id.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        pytest.param(
            {"alexaHostName": "alexa.amazon.co.uk"}, "alexa.amazon.co.uk", id="named"
        ),
        pytest.param({}, "alexa.amazon.com", id="default"),
    ],
)
async def test_get_alexa_domain(
    api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    response: dict[str, Any],
    expected: str,
) -> None:
    """The Alexa host name is read from the welcome page, else the current one."""
    session_request = mock_json_response(response)

    assert await api._login._get_alexa_domain() == expected
    session_request.assert_awaited_once_with(
        method=HTTPMethod.GET, url=URL("https://alexa.amazon.com/api/welcome")
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("home_region", "alexa_host", "expected_domain"),
    [
        pytest.param("FE", None, "co.jp", id="far-east"),
        pytest.param("EU", "alexa.amazon.co.uk", "co.uk", id="other-domain"),
        pytest.param("NA", "alexa.amazon.com", None, id="default-domain"),
    ],
)
async def test_domain_refresh_auth_cookies(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
    home_region: str,
    alexa_host: str | None,
    expected_domain: str | None,
) -> None:
    """Cookies are refreshed for the account's own site when it is not .com."""
    login = api._login
    login._session_state_data.login_stored_data = {
        "customer_info": {"home_region": home_region}
    }
    get_alexa_domain = AsyncMock(return_value=alexa_host)
    refresh_auth_cookies = AsyncMock()
    monkeypatch.setattr(login, "_get_alexa_domain", get_alexa_domain)
    monkeypatch.setattr(login, "_refresh_auth_cookies", refresh_auth_cookies)
    monkeypatch.setattr(login._http_wrapper, "clear_csrf_cookie", AsyncMock())

    await login._domain_refresh_auth_cookies()

    assert get_alexa_domain.await_args_list == ([] if alexa_host is None else [()])
    assert refresh_auth_cookies.await_args_list == (
        [] if expected_domain is None else [()]
    )
    assert login._session_state_data.domain == (expected_domain or "com")


@pytest.mark.anyio
async def test_refresh_auth_cookies(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refreshed cookies replace the old ones for each of their domains."""
    login = api._login
    login._session_state_data.login_stored_data = {
        "website_cookies": {"old": "OLD"},
        "store_authentication_cookie": {"cookie": "OLD_SESSION"},
    }
    refresh_data = AsyncMock(
        return_value=(
            True,
            {
                "response": {
                    "tokens": {
                        "cookies": {
                            ".amazon.co.uk": [
                                {"Name": "session-token", "Value": '"NEW_SESSION"'},
                                {"Name": "ubid-acbuk", "Value": "UBID"},
                            ],
                            ".amazon.com": [{"Name": "at-main", "Value": "AT"}],
                        }
                    }
                }
            },
        )
    )
    clear_cookies = AsyncMock()
    set_cookies = AsyncMock()
    monkeypatch.setattr(login._http_wrapper, "refresh_data", refresh_data)
    monkeypatch.setattr(login._http_wrapper, "clear_cookies", clear_cookies)
    monkeypatch.setattr(login._http_wrapper, "set_cookies", set_cookies)

    await login._refresh_auth_cookies()

    refresh_data.assert_awaited_once_with(REFRESH_AUTH_COOKIES)
    clear_cookies.assert_awaited_once()
    uk = URL.build(scheme="https", host=".amazon.co.uk")
    com = URL.build(scheme="https", host=".amazon.com")
    assert set_cookies.await_args_list == [
        call({"session-token": "NEW_SESSION"}, uk),
        call({"ubid-acbuk": "UBID"}, uk),
        call({"at-main": "AT"}, com),
    ]
    assert login._session_state_data.login_stored_data == {
        "website_cookies": {
            "session-token": "NEW_SESSION",
            "ubid-acbuk": "UBID",
            "at-main": "AT",
        },
        "store_authentication_cookie": {"cookie": "NEW_SESSION"},
    }
