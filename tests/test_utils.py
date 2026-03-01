"""Tests for utility helpers."""

import pytest

from aioamazondevices.utils import parse_device_details


@pytest.mark.parametrize(
    ("raw_model", "expected_model", "expected_hardware_version"),
    [
        (
            "Echo Dot (5th gen) with Clock",
            "Echo Dot with Clock",
            "5th Gen",
        ),
        (
            "Echo Dot (4th generation)",
            "Echo Dot",
            "4th Gen",
        ),
        (
            "Echo Dot (3rd Gen)",
            "Echo Dot",
            "3rd Gen",
        ),
        (
            "Fire TV Stick 4K (2nd Gen)",
            "Fire TV Stick 4K",
            "2nd Gen",
        ),
        (
            "Echo Dot (5th gen)",
            "Echo Dot",
            "5th Gen",
        ),
    ],
)
def test_parse_device_details_hardware_generation(
    raw_model: str,
    expected_model: str,
    expected_hardware_version: str,
) -> None:
    """Validate parsing and normalization of hardware generation strings."""
    model, hardware_version = parse_device_details(raw_model)

    assert model == expected_model
    assert hardware_version == expected_hardware_version


def test_parse_device_details_none() -> None:
    """Validate null model handling."""
    model, hardware_version = parse_device_details(None)

    assert model is None
    assert hardware_version is None
