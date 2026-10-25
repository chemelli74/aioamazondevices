# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for setting device volume in AmazonEchoApi."""

from collections.abc import Callable
from http import HTTPMethod
from typing import Any
from unittest.mock import AsyncMock, call

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonDevice, AmazonVolumeState

from .const import TEST_SERIAL_1, TEST_SERIAL_2

TEST_VOLUME = 50


def _speaker_volume_call(
    api: AmazonEchoApi, amount: int, *, muted: bool = False
) -> object:
    """Build the expected speakerVolume request for TEST_SERIAL_1."""
    return call(
        method=HTTPMethod.PUT,
        url=api._session_state_data.alexa_website_url
        / f"api/devices/A1B2C3/{TEST_SERIAL_1}/audio/v2/speakerVolume",
        input_data={
            "dsn": TEST_SERIAL_1,
            "deviceType": "A1B2C3",
            "amount": amount,
            "volume": TEST_VOLUME,
            "muted": muted,
            "synchronous": True,
        },
        json_data=True,
    )


@pytest.mark.parametrize(
    ("cached_volume", "expected_amount"),
    [
        pytest.param(AmazonVolumeState(30, False), 20, id="increase"),
        pytest.param(AmazonVolumeState(70, False), -20, id="decrease"),
        pytest.param(AmazonVolumeState(None, False), TEST_VOLUME, id="unknown_volume"),
        pytest.param(AmazonVolumeState(30, True), 20, id="muted"),
    ],
)
@pytest.mark.anyio
async def test_set_device_volume(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    cached_volume: AmazonVolumeState,
    expected_amount: int,
) -> None:
    """Volume is set through the speakerVolume endpoint as a relative step."""
    api._media_handler._device_volumes = {TEST_SERIAL_1: cached_volume}
    session_request = mock_json_response({})

    await api.set_device_volume(make_device(TEST_SERIAL_1), TEST_VOLUME)

    assert session_request.await_args_list == [
        _speaker_volume_call(api, expected_amount, muted=bool(cached_volume.is_muted))
    ]


@pytest.mark.anyio
async def test_set_device_volume_syncs_empty_cache(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """The current volumes are fetched first when none are cached."""
    session_request = mock_json_response(
        {
            "volumes": [
                {"dsn": TEST_SERIAL_1, "speakerVolume": 30, "speakerMuted": False}
            ]
        }
    )

    await api.set_device_volume(make_device(TEST_SERIAL_1), TEST_VOLUME)

    assert session_request.await_args_list == [
        call(
            method=HTTPMethod.GET,
            url=api._session_state_data.alexa_website_url
            / "api/devices/deviceType/dsn/audio/v1/allDeviceVolumes",
        ),
        _speaker_volume_call(api, 20),
    ]


@pytest.mark.anyio
async def test_set_device_volume_unknown_device(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """A device missing from the volume list is rejected."""
    api._media_handler._device_volumes = {TEST_SERIAL_1: AmazonVolumeState(30, False)}
    session_request = mock_json_response({})

    with pytest.raises(ValueError, match=TEST_SERIAL_2):
        await api.set_device_volume(make_device(TEST_SERIAL_2), TEST_VOLUME)

    session_request.assert_not_awaited()


@pytest.mark.parametrize("volume", [-1, 101])
@pytest.mark.anyio
async def test_set_device_volume_out_of_range(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    volume: int,
) -> None:
    """Volumes outside 0-100 are rejected before any request."""
    session_request = mock_json_response({})

    with pytest.raises(ValueError, match="Volume must be between"):
        await api.set_device_volume(make_device(TEST_SERIAL_1), volume)

    session_request.assert_not_awaited()
