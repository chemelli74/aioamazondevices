# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the HTTP wrapper."""

from collections.abc import AsyncIterator, Callable
from http import HTTPMethod, HTTPStatus
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer
from yarl import URL

from aioamazondevices import http_wrapper as http_wrapper_module
from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import (
    ARRAY_WRAPPER,
    CSRF_COOKIE,
    REFRESH_ACCESS_TOKEN,
    REFRESH_AUTH_COOKIES,
    URI_CAPABILITIES,
    URI_SIGNIN,
)
from aioamazondevices.exceptions import (
    CannotAuthenticate,
    CannotConnect,
    CannotRetrieveData,
)
from aioamazondevices.structures import AmazonSaveDataConfig

from .const import TEST_ACCESS_TOKEN, TEST_CSRF, TEST_EMAIL, TEST_PASSWORD

TEST_SESSION_TOKEN = "session-token-value"  # noqa: S105
TEST_REFRESH_TOKEN = "refresh-token"  # noqa: S105


async def _status(request: web.Request) -> web.Response:
    """Reply with the status given in the path."""
    return web.Response(status=int(request.match_info["status"]))


async def _signin(_: web.Request) -> web.Response:
    """Redirect the sign-in page to a missing page, as Amazon does."""
    raise web.HTTPFound("/status/404")


async def _body(request: web.Request) -> web.Response:
    """Reply with the body and content type given in the query."""
    return web.Response(
        text=request.query["text"], content_type=request.query["content_type"]
    )


async def _status_no_content(_: web.Request) -> web.Response:
    """Reply with no content, as the capabilities endpoint does."""
    return web.Response(status=HTTPStatus.NO_CONTENT)


@pytest.fixture
async def server() -> AsyncIterator[TestServer]:
    """Run a local server replying like the Amazon endpoints."""
    app = web.Application()
    app.router.add_get("/status/{status}", _status)
    app.router.add_get(f"/{URI_SIGNIN}", _signin)
    app.router.add_get(f"/{URI_SIGNIN}/body", _body)
    app.router.add_get(f"/{URI_CAPABILITIES}", _status_no_content)
    app.router.add_get("/body", _body)
    test_server = TestServer(app)
    async with test_server:
        yield test_server


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


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "phrase"),
    [
        pytest.param(199, "Miscellaneous Warning", id="199"),
        pytest.param(299, "Miscellaneous Persistent Warning", id="299"),
        pytest.param(HTTPStatus.NOT_FOUND, "Not Found", id="standard"),
    ],
)
async def test_http_phrase_error(api: AmazonEchoApi, error: int, phrase: str) -> None:
    """Amazon warning codes have their own phrase, others use the HTTP one."""
    assert await api._http_wrapper.http_phrase_error(error) == phrase


@pytest.mark.anyio
async def test_refresh_data_without_login(api: AmazonEchoApi) -> None:
    """Nothing can be refreshed before logging in."""
    assert await api._http_wrapper.refresh_data(REFRESH_ACCESS_TOKEN) == (False, {})


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("data_type", "response", "expected"),
    [
        pytest.param(
            REFRESH_ACCESS_TOKEN,
            {REFRESH_ACCESS_TOKEN: TEST_ACCESS_TOKEN},
            (True, {REFRESH_ACCESS_TOKEN: TEST_ACCESS_TOKEN}),
            id="access-token",
        ),
        pytest.param(
            REFRESH_AUTH_COOKIES,
            {"cookies": {}},
            (True, {"cookies": {}}),
            id="auth-cookies",
        ),
        pytest.param(
            REFRESH_ACCESS_TOKEN,
            {},
            (False, {}),
            id="access-token-missing",
        ),
    ],
)
async def test_refresh_data(
    api: AmazonEchoApi,
    mock_json_response: Callable[..., AsyncMock],
    data_type: str,
    response: dict[str, Any],
    expected: tuple[bool, dict[str, Any]],
) -> None:
    """The refreshed data is returned only when the response carries it."""
    api._session_state_data.login_stored_data = {"refresh_token": TEST_REFRESH_TOKEN}
    session_request = mock_json_response(response)

    assert await api._http_wrapper.refresh_data(data_type) == expected

    assert session_request.await_args is not None
    assert session_request.await_args.kwargs["input_data"]["source_token"] == (
        TEST_REFRESH_TOKEN
    )


