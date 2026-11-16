# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the vocal history push-event proxy in AmazonEchoApi."""

from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonVocalRecord

from .const import TEST_SERIAL_1

RECORD = AmazonVocalRecord(
    timestamp=1,
    history_type="UTTERANCE",
    intent="Unknown",
    title="",
    sub_title="",
)


@pytest.fixture
def get_vocal_history(api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Replace fetching the vocal history, returning one record."""
    get_vocal_history = AsyncMock(return_value={TEST_SERIAL_1: RECORD})
    monkeypatch.setattr(api._history_handler, "get_vocal_history", get_vocal_history)
    return get_vocal_history


@pytest.mark.anyio
async def test_eq_event_without_subscribers_skips_history(
    api: AmazonEchoApi, get_vocal_history: AsyncMock
) -> None:
    """The history is not fetched when nobody is subscribed."""
    await api._handle_eq_event_as_history_proxy()

    get_vocal_history.assert_not_awaited()


@pytest.mark.anyio
async def test_eq_event_emits_history_to_subscribers(
    api: AmazonEchoApi, get_vocal_history: AsyncMock
) -> None:
    """The history is fetched and emitted when someone is subscribed."""
    on_history = AsyncMock()
    api.on_history_event.append(on_history)
    api.on_history_event.freeze()

    await api._handle_eq_event_as_history_proxy()

    get_vocal_history.assert_awaited_once_with()
    on_history.assert_awaited_once_with({TEST_SERIAL_1: RECORD})
