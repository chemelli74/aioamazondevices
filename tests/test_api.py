# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the AmazonEchoApi public methods and push-event dispatch."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientSession

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.login import AmazonLogin
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonDropInStatus,
    AmazonListEvent,
    AmazonListEventType,
    AmazonPushMessage,
    AmazonSaveDataConfig,
)

from .const import TEST_EMAIL, TEST_PASSWORD, TEST_SERIAL_1

PUSH_PAYLOAD = {"key": "value"}


@pytest.mark.anyio
async def test_domain_from_login_site(
    client_session: ClientSession, tmp_path: Path
) -> None:
    """The domain comes from the site stored with the previous login."""
    api = AmazonEchoApi(
        client_session,
        TEST_EMAIL,
        TEST_PASSWORD,
        save_data=AmazonSaveDataConfig(path=tmp_path),
        login_data={
            "site": "https://www.amazon.it",
            "device_info": {"device_serial_number": TEST_SERIAL_1},
        },
    )

    assert api.domain == "it"


@pytest.mark.anyio
async def test_login(api: AmazonEchoApi) -> None:
    """The login helper is exposed."""
    assert isinstance(api.login, AmazonLogin)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("event_type", "handler", "expected_args"),
    [
        pytest.param(
            AmazonPushMessage.VolumeChange,
            "_handle_volume_change_event",
            (PUSH_PAYLOAD,),
            id="volume",
        ),
        pytest.param(
            AmazonPushMessage.EqualizerStateChange,
            "_handle_eq_event_as_history_proxy",
            (),
            id="equalizer",
        ),
        pytest.param(
            AmazonPushMessage.AudioPlayerState,
            "_handle_audio_player_state_event",
            (),
            id="audio-player",
        ),
        pytest.param(
            AmazonPushMessage.ItemChange,
            "_handle_item_change_event",
            (PUSH_PAYLOAD,),
            id="item-change",
        ),
        pytest.param(
            AmazonPushMessage.DoNotDisturbChange,
            "_handle_dnd_event",
            (PUSH_PAYLOAD,),
            id="dnd",
        ),
    ],
)
async def test_push_event_dispatch(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
    event_type: AmazonPushMessage,
    handler: str,
    expected_args: tuple[dict[str, str], ...],
) -> None:
    """Each push event type is routed to its handler."""
    handler_mock = AsyncMock()
    monkeypatch.setattr(api, handler, handler_mock)

    await api._http2_push_event_handler(event_type.value, PUSH_PAYLOAD)

    handler_mock.assert_awaited_once_with(*expected_args)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "value"),
    [
        pytest.param("set_communication_status", True, id="communication"),
        pytest.param("set_dropin_status", AmazonDropInStatus.HOME, id="dropin"),
        pytest.param("set_announcement_status", False, id="announcement"),
    ],
)
async def test_communication_settings(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    value: bool | AmazonDropInStatus,
) -> None:
    """Communication settings are forwarded to the communications handler."""
    device = make_device(TEST_SERIAL_1)
    handler_mock = AsyncMock()
    monkeypatch.setattr(api._communication_handler, method, handler_mock)

    await getattr(api, method)(device, value)

    handler_mock.assert_awaited_once_with(device, value)


@pytest.mark.anyio
async def test_restart_device(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A restart is forwarded to the device handler."""
    device = make_device(TEST_SERIAL_1)
    restart = AsyncMock()
    monkeypatch.setattr(api._device_handler, "restart_device", restart)

    await api.restart_device(device)

    restart.assert_awaited_once_with(device)


@pytest.mark.anyio
async def test_sync_history_state(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The vocal history comes from the history handler."""
    history = {TEST_SERIAL_1: object()}
    monkeypatch.setattr(
        api._history_handler, "get_vocal_history", AsyncMock(return_value=history)
    )

    assert await api.sync_history_state() is history


@pytest.mark.anyio
async def test_todo_event_without_subscribers(api: AmazonEchoApi) -> None:
    """A todo event is not sent before the subscribers are frozen."""
    callback = AsyncMock()
    api.on_todo_event.append(callback)

    await api._emit_todo_event(
        AmazonListEvent("list", "item", AmazonListEventType.CREATED)
    )

    callback.assert_not_awaited()


@pytest.mark.anyio
async def test_dnd_event_without_serial_is_ignored(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DND event with no device serial triggers neither sync nor update."""
    sync = AsyncMock()
    monkeypatch.setattr(api._dnd_handler, "sync_do_not_disturb_status", sync)

    await api._handle_dnd_event({"dopplerId": {}, "enabled": True})

    sync.assert_not_awaited()
    assert api._dnd_handler.dnd_states == {}
