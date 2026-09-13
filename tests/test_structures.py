# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for AmazonDevice structure helpers."""

from collections.abc import Callable

import pytest

from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1


@pytest.mark.parametrize(
    "expected",
    [
        pytest.param(True, id="voice-capable"),
        pytest.param(False, id="voice-incapable"),
    ],
)
def test_voice_control_supported(
    make_device: Callable[..., AmazonDevice],
    expected: bool,
) -> None:
    """The voice_control_supported field reflects what the device reports."""
    device = make_device(TEST_SERIAL_1, voice_control_supported=expected)

    assert device.voice_control_supported is expected
