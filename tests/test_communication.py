# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Alexa communications handler."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.implementation.communication import AlexaCommunicationsHandler

from .const import TEST_SERIAL_1, TEST_SERIAL_2

TEST_USER_ID = "USER_ID"
TEST_HOMEGROUP_ID = "HOMEGROUP_ID"


def _homegroup_device(
    serial: str,
    *,
    comms: str = "ON",
    dropin: str = "ON",
    announcements: str = "ON",
) -> dict[str, Any]:
    return {
        "deviceSerialNumber": serial,
        "deviceType": "A1B2C3",
        "deviceName": f"Echo {serial}",
        "deviceStatus": {
            "deviceCommsAvailability": comms,
            "deviceDropInAvailability": dropin,
            "announcementAvailability": announcements,
        },
    }


def _announcements_pref(state: str, *, allowed: bool = True) -> dict[str, Any]:
    return {
        "devicePermissionsPreferences": [
            {"devicePreference": "announcements", "state": state, "allowed": allowed}
        ]
    }


def _route_responses(
    handler: AlexaCommunicationsHandler,
    responses: dict[str, dict[str, Any] | Exception],
) -> list[URL]:
    """Mock HTTP calls, picking a response by the first matching URL fragment."""
    requested: list[URL] = []

    async def _session_request(
        method: str,  # noqa: ARG001
        url: URL,
        **kwargs: object,  # noqa: ARG001
    ) -> tuple[None, URL]:
        requested.append(url)
        for fragment, response in responses.items():
            if fragment in str(url) and isinstance(response, Exception):
                raise response
        return None, url

    async def _response_to_json(url: URL, description: str) -> dict[str, Any]:  # noqa: ARG001
        for fragment, response in responses.items():
            if fragment in str(url):
                assert isinstance(response, dict)
                return response
        msg = f"Unexpected request to {url}"
        raise AssertionError(msg)

    handler._http_wrapper.session_request = AsyncMock(side_effect=_session_request)  # type: ignore[method-assign]
    handler._http_wrapper.response_to_json = AsyncMock(side_effect=_response_to_json)  # type: ignore[method-assign]
    return requested


@pytest.fixture
def handler(api: AmazonEchoApi) -> AlexaCommunicationsHandler:
    """Return the communications handler with a logged-in user id."""
    api._session_state_data.login_stored_data = {
        "customer_info": {"user_id": TEST_USER_ID}
    }
    return api._communication_handler


@pytest.mark.anyio
async def test_get_homegroup_id_cached(handler: AlexaCommunicationsHandler) -> None:
    """The homegroup id is fetched once from the identity endpoint and cached."""
    requested = _route_responses(
        handler, {"/identities": {"homeGroupId": TEST_HOMEGROUP_ID}}
    )

    assert await handler.get_homegroup_id() == TEST_HOMEGROUP_ID
    assert await handler.get_homegroup_id() == TEST_HOMEGROUP_ID

    assert len(requested) == 1
    assert TEST_USER_ID in str(requested[0])


@pytest.mark.anyio
async def test_get_communication_preferences(
    handler: AlexaCommunicationsHandler,
) -> None:
    """Homegroup status and per-device announcements are merged per serial."""
    requested = _route_responses(
        handler,
        {
            "/identities": {"homeGroupId": TEST_HOMEGROUP_ID},
            f"/homegroups/{TEST_HOMEGROUP_ID}/devices": {
                "devices": [
                    _homegroup_device(TEST_SERIAL_1, comms="ON", dropin="OFF"),
                    _homegroup_device(TEST_SERIAL_2, comms="OFF", dropin="ALL"),
                ]
            },
            f"/deviceId/{TEST_SERIAL_1}/": _announcements_pref("OFF"),
            f"/deviceId/{TEST_SERIAL_2}/": _announcements_pref("OFF", allowed=False),
        },
    )

    preferences = await handler.get_communication_preferences()

    assert preferences == {
        # announcements overridden by the allowed device preference
        TEST_SERIAL_1: {
            "announcements": "OFF",
            "communications": "ON",
            "dropin": "OFF",
        },
        # not allowed, so homegroup announcement availability is kept
        TEST_SERIAL_2: {
            "announcements": "ON",
            "communications": "OFF",
            "dropin": "ALL",
        },
    }
    assert [
        call.kwargs.get("fail_fast")
        for call in handler._http_wrapper.session_request.call_args_list  # type: ignore[attr-defined]
        if "/preferences" in str(call.kwargs["url"])
    ] == [True, True]
    assert all(
        url.query.getall("devicePreferences") == ["announcements"]
        for url in requested
        if "/preferences" in str(url)
    )


@pytest.mark.anyio
async def test_get_communication_preferences_reuses_homegroup_id(
    handler: AlexaCommunicationsHandler,
) -> None:
    """The identity endpoint is not called again on later refreshes."""
    requested = _route_responses(
        handler,
        {
            "/identities": {"homeGroupId": TEST_HOMEGROUP_ID},
            "/homegroups/": {"devices": []},
        },
    )

    await handler.get_communication_preferences()
    await handler.get_communication_preferences()

    assert [url.path.rsplit("/", 1)[-1] for url in requested] == [
        "identities",
        "devices",
        "devices",
    ]


@pytest.mark.anyio
async def test_get_communication_preferences_keeps_cached_announcements(
    handler: AlexaCommunicationsHandler,
) -> None:
    """A failed preferences call keeps the previous announcements state."""
    homegroup = {
        "devices": [
            _homegroup_device(TEST_SERIAL_1, comms="ON", announcements="ON"),
        ]
    }
    _route_responses(
        handler,
        {
            "/identities": {"homeGroupId": TEST_HOMEGROUP_ID},
            "/homegroups/": homegroup,
            "/preferences": _announcements_pref("OFF"),
        },
    )
    await handler.get_communication_preferences()

    homegroup["devices"] = [
        _homegroup_device(TEST_SERIAL_1, comms="OFF", announcements="ON"),
    ]
    _route_responses(
        handler,
        {
            "/homegroups/": homegroup,
            "/preferences": CannotRetrieveData("boom"),
        },
    )
    preferences = await handler.get_communication_preferences()

    assert preferences == {
        TEST_SERIAL_1: {"announcements": "OFF", "communications": "OFF", "dropin": "ON"}
    }
