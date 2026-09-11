# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for Alexa vocal history parsing."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.implementation import history as history_module
from aioamazondevices.implementation.history import AmazonHistoryHandler

from .const import TEST_SERIAL_1

PersonsInfo = dict[str, str] | list[dict[str, str]] | None

TEST_PERSON = {
    "personId": "amzn1.actor.person.oid.PERSON_ID",
    "personFirstName": "Alice",
    "personType": "ADULT",
}


def _record(persons_info: PersonsInfo) -> dict[str, Any]:
    """Build a minimal vocal history record, shaped like the Amazon payload."""
    return {
        "timestamp": 1757000000000,
        "utteranceType": "GENERAL",
        "intent": "PlayMusicIntent",
        "title": "play some music",
        "subTitle": "Echo Dot",
        "deviceInfo": {"deviceSerialNumber": TEST_SERIAL_1},
        "personsInfo": persons_info,
    }


@pytest.fixture
def handler(monkeypatch: pytest.MonkeyPatch) -> AmazonHistoryHandler:
    """Return a history handler that skips the backend refresh wait."""
    monkeypatch.setattr(history_module, "BACKEND_REFRESH_WAIT_SECONDS", 0)
    return AmazonHistoryHandler(AsyncMock(), AsyncMock())


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("persons_info", "expected"),
    [
        pytest.param(
            TEST_PERSON,
            ("amzn1.actor.person.oid.PERSON_ID", "Alice", "ADULT"),
            id="recognised-speaker",
        ),
        pytest.param(
            [TEST_PERSON],
            ("amzn1.actor.person.oid.PERSON_ID", "Alice", "ADULT"),
            id="recognised-speaker-as-list",
        ),
        pytest.param(None, (None, None, None), id="voice-not-recognised"),
        pytest.param([], (None, None, None), id="empty-list"),
    ],
)
async def test_vocal_history_exposes_speaker(
    handler: AmazonHistoryHandler,
    persons_info: PersonsInfo,
    expected: tuple[str | None, str | None, str | None],
) -> None:
    """The recognised speaker is taken from personsInfo, absent when unknown."""
    handler._vocal_history_json = AsyncMock(  # type: ignore[method-assign]
        return_value={"alexaHistoryRecords": [_record(persons_info)]}
    )

    records = await handler.get_vocal_history()

    record = records[TEST_SERIAL_1]
    assert (record.person_id, record.person_first_name, record.person_type) == expected
