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

    Regression test: the Air Quality Monitor is created by update_devices(), so
    resolving the default device before that call aborted the whole refresh with
    NoOnlineDevicesError on accounts without an Echo device.
    """
    call_order: list[str] = []

    async def _update_devices() -> None:
        call_order.append("update_devices")
        api._device_handler._final_devices[TEST_SERIAL_1] = make_device(
            TEST_SERIAL_1, online=True
        )

    api._device_handler.update_devices = _update_devices  # type: ignore[method-assign]
    api._media_handler.update_music_providers = AsyncMock()  # type: ignore[method-assign]
    api._sequence_handler.update_routines = AsyncMock()  # type: ignore[method-assign]
    api._todo_handler.update_lists = AsyncMock()  # type: ignore[method-assign]

    await api._refresh_basic_data()

    assert call_order == ["update_devices"]
    default_device = await api.get_default_device()
    assert default_device.serial_number == TEST_SERIAL_1
