# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the HTTP wrapper."""

from http import HTTPMethod, HTTPStatus
from typing import Any

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


async def _request_until_failure(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch, *, fail_fast: bool
) -> list[float]:
    """Send a request to a server that is always unavailable."""
    sleeps: list[float] = []

    async def _sleep(delay: float) -> None:
        # aiohttp internals also yield with sleep(0)
        if delay:
            sleeps.append(delay)

    monkeypatch.setattr(http_wrapper_module.asyncio, "sleep", _sleep)

    async def handler(request: web.Request) -> web.Response:  # noqa: ARG001
        return web.Response(status=HTTPStatus.SERVICE_UNAVAILABLE)

    app = web.Application()
    app.router.add_get("/", handler)
    async with TestServer(app) as server:
        with pytest.raises(CannotRetrieveData):
            await api._http_wrapper.session_request(
                HTTPMethod.GET, server.make_url("/"), fail_fast=fail_fast
            )
    return sleeps


@pytest.mark.anyio
async def test_retry_with_backoff(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retryable statuses are retried with back-off delays."""
    sleeps = await _request_until_failure(api, monkeypatch, fail_fast=False)

    assert sleeps == [2, 5, 8, 12, 21]


@pytest.mark.anyio
async def test_fail_fast_does_not_retry(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With fail_fast a retryable status fails without retrying."""
    sleeps = await _request_until_failure(api, monkeypatch, fail_fast=True)

    assert sleeps == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("login_data", "expected"),
    [
        ({"customer_info": {"user_id": "USER_ID"}}, "USER_ID"),
        ({"customer_info": {"user_id": ""}}, None),
        ({"customer_info": {}}, None),
        ({}, None),
    ],
)
async def test_user_id(
    api: AmazonEchoApi, login_data: dict[str, Any], expected: str | None
) -> None:
    """The user id is read from the stored customer info."""
    api._session_state_data.login_stored_data = login_data

    assert api._session_state_data.user_id == expected
