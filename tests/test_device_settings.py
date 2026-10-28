# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for applying communication settings to devices."""

from collections.abc import Callable
from unittest.mock import AsyncMock, Mock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1, TEST_SERIAL_2

COMMUNICATIONS = {TEST_SERIAL_1: {"communicationsEnabled": "true"}}


@pytest.mark.anyio
async def test_communication_settings_are_applied(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """Communication settings are set, and cleared for devices without any."""
    device = make_device(TEST_SERIAL_1)
    other = make_device(TEST_SERIAL_2)
    other.communication_settings = {"communicationsEnabled": "false"}

    api._update_device_settings(
        {TEST_SERIAL_1: device, TEST_SERIAL_2: other}, COMMUNICATIONS
    )

    assert device.communication_settings == COMMUNICATIONS[TEST_SERIAL_1]
    assert other.communication_settings == {}


@pytest.mark.anyio
async def test_get_devices_data_applies_settings(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A poll applies communication settings, then sensors."""
    device = make_device(TEST_SERIAL_1)
    devices = {TEST_SERIAL_1: device}
    api._device_handler._final_devices = devices
    get_communications = AsyncMock(return_value=COMMUNICATIONS)
    update_polled_sensors = AsyncMock()
    update_online_statuses = Mock()
    monkeypatch.setattr(api, "_refresh_basic_data", AsyncMock())
    monkeypatch.setattr(
        api._communication_handler,
        "get_communication_preferences",
        get_communications,
    )
    monkeypatch.setattr(
        api._sensor_handler, "update_polled_sensors", update_polled_sensors
    )
    monkeypatch.setattr(
        api._sensor_handler, "update_device_online_statuses", update_online_statuses
    )

    assert await api.get_devices_data() is devices

    get_communications.assert_awaited_once_with()
    update_polled_sensors.assert_awaited_once_with()
    update_online_statuses.assert_called_once_with(devices)
    assert device.communication_settings == COMMUNICATIONS[TEST_SERIAL_1]
