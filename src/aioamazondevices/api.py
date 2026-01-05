"""Support for Amazon devices."""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import ClientSession

from aioamazondevices.implementation.device import AmazonDeviceHandler
from aioamazondevices.implementation.sensors import AmazonSensorHandler

from . import __version__
from .const.devices import (
    DEVICE_TYPE_TO_MODEL,
)
from .const.http import (
    DEFAULT_SITE,
)
from .http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from .implementation.dnd import AmazonDnDHandler
from .implementation.notification import AmazonNotificationHandler
from .implementation.sequence import AmazonSequenceHandler
from .login import AmazonLogin
from .structures import (
    AmazonDevice,
    AmazonMusicSource,
    AmazonSequenceType,
)
from .utils import _LOGGER


class AmazonEchoApi:
    """Queries Amazon for Echo devices."""

    def __init__(
        self,
        client_session: ClientSession,
        login_email: str,
        login_password: str,
        login_data: dict[str, Any] | None = None,
        save_to_file: Callable[[str | dict, str, str], Coroutine[Any, Any, None]]
        | None = None,
    ) -> None:
        """Initialize the scanner."""
        _LOGGER.debug("Initialize library v%s", __version__)

        # Check if there is a previous login, otherwise use default (US)
        site = login_data.get("site", DEFAULT_SITE) if login_data else DEFAULT_SITE
        _LOGGER.debug("Using site: %s", site)

        self._session_state_data = AmazonSessionStateData(
            site, login_email, login_password, login_data
        )

        self._http_wrapper = AmazonHttpWrapper(
            client_session,
            self._session_state_data,
            save_to_file,
        )

        self._login = AmazonLogin(
            http_wrapper=self._http_wrapper,
            session_state_data=self._session_state_data,
        )

        self._device_handler = AmazonDeviceHandler(
            session_state_data=self._session_state_data,
            http_wrapper=self._http_wrapper,
        )

        self._sensor_handler = AmazonSensorHandler(
            session_state_data=self._session_state_data,
            http_wrapper=self._http_wrapper,
        )

        self._notification_handler = AmazonNotificationHandler(
            http_wrapper=self._http_wrapper,
            session_state_data=self._session_state_data,
        )

        self._sequence_handler = AmazonSequenceHandler(
            http_wrapper=self._http_wrapper,
            session_state_data=self._session_state_data,
        )

        self._dnd_handler = AmazonDnDHandler(
            http_wrapper=self._http_wrapper, session_state_data=self._session_state_data
        )

        initial_time = datetime.now(UTC) - timedelta(days=2)  # force initial refresh
        self._last_devices_refresh: datetime = initial_time
        self._last_endpoint_refresh: datetime = initial_time

    @property
    def domain(self) -> str:
        """Return current Amazon domain."""
        return self._session_state_data.domain

    @property
    def login(self) -> AmazonLogin:
        """Return login."""
        return self._login

    async def get_devices_data(
        self,
    ) -> dict[str, AmazonDevice]:
        """Get Amazon devices data."""
        delta_devices = datetime.now(UTC) - self._last_devices_refresh
        if delta_devices >= timedelta(days=1):
            _LOGGER.debug(
                "Refreshing devices data after %s",
                str(timedelta(minutes=round(delta_devices.total_seconds() / 60))),
            )
            # Request base device data
            await self._device_handler.build_device_list()
            self._last_devices_refresh = datetime.now(UTC)

        # Only refresh endpoint data if we have no endpoints yet
        delta_endpoints = datetime.now(UTC) - self._last_endpoint_refresh
        endpoint_refresh_needed = delta_endpoints >= timedelta(days=1)
        endpoints_recently_checked = delta_endpoints < timedelta(minutes=30)
        if (
            not self._device_handler.endpoints and not endpoints_recently_checked
        ) or endpoint_refresh_needed:
            _LOGGER.debug(
                "Refreshing endpoint data after %s",
                str(timedelta(minutes=round(delta_endpoints.total_seconds() / 60))),
            )
            # Set device endpoint data
            await self._device_handler.enrich_with_endpoint_ids()
            self._last_endpoint_refresh = datetime.now(UTC)

        dnd_sensors = await self._dnd_handler.get_do_not_disturb_status()
        notifications = await self._notification_handler.get_notifications()
        await self._sensor_handler.update_sensor_data(
            self._device_handler.devices,
            self._device_handler.endpoints,
            dnd_sensors,
            notifications,
        )

        return self._device_handler.devices

    def get_model_details(self, device: AmazonDevice) -> dict[str, str | None] | None:
        """Return model datails."""
        model_details: dict[str, str | None] | None = DEVICE_TYPE_TO_MODEL.get(
            device.device_type
        )
        if not model_details:
            _LOGGER.warning(
                "Unknown device type '%s' for %s: please read https://github.com/chemelli74/aioamazondevices/wiki/Unknown-Device-Types",
                device.device_type,
                device.account_name,
            )

        return model_details

    async def call_alexa_speak(
        self,
        device: AmazonDevice,
        text_to_speak: str,
    ) -> None:
        """Call Alexa.Speak to send a message."""
        await self._sequence_handler.send_message(
            device, AmazonSequenceType.Speak, text_to_speak
        )

    async def call_alexa_announcement(
        self,
        device: AmazonDevice,
        text_to_announce: str,
    ) -> None:
        """Call AlexaAnnouncement to send a message."""
        await self._sequence_handler.send_message(
            device, AmazonSequenceType.Announcement, text_to_announce
        )

    async def call_alexa_sound(
        self,
        device: AmazonDevice,
        sound_name: str,
    ) -> None:
        """Call Alexa.Sound to play sound."""
        await self._sequence_handler.send_message(
            device, AmazonSequenceType.Sound, sound_name
        )

    async def call_alexa_music(
        self,
        device: AmazonDevice,
        search_phrase: str,
        music_source: AmazonMusicSource,
    ) -> None:
        """Call Alexa.Music.PlaySearchPhrase to play music."""
        await self._sequence_handler.send_message(
            device, AmazonSequenceType.Music, search_phrase, music_source
        )

    async def call_alexa_text_command(
        self,
        device: AmazonDevice,
        text_command: str,
    ) -> None:
        """Call Alexa.TextCommand to issue command."""
        await self._sequence_handler.send_message(
            device, AmazonSequenceType.TextCommand, text_command
        )

    async def call_alexa_skill(
        self,
        device: AmazonDevice,
        skill_name: str,
    ) -> None:
        """Call Alexa.LaunchSkill to launch a skill."""
        await self._sequence_handler.send_message(
            device, AmazonSequenceType.LaunchSkill, skill_name
        )

    async def call_alexa_info_skill(
        self,
        device: AmazonDevice,
        info_skill_name: str,
    ) -> None:
        """Call Info skill.  See ALEXA_INFO_SKILLS . const."""
        await self._sequence_handler.send_message(device, info_skill_name, "")

    async def set_do_not_disturb(self, device: AmazonDevice, enable: bool) -> None:
        """Set Do Not Disturb status for a device."""
        await self._dnd_handler.set_do_not_disturb(device, enable)
