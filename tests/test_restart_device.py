# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for restarting a device."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotRestartDevice, CannotRetrieveData
from aioamazondevices.structures import AmazonDevice

from .const import TEST_ACCESS_TOKEN, TEST_DEVICE_TYPE, TEST_SERIAL_1


@pytest.mark.anyio
async def test_restart_device(
    logged_in: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
) -> None:
    """The restart request names the device and carries the access token."""
    session_request = mock_json_response({})

    await logged_in.restart_device(make_device(TEST_SERIAL_1))

    assert session_request.await_args is not None
    kwargs = session_request.await_args.kwargs
    assert kwargs["input_data"] == {
        "deviceSerialNumber": TEST_SERIAL_1,
        "deviceType": TEST_DEVICE_TYPE,
    }
    assert kwargs["extended_headers"]["Authorization"] == (
        f"Bearer {TEST_ACCESS_TOKEN}"
    )


@pytest.mark.anyio
async def test_restart_device_fails(
    logged_in: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed restart request is raised as CannotRestartDevice."""
    monkeypatch.setattr(
        logged_in._http_wrapper,
        "session_request",
        AsyncMock(side_effect=CannotRetrieveData("boom")),
    )

    with pytest.raises(CannotRestartDevice):
        await logged_in.restart_device(make_device(TEST_SERIAL_1))
