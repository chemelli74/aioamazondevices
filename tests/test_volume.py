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

TEST_GROUP_SERIAL = "GROUP_SERIAL"
TEST_VOLUME = 50


@pytest.fixture
def make_volume_device(
    make_device: Callable[..., AmazonDevice],
) -> Callable[..., AmazonDevice]:
    """Return a factory for devices whose only cluster member is themselves."""

    def _make_volume_device(serial: str) -> AmazonDevice:
        device = make_device(serial)
        device.device_cluster_members = {serial: device.device_type}
        return device

    return _make_volume_device


def _speaker_volume_call(
    api: AmazonEchoApi,
    amount: int,
    *,
    serial: str = TEST_SERIAL_1,
    muted: bool = False,
) -> object:
    """Build the expected speakerVolume request for a device."""
    return call(
        method=HTTPMethod.PUT,
        url=api._session_state_data.alexa_website_url
        / f"api/devices/A1B2C3/{serial}/audio/v2/speakerVolume",
        input_data={
            "dsn": serial,
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
    make_volume_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    cached_volume: AmazonVolumeState,
    expected_amount: int,
) -> None:
    """Volume is set through the speakerVolume endpoint as a relative step."""
    api._media_handler._device_volumes = {TEST_SERIAL_1: cached_volume}
    session_request = mock_json_response({})

    await api.set_device_volume(make_volume_device(TEST_SERIAL_1), TEST_VOLUME)

    assert session_request.await_args_list == [
        _speaker_volume_call(api, expected_amount, muted=bool(cached_volume.is_muted))
    ]


@pytest.mark.anyio
async def test_set_speaker_group_volume(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """Each group member is stepped from its own volume to the target."""
    api._media_handler._device_volumes = {
        TEST_SERIAL_1: AmazonVolumeState(30, False),
        TEST_SERIAL_2: AmazonVolumeState(70, True),
        TEST_GROUP_SERIAL: AmazonVolumeState(50, False),
    }
    group = make_device(TEST_GROUP_SERIAL)
    group.device_cluster_members = {TEST_SERIAL_1: "A1B2C3", TEST_SERIAL_2: "A1B2C3"}
    session_request = mock_json_response({})

    await api.set_device_volume(group, TEST_VOLUME)

    assert session_request.await_args_list == [
        _speaker_volume_call(api, 20),
        _speaker_volume_call(api, -20, serial=TEST_SERIAL_2, muted=True),
    ]


@pytest.mark.anyio
async def test_set_device_volume_updates_cache(
    api: AmazonEchoApi,
    make_volume_device: Callable[..., AmazonDevice],
    make_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """A set updates the cache so the next step starts from the new volume."""
    api._media_handler._device_volumes = {
        TEST_SERIAL_1: AmazonVolumeState(30, True),
        TEST_SERIAL_2: AmazonVolumeState(70, False),
    }
    member = make_volume_device(TEST_SERIAL_1)
    member.parent_clusters = [TEST_GROUP_SERIAL]
    group = make_device(TEST_GROUP_SERIAL)
    group.device_cluster_members = {TEST_SERIAL_1: "A1B2C3", TEST_SERIAL_2: "A1B2C3"}
    api._device_handler._final_devices = {
        TEST_SERIAL_1: member,
        TEST_GROUP_SERIAL: group,
    }
    session_request = mock_json_response({})

    await api.set_device_volume(member, 40)
    await api.set_device_volume(member, TEST_VOLUME)

    assert session_request.await_args_list[-1] == _speaker_volume_call(
        api, 10, muted=True
    )
    assert api._media_handler._device_volumes == {
        TEST_SERIAL_1: AmazonVolumeState(TEST_VOLUME, True),
        TEST_SERIAL_2: AmazonVolumeState(70, False),
        TEST_GROUP_SERIAL: AmazonVolumeState(60, False),
    }


@pytest.mark.anyio
async def test_set_device_volume_syncs_empty_cache(
    api: AmazonEchoApi,
    make_volume_device: Callable[..., AmazonDevice],
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

    await api.set_device_volume(make_volume_device(TEST_SERIAL_1), TEST_VOLUME)

    assert session_request.await_args_list == [
        call(
            method=HTTPMethod.GET,
            url=api._session_state_data.alexa_website_url
            / "api/devices/deviceType/dsn/audio/v1/allDeviceVolumes",
        ),
        _speaker_volume_call(api, 20),
    ]


@pytest.mark.parametrize(
    ("cluster_members", "cached_serials"),
    [
        pytest.param({TEST_SERIAL_2: "A1B2C3"}, [TEST_SERIAL_1], id="no_volume"),
        pytest.param(
            {TEST_SERIAL_1: "A1B2C3", TEST_SERIAL_2: "A1B2C3"},
            [TEST_SERIAL_1],
            id="group_no_volume",
        ),
        pytest.param(
            {TEST_SERIAL_2: None}, [TEST_SERIAL_1, TEST_SERIAL_2], id="no_device_type"
        ),
    ],
)
@pytest.mark.anyio
async def test_set_device_volume_unknown_device(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    cluster_members: dict[str, str | None],
    cached_serials: list[str],
) -> None:
    """No member is changed when any of them cannot be set."""
    api._media_handler._device_volumes = dict.fromkeys(
        cached_serials, AmazonVolumeState(30, False)
    )
    device = make_device(TEST_GROUP_SERIAL)
    device.device_cluster_members = cluster_members
    session_request = mock_json_response({})

    with pytest.raises(ValueError, match=TEST_SERIAL_2):
        await api.set_device_volume(device, TEST_VOLUME)

    session_request.assert_not_awaited()


@pytest.mark.parametrize("volume", [-1, 101])
@pytest.mark.anyio
async def test_set_device_volume_out_of_range(
    api: AmazonEchoApi,
    make_volume_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    volume: int,
) -> None:
    """Volumes outside 0-100 are rejected before any request."""
    session_request = mock_json_response({})

    with pytest.raises(ValueError, match="Volume must be between"):
        await api.set_device_volume(make_volume_device(TEST_SERIAL_1), volume)

    session_request.assert_not_awaited()
