# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Amazon login flow."""

import pytest
from bs4 import BeautifulSoup
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotAuthenticate

from .const import FIXTURES_DIR

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
