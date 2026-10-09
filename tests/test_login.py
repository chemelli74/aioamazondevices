# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Amazon login flow."""

from pathlib import Path

import pytest
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotAuthenticate
from aioamazondevices.structures import AmazonLoginContext, AmazonSaveDataConfig

from .const import FIXTURES_DIR, TEST_EMAIL, TEST_PASSWORD

MAPLANDING_URL = URL("https://www.amazon.com/ap/maplanding")


@pytest.mark.anyio
async def test_explicit_interactive_login_context(
    client_session: ClientSession,
    tmp_path: Path,
) -> None:
    """Interactive reauth can reuse non-secret context without stored session data."""
    api = AmazonEchoApi(
        client_session,
        TEST_EMAIL,
        TEST_PASSWORD,
        save_data=AmazonSaveDataConfig(path=tmp_path),
        login_data=AmazonLoginContext(
            site="https://www.amazon.co.uk",
            device_serial_number="EXISTING_SERIAL",
        ),
    )

    assert api.domain == "co.uk"
    assert api._session_state_data.login_stored_data == {}
    assert api._login._serial == "EXISTING_SERIAL"

    client_id = api._login._build_client_id()
    assert bytes.fromhex(client_id).split(b"#", 1)[0] == b"EXISTING_SERIAL"

    oauth_url = api._login._build_oauth_url(b"code-verifier", client_id)
    assert oauth_url.host == "www.amazon.co.uk"
    assert oauth_url.path == "/ap/signin"
    assert oauth_url.query["openid.oa2.client_id"] == f"device:{client_id}"


@pytest.mark.anyio
async def test_stored_login_data_context_remains_backward_compatible(
    client_session: ClientSession,
    tmp_path: Path,
) -> None:
    """Existing stored-login callers still derive site and serial from login data."""
    login_data = {
        "site": "https://www.amazon.de",
        "device_info": {"device_serial_number": "STORED_SERIAL"},
    }
    api = AmazonEchoApi(
        client_session,
        TEST_EMAIL,
        TEST_PASSWORD,
        save_data=AmazonSaveDataConfig(path=tmp_path),
        login_data=login_data,
    )

    assert api.domain == "de"
    assert api._session_state_data.login_stored_data is login_data
    assert api._login._serial == "STORED_SERIAL"


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
