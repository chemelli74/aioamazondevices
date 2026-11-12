# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the HTTP wrapper."""

from http import HTTPMethod, HTTPStatus

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from aioamazondevices import http_wrapper as http_wrapper_module
from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import CSRF_COOKIE
from aioamazondevices.exceptions import CannotRetrieveData

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


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("fail_fast", "expected_sleeps", "expected_requests"),
    [
        pytest.param(False, [2, 5], 3, id="retries-with-backoff"),
        pytest.param(True, [], 1, id="fail-fast-does-not-retry"),
    ],
)
async def test_retry_behaviour(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail_fast: bool,
    expected_sleeps: list[float],
    expected_requests: int,
) -> None:
    """Retryable statuses back off and retry, unless fail_fast is set."""
    sleeps: list[float] = []
    requests: list[web.Request] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(http_wrapper_module.asyncio, "sleep", sleep)

    async def handler(request: web.Request) -> web.Response:
        requests.append(request)
        return web.Response(status=HTTPStatus.SERVICE_UNAVAILABLE)

    app = web.Application()
    app.router.add_get("/", handler)
    async with TestServer(app) as server:
        with pytest.raises(CannotRetrieveData):
            await api._http_wrapper.session_request(
                HTTPMethod.GET, server.make_url("/"), fail_fast=fail_fast
            )

    # aiohttp internals also yield with sleep(0), so only the delays are compared.
    assert [delay for delay in sleeps if delay] == expected_sleeps
    assert len(requests) == expected_requests
