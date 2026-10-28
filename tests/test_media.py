# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the media player features of AmazonMediaHandler and AmazonEchoApi."""

import dataclasses
from collections.abc import Callable
from http import HTTPMethod
from typing import Any
from unittest.mock import AsyncMock, call

import pytest
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import (
    ARRAY_WRAPPER,
    URI_DEVICE_VOLUMES,
    URI_MEDIA_CONTROL,
    URI_MEDIA_STATE,
    URI_MUSIC_PROVIDERS,
)
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonMediaControls,
    AmazonMediaState,
    AmazonMusicProvider,
    AmazonSequenceType,
    AmazonVolumeState,
)

from .const import TEST_SERIAL_1, TEST_SERIAL_2

TEST_SERIAL_GROUP = "GROUP-1"
TEST_PROVIDER_ID = "AMAZON_MUSIC"

EMPTY_MEDIA_STATE = AmazonMediaState(
    player_state=None,
    now_playing_url=None,
    now_playing_title=None,
    now_playing_line1=None,
    now_playing_line2=None,
    next_enabled=False,
    previous_enabled=False,
    pause_enabled=False,
    seek_forward_enabled=False,
    seek_back_enabled=False,
    shuffle_enabled=False,
    repeat_enabled=False,
    media_length=None,
    media_position=None,
    media_position_updated_at=None,
    media_provider=None,
    media_provider_url=None,
)


@pytest.fixture
def media_device(make_device: Callable[..., AmazonDevice]) -> AmazonDevice:
    """Return a device that supports the media player."""
    return dataclasses.replace(make_device(TEST_SERIAL_1), media_player_supported=True)


