# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for correcting the AVS site from the SynchronizeState response."""

from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock

import pytest

from aioamazondevices.const.http import REFRESH_ACCESS_TOKEN
from aioamazondevices.exceptions import UpdatedAVSSite
from aioamazondevices.implementation.http2 import AmazonHTTP2Client

HOME_REGION_EVENTS_URL = "https://bob-dispatch-prod-eu.amazon.com/v20160207/events"
CORRECT_SITE = "https://bob-dispatch-prod-na.amazon.com"


def _http2_client(post: AsyncMock) -> AmazonHTTP2Client:
    """Build an HTTP2 client whose POST requests are answered by ``post``."""
    session_state_data = MagicMock()
    session_state_data.login_stored_data = {
        "customer_info": {"home_region": "EU"},
        REFRESH_ACCESS_TOKEN: "token",
    }
    httpx_client = MagicMock()
    httpx_client.post = post
    return AmazonHTTP2Client(MagicMock(), session_state_data, httpx_client)


def _response(status_code: int, content: bytes = b"") -> MagicMock:
    """Build an httpx response with a multipart content type."""
    return MagicMock(
        status_code=status_code,
        headers={"content-type": 'multipart/related; boundary="b"'},
        content=content,
        text=content.decode(),
    )


@pytest.mark.anyio
async def test_avs_site_kept_when_home_region_is_correct() -> None:
    """An empty response means the home region site is the right one."""
    post = AsyncMock(return_value=_response(HTTPStatus.NO_CONTENT))
    client = _http2_client(post)

    await client._check_avs_site()
    await client._check_avs_site()

    assert [c.args[0] for c in post.await_args_list] == [HOME_REGION_EVENTS_URL] * 2


@pytest.mark.anyio
async def test_avs_site_updated_from_synchronize_state_response() -> None:
    """A wrong home region site is replaced by the endpoint in the response."""
    body = (
        b"--b\r\nContent-Type: application/json\r\n\r\n"
        b'{"directive": {"payload": {"endpoint": "' + CORRECT_SITE.encode() + b'"}}}'
        b"\r\n--b--"
    )
    post = AsyncMock(
        side_effect=[
            _response(HTTPStatus.OK, body),
            _response(HTTPStatus.NO_CONTENT),
        ]
    )
    client = _http2_client(post)

    with pytest.raises(UpdatedAVSSite):
        await client._check_avs_site()
    await client._check_avs_site()

    assert [c.args[0] for c in post.await_args_list] == [
        HOME_REGION_EVENTS_URL,
        f"{CORRECT_SITE}/v20160207/events",
    ]
