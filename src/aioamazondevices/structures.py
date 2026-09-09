# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Structures module for Amazon devices."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from os import PathLike
from typing import Any


@dataclass
class AmazonSaveDataConfig:
    """Configuration for saving raw HTTP responses to disk (debug only)."""

    path: PathLike[str]
    callback: (
        Callable[[PathLike[str], str, str, str], Coroutine[Any, Any, None]] | None
    ) = None


@dataclass
class AmazonDeviceSensor:
    """Amazon device sensor class."""

    name: str
    value: str | int | float
    error: bool
    error_type: str | None
    error_msg: str | None
    scale: str | None


@dataclass
class AmazonDeviceLight:
    """Amazon smart light state (e.g. Echo Glow).

    Colour is reported as HSB: ``hue`` in degrees (0-360), ``saturation``
    and the colour's own ``brightness`` as fractions (0-1). ``brightness``
    is the light's overall level as a percentage (0-100).
    """

    power: bool
    brightness: int | None
    hue: float | None
    saturation: float | None
    color_name: str | None
    effect: str | None
    effects: list[str]
    supports_brightness: bool
    supports_color: bool
    supports_effects: bool
    supports_tap: bool
    tap_enabled: bool | None


@dataclass
class AmazonMusicProvider:
    """Music provider class."""

    provider_id: str
    provider_name: str
    availability: str
    default_provider: bool


@dataclass
class AmazonSchedule:
    """Amazon schedule class."""

    type: str  # alarm, reminder, timer
    status: str
    label: str
    next_occurrence: datetime | None


@dataclass
class AmazonDevice:
    """Amazon device class."""

    account_name: str
    capabilities: list[str]
    device_family: str
    device_type: str
    device_owner_customer_id: str
    household_device: bool
    device_cluster_members: dict[str, str | None]
    online: bool
    serial_number: str
    manufacturer: str | None
    model: str | None
    software_version: str | None
    hardware_version: str | None
    entity_id: str | None
    endpoint_id: str | None
    sensors: dict[str, AmazonDeviceSensor]
    notifications_supported: bool
    notifications: dict[str, AmazonSchedule]
    media_player_supported: bool
    communication_settings: dict[str, str]
    light: AmazonDeviceLight | None


def build_endpoint_device(  # noqa: PLR0913 - a device just has many fields
    *,
    account_name: str,
    device_family: str,
    device_type: str,
    serial_number: str,
    customer_id: str | None,
    online: bool,
    manufacturer: str | None = None,
    model: str | None = None,
    software_version: str | None = None,
    entity_id: str | None = None,
    endpoint_id: str | None = None,
    light: AmazonDeviceLight | None = None,
) -> AmazonDevice:
    """Build an AmazonDevice for a GraphQL-discovered endpoint.

    Air quality monitors and smart home lights are not returned by
    ``api/devices-v2/device``, so the voice-device fields are left empty.
    """
    return AmazonDevice(
        account_name=account_name,
        capabilities=[],
        device_family=device_family,
        device_type=device_type,
        device_owner_customer_id=customer_id or "n/a",
        household_device=False,
        device_cluster_members={serial_number: device_type},
        online=online,
        serial_number=serial_number,
        software_version=software_version,
        manufacturer=manufacturer,
        model=model,
        hardware_version=None,
        entity_id=entity_id,
        endpoint_id=endpoint_id,
        sensors={},
        notifications_supported=False,
        notifications={},
        media_player_supported=False,
        communication_settings={},
        light=light,
    )


class AmazonSequenceType(StrEnum):
    """Amazon sequence types."""

    Announcement = "AlexaAnnouncement"
    Speak = "Alexa.Speak"
    Sound = "Alexa.Sound"
    Music = "Alexa.Music.PlaySearchPhrase"
    TextCommand = "Alexa.TextCommand"
    LaunchSkill = "Alexa.Operation.SkillConnections.Launch"
    Volume = "Alexa.DeviceControls.Volume"
    Stop = "Alexa.DeviceControls.Stop"
    Routines = "Pseudo.Type.Routines"


