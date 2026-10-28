# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the AVS HTTP2 push client."""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any
from unittest.mock import AsyncMock, call

import anyio
import httpx
import orjson
import pytest
from h2.errors import ErrorCodes
from h2.events import ConnectionTerminated

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import HTTP2_DIRECTIVES_VERSION, REFRESH_ACCESS_TOKEN
from aioamazondevices.exceptions import (
    AVSStreamEndedUnexpectedly,
    CannotAuthenticate,
    CannotConnect,
    CannotRetrieveData,
    UpdatedAVSSite,
)
from aioamazondevices.implementation import http2
from aioamazondevices.implementation.http2 import (
    AmazonHTTP2Client,
    AvsDirectiveStreamParser,
    _extract_rendering_updates,
    _is_notification_change_duplicate,
    _process_rendering_update,
    _TaskAction,
)
from aioamazondevices.structures import AmazonPushMessage

from .const import TEST_SERIAL_1

TEST_BEARER = "access-token"
AVS_SITE = "https://bob-dispatch-prod-eu.amazon.com"
NEW_AVS_SITE = "https://bob-dispatch-prod-na.amazon.com"
BOUNDARY = "avs-boundary"
DELIMITER = f"--{BOUNDARY}".encode()
MULTIPART = f'multipart/related; boundary="{BOUNDARY}"'


def _part(body: dict[str, Any]) -> bytes:
    """Build one JSON part of a multipart AVS response."""
    return b"Content-Type: application/json\r\n\r\n" + orjson.dumps(body)


def _multipart(*parts: bytes) -> bytes:
    """Build a multipart body, which starts with a delimiter like the AVS stream."""
    return b"".join(DELIMITER + b"\r\n" + part + b"\r\n" for part in parts) + DELIMITER


def _update(
    resource_id: str = AmazonPushMessage.VolumeChange.value,
    payload: object = None,
    **fields: object,
) -> dict[str, Any]:
    """Build a rendering update for a push event."""
    if payload is None:
        payload = {"dopplerId": {"deviceSerialNumber": TEST_SERIAL_1}}
    return {
        "resourceId": resource_id,
        "resourceMetadata": {"payload": payload},
        **fields,
    }


def _directive(*updates: object) -> dict[str, Any]:
    """Build a directive carrying the given rendering updates."""
    return {"directive": {"payload": {"renderingUpdates": list(updates)}}}


def _caused(exc: BaseException, cause: BaseException) -> BaseException:
    """Return exc with cause set as its __cause__."""
    exc.__cause__ = cause
    return exc


def _goaway(error_code: ErrorCodes) -> Exception:
    """Return an h2 error wrapping a GOAWAY frame with the given error code."""
    terminated = ConnectionTerminated()
    terminated.error_code = error_code
    return Exception(terminated)


async def _stream(*chunks: bytes, stay_open: bool = False) -> AsyncIterator[bytes]:
    """Yield the chunks of a directives stream, optionally keeping it open."""
    for chunk in chunks:
        yield chunk
    if stay_open:
        await asyncio.Event().wait()


