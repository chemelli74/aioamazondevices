# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for applying notifications and communication settings to devices."""

from collections.abc import Callable
from typing import Any, cast

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
    notifications: dict[str, dict[str, Any]] = {
        TEST_SERIAL_1: {
            NOTIFICATION_REMINDER: REMINDER,
            NOTIFICATION_TIMER: TIMER,
        }
    }

    api._update_device_settings({TEST_SERIAL_1: device}, notifications, COMMUNICATIONS)

    assert device.notifications == {NOTIFICATION_REMINDER: REMINDER}
    assert device.communication_settings == COMMUNICATIONS[TEST_SERIAL_1]


async def test_missing_notifications_keep_previous(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """Notifications that could not be retrieved leave the previous ones alone."""
    device = make_device(TEST_SERIAL_1, capabilities=["REMINDERS"])
    device.notifications = {NOTIFICATION_REMINDER: REMINDER}

    api._update_device_settings({TEST_SERIAL_1: device}, None, {})

    assert device.notifications == {NOTIFICATION_REMINDER: REMINDER}
    assert device.communication_settings == {}
