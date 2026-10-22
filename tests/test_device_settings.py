# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for applying notifications and communication settings to devices."""

from collections.abc import Callable
from typing import cast
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.schedules import (
    NOTIFICATION_ALARM,
    NOTIFICATION_REMINDER,
    NOTIFICATION_TIMER,
)
from aioamazondevices.structures import AmazonDevice, AmazonSchedule

from .const import TEST_SERIAL_1

pytestmark = pytest.mark.anyio

COMMUNICATIONS = {TEST_SERIAL_1: {"communicationsEnabled": "true"}}
REMINDER = cast("AmazonSchedule", object())
TIMER = cast("AmazonSchedule", object())
ALARM = cast("AmazonSchedule", object())


async def test_only_supported_notifications_are_applied(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """Notifications are replaced, keeping only types the device supports."""
    device = make_device(TEST_SERIAL_1, capabilities=["REMINDERS"])
    device.notifications = {NOTIFICATION_ALARM: ALARM}
    notifications = {
        TEST_SERIAL_1: {
            NOTIFICATION_REMINDER: REMINDER,
            NOTIFICATION_TIMER: TIMER,
        }
    }

    api._notification_handler.update_device_notifications(
        {TEST_SERIAL_1: device}, notifications
    )

    assert device.notifications == {NOTIFICATION_REMINDER: REMINDER}


async def test_timers_and_alarms_are_applied(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """Timers and alarms are both applied for TIMERS_AND_ALARMS devices."""
    device = make_device(TEST_SERIAL_1, capabilities=["TIMERS_AND_ALARMS"])
    notifications = {
        TEST_SERIAL_1: {
            NOTIFICATION_ALARM: ALARM,
            NOTIFICATION_REMINDER: REMINDER,
            NOTIFICATION_TIMER: TIMER,
        }
    }

    api._notification_handler.update_device_notifications(
        {TEST_SERIAL_1: device}, notifications
    )

    assert device.notifications == {
        NOTIFICATION_ALARM: ALARM,
        NOTIFICATION_TIMER: TIMER,
    }


async def test_missing_notifications_keep_previous(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """Notifications that could not be retrieved leave the previous ones alone."""
    device = make_device(TEST_SERIAL_1, capabilities=["REMINDERS"])
    device.notifications = {NOTIFICATION_REMINDER: REMINDER}

    api._notification_handler.update_device_notifications({TEST_SERIAL_1: device}, None)

    assert device.notifications == {NOTIFICATION_REMINDER: REMINDER}


async def test_communication_settings_are_applied(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """Communication settings are set, and cleared for devices without any."""
    device = make_device(TEST_SERIAL_1)
    other = make_device("other")
    other.communication_settings = {"communicationsEnabled": "false"}

    api._update_device_settings(
        {TEST_SERIAL_1: device, "other": other}, None, COMMUNICATIONS
    )

    assert device.communication_settings == COMMUNICATIONS[TEST_SERIAL_1]
    assert other.communication_settings == {}


async def test_get_devices_data_applies_settings(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """A poll applies notifications and communication settings, then sensors."""
    device = make_device(TEST_SERIAL_1, capabilities=["REMINDERS"])
    devices = {TEST_SERIAL_1: device}
    api._device_handler._final_devices = devices
    api._refresh_basic_data = AsyncMock()  # type: ignore[method-assign]
    api._notification_handler.get_notifications = AsyncMock(  # type: ignore[method-assign]
        return_value={TEST_SERIAL_1: {NOTIFICATION_REMINDER: REMINDER}}
    )
    get_communications = AsyncMock(return_value=COMMUNICATIONS)
    api._communication_handler.get_communication_preferences = get_communications  # type: ignore[method-assign]
    update_sensor_data = AsyncMock()
    api._sensor_handler.update_sensor_data = update_sensor_data  # type: ignore[method-assign]

    assert await api.get_devices_data() is devices

    get_communications.assert_awaited_once_with([device])
    update_sensor_data.assert_awaited_once_with(devices)
    assert device.notifications == {NOTIFICATION_REMINDER: REMINDER}
    assert device.communication_settings == COMMUNICATIONS[TEST_SERIAL_1]