@dataclass
class AvsServer:
    """A fake AVS server, serving one canned response per endpoint."""

    directives: httpx.Response = field(
        default_factory=lambda: httpx.Response(
            HTTPStatus.OK, headers={"content-type": MULTIPART}
        )
    )
    events: httpx.Response = field(
        default_factory=lambda: httpx.Response(HTTPStatus.NO_CONTENT)
    )
    ping: httpx.Response = field(
        default_factory=lambda: httpx.Response(HTTPStatus.NO_CONTENT)
    )
    requests: list[httpx.Request] = field(default_factory=list)

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Return the response for the requested endpoint."""
        self.requests.append(request)
        endpoint = request.url.path.rsplit("/", 1)[-1]
        response: httpx.Response = getattr(self, endpoint)
        return response

    def set_stream(self, *chunks: bytes, stay_open: bool = False) -> None:
        """Serve the given chunks on the directives stream."""
        self.directives = httpx.Response(
            HTTPStatus.OK,
            headers={"content-type": MULTIPART},
            content=_stream(*chunks, stay_open=stay_open),
        )


@pytest.fixture
def avs_server() -> AvsServer:
    """Return the fake AVS server."""
    return AvsServer()


@pytest.fixture
async def client(
    api: AmazonEchoApi, avs_server: AvsServer, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AmazonHTTP2Client]:
    """Return a logged in HTTP2 client talking to the fake AVS server."""
    api._session_state_data.login_stored_data = {
        "customer_info": {"home_region": "eu"},
        REFRESH_ACCESS_TOKEN: TEST_BEARER,
    }
    monkeypatch.setattr(
        api._http_wrapper, "refresh_data", AsyncMock(return_value=(True, {}))
    )
    transport = httpx.MockTransport(avs_server.handle)
    async with httpx.AsyncClient(transport=transport) as httpx_client:
        yield AmazonHTTP2Client(
            api._http_wrapper, api._session_state_data, httpx_client
        )


@pytest.fixture
def push_events(client: AmazonHTTP2Client) -> list[tuple[str, dict[str, Any]]]:
    """Subscribe to push events and return the list they are recorded in."""
    received: list[tuple[str, dict[str, Any]]] = []

    async def on_push_event(event_type: str, payload: dict[str, Any]) -> None:
        received.append((event_type, payload))

    client.on_push_event.append(on_push_event)
    client.on_push_event.freeze()
    return received


@pytest.fixture
def avs_directives(
    client: AmazonHTTP2Client, monkeypatch: pytest.MonkeyPatch
) -> AsyncMock:
    """Replace the stream and ping tasks, returning the stream mock."""
    get_avs_directives = AsyncMock()
    monkeypatch.setattr(client, "_get_avs_directives", get_avs_directives)
    monkeypatch.setattr(client, "_ping_loop", AsyncMock())
    return get_avs_directives


@pytest.fixture
def debug_logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """Capture debug logs as well as warnings."""
    caplog.set_level(logging.DEBUG)
    return caplog


@pytest.mark.parametrize(
    ("chunk_json", "expected", "message"),
    [
        pytest.param(_directive(_update()), [_update()], "", id="rendering-updates"),
        pytest.param({"directive": {}}, None, "Malformed directive", id="missing"),
        pytest.param({"directive": None}, None, "Malformed directive", id="null"),
        pytest.param(
            {"directive": {"payload": {"renderingUpdates": {}}}},
            None,
            "Malformed renderingUpdates",
            id="not-a-list",
        ),
    ],
)
def test_extract_rendering_updates(
    caplog: pytest.LogCaptureFixture,
    chunk_json: dict[str, Any],
    expected: list[object] | None,
    message: str,
) -> None:
    """Rendering updates are read from the directive, and malformed ones warn."""
    assert _extract_rendering_updates(chunk_json) == expected
    assert message in caplog.text


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        pytest.param({"notificationVersion": 3}, False, id="odd"),
        pytest.param({"notificationVersion": 4}, True, id="even"),
        pytest.param({}, False, id="missing"),
        pytest.param({"notificationVersion": "4"}, False, id="not-an-int"),
    ],
)
def test_is_notification_change_duplicate(
    payload: dict[str, Any], expected: bool
) -> None:
    """Even notification versions are duplicates."""
    assert _is_notification_change_duplicate(payload) is expected


@pytest.mark.parametrize(
    ("rendering_update", "message"),
    [
        pytest.param("update", "Malformed rendering update node", id="not-a-dict"),
        pytest.param(_update(resource_id=""), "Missing resourceId", id="no-resource"),
        pytest.param(
            {"resourceId": AmazonPushMessage.VolumeChange.value},
            "Malformed resourceMetadata",
            id="no-metadata",
        ),
        pytest.param(_update(payload=[]), "Malformed push payload", id="bad-payload"),
        pytest.param(
            _update(resource_id="PUSH_SOMETHING_NEW"),
            "Unknown HTTP2 push message from device 1234: PUSH_SOMETHING_NEW",
            id="unknown-type",
        ),
        pytest.param(
            _update(
                AmazonPushMessage.NotificationChange.value,
                {"notificationVersion": 2},
            ),
            "",
            id="duplicate-notification",
        ),
    ],
)
def test_process_rendering_update_rejects(
    caplog: pytest.LogCaptureFixture, rendering_update: object, message: str
) -> None:
    """Malformed, unknown and duplicate updates are dropped."""
    assert _process_rendering_update(rendering_update) is None
    assert message in caplog.text


@pytest.mark.parametrize(
    ("rendering_update", "expected"),
    [
        pytest.param(
            _update(),
            (
                AmazonPushMessage.VolumeChange.value,
                {"dopplerId": {"deviceSerialNumber": TEST_SERIAL_1}},
            ),
            id="known-type",
        ),
        pytest.param(
            _update(
                AmazonPushMessage.NotificationChange.value,
                {"notificationVersion": 1, "dopplerId": None},
            ),
            (
                AmazonPushMessage.NotificationChange.value,
                {"notificationVersion": 1, "dopplerId": None},
            ),
            id="new-notification",
        ),
        pytest.param(
            _update(resource_id="", payload={}, route="EventBus:AlexaMobile::FDAL"),
            (AmazonPushMessage.SmartHome.value, {}),
            id="smart-home-route",
        ),
    ],
)
def test_process_rendering_update_accepts(
    rendering_update: dict[str, Any], expected: tuple[str, dict[str, Any]]
) -> None:
    """Known updates return their event type and payload."""
    assert _process_rendering_update(rendering_update) == expected


def test_stream_parser_splits_parts_across_chunks() -> None:
    """Parts are returned once complete, even when a delimiter is split."""
    parser = AvsDirectiveStreamParser(DELIMITER)

    assert parser.feed(DELIMITER + b"\r\nfirst\r\n" + DELIMITER[:4]) == [b""]
    assert parser.feed(DELIMITER[4:] + b"\r\nsecond\r\n" + DELIMITER) == [
        b"first",
        b"second",
    ]
    assert parser.feed(b"partial") == []


def test_stream_parser_limits_buffer_size(monkeypatch: pytest.MonkeyPatch) -> None:
    """A part that never ends cannot grow the buffer without limit."""
    monkeypatch.setattr(http2, "_MAX_BUFFER_SIZE", 8)
    parser = AvsDirectiveStreamParser(DELIMITER)

    with pytest.raises(BufferError):
        parser.feed(b"123456789")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("conn_exc", "root", "expected"),
    [
        pytest.param(
            httpx.ConnectError("refused"), None, True, id="other-transport-error"
        ),
        pytest.param(
            httpx.ReadError(""),
            anyio.ClosedResourceError(),
            False,
            id="read-error-client-closed",
        ),
        pytest.param(
            httpx.ReadError(""), OSError("reset"), True, id="read-error-other"
        ),
        pytest.param(
            httpx.RemoteProtocolError(""),
            Exception("Server disconnected"),
            False,
            id="server-disconnected",
        ),
        pytest.param(
            httpx.RemoteProtocolError(""),
            _goaway(ErrorCodes.NO_ERROR),
            False,
            id="goaway-no-error",
        ),
        pytest.param(
            httpx.RemoteProtocolError(""),
            _goaway(ErrorCodes.PROTOCOL_ERROR),
            True,
            id="goaway-protocol-error",
        ),
        pytest.param(httpx.RemoteProtocolError(""), Exception(), True, id="no-details"),
    ],
)
async def test_is_informative(
    client: AmazonHTTP2Client,
    conn_exc: httpx.TransportError,
    root: BaseException | None,
    expected: bool,
) -> None:
    """Expected connection drops are not worth a warning, other errors are."""
    assert client.is_informative(conn_exc, root or conn_exc) is expected


@pytest.mark.anyio
async def test_bearer_token_required(client: AmazonHTTP2Client) -> None:
    """Requests cannot be made without an access token."""
    del client._session_state_data.login_stored_data[REFRESH_ACCESS_TOKEN]

    with pytest.raises(CannotAuthenticate, match="No access token available"):
        client._get_bearer_token()


@pytest.mark.anyio
async def test_check_avs_site_correct_site(
    client: AmazonHTTP2Client, avs_server: AvsServer
) -> None:
    """An empty response from the events endpoint keeps the site."""
    await client._check_avs_site()

    (request,) = avs_server.requests
    assert request.method == "POST"
    assert str(request.url) == f"{AVS_SITE}/v{HTTP2_DIRECTIVES_VERSION}/events"
    assert request.headers["Authorization"] == f"Bearer {TEST_BEARER}"
    assert client._avs_directive_site == AVS_SITE


@pytest.mark.anyio
async def test_check_avs_site_updates_site(
    client: AmazonHTTP2Client, avs_server: AvsServer
) -> None:
    """A response naming another endpoint switches to that site."""
    avs_server.events = httpx.Response(
        HTTPStatus.OK,
        headers={"content-type": MULTIPART},
        content=_multipart(
            _part({"directive": {"payload": {"endpoint": NEW_AVS_SITE}}})
        ),
    )

    with pytest.raises(UpdatedAVSSite):
        await client._check_avs_site()

    assert client._avs_directive_site == NEW_AVS_SITE


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param(
            _multipart(b"Content-Type: text/plain\r\n\r\nnope"),
            "Could not extract JSON",
            id="no-json",
        ),
        pytest.param(
            _multipart(_part({"directive": {"payload": {}}})),
            "Could not extract AVS site",
            id="no-endpoint",
        ),
    ],
)
async def test_check_avs_site_unreadable_response_keeps_site(
    client: AmazonHTTP2Client,
    avs_server: AvsServer,
    caplog: pytest.LogCaptureFixture,
    content: bytes,
    message: str,
) -> None:
    """A response without a usable endpoint keeps the site."""
    avs_server.events = httpx.Response(
        HTTPStatus.OK, headers={"content-type": MULTIPART}, content=content
    )

    await client._check_avs_site()

    assert message in caplog.text
    assert client._avs_directive_site == AVS_SITE


@pytest.mark.anyio
async def test_stream_delivers_push_events(
    client: AmazonHTTP2Client,
    avs_server: AvsServer,
    push_events: list[tuple[str, dict[str, Any]]],
) -> None:
    """Push events in the stream are sent to subscribers, malformed parts skipped."""
    volume = _update()
    media = _update(AmazonPushMessage.MediaChange.value, {"dopplerId": None})
    body = _multipart(
        _part(_directive(volume, "malformed")),
        b"Content-Type: text/plain\r\n\r\nnot json",
        _part({"directive": None}),
        _part(_directive(media)),
    )
    # Split the body so that a part spans two chunks.
    avs_server.set_stream(body[:50], body[50:])

    await client._stream_and_process()

    assert push_events == [
        (AmazonPushMessage.VolumeChange.value, volume["resourceMetadata"]["payload"]),
        (AmazonPushMessage.MediaChange.value, {"dopplerId": None}),
    ]
    stream_request, check_site_request = avs_server.requests
    assert str(stream_request.url) == (
        f"{AVS_SITE}/v{HTTP2_DIRECTIVES_VERSION}/directives"
    )
    assert stream_request.headers["Authorization"] == f"Bearer {TEST_BEARER}"
    assert stream_request.headers["Accept"] == "multipart/related"
    # The empty part before the first delimiter triggers the site check.
    assert check_site_request.url.path.endswith("/events")
    assert not client._connected_event.is_set()


@pytest.mark.anyio
async def test_stream_subscriber_error_is_logged(
    client: AmazonHTTP2Client,
    avs_server: AvsServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing subscriber is logged and later events are still delivered."""
    on_push_event = AsyncMock(side_effect=[ValueError("boom"), None])
    client.on_push_event.append(on_push_event)
    client.on_push_event.freeze()
    avs_server.set_stream(_multipart(_part(_directive(_update(), _update()))))

    await client._stream_and_process()

    assert "Error processing push event type <PUSH_VOLUME_CHANGE>" in caplog.text
    payload = _update()["resourceMetadata"]["payload"]
    assert on_push_event.await_args_list == [
        call(AmazonPushMessage.VolumeChange.value, payload),
        call(AmazonPushMessage.VolumeChange.value, payload),
    ]