@pytest.mark.anyio
async def test_refresh_data_request_failed(
    api: AmazonEchoApi, mock_json_response: Callable[..., AsyncMock]
) -> None:
    """A failed refresh request returns no data."""
    api._session_state_data.login_stored_data = {"refresh_token": TEST_REFRESH_TOKEN}
    mock_json_response({}, HTTPStatus.BAD_REQUEST)

    assert await api._http_wrapper.refresh_data(REFRESH_ACCESS_TOKEN) == (False, {})


@pytest.mark.anyio
async def test_refresh_access_token_is_stored(
    api: AmazonEchoApi, mock_json_response: Callable[..., AsyncMock]
) -> None:
    """A refreshed access token replaces the stored one."""
    api._session_state_data.login_stored_data = {"refresh_token": TEST_REFRESH_TOKEN}
    mock_json_response({REFRESH_ACCESS_TOKEN: TEST_ACCESS_TOKEN})

    await api._http_wrapper.refresh_data(REFRESH_ACCESS_TOKEN)

    assert api._session_state_data.login_stored_data[REFRESH_ACCESS_TOKEN] == (
        TEST_ACCESS_TOKEN
    )


@pytest.mark.anyio
async def test_logged_in_cookies_set_for_both_domains(
    client_session: ClientSession, tmp_path: Path, server: TestServer
) -> None:
    """Once logged in outside the US, website cookies are set for amazon.com too."""
    api = AmazonEchoApi(
        client_session,
        TEST_EMAIL,
        TEST_PASSWORD,
        save_data=AmazonSaveDataConfig(path=tmp_path),
        login_data={
            "site": "https://www.amazon.it",
            "device_info": {"device_serial_number": "serial"},
            "website_cookies": {},
            "store_authentication_cookie": {"cookie": TEST_SESSION_TOKEN},
        },
    )

    await api._http_wrapper.session_request(
        HTTPMethod.GET, server.make_url("/status/200")
    )

    for host in ("www.amazon.it", "www.amazon.com"):
        cookies = client_session.cookie_jar.filter_cookies(
            URL.build(scheme="https", host=host)
        )
        assert cookies["session-token"].value == TEST_SESSION_TOKEN
        assert cookies["lc-acbit"].value == "it-IT"


@pytest.mark.anyio
async def test_connection_error(api: AmazonEchoApi) -> None:
    """A connection failure is raised as CannotConnect."""
    async with TestServer(web.Application()) as closed_server:
        url = closed_server.make_url("/")

    with pytest.raises(CannotConnect):
        await api._http_wrapper.session_request(HTTPMethod.GET, url)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status",
    [
        pytest.param(HTTPStatus.UNAUTHORIZED, id="unauthorized"),
        pytest.param(HTTPStatus.FORBIDDEN, id="forbidden"),
        pytest.param(
            HTTPStatus.PROXY_AUTHENTICATION_REQUIRED,
            id="proxy-authentication-required",
        ),
    ],
)
async def test_authentication_error(
    api: AmazonEchoApi, server: TestServer, status: HTTPStatus
) -> None:
    """Authentication statuses are raised as CannotAuthenticate."""
    with pytest.raises(CannotAuthenticate):
        await api._http_wrapper.session_request(
            HTTPMethod.GET, server.make_url(f"/status/{status}")
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "status"),
    [
        pytest.param(f"/{URI_SIGNIN}", HTTPStatus.NOT_FOUND, id="signin"),
        pytest.param(f"/{URI_CAPABILITIES}", HTTPStatus.NO_CONTENT, id="capabilities"),
    ],
)
async def test_expected_errors_ignored(
    api: AmazonEchoApi, server: TestServer, path: str, status: HTTPStatus
) -> None:
    """The sign-in and capabilities endpoints reply with errors by design."""
    _, response = await api._http_wrapper.session_request(
        HTTPMethod.GET, server.make_url(path)
    )

    assert response.status == status


