# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Amazon login flow."""

from contextlib import AbstractContextManager, nullcontext
from unittest.mock import AsyncMock, MagicMock

import pytest
from bs4 import BeautifulSoup
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import (
    CannotAuthenticate,
    MissingCountryError,
    WrongMethod,
)

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
async def test_login_interactive_oauth(api: AmazonEchoApi) -> None:
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
    login._http_wrapper.session_request = session_request  # type: ignore[method-assign]

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
async def test_login_interactive_oauth_wrong_email(api: AmazonEchoApi) -> None:
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
    login._http_wrapper.session_request = session_request  # type: ignore[method-assign]

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
    api: AmazonEchoApi, final_page: str, match: str
) -> None:
    """Without an authorization code, Amazon's message is used when present."""
    login = api._login
    login._http_wrapper.session_request = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _page(EMAIL_PAGE, SIGNIN_URL),
            _page(PASSWORD_PAGE, URL("https://www.amazon.com/ax/claim")),
            _page(MFA_PAGE, SIGNIN_URL),
            _page(final_page, SIGNIN_URL),
        ]
    )

    with pytest.raises(CannotAuthenticate, match=match):
        await login._login_mode_interactive_oauth("123456")


@pytest.mark.anyio
async def test_login_interactive_oauth_unexpected_page(api: AmazonEchoApi) -> None:
    """The password is not posted to a page that does not ask for it."""
    login = api._login
    session_request = AsyncMock(
        side_effect=[
            _page(EMAIL_PAGE, SIGNIN_URL),
            _page(
                '<form id="verify-form" method="post" action="verify"></form>',
                SIGNIN_URL,
            ),
        ]
    )
    login._http_wrapper.session_request = session_request  # type: ignore[method-assign]

    with pytest.raises(CannotAuthenticate, match="MFA OTP code not found"):
        await login._login_mode_interactive_oauth("123456")

    for call in session_request.await_args_list:
        assert "password" not in (call.kwargs.get("input_data") or {})


@pytest.mark.anyio
async def test_login_interactive_oauth_code_with_warning(api: AmazonEchoApi) -> None:
    """An authorization code wins over a warning box on the final page."""
    login = api._login
    login._http_wrapper.session_request = AsyncMock(  # type: ignore[method-assign]
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

    result = await login._login_mode_interactive_oauth("123456")

    assert result["authorization_code"] == "AN1"


@pytest.mark.anyio
async def test_login_stored_data_registers_capabilities(api: AmazonEchoApi) -> None:
    """Stored-data login re-registers device capabilities."""
    state = api._login._session_state_data
    state.login_stored_data = {"customer_info": {}}
    state.account_customer_id = "CUSTOMER_ID"
    api._login._register_device_capabilities = AsyncMock()  # type: ignore[method-assign]

    await api._login.login_mode_stored_data()

    api._login._register_device_capabilities.assert_awaited_once()


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
) -> None:
    """The customer id is stored only when a country of residence is set."""
    login = api._login
    login._http_wrapper.session_request = AsyncMock(return_value=(None, None))  # type: ignore[method-assign]
    login._http_wrapper.response_to_json = AsyncMock(return_value=response)  # type: ignore[method-assign]

    with expectation:
        await login.obtain_account_customer_id()

    assert login._session_state_data.account_customer_id == expected_customer_id
