# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for setting device volume in AmazonEchoApi."""

from collections.abc import Callable
from http import HTTPMethod
from typing import Any
from unittest.mock import AsyncMock, call

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotConnect
from aioamazondevices.structures import AmazonDevice, AmazonVolumeState

from .const import TEST_DEVICE_TYPE, TEST_SERIAL_1, TEST_SERIAL_2, TEST_SERIAL_GROUP

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


@pytest.fixture
def group_of_two(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    make_volume_device: Callable[..., AmazonDevice],
) -> AmazonDevice:
    """Register a speaker group of two typed members and return the group."""
    group = make_device(TEST_SERIAL_GROUP)
    group.device_cluster_members = {
        TEST_SERIAL_1: TEST_DEVICE_TYPE,
        TEST_SERIAL_2: TEST_DEVICE_TYPE,
    }
    members = {
        serial: make_volume_device(serial) for serial in (TEST_SERIAL_1, TEST_SERIAL_2)
    }
    for member in members.values():
        member.parent_clusters = [TEST_SERIAL_GROUP]
    api._device_handler._final_devices = {**members, TEST_SERIAL_GROUP: group}
    return group


def speaker_volume_call(
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
        / f"api/devices/{TEST_DEVICE_TYPE}/{serial}/audio/v2/speakerVolume",
        input_data={
            "dsn": serial,
            "deviceType": TEST_DEVICE_TYPE,
            "amount": amount,
            "volume": TEST_VOLUME,
            "muted": muted,
            "synchronous": True,
        },
        json_data=True,
    )


def device_volumes_call(api: AmazonEchoApi) -> object:
    """Build the expected request fetching all device volumes."""
    return call(
        method=HTTPMethod.GET,
        url=api._session_state_data.alexa_website_url
        / "api/devices/deviceType/dsn/audio/v1/allDeviceVolumes",
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("cached_volume", "expected_amount"),
    [
        pytest.param(AmazonVolumeState(30, False), 20, id="increase"),
        pytest.param(AmazonVolumeState(70, False), -20, id="decrease"),
        pytest.param(AmazonVolumeState(None, False), TEST_VOLUME, id="unknown-volume"),
        pytest.param(AmazonVolumeState(30, True), 20, id="muted"),
    ],
)
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
        speaker_volume_call(api, expected_amount, muted=bool(cached_volume.is_muted))
    ]


