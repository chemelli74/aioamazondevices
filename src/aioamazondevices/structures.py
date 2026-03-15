"""aioamazondevices structures module."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


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


class AmazonMusicSource(StrEnum):
    """Amazon music sources."""

    Radio = "TUNEIN"
    AmazonMusic = "AMAZON_MUSIC"


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

    volume: int | None
    is_muted: bool
    player_state: str
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
