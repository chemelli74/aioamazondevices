# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for default device persistence in AmazonEchoApi."""

from collections.abc import Callable
from pathlib import Path

import orjson
import pytest

from aioamazondevices.api import (
    SETTINGS_DEFAULT_DEVICE,
    SETTINGS_FILENAME,
    AmazonEchoApi,
)
from aioamazondevices.exceptions import NoOnlineDevicesError
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1, TEST_SERIAL_2


@pytest.mark.anyio
async def test_set_default_device_persists_serial(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice], tmp_path: Path
) -> None:
    """Setting the default device writes its serial number to settings.json."""
    device = make_device(TEST_SERIAL_1)

    await api.set_default_device(device)

    settings_file = tmp_path / SETTINGS_FILENAME
    assert orjson.loads(settings_file.read_bytes()) == {
        SETTINGS_DEFAULT_DEVICE: TEST_SERIAL_1
    }


@pytest.mark.anyio
async def test_get_default_device_returns_device_just_set(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """get_default_device returns the device passed to set_default_device."""
    device = make_device(TEST_SERIAL_1)
    api._device_handler._final_devices = {device.serial_number: device}

    await api.set_default_device(device)

    assert await api.get_default_device() == device


@pytest.mark.anyio
@pytest.mark.parametrize(
    "persisted_serial",
    [
        pytest.param(TEST_SERIAL_1, id="persisted-serial-matches-device"),
        pytest.param(TEST_SERIAL_2, id="persisted-serial-is-stale"),
    ],
)
async def test_init_default_device_resolves_persisted_or_falls_back(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    tmp_path: Path,
    persisted_serial: str,
) -> None:
    """A matching persisted serial is used; a stale one falls back to online."""
    online_device = make_device(TEST_SERIAL_1, online=True)
    api._device_handler._final_devices = {online_device.serial_number: online_device}
    (tmp_path / SETTINGS_FILENAME).write_bytes(
        orjson.dumps({SETTINGS_DEFAULT_DEVICE: persisted_serial})
    )

    await api._init_default_device()

    assert await api.get_default_device() == online_device


@pytest.mark.anyio
async def test_init_default_device_falls_back_to_first_online_device(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """With nothing persisted, the first online device becomes the default."""
    offline_device = make_device(TEST_SERIAL_1, online=False)
    online_device = make_device(TEST_SERIAL_2, online=True)
    api._device_handler._final_devices = {
        offline_device.serial_number: offline_device,
        online_device.serial_number: online_device,
    }

    await api._init_default_device()

    assert await api.get_default_device() == online_device


@pytest.mark.anyio
@pytest.mark.parametrize(
    "settings_bytes",
    [
        pytest.param(b"not valid json", id="malformed-json"),
        pytest.param(orjson.dumps([1, 2, 3]), id="non-object-json"),
    ],
)
async def test_init_default_device_ignores_invalid_settings_file(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    tmp_path: Path,
    settings_bytes: bytes,
) -> None:
    """Invalid settings.json content is treated as no persisted settings."""
    online_device = make_device(TEST_SERIAL_1, online=True)
    api._device_handler._final_devices = {online_device.serial_number: online_device}
    (tmp_path / SETTINGS_FILENAME).write_bytes(settings_bytes)

    await api._init_default_device()

    assert await api.get_default_device() == online_device


@pytest.mark.anyio
async def test_init_default_device_raises_without_online_devices(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """No online devices means no default device can be resolved."""
    offline_device = make_device(TEST_SERIAL_1, online=False)
    api._device_handler._final_devices = {offline_device.serial_number: offline_device}

    with pytest.raises(NoOnlineDevicesError):
        await api._init_default_device()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("second_round_serials", "expected_serial"),
    [
        pytest.param(
            (TEST_SERIAL_1, TEST_SERIAL_2), TEST_SERIAL_1, id="device-still-present"
        ),
        pytest.param((TEST_SERIAL_2,), TEST_SERIAL_2, id="device-removed"),
    ],
)
async def test_init_default_device_revalidates_on_second_call(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    second_round_serials: tuple[str, ...],
    expected_serial: str,
) -> None:
    """A resolved device is kept if still present, re-resolved if removed."""
    first_device = make_device(TEST_SERIAL_1, online=True)
    second_device = make_device(TEST_SERIAL_2, online=True)
    all_devices = {
        first_device.serial_number: first_device,
        second_device.serial_number: second_device,
    }
    api._device_handler._final_devices = {first_device.serial_number: first_device}

    await api._init_default_device()

    api._device_handler._final_devices = {
        serial: all_devices[serial] for serial in second_round_serials
    }
    await api._init_default_device()

    assert await api.get_default_device() == all_devices[expected_serial]