@pytest.fixture
def send_message(api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Replace the sequence handler's send_message and return the mock."""
    send_message = AsyncMock()
    monkeypatch.setattr(api._sequence_handler, "send_message", send_message)
    return send_message


@pytest.fixture
def speaker_group(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> AmazonDevice:
    """Register two member devices and return a speaker group containing them."""
    group = make_device(TEST_SERIAL_GROUP)
    group.device_cluster_members = {TEST_SERIAL_1: None, TEST_SERIAL_2: None}
    api._device_handler._final_devices = {
        TEST_SERIAL_1: make_device(TEST_SERIAL_1),
        TEST_SERIAL_2: make_device(TEST_SERIAL_2),
        TEST_SERIAL_GROUP: group,
    }
    return group


def _music_provider(
    provider_id: str | None,
    *,
    display_name: str = "Provider",
    availability: str = "AVAILABLE",
    supported: tuple[str, ...] = (AmazonSequenceType.Music,),
) -> dict[str, Any]:
    """Build a music provider entry as returned by the behaviors API."""
    return {
        "id": provider_id,
        "displayName": display_name,
        "availability": availability,
        "supportedProperties": list(supported),
        "providerData": {"isDefaultMusicProvider": provider_id == TEST_PROVIDER_ID},
    }


@pytest.mark.anyio
async def test_music_providers_are_fetched_once_and_filtered(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """Only available music providers with an id and a name are kept."""
    session_request = mock_json_response(
        {
            ARRAY_WRAPPER: [
                _music_provider(TEST_PROVIDER_ID, display_name="Amazon Music"),
                _music_provider("SPOTIFY", display_name="Spotify"),
                _music_provider("NOT_MUSIC", supported=("Alexa.Other",)),
                _music_provider(None),
                _music_provider("NO_NAME", display_name=""),
                _music_provider("OFFLINE", availability="UNAVAILABLE"),
            ]
        }
    )
    handler = api._media_handler

    providers = await handler.music_providers
    assert await handler.music_providers is providers

    assert providers == {
        TEST_PROVIDER_ID: AmazonMusicProvider(
            provider_id=TEST_PROVIDER_ID,
            provider_name="Amazon Music",
            availability="AVAILABLE",
            default_provider=True,
        ),
        "SPOTIFY": AmazonMusicProvider(
            provider_id="SPOTIFY",
            provider_name="Spotify",
            availability="AVAILABLE",
            default_provider=False,
        ),
    }
    session_request.assert_awaited_once_with(
        method=HTTPMethod.GET,
        url=URL.joinpath(
            handler._session_state_data.alexa_website_url, URI_MUSIC_PROVIDERS
        ).with_query({"skillId": "amzn1.ask.1p.music"}),
    )


@pytest.mark.anyio
async def test_device_volumes_are_fetched_once(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """Device volumes are synced on first access and then served from cache."""
    session_request = mock_json_response(
        {
            "volumes": [
                {"dsn": TEST_SERIAL_1, "speakerVolume": 30, "speakerMuted": False},
                {"dsn": TEST_SERIAL_2, "speakerVolume": 0, "speakerMuted": True},
            ]
        }
    )
    handler = api._media_handler

    volumes = await handler.device_volumes
    assert await handler.device_volumes is volumes

    assert volumes == {
        TEST_SERIAL_1: AmazonVolumeState(30, False),
        TEST_SERIAL_2: AmazonVolumeState(0, True),
    }
    session_request.assert_awaited_once_with(
        method=HTTPMethod.GET,
        url=URL.joinpath(
            handler._session_state_data.alexa_website_url, URI_DEVICE_VOLUMES
        ),
    )


@pytest.mark.anyio
async def test_sync_device_volumes_without_volumes_clears_cache(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """A response with no volumes list replaces the cache with an empty one."""
    mock_json_response({})
    handler = api._media_handler
    handler.update_cached_device_volume(TEST_SERIAL_1, AmazonVolumeState(10, False))

    await handler.sync_device_volumes()

    assert handler._device_volumes == {}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("member_volumes", "expected"),
    [
        pytest.param(
            {
                TEST_SERIAL_1: AmazonVolumeState(50, False),
                TEST_SERIAL_2: AmazonVolumeState(33, True),
            },
            AmazonVolumeState(41, False),
            id="floored-average-partly-muted",
        ),
        pytest.param(
            {
                TEST_SERIAL_1: AmazonVolumeState(20, True),
                TEST_SERIAL_2: AmazonVolumeState(40, True),
            },
            AmazonVolumeState(30, True),
            id="all-muted",
        ),
        pytest.param(
            {
                TEST_SERIAL_1: AmazonVolumeState(20, False),
                TEST_SERIAL_2: AmazonVolumeState(None, True),
            },
            AmazonVolumeState(20, False),
            id="member-without-volume-ignored",
        ),
        pytest.param(
            {TEST_SERIAL_1: AmazonVolumeState(None, False)},
            None,
            id="no-member-volumes",
        ),
        pytest.param({}, None, id="no-cached-members"),
    ],
)
async def test_update_cached_speaker_group_volume(
    api: AmazonEchoApi,
    member_volumes: dict[str, AmazonVolumeState],
    expected: AmazonVolumeState | None,
) -> None:
    """The group volume is the floored member average, muted only if all are."""
    handler = api._media_handler
    for serial, volume in member_volumes.items():
        handler.update_cached_device_volume(serial, volume)

    handler.update_cached_speaker_group_volume(
        TEST_SERIAL_GROUP, [TEST_SERIAL_1, TEST_SERIAL_2]
    )

    assert handler._device_volumes.get(TEST_SERIAL_GROUP) == expected


@pytest.mark.anyio
async def test_get_media_states_maps_sessions_by_serial(
    api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    media_device: AmazonDevice,
) -> None:
    """Each endpoint in a session is mapped to that session by its serial."""
    group_session = {
        "endpointList": [
            {"id": {"deviceSerialNumber": TEST_SERIAL_1}},
            {"id": {"deviceSerialNumber": TEST_SERIAL_2}},
        ],
        "nowPlayingData": {"playerState": "PLAYING"},
    }
    session_request = mock_json_response(
        {"mediaSessionList": [group_session, {"endpointList": None}]}
    )
    handler = api._media_handler

    sessions = await handler._get_media_states(media_device)

    assert sessions == {TEST_SERIAL_1: group_session, TEST_SERIAL_2: group_session}
    session_request.assert_awaited_once_with(
        method=HTTPMethod.GET,
        url=URL.joinpath(
            handler._session_state_data.alexa_website_url, URI_MEDIA_STATE
        ).with_query(
            {
                "deviceSerialNumber": TEST_SERIAL_1,
                "deviceType": media_device.device_type,
            }
        ),
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        pytest.param({}, id="missing"),
        pytest.param({"mediaSessionList": None}, id="null"),
    ],
)
async def test_get_media_states_without_sessions(
    api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    media_device: AmazonDevice,
    response: dict[str, Any],
) -> None:
    """A missing or null session list returns no sessions."""
    mock_json_response(response)

    assert await api._media_handler._get_media_states(media_device) == {}


@pytest.mark.anyio
async def test_sync_media_state_parses_now_playing(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
    make_device: Callable[..., AmazonDevice],
    media_device: AmazonDevice,
) -> None:
    """Now playing data is parsed, and media devices without a session are empty."""
    idle_device = dataclasses.replace(
        make_device(TEST_SERIAL_2), media_player_supported=True
    )
    non_media_device = make_device(TEST_SERIAL_GROUP)
    now_playing = {
        "playerState": "PLAYING",
        "mainArt": {"largeUrl": "https://example.com/art.jpg"},
        "infoText": {"title": "Song", "subText1": "Artist", "subText2": "Album"},
        "transport": {
            "next": "ENABLED",
            "previous": "DISABLED",
            "playPause": "ENABLED",
            "seekForward": "ENABLED",
            "seekBack": "HIDDEN",
            "shuffle": "ENABLED",
            "repeat": "DISABLED",
        },
        "progress": {"mediaLength": "245500", "mediaProgress": "61999"},
        "provider": {
            "providerName": "Amazon Music",
            "providerLogo": {"url": "https://example.com/logo.png"},
        },
    }
    get_media_states = AsyncMock(
        return_value={TEST_SERIAL_1: {"nowPlayingData": now_playing}}
    )
    handler = api._media_handler
    monkeypatch.setattr(handler, "_get_media_states", get_media_states)

    await handler.sync_media_state(
        {
            TEST_SERIAL_GROUP: non_media_device,
            TEST_SERIAL_1: media_device,
            TEST_SERIAL_2: idle_device,
        }
    )

    get_media_states.assert_awaited_once_with(media_device)
    media_states = await handler.media_states
    assert list(media_states) == [TEST_SERIAL_1, TEST_SERIAL_2]
    assert all(
        state.media_position_updated_at is not None for state in media_states.values()
    )
    assert dataclasses.replace(
        media_states[TEST_SERIAL_1], media_position_updated_at=None
    ) == AmazonMediaState(
        player_state="PLAYING",
        now_playing_url="https://example.com/art.jpg",
        now_playing_title="Song",
        now_playing_line1="Artist",
        now_playing_line2="Album",
        next_enabled=True,
        previous_enabled=False,
        pause_enabled=True,
        seek_forward_enabled=True,
        seek_back_enabled=False,
        shuffle_enabled=True,
        repeat_enabled=False,
        media_length=245,
        media_position=61,
        media_position_updated_at=None,
        media_provider="Amazon Music",
        media_provider_url="https://example.com/logo.png",
    )
    assert (
        dataclasses.replace(media_states[TEST_SERIAL_2], media_position_updated_at=None)
        == EMPTY_MEDIA_STATE
    )


@pytest.mark.anyio
async def test_sync_media_state_without_media_devices_skips_request(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
    make_device: Callable[..., AmazonDevice],
) -> None:
    """With no media player devices the states are cleared without a request."""
    get_media_states = AsyncMock()
    handler = api._media_handler
    monkeypatch.setattr(handler, "_get_media_states", get_media_states)
    handler._media_states = {TEST_SERIAL_1: EMPTY_MEDIA_STATE}

    await handler.sync_media_state({TEST_SERIAL_1: make_device(TEST_SERIAL_1)})

    get_media_states.assert_not_awaited()
    assert await handler.media_states == {}


@pytest.mark.anyio
async def test_sync_media_state_without_sessions_clears_states(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch, media_device: AmazonDevice
) -> None:
    """When no media sessions are returned the states are cleared."""
    handler = api._media_handler
    monkeypatch.setattr(handler, "_get_media_states", AsyncMock(return_value={}))
    handler._media_states = {TEST_SERIAL_1: EMPTY_MEDIA_STATE}

    await handler.sync_media_state({TEST_SERIAL_1: media_device})

    assert await handler.media_states == {}


@pytest.mark.anyio
async def test_handler_send_media_command_posts_command(
    api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    media_device: AmazonDevice,
) -> None:
    """The command is posted as JSON to the device's media control endpoint."""
    session_request = mock_json_response({})
    handler = api._media_handler

    await handler.send_media_command(media_device, AmazonMediaControls.Pause)

    session_request.assert_awaited_once_with(
        method=HTTPMethod.POST,
        url=URL.joinpath(
            handler._session_state_data.alexa_website_url, URI_MEDIA_CONTROL
        ).with_query(
            {
                "deviceSerialNumber": TEST_SERIAL_1,
                "deviceType": media_device.device_type,
            }
        ),
        input_data={"type": "PauseCommand"},
        json_data=True,
    )


@pytest.mark.anyio
async def test_send_media_command_stop_uses_sequence_per_member(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
    send_message: AsyncMock,
    speaker_group: AmazonDevice,
) -> None:
    """Stop is sent as a sequence to every cluster member, not as a command."""
    handler_command = AsyncMock()
    monkeypatch.setattr(api._media_handler, "send_media_command", handler_command)
    devices = api._device_handler.devices

    await api.send_media_command(speaker_group, AmazonMediaControls.Stop)

    handler_command.assert_not_awaited()
    assert send_message.await_args_list == [
        call(devices[TEST_SERIAL_1], AmazonSequenceType.Stop, "", None),
        call(devices[TEST_SERIAL_2], AmazonSequenceType.Stop, "", None),
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "command",
    [
        pytest.param(command, id=command.name.lower())
        for command in AmazonMediaControls
        if command != AmazonMediaControls.Stop
    ],
)
async def test_send_media_command_delegates_to_handler(
    api: AmazonEchoApi,
    monkeypatch: pytest.MonkeyPatch,
    send_message: AsyncMock,
    media_device: AmazonDevice,
    command: AmazonMediaControls,
) -> None:
    """Commands other than Stop go to the media control endpoint."""
    handler_command = AsyncMock()
    monkeypatch.setattr(api._media_handler, "send_media_command", handler_command)

    await api.send_media_command(media_device, command)

    handler_command.assert_awaited_once_with(media_device, command)
    send_message.assert_not_awaited()


@pytest.mark.anyio
async def test_set_device_volume_sends_to_each_member(
    api: AmazonEchoApi, send_message: AsyncMock, speaker_group: AmazonDevice
) -> None:
    """The volume is sent as a sequence to every cluster member."""
    devices = api._device_handler.devices

    await api.set_device_volume(speaker_group, 35)

    assert send_message.await_args_list == [
        call(devices[TEST_SERIAL_1], AmazonSequenceType.Volume, "35", None),
        call(devices[TEST_SERIAL_2], AmazonSequenceType.Volume, "35", None),
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "volume",
    [
        pytest.param(-1, id="below-min"),
        pytest.param(101, id="above-max"),
    ],
)
async def test_set_device_volume_out_of_range_raises(
    api: AmazonEchoApi,
    send_message: AsyncMock,
    speaker_group: AmazonDevice,
    volume: int,
) -> None:
    """A volume outside 0-100 is rejected before anything is sent."""
    with pytest.raises(ValueError, match="Volume must be between"):
        await api.set_device_volume(speaker_group, volume)

    send_message.assert_not_awaited()


@pytest.mark.anyio
async def test_call_alexa_music_sends_search_phrase(
    api: AmazonEchoApi, send_message: AsyncMock, media_device: AmazonDevice
) -> None:
    """A known provider plays the search phrase on the device."""
    api._media_handler._music_providers = {
        TEST_PROVIDER_ID: AmazonMusicProvider(
            TEST_PROVIDER_ID, "Amazon Music", "AVAILABLE", default_provider=True
        )
    }

    await api.call_alexa_music(media_device, "jazz", TEST_PROVIDER_ID)

    send_message.assert_awaited_once_with(
        media_device, AmazonSequenceType.Music, "jazz", TEST_PROVIDER_ID
    )


@pytest.mark.anyio
async def test_call_alexa_music_unknown_provider_raises(
    api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    send_message: AsyncMock,
    media_device: AmazonDevice,
) -> None:
    """An unavailable provider is rejected before anything is sent."""
    mock_json_response({ARRAY_WRAPPER: [_music_provider(TEST_PROVIDER_ID)]})

    with pytest.raises(ValueError, match="SPOTIFY is not available"):
        await api.call_alexa_music(media_device, "jazz", "SPOTIFY")

    send_message.assert_not_awaited()


@pytest.mark.anyio
async def test_api_music_providers_returns_handler_providers(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """The API exposes the music providers fetched by the media handler."""
    mock_json_response({ARRAY_WRAPPER: [_music_provider(TEST_PROVIDER_ID)]})

    assert list(await api.music_providers) == [TEST_PROVIDER_ID]
