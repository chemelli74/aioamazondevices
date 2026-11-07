# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Do Not Disturb handler and the API calls that use it."""

from collections.abc import Callable
from http import HTTPMethod
from typing import Any
from unittest.mock import AsyncMock

import pytest
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.devices import (
    DEVICE_TYPE_SPEAKER_GROUP,
    DEVICE_TYPE_STEREO_PAIR,
    DEVICE_TYPES_TO_IGNORE,
)
from aioamazondevices.const.http import URI_DND_STATUS_ALL, URI_DND_STATUS_DEVICE
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1, TEST_SERIAL_2


def _dnd_status(
    serial: str, enabled: bool, device_type: str = "A1B2C3"
) -> dict[str, Any]:
    """Build a device status entry as returned by the DND API."""
    return {"deviceSerialNumber": serial, "deviceType": device_type, "enabled": enabled}


@pytest.mark.anyio
async def test_sync_do_not_disturb_status_skips_groups(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """Speaker groups, stereo pairs and ignored device types are left out."""
    session_request = mock_json_response(
        {
            "doNotDisturbDeviceStatusList": [
                _dnd_status(TEST_SERIAL_1, True),
                _dnd_status(TEST_SERIAL_2, False),
                _dnd_status("GROUP", True, DEVICE_TYPE_SPEAKER_GROUP),
                _dnd_status("PAIR", True, DEVICE_TYPE_STEREO_PAIR),
                _dnd_status("APP", True, DEVICE_TYPES_TO_IGNORE[0]),
            ]
        }
    )
    handler = api._dnd_handler

    await handler.sync_do_not_disturb_status()

    assert handler.dnd_states == {TEST_SERIAL_1: True, TEST_SERIAL_2: False}
    session_request.assert_awaited_once_with(
        method=HTTPMethod.GET,
        url=URL.joinpath(api._session_state_data.alexa_website_url, URI_DND_STATUS_ALL),
    )


@pytest.mark.anyio
async def test_sync_do_not_disturb_status_without_list_clears_states(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """A response with no status list replaces the states with an empty one."""
    mock_json_response({})
    handler = api._dnd_handler
    handler.update_cached_dnd_state(TEST_SERIAL_1, True)

    await handler.sync_do_not_disturb_status()

    assert handler.dnd_states == {}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "enable",
    [
        pytest.param(True, id="enable"),
        pytest.param(False, id="disable"),
    ],
)
async def test_set_do_not_disturb(
    api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    make_device: Callable[..., AmazonDevice],
    enable: bool,
) -> None:
    """The device's DND flag is set through the API."""
    session_request = mock_json_response({})

    await api.set_do_not_disturb(make_device(TEST_SERIAL_1), enable)

    session_request.assert_awaited_once_with(
        method=HTTPMethod.PUT,
        url=URL.joinpath(
            api._session_state_data.alexa_website_url, URI_DND_STATUS_DEVICE
        ),
        input_data={
            "deviceSerialNumber": TEST_SERIAL_1,
            "deviceType": "A1B2C3",
            "enabled": enable,
        },
        json_data=True,
    )


@pytest.mark.anyio
async def test_sync_dnd_state_emits_to_subscribers(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """A full sync marks DND as initialised and emits the states."""
    mock_json_response(
        {"doNotDisturbDeviceStatusList": [_dnd_status(TEST_SERIAL_1, True)]}
    )
    on_dnd_event = AsyncMock()
    api.on_dnd_event.append(on_dnd_event)
    api.on_dnd_event.freeze()

    await api.sync_dnd_state()

    assert api._dnd_initialized
    on_dnd_event.assert_awaited_once_with({TEST_SERIAL_1: True})
