# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Amazon login flow."""

import pytest
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotAuthenticate

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
