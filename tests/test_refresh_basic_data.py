# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for _refresh_basic_data in AmazonEchoApi."""

from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1, TEST_SERIAL_2

COMMUNICATIONS = {TEST_SERIAL_1: {"communicationsEnabled": "true"}}


@pytest.fixture
def get_communications(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> AsyncMock:
    """Stub the daily refresh calls other than update_devices."""
    get_communications = AsyncMock(return_value={})
    monkeypatch.setattr(api._media_handler, "update_music_providers", AsyncMock())
    monkeypatch.setattr(api._sequence_handler, "update_routines", AsyncMock())
    monkeypatch.setattr(api._todo_handler, "update_lists", AsyncMock())
    monkeypatch.setattr(
        api._communication_handler,
        "get_communication_preferences",
        get_communications,
    )
    return get_communications


@pytest.mark.anyio
async def test_refresh_resolves_default_device_from_endpoint_only_account(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
    get_communications: AsyncMock,
) -> None:
    """Endpoint-only devices (e.g. Air Quality Monitor) resolve as default device.

    Regression test: the Air Quality Monitor is created by update_devices(), so
    resolving the default device before that call aborted the whole refresh with
    NoOnlineDevicesError on accounts without an Echo device.
    """
    call_order: list[str] = []

    async def update_devices() -> None:
        call_order.append("update_devices")
        api._device_handler._final_devices[TEST_SERIAL_1] = make_device(
            TEST_SERIAL_1, online=True
        )

    monkeypatch.setattr(api._device_handler, "update_devices", update_devices)

    assert await api._refresh_basic_data() is True

    assert call_order == ["update_devices"]
    default_device = await api.get_default_device()
    assert default_device.serial_number == TEST_SERIAL_1

    # not due again, so no refresh, no full sensor sync and no comms query
    assert await api._refresh_basic_data() is False
    assert call_order == ["update_devices"]
    get_communications.assert_awaited_once()


@pytest.mark.anyio
async def test_refresh_applies_communication_settings(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
    get_communications: AsyncMock,
) -> None:
    """Communication settings are set, and cleared for devices without any."""
    device = make_device(TEST_SERIAL_1, online=True)
    other = make_device(TEST_SERIAL_2, online=True)
    other.communication_settings = {"communicationsEnabled": "false"}
    get_communications.return_value = COMMUNICATIONS

    async def update_devices() -> None:
        api._device_handler._final_devices.update(
            {TEST_SERIAL_1: device, TEST_SERIAL_2: other}
        )

    monkeypatch.setattr(api._device_handler, "update_devices", update_devices)

    assert await api._refresh_basic_data() is True

    get_communications.assert_awaited_once_with([device, other])
    assert device.communication_settings == COMMUNICATIONS[TEST_SERIAL_1]
    assert other.communication_settings == {}
