# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Alexa vocal history handler."""

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from aioamazondevices.const.metadata import UTTERANCE_TYPES_TO_SKIP
from aioamazondevices.implementation import history
from aioamazondevices.implementation.history import AmazonHistoryHandler

CUSTOMER_ID = "A1CUSTOMERID"
DEVICE_TYPE = "A39OV95SPFQ9YG"
SERIAL_A = "aa4228b15aa44796a0c2c1bdc9eae303"
SERIAL_B = "5a3171f56be444be892e80087a556fac"
UNKNOWN_SERIAL = "ffffffffffffffffffffffffffffffff"

DEFAULT_TIMESTAMP = 1785981806720
NEWEST_TIMESTAMP = 2000


def _record(**overrides: object) -> dict[str, Any]:
    """Build a history record shaped like the Amazon payload."""
    timestamp = overrides.pop("timestamp", DEFAULT_TIMESTAMP)
    serial = overrides.pop("serial", SERIAL_A)

    record: dict[str, Any] = {
        "recordType": "utterance",
        "customerId": CUSTOMER_ID,
        "timestamp": timestamp,
        "activityKey": f"{CUSTOMER_ID}#{timestamp}#{DEVICE_TYPE}#{serial}",
        "utteranceType": "GENERAL",
        "intent": "QAIntent",
        "title": "what time is it",
        "subTitle": "",
        "deviceInfo": None,
    }
    record.update(overrides)
    return record


def _run(
    records: list[dict[str, Any]],
    known: set[str] | None = None,
) -> dict[str, Any]:
    """Run get_vocal_history against a fixed set of records."""
    handler = AmazonHistoryHandler(MagicMock(), MagicMock())

    async def _fake_json() -> dict[str, Any]:
        return {"alexaHistoryRecords": records}

    handler._vocal_history_json = _fake_json  # type: ignore[method-assign]  # noqa: SLF001
    return asyncio.run(handler.get_vocal_history(known))


@pytest.fixture(autouse=True)
def _no_backend_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid the real backend settle delay."""
    monkeypatch.setattr(history, "BACKEND_REFRESH_WAIT_SECONDS", 0)


def test_serial_read_from_device_info() -> None:
    """Read the serial number from a record that carries device info."""
    records = _run([_record(deviceInfo={"deviceSerialNumber": SERIAL_A})])

    assert list(records) == [SERIAL_A]
    assert records[SERIAL_A].title == "what time is it"


def test_serial_read_from_device_info_list() -> None:
    """Accept device info delivered as a list."""
    records = _run([_record(deviceInfo=[{"deviceSerialNumber": SERIAL_A}])])

    assert list(records) == [SERIAL_A]


def test_serial_recovered_from_activity_key() -> None:
    """Fall back to the activity key when device info is missing."""
    records = _run([_record()], {SERIAL_A})

    assert list(records) == [SERIAL_A]


def test_activity_key_serial_must_be_known() -> None:
    """Discard an activity key serial that matches no known device."""
    records = _run([_record(serial=UNKNOWN_SERIAL)], {SERIAL_A})

    assert records == {}


def test_activity_key_accepted_when_devices_unknown() -> None:
    """Trust the activity key serial when no device set is supplied."""
    records = _run([_record(serial=UNKNOWN_SERIAL)])

    assert list(records) == [UNKNOWN_SERIAL]


@pytest.mark.parametrize(
    "activity_key",
    [None, "", "not-a-key", f"{CUSTOMER_ID}#123#{DEVICE_TYPE}", 12345],
)
def test_malformed_activity_key_is_skipped(activity_key: object) -> None:
    """Skip records whose activity key cannot be parsed."""
    records = _run([_record(activityKey=activity_key)])

    assert records == {}


@pytest.mark.parametrize("utterance_type", UTTERANCE_TYPES_TO_SKIP)
def test_ignored_utterance_types(utterance_type: str) -> None:
    """Keep filtering out non conversational utterance types."""
    records = _run([_record(utteranceType=utterance_type)], {SERIAL_A})

    assert records == {}


def test_only_latest_record_per_device_is_kept() -> None:
    """Keep the newest record for a given serial number."""
    records = _run(
        [
            _record(timestamp=1000, title="older"),
            _record(timestamp=NEWEST_TIMESTAMP, title="newer"),
            _record(timestamp=1500, title="middle"),
        ],
        {SERIAL_A},
    )

    assert records[SERIAL_A].title == "newer"
    assert records[SERIAL_A].timestamp == NEWEST_TIMESTAMP


def test_records_are_grouped_per_device() -> None:
    """Track the latest record separately for each device."""
    records = _run(
        [
            _record(serial=SERIAL_A, title="office"),
            _record(serial=SERIAL_B, title="kitchen"),
        ],
        {SERIAL_A, SERIAL_B},
    )

    assert records[SERIAL_A].title == "office"
    assert records[SERIAL_B].title == "kitchen"


def test_device_info_takes_precedence_over_activity_key() -> None:
    """Prefer device info over the activity key for the serial number."""
    records = _run(
        [_record(serial=SERIAL_B, deviceInfo={"deviceSerialNumber": SERIAL_A})],
        {SERIAL_A, SERIAL_B},
    )

    assert list(records) == [SERIAL_A]


def test_false_wake_does_not_mask_a_real_command() -> None:
    """Keep the latest real command even when a false wake is more recent."""
    records = _run(
        [
            _record(timestamp=1000, title="alexa turn off the nursery"),
            _record(
                timestamp=NEWEST_TIMESTAMP,
                utteranceType="FALSE_WAKE_WORD_1P",
                title="",
            ),
        ],
        {SERIAL_A},
    )

    assert records[SERIAL_A].title == "alexa turn off the nursery"
