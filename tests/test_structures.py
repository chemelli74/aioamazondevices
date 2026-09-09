# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for AmazonDevice structure helpers."""

from collections.abc import Callable

import pytest

from aioamazondevices.const.devices import SPEAKER_GROUP_FAMILY
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1


@pytest.mark.parametrize(
    ("capabilities", "device_family", "expected"),
    [
        pytest.param(["MICROPHONE", "AUDIO_PLAYER"], "ECHO", True, id="echo"),
        pytest.param(
            ["MICROPHONE", "AUDIO_PLAYER"],
            SPEAKER_GROUP_FAMILY,
            False,
            id="speaker-group",
        ),
        pytest.param([], "AIR_QUALITY_MONITOR", False, id="air-quality-monitor"),
    ],
)
def test_voice_control_supported(
    make_device: Callable[..., AmazonDevice],
    capabilities: list[str],
    device_family: str,
    expected: bool,
) -> None:
    """Only devices exposing the speech recognizer can be spoken to."""
    device = make_device(
        TEST_SERIAL_1, capabilities=capabilities, device_family=device_family
    )

    assert device.voice_control_supported is expected
