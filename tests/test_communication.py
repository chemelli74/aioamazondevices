# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Alexa communications handler."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1


def _preferences(state: str) -> dict[str, Any]:
    return {
        "devicePermissionsPreferences": [
            {"devicePreference": "announcements", "state": state, "allowed": True}
        ]
    }


@pytest.mark.anyio
async def test_get_communication_preferences_fails_fast(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preference requests do not retry, as there is one for every device."""
    wrapper = api._http_wrapper
    session_request = AsyncMock(return_value=(None, None))
    monkeypatch.setattr(wrapper, "session_request", session_request)
    monkeypatch.setattr(
        wrapper, "response_to_json", AsyncMock(return_value=_preferences("ON"))
    )

    await api._communication_handler.get_communication_preferences(
        [make_device(TEST_SERIAL_1)]
    )

    session_request.assert_awaited_once()
    assert session_request.await_args is not None
    assert session_request.await_args.kwargs["fail_fast"] is True


@pytest.mark.anyio
async def test_get_communication_preferences_keeps_cached_values(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed preferences call keeps the device's previous values."""
    wrapper = api._http_wrapper
    handler = api._communication_handler
    devices = [make_device(TEST_SERIAL_1)]
    expected = {TEST_SERIAL_1: {"announcements": "OFF"}}

    monkeypatch.setattr(
        wrapper, "session_request", AsyncMock(return_value=(None, None))
    )
    monkeypatch.setattr(
        wrapper, "response_to_json", AsyncMock(return_value=_preferences("OFF"))
    )
    assert await handler.get_communication_preferences(devices) == expected

    monkeypatch.setattr(
        wrapper, "session_request", AsyncMock(side_effect=CannotRetrieveData("boom"))
    )
    assert await handler.get_communication_preferences(devices) == expected