class AmazonMediaControls(StrEnum):
    """Amazon media controls."""

    Play = "PlayCommand"
    Stop = "StopSequence"
    Pause = "PauseCommand"
    Next = "NextCommand"
    Previous = "PreviousCommand"
    Rewind = "RewindCommand"
    FastForward = "ForwardCommand"


@dataclass
class AmazonMediaState:
    """Amazon media state class."""

    player_state: str | None
    now_playing_url: str | None
    now_playing_title: str | None
    now_playing_line1: str | None
    now_playing_line2: str | None
    next_enabled: bool
    previous_enabled: bool
    pause_enabled: bool
    seek_forward_enabled: bool
    seek_back_enabled: bool
    shuffle_enabled: bool
    repeat_enabled: bool
    media_length: int | None
    media_position: int | None
    media_position_updated_at: datetime | None
    media_provider: str | None
    media_provider_url: str | None


@dataclass
class AmazonVolumeState:
    """Amazon volume state."""

    volume: int | None
    is_muted: bool | None


class AmazonPushMessage(StrEnum):
    """Amazon push message types."""

    # Generic
    GenericActivity = "PUSH_ACTIVITY"
    ConnectionStatus = "PUSH_DOPPLER_CONNECTION_CHANGE"
    BluetoothStatus = "PUSH_BLUETOOTH_STATE_CHANGE"
    MicrophoneStatus = "PUSH_MICROPHONE_STATE"

    # Notifications
    NotificationChange = "PUSH_NOTIFICATION_CHANGE"

    # Media
    AudioPlayerState = "PUSH_AUDIO_PLAYER_STATE"
    EqualizerStateChange = "PUSH_EQUALIZER_STATE_CHANGE"
    MediaQueueChange = "PUSH_MEDIA_QUEUE_CHANGE"
    MediaChange = "PUSH_MEDIA_CHANGE"
    MediaProgressChange = "PUSH_MEDIA_PROGRESS_CHANGE"
    VolumeChange = "PUSH_VOLUME_CHANGE"

    MediaSessionsUpdated = "NotifyMediaSessionsUpdated"
    NowPlayingUpdated = "NotifyNowPlayingUpdated"

    # Lists
    ItemChange = "PUSH_LIST_ITEM_CHANGE"

    # Matter
    MatterDeviceFound = "MATTER_SETUP_NOTIFICATION"


@dataclass
class AmazonSequenceNode:
    """Amazon sequence node used in routines."""

    message_type: str
    message_body: str | float | None
    music_provider_id: str | None
    device: AmazonDevice
    operation_node: dict[str, Any]


@dataclass
class AmazonVocalRecord:
    """Amazon vocal record."""

    timestamp: int
    history_type: str
    intent: str
    title: str
    sub_title: str


class AmazonListType(StrEnum):
    """Amazon list types."""

    SHOP = "SHOP"
    TODO = "TODO"
    CUSTOM = "CUSTOM"


@dataclass
class AmazonListInfo:
    """Amazon list info."""

    id: str
    list_type: AmazonListType
    name: str | None


class AmazonListItemStatus(StrEnum):
    """Amazon list item statuses."""

    ACTIVE = "ACTIVE"
    COMPLETE = "COMPLETE"


@dataclass
class AmazonListItem:
    """Amazon list item."""

    id: str
    status: AmazonListItemStatus
    name: str
    version: int


class AmazonListEventType(StrEnum):
    """Amazon list event types."""

    DELETED = "itemDeleted"
    UPDATED = "itemUpdated"
    CREATED = "itemCreated"


@dataclass
class AmazonListEvent:
    """Amazon list event."""

    list_id: str
    item_id: str
    type: AmazonListEventType
    items: AmazonListItem | None = None


class AmazonDropInStatus(StrEnum):
    """Amazon drop-in status types."""

    ALL = "All"
    HOME = "Home"
    OFF = "Off"
