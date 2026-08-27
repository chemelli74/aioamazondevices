# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the vocal history push-event proxy in AmazonEchoApi."""

from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonVocalRecord

RECORD = AmazonVocalRecord(
    timestamp=1,
    history_type="UTTERANCE",
    intent="Unknown",
    title="",
    sub_title="",
)


@pytest.mark.anyio
async def test_eq_event_skips_history_fetch_without_subscribers(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No subscribers means the vocal history is never requested."""
    get_vocal_history = AsyncMock(return_value={})
    monkeypatch.setattr(api._history_handler, "get_vocal_history", get_vocal_history)

    await api._handle_eq_event_as_history_proxy()

    get_vocal_history.assert_not_awaited()


@pytest.mark.anyio
async def test_eq_event_fetches_history_for_subscribers(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a subscriber attached the history is fetched and emitted."""
    get_vocal_history = AsyncMock(return_value={"SERIAL": RECORD})
    monkeypatch.setattr(api._history_handler, "get_vocal_history", get_vocal_history)

    received: list[dict[str, AmazonVocalRecord]] = []

    async def on_history(history: dict[str, AmazonVocalRecord]) -> None:
        received.append(history)

    api.on_history_event.append(on_history)
    api.on_history_event.freeze()

    await api._handle_eq_event_as_history_proxy()

    get_vocal_history.assert_awaited_once()
    assert received == [{"SERIAL": RECORD}]
