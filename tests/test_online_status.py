# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for deriving device online status."""

from collections.abc import Callable

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.devices import SPEAKER_GROUP_FAMILY
from aioamazondevices.structures import AmazonDevice, AmazonDeviceSensor

from .const import TEST_SERIAL_1, TEST_SERIAL_2

pytestmark = pytest.mark.anyio


def _reachability(value: str) -> AmazonDeviceSensor:
    return AmazonDeviceSensor(
        "reachability",
        value,
        False,
        None,
        None,
        None,
        feature_name="connectivity",
        property_name="reachability",
        instance="",
    )


@pytest.mark.parametrize(("value", "online"), [("OK", True), ("UNREACHABLE", False)])
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


async def test_online_status_kept_without_reachability(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """A device without a reachability sensor keeps its online status."""
    device = make_device(TEST_SERIAL_1, online=False)

    api._sensor_handler.update_device_online_statuses({TEST_SERIAL_1: device})

    assert device.online is False


@pytest.mark.parametrize(("value", "online"), [("OK", True), ("UNREACHABLE", False)])
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
