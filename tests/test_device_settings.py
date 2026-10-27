# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for applying notifications and communication settings to devices."""

from collections.abc import Callable
from unittest.mock import AsyncMock, Mock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.schedules import (
    NOTIFICATION_ALARM,
    NOTIFICATION_REMINDER,
    NOTIFICATION_TIMER,
)
from aioamazondevices.structures import AmazonDevice, AmazonSchedule

from .const import TEST_SERIAL_1, TEST_SERIAL_2


def _schedule(schedule_type: str) -> AmazonSchedule:
    """Build a schedule of the given type."""
    return AmazonSchedule(
        type=schedule_type, status="ON", label="", next_occurrence=None
    )


COMMUNICATIONS = {TEST_SERIAL_1: {"communicationsEnabled": "true"}}
REMINDER = _schedule(NOTIFICATION_REMINDER)
TIMER = _schedule(NOTIFICATION_TIMER)
ALARM = _schedule(NOTIFICATION_ALARM)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("capabilities", "notifications", "expected"),
    [
        pytest.param(
            ["REMINDERS"],
            {
                TEST_SERIAL_1: {
                    NOTIFICATION_REMINDER: REMINDER,
                    NOTIFICATION_TIMER: TIMER,
                }
            },
            {NOTIFICATION_REMINDER: REMINDER},
            id="only-supported-applied",
        ),
        pytest.param(
            ["TIMERS_AND_ALARMS"],
            {
                TEST_SERIAL_1: {
                    NOTIFICATION_ALARM: ALARM,
                    NOTIFICATION_REMINDER: REMINDER,
                    NOTIFICATION_TIMER: TIMER,
                }
            },
            {NOTIFICATION_ALARM: ALARM, NOTIFICATION_TIMER: TIMER},
            id="timers-and-alarms",
        ),
        pytest.param(
            ["REMINDERS"],
            None,
            {NOTIFICATION_ALARM: ALARM},
            id="missing-keeps-previous",
        ),
    ],
)
async def test_update_device_notifications(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    capabilities: list[str],
    notifications: dict[str, dict[str, AmazonSchedule]] | None,
    expected: dict[str, AmazonSchedule],
) -> None:
    """Notifications are replaced with supported types, or kept if unavailable."""
    device = make_device(TEST_SERIAL_1, capabilities=capabilities)
    device.notifications = {NOTIFICATION_ALARM: ALARM}

    api._notification_handler.update_device_notifications(
        {TEST_SERIAL_1: device}, notifications
    )

    assert device.notifications == expected


@pytest.mark.anyio
async def test_communication_settings_are_applied(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """Communication settings are set, and cleared for devices without any."""
    device = make_device(TEST_SERIAL_1)
    other = make_device(TEST_SERIAL_2)
    other.communication_settings = {"communicationsEnabled": "false"}

    api._update_device_settings(
        {TEST_SERIAL_1: device, TEST_SERIAL_2: other}, None, COMMUNICATIONS
    )

    assert device.communication_settings == COMMUNICATIONS[TEST_SERIAL_1]
    assert other.communication_settings == {}


@pytest.mark.anyio
async def test_get_devices_data_applies_settings(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A poll applies notifications and communication settings, then sensors."""
    device = make_device(TEST_SERIAL_1, capabilities=["REMINDERS"])
    devices = {TEST_SERIAL_1: device}
    api._device_handler._final_devices = devices
    get_communications = AsyncMock(return_value=COMMUNICATIONS)
    update_polled_sensors = AsyncMock()
    update_online_statuses = Mock()
    monkeypatch.setattr(api, "_refresh_basic_data", AsyncMock())
    monkeypatch.setattr(
        api._notification_handler,
        "get_notifications",
        AsyncMock(return_value={TEST_SERIAL_1: {NOTIFICATION_REMINDER: REMINDER}}),
    )
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
    assert device.notifications == {NOTIFICATION_REMINDER: REMINDER}
    assert device.communication_settings == COMMUNICATIONS[TEST_SERIAL_1]
