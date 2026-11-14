# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for applying communication settings to devices."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, Mock, call

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
    monkeypatch.setattr(api, "_refresh_basic_data", AsyncMock(return_value=False))
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

    get_communications.assert_awaited_once_with([device])
    update_polled_sensors.assert_awaited_once_with()
    update_online_statuses.assert_called_once_with(devices)
    assert device.communication_settings == COMMUNICATIONS[TEST_SERIAL_1]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("daily_refreshed", "resync_required", "expected"),
    [
        pytest.param(False, False, ([], [call()]), id="no-full-sync"),
        pytest.param(True, False, ([], []), id="daily-refresh"),
        pytest.param(False, True, ([call()], []), id="resync-retry"),
    ],
)
async def test_get_devices_data_skips_poll_after_full_sync(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
    *,
    daily_refreshed: bool,
    resync_required: bool,
    expected: tuple[list[Any], list[Any]],
) -> None:
    """A full sensor sync in the same poll makes the polled query redundant."""
    update_polled_sensors = AsyncMock()
    resync_sensors = AsyncMock()
    api._sensor_resync_required = resync_required
    monkeypatch.setattr(
        api, "_refresh_basic_data", AsyncMock(return_value=daily_refreshed)
    )
    monkeypatch.setattr(api, "_resync_sensors", resync_sensors)
    monkeypatch.setattr(
        api._notification_handler, "get_notifications", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        api._communication_handler,
        "get_communication_preferences",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        api._sensor_handler, "update_polled_sensors", update_polled_sensors
    )

    expected_resyncs, expected_polls = expected

    await api.get_devices_data()

    assert resync_sensors.await_args_list == expected_resyncs
    assert update_polled_sensors.await_args_list == expected_polls
