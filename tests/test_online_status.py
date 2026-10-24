# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for deriving device online status."""

from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.devices import SPEAKER_GROUP_FAMILY
from aioamazondevices.structures import AmazonDevice, AmazonDeviceSensor

from .const import TEST_SERIAL_1, TEST_SERIAL_2


def _reachability(value: str, *, error: bool = False) -> AmazonDeviceSensor:
    """Build a reachability sensor."""
    return AmazonDeviceSensor(
        "reachability",
        value,
        error,
        None,
        None,
        None,
        feature_name="connectivity",
        property_name="reachability",
        instance="",
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("value", "online"),
    [
        pytest.param("OK", True, id="reachable"),
        pytest.param("UNREACHABLE", False, id="unreachable"),
    ],
)
async def test_online_status_follows_reachability(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    value: str,
    online: bool,
) -> None:
    """A reachability sensor sets the device online status."""
    device = make_device(TEST_SERIAL_1, online=not online)
    device.sensors = {"reachability": _reachability(value)}

    api._sensor_handler.update_device_online_statuses({TEST_SERIAL_1: device})

    assert device.online is online


@pytest.mark.anyio
@pytest.mark.parametrize(
    "sensors",
    [
        pytest.param({}, id="no-reachability-sensor"),
        pytest.param(
            {"reachability": _reachability("OK", error=True)},
            id="reachability-sensor-error",
        ),
    ],
)
async def test_online_status_kept_without_valid_reachability(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    sensors: dict[str, AmazonDeviceSensor],
) -> None:
    """A missing or failed reachability sensor keeps the online status."""
    device = make_device(TEST_SERIAL_1, online=False)
    device.sensors = sensors

    api._sensor_handler.update_device_online_statuses({TEST_SERIAL_1: device})

    assert device.online is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("value", "online"),
    [
        pytest.param("OK", True, id="member-reachable"),
        pytest.param("UNREACHABLE", False, id="member-unreachable"),
    ],
)
async def test_speaker_group_follows_members(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    value: str,
    online: bool,
) -> None:
    """A speaker group is online only when all its members are."""
    member = make_device(TEST_SERIAL_1)
    member.sensors = {"reachability": _reachability(value)}
    group = make_device(TEST_SERIAL_2, device_family=SPEAKER_GROUP_FAMILY)
    group.device_cluster_members = {TEST_SERIAL_1: None}

    api._sensor_handler.update_device_online_statuses(
        {TEST_SERIAL_1: member, TEST_SERIAL_2: group}
    )

    assert group.online is online


@pytest.mark.anyio
async def test_get_devices_data_updates_online_status(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A poll derives online status from the refreshed sensors."""
    device = make_device(TEST_SERIAL_1, online=True)
    devices = {TEST_SERIAL_1: device}
    api._device_handler._final_devices = devices
    monkeypatch.setattr(api, "_refresh_basic_data", AsyncMock())
    monkeypatch.setattr(
        api._notification_handler,
        "get_notifications",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        api._communication_handler,
        "get_communication_preferences",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(api._sensor_handler, "update_sensor_data", AsyncMock())
    device.sensors = {"reachability": _reachability("UNREACHABLE")}

    assert await api.get_devices_data() is devices

    assert device.online is False
