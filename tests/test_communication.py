# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for AlexaCommunicationsHandler error handling."""

from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1


@pytest.mark.anyio
async def test_failed_preferences_refresh_logs_the_underlying_error(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The HTTP failure reason is logged, not swallowed."""
    device = make_device(TEST_SERIAL_1)
    session_request = AsyncMock(
        side_effect=CannotRetrieveData("Request failed: Forbidden")
    )
    monkeypatch.setattr(
        api._communication_handler._http_wrapper, "session_request", session_request
    )

    preferences = await api._communication_handler.get_communication_preferences(
        [device]
    )

    assert preferences == {}
    assert "Request failed: Forbidden" in caplog.text
