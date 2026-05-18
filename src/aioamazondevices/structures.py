"""Structures module for Amazon devices."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


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
    utterance_type: str
    intent: str
    title: str
    sub_title: str


class ListType(StrEnum):
    """Amazon list types."""

    SHOP = "SHOP"
    TODO = "TODO"
    CUSTOM = "CUSTOM"


@dataclass
class ListInfo:
    """Amazon list info."""

    id: str
    list_type: ListType
    custom_list_name: str | None

    @property
    def name(self) -> str:
        """Get the name of the list.

        If the list type is custom, return the custom list name.
        Otherwise, return the capitalized value of the list type.

        Returns:
            The name of the list.

        """
        if self.list_type == ListType.CUSTOM and self.custom_list_name is not None:
            return self.custom_list_name
        return self.list_type.value.capitalize()


class ListItemStatus(StrEnum):
    """Amazon list item statuses."""

    ACTIVE = "ACTIVE"
    COMPLETE = "COMPLETE"


@dataclass
class ListItem:
    """Amazon list item."""

    id: str
    status: ListItemStatus
    original_name: str
    version: int

    @property
    def name(self) -> str:
        """Get the name of the list item with the first letter capitalized.

        Returns:
            Name of the list item with the first letter capitalized.

        """
        return self.original_name.capitalize()

    @property
    def is_complete(self) -> bool:
        """Check if the list item is marked as complete.

        Returns:
            True if the list item is marked as complete, otherwise False.

        """
        return self.status == ListItemStatus.COMPLETE
