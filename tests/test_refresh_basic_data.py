# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for _refresh_basic_data ordering in AmazonEchoApi."""

from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1


@pytest.mark.anyio
async def test_refresh_resolves_default_device_from_endpoint_only_account(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """Endpoint-only devices (e.g. Air Quality Monitor) resolve as default device.

    Regression test: the Air Quality Monitor is created by
    set_device_endpoints_data(), so resolving the default device before that call
    aborted the whole refresh with NoOnlineDevicesError on accounts without an
    Echo device.
    """
    call_order: list[str] = []

    async def _get_base_devices() -> None:
        call_order.append("get_base_devices")

    async def _set_device_endpoints_data() -> None:
        call_order.append("set_device_endpoints_data")
        api._device_handler._final_devices[TEST_SERIAL_1] = make_device(
            TEST_SERIAL_1, online=True
        )

    api._device_handler.get_base_devices = _get_base_devices  # type: ignore[method-assign]
    api._device_handler.set_device_endpoints_data = _set_device_endpoints_data  # type: ignore[method-assign]
    api._media_handler.update_music_providers = AsyncMock()  # type: ignore[method-assign]
    api._sequence_handler.update_routines = AsyncMock()  # type: ignore[method-assign]
    api._todo_handler.update_lists = AsyncMock()  # type: ignore[method-assign]

    await api._refresh_basic_data()

    assert call_order == ["get_base_devices", "set_device_endpoints_data"]
    default_device = await api.get_default_device()
    assert default_device.serial_number == TEST_SERIAL_1