@pytest.mark.anyio
async def test_stream_stops_reading_once_stopped(
    client: AmazonHTTP2Client, avs_server: AvsServer
) -> None:
    """Chunks arriving after a stop are not processed."""
    on_push_event = AsyncMock(side_effect=lambda *_: client._stop_event.set())
    client.on_push_event.append(on_push_event)
    client.on_push_event.freeze()
    first = _multipart(_part(_directive(_update())))
    second = _part(_directive(_update())) + b"\r\n" + DELIMITER
    avs_server.set_stream(first, second)

    await client._stream_and_process()

    on_push_event.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status",
    [
        pytest.param(HTTPStatus.UNAUTHORIZED, id="unauthorized"),
        pytest.param(HTTPStatus.FORBIDDEN, id="forbidden"),
        pytest.param(HTTPStatus.PROXY_AUTHENTICATION_REQUIRED, id="proxy-auth"),
    ],
)
async def test_stream_auth_failure(
    client: AmazonHTTP2Client, avs_server: AvsServer, status: HTTPStatus
) -> None:
    """An authentication failure on the stream requires a reauth."""
    avs_server.directives = httpx.Response(status)

    with pytest.raises(CannotAuthenticate, match=f"returned {status.value}"):
        await client._stream_and_process()

    assert not client._connected_event.is_set()


