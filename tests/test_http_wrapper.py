# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the HTTP wrapper."""

import logging
from http import HTTPMethod, HTTPStatus

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from aioamazondevices import http_wrapper as http_wrapper_module
from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import CSRF_COOKIE
from aioamazondevices.exceptions import CannotRetrieveData

from .const import TEST_CSRF

SDP_ICE_VALUE = "rtc-private-value"
SDP_ADDRESS = "192.0.2.123"
EXPECTED_REDACTED_LOGS = 2
SDP = (
    "v=0\r\n"
    f"a=ice-pwd:{SDP_ICE_VALUE}\r\n"
    f"a=candidate:1 1 UDP 2122260223 {SDP_ADDRESS} 54400 typ host\r\n"
)


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
        pytest.param(False, [2, 5], 3, id="retries_with_backoff"),
        pytest.param(True, [], 1, id="fail_fast_does_not_retry"),
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

    async def _sleep(delay: float) -> None:
        # aiohttp internals also yield with sleep(0)
        if delay:
            sleeps.append(delay)

    monkeypatch.setattr(http_wrapper_module.asyncio, "sleep", _sleep)

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

    assert sleeps == expected_sleeps
    assert len(requests) == expected_requests


@pytest.mark.anyio
async def test_sdp_is_redacted_from_request_and_response_logs(
    api: AmazonEchoApi, caplog: pytest.LogCaptureFixture
) -> None:
    """SDP credentials and addresses are sent over the wire but omitted from logs."""
    request_payload = {"payload": {"offer": {"format": "SDP", "value": SDP}}}
    response_payload = {"responsePayload": {"answer": {"format": "SDP", "value": SDP}}}
    received_payloads: list[object] = []

    async def handler(request: web.Request) -> web.Response:
        received_payloads.append(await request.json())
        return web.json_response(response_payload)

    app = web.Application()
    app.router.add_post("/", handler)
    async with TestServer(app) as server:
        with caplog.at_level(logging.DEBUG, logger="aioamazondevices"):
            _, response = await api._http_wrapper.session_request(
                HTTPMethod.POST,
                server.make_url("/"),
                input_data=request_payload,
                json_data=True,
            )
            parsed_response = await api._http_wrapper.response_to_json(
                response, "RTC session"
            )

    assert received_payloads == [request_payload]
    assert parsed_response == response_payload
    assert SDP_ICE_VALUE not in caplog.text
    assert SDP_ADDRESS not in caplog.text
    assert caplog.text.count("[REDACTED]") == EXPECTED_REDACTED_LOGS
