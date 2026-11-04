# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the HTTP wrapper."""

from http import HTTPMethod

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import CSRF_COOKIE

from .const import TEST_CSRF


@pytest.mark.anyio
async def test_csrf_cookie_sent_on_next_request(api: AmazonEchoApi) -> None:
    """A CSRF cookie set by a response is sent as a header on later requests."""
    received_csrf: list[str | None] = []

    async def handler(request: web.Request) -> web.Response:
        received_csrf.append(request.headers.get(CSRF_COOKIE))
        response = web.Response(text="<html></html>", content_type="text/html")
        response.set_cookie(CSRF_COOKIE, TEST_CSRF)
        return response

    app = web.Application()
    app.router.add_get("/", handler)
    async with TestServer(app) as server:
        url = server.make_url("/")
        await api._http_wrapper.session_request(HTTPMethod.GET, url)
        await api._http_wrapper.session_request(HTTPMethod.GET, url)

    assert received_csrf == [None, TEST_CSRF]
