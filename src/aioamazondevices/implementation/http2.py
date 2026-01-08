"""Support for Amazon devices."""

import asyncio
import contextlib
from http import HTTPMethod, HTTPStatus
from typing import Any, cast

import httpx
import orjson

from aioamazondevices.capabilities import (
    DEVICE_CAPABILITIES,
    DEVICE_CAPABILITIES_REGISTERED,
)
from aioamazondevices.const.http import (
    HTTP2_DIRECTIVES_VERSION,
    HTTP2_RECONNECT_DELAY,
    HTTP2_SITE,
    REFRESH_ACCESS_TOKEN,
    URI_CAPABILITIES,
)
from aioamazondevices.exceptions import CannotAuthenticate, CannotRegisterDevice
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonPushMessage
from aioamazondevices.utils import _LOGGER


class AmazonHTTP2Client:
    """Amazon push HTTP2 messages."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize Amazon HTTP2 client class."""
        self._http_wrapper = http_wrapper
        self._login_stored_data = session_state_data.login_stored_data

        self._http2_client: httpx.AsyncClient

        self.reconnect_delay = HTTP2_RECONNECT_DELAY
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start_thread(self) -> None:
        """Start the background task."""
        if self._task and not self._task.done():
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._get_avs_directives())

    async def stop_thread(self) -> None:
        """Stop the background task gracefully."""
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _register_device_capabilities(self) -> None:
        """Register device capabilities."""
        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.PUT,
            url=f"https://api.amazonalexa.com/{URI_CAPABILITIES}",
            input_data=DEVICE_CAPABILITIES,
            json_data=True,
            extended_headers={
                "Authorization": f"Bearer {self._login_stored_data['access_token']}"
            },
        )

        if raw_resp.status != HTTPStatus.NO_CONTENT:
            raise CannotRegisterDevice(
                f"Register capabilities returned {raw_resp.status} (expected 204)"
            )

        self._login_stored_data[DEVICE_CAPABILITIES_REGISTERED] = True
        _LOGGER.debug("Device capabilities registered successfully")

    async def _get_avs_directives(self) -> None:
        """Get AVS directives."""
        if not self._login_stored_data:
            _LOGGER.warning("No login data available, cannot get directives")
            return

        refreshed_token, _ = await self._http_wrapper.refresh_data(REFRESH_ACCESS_TOKEN)
        if not refreshed_token:
            _LOGGER.warning("Failed to refresh access token, cannot get directives")
            return

        if not self._login_stored_data.get(DEVICE_CAPABILITIES_REGISTERED, False):
            _LOGGER.debug("Device capabilities not set, registering now.")
            await self._register_device_capabilities()

        await self._http2_init_client()

        try:
            _LOGGER.debug("Starting AVS Directives stream")
            async with self._http2_client.stream(
                "GET",
                f"{await self._http2_site()}/v{HTTP2_DIRECTIVES_VERSION}/directives",
                headers={
                    "Authorization": f"Bearer {self._login_stored_data['access_token']}",  # noqa: E501
                    "Accept": "text/event-stream",
                    "Accept-Encoding": "gzip",
                },
            ) as response:
                _LOGGER.debug(
                    "AVS Directives response status: %s [%s]",
                    response.status_code,
                    response.http_version,
                )
                async for chunk in response.aiter_text():
                    _LOGGER.debug("AVS Directives chunk: %s", chunk)
                    if chunk.startswith("-----"):
                        _LOGGER.debug("Pinging...")
                        await self._ping()
                        continue

                    chunk_json = await self._extract_json_from_chunk(chunk)
                    updates_node = chunk_json["directive"]["payload"][
                        "renderingUpdates"
                    ][0]
                    chunk_type = updates_node["resourceId"]
                    chunk_device = (
                        updates_node["resourceMetadata"]["payload"]
                        .get("dopplerId", {})
                        .get("deviceSerialNumber")
                    )

                    if chunk_type in AmazonPushMessage.__members__.values():
                        _LOGGER.debug(
                            "Detected push type <%s> on device <%s>",
                            chunk_type,
                            chunk_device,
                        )

            _LOGGER.debug("AVS Directives stream closed")
        except httpx.RemoteProtocolError as excp:
            _LOGGER.warning("Disconnect detected: %s", excp)

    async def _string_recursive_parse(
        self, obj: dict | str | list
    ) -> dict | list | str:
        """Recursively parse strings inside dicts/lists if they are valid JSON."""
        if isinstance(obj, dict):
            return {k: await self._string_recursive_parse(v) for k, v in obj.items()}

        if isinstance(obj, list):
            return [await self._string_recursive_parse(i) for i in obj]

        try:
            parsed = orjson.loads(obj)
            return await self._string_recursive_parse(parsed)
        except orjson.JSONDecodeError:
            return obj

    async def _extract_json_from_chunk(self, chunk: str) -> dict[str, Any]:
        """Extract JSON from chunk."""
        # split header and body
        body = chunk.split("\r\n\r\n", 1)[1]

        # remove potential boundary terminator
        if "\r\n--------" in body:
            body = body.split("\r\n--------", 1)[0]

        # parse top-level JSON
        top_level_json = orjson.loads(body)

        # recursively parse strings inside JSON
        json_chunk = await self._string_recursive_parse(top_level_json)

        return cast("dict[str,Any]", json_chunk)

    async def _http2_init_client(self) -> None:
        """Create HTTP2 client session."""
        _LOGGER.debug("Initialized HTTP2 client")
        self._http2_client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(None),
        )

    async def _http2_site(self) -> str:
        """Get HTTP2 site."""
        if not self._login_stored_data:
            _LOGGER.debug("No login data available, cannot get HTTP2 site")
            return ""

        region = self._login_stored_data["customer_info"]["home_region"]
        return HTTP2_SITE.replace("{region}", region)

    async def _ping(self) -> None:
        """Ping."""
        if not self._login_stored_data:
            _LOGGER.warning("No login data available, cannot get directives")
            return

        response = await self._http2_client.post(
            f"{await self._http2_site()}/ping",
            headers={
                "Authorization": f"Bearer {self._login_stored_data['access_token']}",
            },
        )
        _LOGGER.debug(
            "Received response: %s:%s",
            response.status_code,
            response.text,
        )
        if response.status_code in [
            HTTPStatus.FORBIDDEN,
            HTTPStatus.PROXY_AUTHENTICATION_REQUIRED,
            HTTPStatus.UNAUTHORIZED,
        ]:
            raise CannotAuthenticate(
                "Detected ping 403, please check your credentials and region"
            )
