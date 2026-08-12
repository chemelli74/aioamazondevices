# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for HTTP/2 push handling of vocal history refreshes."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonDevice, AmazonPushMessage

SONOS_SERIAL = "aa4228b15aa44796a0c2c1bdc9eae303"
ECHO_SERIAL = "b182ad697e064415841cfe96a66cbf64"
UNKNOWN_SERIAL = "ffffffffffffffffffffffffffffffff"

EXPECTED_REFRESHES_AFTER_WINDOW = 2


def _device(serial: str, manufacturer: str | None) -> AmazonDevice:
    """Build a minimal device entry."""
    return AmazonDevice(
        account_name="Speaker",
        capabilities=[],
        device_family="ECHO",
        device_type="A39OV95SPFQ9YG",
        device_owner_customer_id="A1CUSTOMERID",
        household_device=False,
        device_cluster_members={},
        online=True,
        serial_number=serial,
        manufacturer=manufacturer,
        model="Era 100",
        software_version=None,
        hardware_version=None,
        entity_id=None,
        endpoint_id=None,
        sensors={},
        notifications_supported=False,
        notifications={},
        media_player_supported=True,
        communication_settings={},
    )


@pytest.fixture
def api() -> AmazonEchoApi:
    """Return an API instance with two known devices and no I/O."""
    instance = AmazonEchoApi(MagicMock(), "user@example.com", "password")
    instance._device_handler._final_devices = {  # noqa: SLF001
        SONOS_SERIAL: _device(SONOS_SERIAL, "Sonos, Inc."),
        ECHO_SERIAL: _device(ECHO_SERIAL, "Amazon"),
    }
    return instance


@pytest.fixture
def refreshes(api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Record history refreshes while suppressing unrelated push work."""
    calls: list[int] = []

    async def _get_vocal_history(
        _known_serials: set[str] | None = None,
    ) -> dict[str, Any]:
        return {}

    async def _emit(_vocal_history: dict[str, Any]) -> None:
        calls.append(1)

    async def _volume(_payload: dict[str, Any]) -> None:
        return None

    monkeypatch.setattr(
        api._history_handler,  # noqa: SLF001
        "get_vocal_history",
        _get_vocal_history,
    )
    monkeypatch.setattr(api, "_emit_history_event", _emit)
    monkeypatch.setattr(api, "_handle_volume_change_event", _volume)
    return calls


def _volume_payload(serial: str) -> dict[str, Any]:
    return {
        "dopplerId": {"deviceSerialNumber": serial, "deviceType": "A39OV95SPFQ9YG"},
        "volumeSetting": 10,
        "isMuted": False,
    }


def _push(api: AmazonEchoApi, event: str, payload: dict[str, Any]) -> None:
    asyncio.run(api._http2_push_event_handler(event, payload))  # noqa: SLF001


@pytest.mark.parametrize(
    ("serial", "expected"),
    [
        (SONOS_SERIAL, True),
        (ECHO_SERIAL, False),
        (UNKNOWN_SERIAL, False),
        (None, False),
    ],
)
def test_is_sonos_device(
    api: AmazonEchoApi, serial: str | None, expected: bool
) -> None:
    """Only devices reporting a Sonos manufacturer are detected."""
    assert api._is_sonos_device(serial) is expected  # noqa: SLF001


def test_volume_change_refreshes_history_for_sonos(
    api: AmazonEchoApi, refreshes: list[int]
) -> None:
    """A Sonos volume change stands in for the missing equalizer event."""
    _push(api, AmazonPushMessage.VolumeChange.value, _volume_payload(SONOS_SERIAL))

    assert len(refreshes) == 1


def test_volume_change_ignored_for_echo(
    api: AmazonEchoApi, refreshes: list[int]
) -> None:
    """Echo volume changes must not trigger history requests."""
    _push(api, AmazonPushMessage.VolumeChange.value, _volume_payload(ECHO_SERIAL))

    assert refreshes == []


def test_volume_change_ignored_for_unknown_device(
    api: AmazonEchoApi, refreshes: list[int]
) -> None:
    """An unrecognised serial number is never treated as a Sonos."""
    _push(api, AmazonPushMessage.VolumeChange.value, _volume_payload(UNKNOWN_SERIAL))

    assert refreshes == []


def test_repeated_volume_changes_are_debounced(
    api: AmazonEchoApi, refreshes: list[int]
) -> None:
    """Arbitration bursts collapse into a single history refresh."""
    payload = _volume_payload(SONOS_SERIAL)

    _push(api, AmazonPushMessage.VolumeChange.value, payload)
    _push(api, AmazonPushMessage.VolumeChange.value, payload)
    _push(api, AmazonPushMessage.VolumeChange.value, payload)

    assert len(refreshes) == 1


def test_history_refreshes_again_after_debounce_window(
    api: AmazonEchoApi, refreshes: list[int]
) -> None:
    """A later utterance still refreshes once the window has passed."""
    payload = _volume_payload(SONOS_SERIAL)

    _push(api, AmazonPushMessage.VolumeChange.value, payload)
    api._last_sonos_history_refresh = datetime.now(UTC) - timedelta(minutes=1)  # noqa: SLF001
    _push(api, AmazonPushMessage.VolumeChange.value, payload)

    assert len(refreshes) == EXPECTED_REFRESHES_AFTER_WINDOW


def test_equalizer_event_still_refreshes_history(
    api: AmazonEchoApi, refreshes: list[int]
) -> None:
    """Existing Echo behaviour is unchanged and is not debounced."""
    _push(api, AmazonPushMessage.EqualizerStateChange.value, {})

    assert len(refreshes) == 1


def test_equalizer_event_is_not_debounced(
    api: AmazonEchoApi, refreshes: list[int]
) -> None:
    """The Sonos throttle must not affect the equalizer path."""
    _push(api, AmazonPushMessage.EqualizerStateChange.value, {})
    _push(api, AmazonPushMessage.EqualizerStateChange.value, {})

    assert len(refreshes) == EXPECTED_REFRESHES_AFTER_WINDOW