@pytest.mark.anyio
async def test_set_speaker_group_volume(
    api: AmazonEchoApi,
    group_of_two: AmazonDevice,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """Each group member is stepped from its own volume to the target."""
    api._media_handler._device_volumes = {
        TEST_SERIAL_1: AmazonVolumeState(30, False),
        TEST_SERIAL_2: AmazonVolumeState(70, True),
        TEST_SERIAL_GROUP: AmazonVolumeState(50, False),
    }
    session_request = mock_json_response({})

    await api.set_device_volume(group_of_two, TEST_VOLUME)

    assert session_request.await_args_list == [
        speaker_volume_call(api, 20),
        speaker_volume_call(api, -20, serial=TEST_SERIAL_2, muted=True),
    ]


@pytest.mark.anyio
@pytest.mark.usefixtures("group_of_two")
async def test_set_device_volume_updates_cache(
    api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """A set updates the cache so the next step starts from the new volume."""
    api._media_handler._device_volumes = {
        TEST_SERIAL_1: AmazonVolumeState(30, True),
        TEST_SERIAL_2: AmazonVolumeState(70, False),
    }
    member = api._device_handler.devices[TEST_SERIAL_1]
    session_request = mock_json_response({})

    await api.set_device_volume(member, 40)
    await api.set_device_volume(member, TEST_VOLUME)

    assert session_request.await_args_list[-1] == speaker_volume_call(
        api, 10, muted=True
    )
    assert api._media_handler._device_volumes == {
        TEST_SERIAL_1: AmazonVolumeState(TEST_VOLUME, True),
        TEST_SERIAL_2: AmazonVolumeState(70, False),
        TEST_SERIAL_GROUP: AmazonVolumeState(60, False),
    }


@pytest.mark.anyio
async def test_set_device_volume_failure_updates_group_cache(
    api: AmazonEchoApi,
    group_of_two: AmazonDevice,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """The group volume reflects members set before a later request failed."""
    api._media_handler._device_volumes = {
        TEST_SERIAL_1: AmazonVolumeState(30, False),
        TEST_SERIAL_2: AmazonVolumeState(70, False),
        TEST_SERIAL_GROUP: AmazonVolumeState(50, False),
    }
    session_request = mock_json_response({})
    session_request.side_effect = [session_request.return_value, CannotConnect]

    with pytest.raises(CannotConnect):
        await api.set_device_volume(group_of_two, TEST_VOLUME)

    assert api._media_handler._device_volumes == {
        TEST_SERIAL_1: AmazonVolumeState(TEST_VOLUME, False),
        TEST_SERIAL_2: AmazonVolumeState(70, False),
        TEST_SERIAL_GROUP: AmazonVolumeState(60, False),
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "cached_volumes",
    [
        pytest.param({}, id="empty-cache"),
        pytest.param(
            {TEST_SERIAL_2: AmazonVolumeState(70, False)}, id="member-not-cached"
        ),
    ],
)
async def test_set_device_volume_syncs_missing_member(
    api: AmazonEchoApi,
    make_volume_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    cached_volumes: dict[str, AmazonVolumeState],
) -> None:
    """The volumes are fetched first when a member has no cached volume."""
    api._media_handler._device_volumes = cached_volumes
    session_request = mock_json_response(
        {
            "volumes": [
                {"dsn": TEST_SERIAL_1, "speakerVolume": 30, "speakerMuted": False}
            ]
        }
    )

    await api.set_device_volume(make_volume_device(TEST_SERIAL_1), TEST_VOLUME)

    assert session_request.await_args_list == [
        device_volumes_call(api),
        speaker_volume_call(api, 20),
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "cluster_members",
    [
        pytest.param({TEST_SERIAL_2: TEST_DEVICE_TYPE}, id="no-volume"),
        pytest.param(
            {TEST_SERIAL_1: TEST_DEVICE_TYPE, TEST_SERIAL_2: TEST_DEVICE_TYPE},
            id="group-no-volume",
        ),
    ],
)
async def test_set_device_volume_member_still_missing(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    cluster_members: dict[str, str | None],
) -> None:
    """No member is changed when one is missing even after a fresh sync."""
    api._media_handler._device_volumes = {TEST_SERIAL_1: AmazonVolumeState(30, False)}
    device = make_device(TEST_SERIAL_GROUP)
    device.device_cluster_members = cluster_members
    session_request = mock_json_response(
        {
            "volumes": [
                {"dsn": TEST_SERIAL_1, "speakerVolume": 30, "speakerMuted": False}
            ]
        }
    )

    with pytest.raises(ValueError, match=TEST_SERIAL_2):
        await api.set_device_volume(device, TEST_VOLUME)

    assert session_request.await_args_list == [device_volumes_call(api)]


@pytest.mark.anyio
async def test_set_device_volume_member_without_device_type(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """A member with no device type cannot be set, so nothing is sent."""
    api._media_handler._device_volumes = dict.fromkeys(
        [TEST_SERIAL_1, TEST_SERIAL_2], AmazonVolumeState(30, False)
    )
    device = make_device(TEST_SERIAL_GROUP)
    device.device_cluster_members = {TEST_SERIAL_2: None}
    session_request = mock_json_response({})

    with pytest.raises(ValueError, match=TEST_SERIAL_2):
        await api.set_device_volume(device, TEST_VOLUME)

    session_request.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "volume",
    [
        pytest.param(-1, id="below-min"),
        pytest.param(101, id="above-max"),
    ],
)
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