@pytest.mark.anyio
async def test_save_data_callback(
    client_session: ClientSession, tmp_path: Path, server: TestServer
) -> None:
    """Each response is passed to the save data callback."""
    callback = AsyncMock()
    api = AmazonEchoApi(
        client_session,
        TEST_EMAIL,
        TEST_PASSWORD,
        save_data=AmazonSaveDataConfig(path=tmp_path, callback=callback),
    )
    url = server.make_url("/body").with_query(text="hello", content_type="text/plain")

    await api._http_wrapper.session_request(HTTPMethod.GET, url)

    callback.assert_awaited_once_with(
        tmp_path, "hello", url.human_repr(), "text/plain; charset=utf-8"
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("text", "description", "expected"),
    [
        pytest.param("[1, 2]", "", {ARRAY_WRAPPER: [1, 2]}, id="list"),
        pytest.param("{}", "empty", {}, id="empty"),
    ],
)
async def test_response_to_json(
    api: AmazonEchoApi,
    server: TestServer,
    text: str,
    description: str,
    expected: dict[str, Any],
) -> None:
    """A JSON list is wrapped into a dict, and empty data becomes an empty dict."""
    _, response = await api._http_wrapper.session_request(
        HTTPMethod.GET,
        server.make_url("/body").with_query(text=text, content_type="application/json"),
    )

    assert await api._http_wrapper.response_to_json(response, description) == expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("text", "warned"),
    [
        pytest.param("[]", False, id="empty-array"),
        pytest.param("{}", True, id="empty-object"),
        pytest.param("null", True, id="null"),
    ],
)
async def test_response_to_json_empty_data_warning(
    api: AmazonEchoApi,
    server: TestServer,
    caplog: pytest.LogCaptureFixture,
    text: str,
    warned: bool,
) -> None:
    """An empty array is a valid reply and is not logged as empty data."""
    _, response = await api._http_wrapper.session_request(
        HTTPMethod.GET,
        server.make_url("/body").with_query(text=text, content_type="application/json"),
    )

    assert await api._http_wrapper.response_to_json(response, "") == {}
    assert ("Empty JSON data received" in caplog.text) is warned


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("url", "error"),
    [
        pytest.param(
            URL("/body").with_query(text="<html/>", content_type="text/html"),
            ValueError,
            id="not-json",
        ),
        pytest.param(
            URL("/body").with_query(text="{corrupted", content_type="application/json"),
            ValueError,
            id="corrupted",
        ),
        pytest.param(
            URL(f"/{URI_SIGNIN}/body").with_query(
                text="<html/>", content_type="text/html"
            ),
            CannotAuthenticate,
            id="signin-page",
        ),
    ],
)
async def test_response_to_json_errors(
    api: AmazonEchoApi, server: TestServer, url: URL, error: type[Exception]
) -> None:
    """A response that is not valid JSON raises, depending on its origin."""
    _, response = await api._http_wrapper.session_request(
        HTTPMethod.GET, server.make_url(url)
    )

    with pytest.raises(error):
        await api._http_wrapper.response_to_json(response, "test")


@pytest.mark.anyio
async def test_clear_cookies(api: AmazonEchoApi, client_session: ClientSession) -> None:
    """Clearing cookies empties the cookie jar and forgets the CSRF token."""
    wrapper = api._http_wrapper
    await wrapper.set_cookies({"name": "value"}, URL("https://www.amazon.com"))
    wrapper._csrf_cookie = TEST_CSRF

    await wrapper.clear_cookies()

    assert len(client_session.cookie_jar) == 0
    assert wrapper._csrf_cookie is None
