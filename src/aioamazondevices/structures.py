"""aioamazondevices structures module."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


@dataclass
class AmazonCredentials:
    """Amazon credentials class."""

    site: str
    login: str
    password: str


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
    software_version: str
    entity_id: str | None
    endpoint_id: str | None
    sensors: dict[str, AmazonDeviceSensor]
    notifications_supported: bool
    notifications: dict[str, AmazonSchedule]


class AmazonSequenceType(StrEnum):
    """Amazon sequence types."""

    Announcement = "AlexaAnnouncement"
    Speak = "Alexa.Speak"
    Sound = "Alexa.Sound"
    Music = "Alexa.Music.PlaySearchPhrase"
    TextCommand = "Alexa.TextCommand"
    LaunchSkill = "Alexa.Operation.SkillConnections.Launch"


class AmazonMusicSource(StrEnum):
    """Amazon music sources."""

    Radio = "TUNEIN"
    AmazonMusic = "AMAZON_MUSIC"