@pytest.mark.anyio
async def test_stream_without_boundary_fails(
    client: AmazonHTTP2Client, avs_server: AvsServer
) -> None:
    """A stream that is not multipart cannot be read."""
    avs_server.directives = httpx.Response(
        HTTPStatus.OK, headers={"content-type": "application/json"}
    )

    with pytest.raises(CannotRetrieveData, match="Missing multipart boundary"):
        await client._stream_and_process()


@pytest.mark.anyio
async def test_stream_buffer_overflow_forces_reconnect(
    client: AmazonHTTP2Client,
    avs_server: AvsServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A part too large for the buffer fails the stream so it reconnects."""
    monkeypatch.setattr(http2, "_MAX_BUFFER_SIZE", 8)
    avs_server.set_stream(b"0123456789")

    with pytest.raises(CannotRetrieveData, match="Buffer exceeded maximum size"):
        await client._stream_and_process()

    assert not client._connected_event.is_set()


@pytest.mark.anyio
async def test_get_avs_directives_ended_stream_raises(
    client: AmazonHTTP2Client,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The token is refreshed first, and a stream ending by itself is reported."""
    refresh_data = AsyncMock(return_value=(False, {}))
    monkeypatch.setattr(client._http_wrapper, "refresh_data", refresh_data)
    stream_and_process = AsyncMock()
    monkeypatch.setattr(client, "_stream_and_process", stream_and_process)

    with pytest.raises(AVSStreamEndedUnexpectedly):
        await client._get_avs_directives()

    refresh_data.assert_awaited_once_with(REFRESH_ACCESS_TOKEN)
    stream_and_process.assert_awaited_once()
    assert "Failed to refresh access token" in caplog.text


@pytest.mark.anyio
async def test_get_avs_directives_after_stop(
    client: AmazonHTTP2Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stream ending because of a stop is not an error."""
    monkeypatch.setattr(client, "_stream_and_process", AsyncMock())
    client._stop_event.set()

    await client._get_avs_directives()


@pytest.mark.anyio
async def test_ping_resets_backoff(
    client: AmazonHTTP2Client, avs_server: AvsServer
) -> None:
    """A healthy ping resets the reconnect backoff."""
    client._reconnect_attempt = 3

    await client._ping()

    (request,) = avs_server.requests
    assert str(request.url) == f"{AVS_SITE}/ping"
    assert request.headers["Authorization"] == f"Bearer {TEST_BEARER}"
    assert client._reconnect_attempt == 0


@pytest.mark.anyio
async def test_ping_auth_failure(
    client: AmazonHTTP2Client, avs_server: AvsServer
) -> None:
    """An authentication failure on ping requires a reauth."""
    avs_server.ping = httpx.Response(HTTPStatus.FORBIDDEN)

    with pytest.raises(CannotAuthenticate, match="Ping returned 403"):
        await client._ping()


@pytest.mark.anyio
async def test_ping_closed_client_stops(
    client: AmazonHTTP2Client, avs_server: AvsServer
) -> None:
    """Once the httpx client is closed, pinging stops processing."""
    await client._http2_client.aclose()

    await client._ping()

    assert avs_server.requests == []
    assert client._stop_event.is_set()


@pytest.mark.anyio
async def test_ping_loop_waits_for_connection(
    client: AmazonHTTP2Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pings start only once the stream is open."""
    monkeypatch.setattr(http2, "_OPEN_TIMEOUT", 0.001)
    monkeypatch.setattr(http2, "_PING_INTERVAL", 0)
    ping = AsyncMock(side_effect=client._stop_event.set)
    monkeypatch.setattr(client, "_ping", ping)

    task = asyncio.create_task(client._ping_loop())
    # Let the wait for the stream to open time out at least once.
    await asyncio.sleep(0.01)
    ping.assert_not_awaited()

    client._connected_event.set()
    await task

    ping.assert_awaited_once()


@pytest.mark.anyio
async def test_ping_loop_skips_ping_after_disconnect(
    client: AmazonHTTP2Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No ping is sent if the stream drops or processing stops while waiting."""
    monkeypatch.setattr(http2, "_PING_INTERVAL", 0.01)
    ping = AsyncMock()
    monkeypatch.setattr(client, "_ping", ping)
    client._connected_event.set()

    task = asyncio.create_task(client._ping_loop())
    await asyncio.sleep(0)
    # The stream drops while the loop waits to ping.
    client._connected_event.clear()
    await asyncio.sleep(0.02)

    # It reconnects, then processing stops while the loop waits to ping.
    client._connected_event.set()
    await asyncio.sleep(0)
    client._stop_event.set()
    await task

    ping.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        pytest.param(None, (_TaskAction.RECONNECT_IMMEDIATE, ""), id="clean-exit"),
        pytest.param(
            UpdatedAVSSite(),
            (_TaskAction.RECONNECT_IMMEDIATE, "AVS site updated"),
            id="site-updated",
        ),
        pytest.param(
            CannotAuthenticate("denied"),
            (_TaskAction.REAUTH, "HTTP2 auth failure"),
            id="auth-failure",
        ),
        pytest.param(
            AVSStreamEndedUnexpectedly("ended"),
            (_TaskAction.RECONNECT, "stream ended cleanly, reconnecting"),
            id="stream-ended",
        ),
        pytest.param(
            CannotConnect("refresh failed"),
            (_TaskAction.RECONNECT, "Token refresh failure, retrying in 5 seconds"),
            id="token-refresh-failure",
        ),
        pytest.param(
            httpx.ConnectError("refused"),
            (_TaskAction.RECONNECT, "(ConnectError: refused), reconnecting in 5"),
            id="connection-error",
        ),
        pytest.param(
            _caused(httpx.ReadError(""), anyio.ClosedResourceError()),
            (_TaskAction.RECONNECT, "HTTP2 Connection lost (unknown)"),
            id="connection-lost",
        ),
        pytest.param(
            httpx.DecodingError("bad gzip"),
            (_TaskAction.RECONNECT, "HTTP2 error detected"),
            id="http-error",
        ),
        pytest.param(
            ValueError("boom"),
            (_TaskAction.RECONNECT, "HTTP2 failure, reconnecting in 5"),
            id="unexpected-error",
        ),
    ],
)
async def test_run_tasks_action(
    client: AmazonHTTP2Client,
    avs_directives: AsyncMock,
    debug_logs: pytest.LogCaptureFixture,
    exception: BaseException | None,
    expected: tuple[_TaskAction, str],
) -> None:
    """How the tasks end decides whether to reconnect, reauth or stop."""
    action, message = expected
    avs_directives.side_effect = exception

    assert await client._run_tasks(5) == action
    assert message in debug_logs.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "exception",
    [
        pytest.param(AVSStreamEndedUnexpectedly("ended"), id="stream-ended"),
        pytest.param(httpx.ReadError("closed"), id="connection-error"),
    ],
)
async def test_run_tasks_stops_during_shutdown(
    client: AmazonHTTP2Client,
    avs_directives: AsyncMock,
    exception: BaseException,
) -> None:
    """Errors caused by shutting down stop processing instead of reconnecting."""
    avs_directives.side_effect = exception
    client._stop_event.set()

    assert await client._run_tasks(5) == _TaskAction.STOP


@pytest.mark.anyio
async def test_orchestrate_backs_off_between_reconnects(
    client: AmazonHTTP2Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each reconnect doubles the delay, an immediate reconnect does not."""
    monkeypatch.setattr(http2, "HTTP2_RECONNECT_DELAY", 0.001)
    run_tasks = AsyncMock(
        side_effect=[
            _TaskAction.RECONNECT,
            _TaskAction.RECONNECT_IMMEDIATE,
            _TaskAction.RECONNECT,
            _TaskAction.STOP,
        ]
    )
    monkeypatch.setattr(client, "_run_tasks", run_tasks)

    await client._orchestrate_tasks()

    assert [args.args[0] for args in run_tasks.await_args_list] == [
        0.001,
        0.002,
        0.002,
        0.004,
    ]


@pytest.mark.anyio
async def test_orchestrate_stops_during_backoff(
    client: AmazonHTTP2Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stop while waiting to reconnect ends processing without waiting."""
    run_tasks = AsyncMock(return_value=_TaskAction.RECONNECT)
    monkeypatch.setattr(client, "_run_tasks", run_tasks)

    task = asyncio.create_task(client._orchestrate_tasks())
    await asyncio.sleep(0)
    client._stop_event.set()
    await task

    run_tasks.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "with_callback",
    [
        pytest.param(True, id="with-callback"),
        pytest.param(False, id="without-callback"),
    ],
)
async def test_orchestrate_reauth(
    client: AmazonHTTP2Client, monkeypatch: pytest.MonkeyPatch, with_callback: bool
) -> None:
    """A reauth calls the callback, if there is one, and ends processing."""
    on_reauth_required = AsyncMock()
    if with_callback:
        client._on_reauth_required = on_reauth_required
    run_tasks = AsyncMock(return_value=_TaskAction.REAUTH)
    monkeypatch.setattr(client, "_run_tasks", run_tasks)

    await client._orchestrate_tasks()

    run_tasks.assert_awaited_once()
    assert on_reauth_required.await_args_list == ([()] if with_callback else [])


@pytest.mark.anyio
async def test_start_and_stop_processing(
    client: AmazonHTTP2Client, avs_server: AvsServer
) -> None:
    """Processing streams push events until stopped."""
    received = asyncio.Event()
    on_push_event = AsyncMock(side_effect=lambda *_: received.set())
    client.on_push_event.append(on_push_event)
    client.on_push_event.freeze()
    avs_server.set_stream(_multipart(_part(_directive(_update()))), stay_open=True)

    task = await client.start_processing()
    assert await client.start_processing() is task
    await received.wait()
    assert client._connected_event.is_set()

    await client.stop_processing()

    assert task.cancelled()
    assert client._run_task is None
    assert client._stop_event.is_set()
    on_push_event.assert_awaited_once_with(
        AmazonPushMessage.VolumeChange.value, _update()["resourceMetadata"]["payload"]
    )


@pytest.mark.anyio
async def test_start_after_finished_starts_new_task(
    client: AmazonHTTP2Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Starting again after processing has ended runs a new task."""
    orchestrate_tasks = AsyncMock()
    monkeypatch.setattr(client, "_orchestrate_tasks", orchestrate_tasks)

    first = await client.start_processing()
    await first
    second = await client.start_processing()
    await second

    assert second is not first
    assert orchestrate_tasks.await_args_list == [(), ()]


@pytest.mark.anyio
async def test_stop_logs_error_from_task(
    client: AmazonHTTP2Client,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An error raised while the task is cancelled is logged, not raised."""
    started = asyncio.Event()

    async def orchestrate_tasks() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise ValueError("boom") from None

    monkeypatch.setattr(client, "_orchestrate_tasks", orchestrate_tasks)
    await client.start_processing()
    await started.wait()

    await client.stop_processing()

    assert "Error while stopping http2 processing" in caplog.text
    assert client._run_task is None


@pytest.mark.anyio
async def test_cancelled_stop_is_propagated(
    client: AmazonHTTP2Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancelling the stop itself is not swallowed while waiting for the task."""
    holding = asyncio.Event()

    async def orchestrate_tasks() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Swallow the stop's cancel, so the stop is left waiting.
            holding.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(client, "_orchestrate_tasks", orchestrate_tasks)
    task = await client.start_processing()
    await asyncio.sleep(0)
    stop = asyncio.create_task(client.stop_processing())
    await holding.wait()

    stop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stop
    task.cancel()
