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


@pytest.mark.anyio
@pytest.mark.parametrize(
    "subscribed",
    [
        pytest.param(False, id="no-subscribers"),
        pytest.param(True, id="subscribed"),
    ],
)
async def test_eq_event_fetches_history_only_for_subscribers(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch, subscribed: bool
) -> None:
    """The history is fetched and emitted only when someone is subscribed."""
    get_vocal_history = AsyncMock(return_value={TEST_SERIAL_1: RECORD})
    monkeypatch.setattr(api._history_handler, "get_vocal_history", get_vocal_history)

    received: list[dict[str, AmazonVocalRecord]] = []

    async def on_history(history: dict[str, AmazonVocalRecord]) -> None:
        received.append(history)

    if subscribed:
        api.on_history_event.append(on_history)
        api.on_history_event.freeze()

    await api._handle_eq_event_as_history_proxy()

    assert get_vocal_history.await_count == int(subscribed)
    assert received == ([{TEST_SERIAL_1: RECORD}] if subscribed else [])
