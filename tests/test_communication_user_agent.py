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

from .const import TEST_SERIAL_1

PREFERENCES_PATH = "/devicesTypes/{type}/deviceId/{serial}/preferences"


@pytest.mark.anyio
async def test_communications_use_app_agent_and_other_requests_keep_browser(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """Communications requests use the app agent, other requests the browser one."""
    received: list[tuple[str, str, object]] = []

    async def get_preferences(request: web.Request) -> web.Response:
        received.append(
            (
                request.headers["User-Agent"],
                "GET",
                request.query.getall("devicePreferences"),
            )
        )
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

    async def set_preference(request: web.Request) -> web.Response:
        received.append(
            (
                request.headers["User-Agent"],
                request.match_info["preference"],
                (request.content_type, await request.json()),
            )
        )
        return web.json_response({})

    async def other(request: web.Request) -> web.Response:
        received.append((request.headers["User-Agent"], "other", None))
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get(PREFERENCES_PATH, get_preferences)
    app.router.add_patch(PREFERENCES_PATH + "/{preference}", set_preference)
    app.router.add_get("/other", other)
    device = make_device(TEST_SERIAL_1)
    handler = api._communication_handler
    async with TestServer(app) as server:
        handler._communication_site = server.make_url("/")
        assert await handler.get_communication_preferences([device]) == {
            TEST_SERIAL_1: {"communications": "ON"}
        }
        await handler.set_communication_status(device, False)
        await handler.set_announcement_status(device, True)
        await handler.set_dropin_status(device, AmazonDropInStatus("Home"))
        await api._http_wrapper.session_request(
            HTTPMethod.GET, server.make_url("/other")
        )

    app_agent, browser = REQUEST_AGENT["Amazon"], REQUEST_AGENT["Browser"]
    json = "application/json"
    assert received == [
        (app_agent, "GET", ["communications", "dropin", "announcements"]),
        (app_agent, "communications", (json, {"state": "OFF"})),
        (app_agent, "announcements", (json, {"state": "ON"})),
        (app_agent, "dropin", (json, {"state": "Home"})),
        (browser, "other", None),
    ]
