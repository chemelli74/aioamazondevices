# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Communications reads and writes must identify as the Alexa app."""

from collections.abc import Callable
from http import HTTPMethod

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import REQUEST_AGENT
from aioamazondevices.structures import AmazonDevice, AmazonDropInStatus


@pytest.mark.anyio
async def test_communications_use_app_agent_and_other_requests_keep_browser(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """An app-agent-only endpoint accepts the combined GET and all three PATCHes."""
    received: list[tuple[str, object]] = []

    async def handler(request: web.Request) -> web.Response:
        if request.headers.get("User-Agent") != REQUEST_AGENT["Amazon"]:
            return web.Response(status=503, text="Service Temporarily Unavailable")
        if request.method == HTTPMethod.GET:
            assert request.query.getall("devicePreferences") == [
                "communications",
                "dropin",
                "announcements",
            ]
            received.append(("GET", None))
            return web.json_response(
                {
                    "devicePermissionsPreferences": [
                        {
                            "devicePreference": "communications",
                            "allowed": True,
                            "state": "ON",
                        }
                    ]
                }
            )
        assert request.content_type == "application/json"
        received.append((request.match_info["preference"], await request.json()))
        return web.json_response({})

    async def unrelated(request: web.Request) -> web.Response:
        assert request.headers["User-Agent"] == REQUEST_AGENT["Browser"]
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/devicesTypes/{type}/deviceId/{serial}/preferences", handler)
    app.router.add_patch(
        "/devicesTypes/{type}/deviceId/{serial}/preferences/{preference}", handler
    )
    app.router.add_get("/other", unrelated)
    async with TestServer(app) as server:
        prefs = api._communication_handler
        prefs._communication_site = server.make_url("/")
        device = make_device("device")
        assert await prefs.get_communication_preferences([device]) == {
            "device": {"communications": "ON"}
        }
        await prefs.set_communication_status(device, False)
        await prefs.set_announcement_status(device, True)
        await prefs.set_dropin_status(device, AmazonDropInStatus("Home"))
        await api._http_wrapper.session_request(
            HTTPMethod.GET, server.make_url("/other")
        )
    assert received == [
        ("GET", None),
        ("communications", {"state": "OFF"}),
        ("announcements", {"state": "ON"}),
        ("dropin", {"state": "Home"}),
    ]
