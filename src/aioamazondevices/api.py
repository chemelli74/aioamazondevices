"""Main module for Amazon devices."""

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from http import HTTPMethod
from typing import Any

import httpx
from aiohttp import ClientSession
from aiosignal import Signal

from aioamazondevices.implementation.device import AmazonDeviceHandler
from aioamazondevices.implementation.media import AmazonMediaHandler
from aioamazondevices.implementation.sensor import AmazonSensorHandler

from . import __version__
from .const.http import (
    DEFAULT_SITE,
    URI_MEDIA_CONTROL,
)
from .const.metadata import (
    ALEXA_INFO_SKILLS,
    VOLUME_MAX,
    VOLUME_MIN,
)
from .http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from .implementation.dnd import AmazonDnDHandler
from .implementation.history import AmazonHistoryHandler
from .implementation.http2 import AmazonHTTP2Client
from .implementation.notification import AmazonNotificationHandler
from .implementation.sequence import AmazonSequenceHandler
from .login import AmazonLogin
from .structures import (
    AmazonDevice,
    AmazonMediaControls,
    AmazonMediaState,
    AmazonMusicProvider,
    AmazonPushMessage,
    AmazonSequenceType,
    AmazonVocalRecord,
    AmazonVolumeState,
)
from .utils import _LOGGER, scrub_fields


class AmazonEchoApi:
    """Queries Amazon for Echo devices."""

    def __init__(
        self,
        client_session: ClientSession,
        login_email: str,
        login_password: str,
        login_data: dict[str, Any] | None = None,
        save_to_file: Callable[
            [str | dict[str, Any], str, str], Coroutine[Any, Any, None]
        ]
        | None = None,
    ) -> None:
        """Initialize the scanner."""
        _LOGGER.debug("Initialize library v%s", __version__)

        self._default_device: AmazonDevice | None = None

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
            http_wrapper=self._http_wrapper,
            session_state_data=self._session_state_data,
        )

        self._sensor_handler = AmazonSensorHandler(
            http_wrapper=self._http_wrapper,
            session_state_data=self._session_state_data,
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
            http_wrapper=self._http_wrapper,
            session_state_data=self._session_state_data,
        )

        self._media_handler = AmazonMediaHandler(
            http_wrapper=self._http_wrapper,
            session_state_data=self._session_state_data,
        )

        self._history_handler = AmazonHistoryHandler(
            http_wrapper=self._http_wrapper,
            session_state_data=self._session_state_data,
        )

        self._device_volumes_initialized: bool = False
        self._voice_history_initialized: bool = False
        self._http2_client: AmazonHTTP2Client | None = None

        initial_time = datetime.now(UTC) - timedelta(days=2)  # force initial refresh
        self._last_daily_refresh: datetime = initial_time
        self._last_endpoint_refresh: datetime = initial_time

        self.on_media_state_event = Signal[dict[str, AmazonMediaState]](self)
        self.on_volume_state_event = Signal[dict[str, AmazonVolumeState]](self)
        self.on_history_event = Signal[dict[str, AmazonVocalRecord]](self)

    @property
    def domain(self) -> str:
        """Return current Amazon domain."""
        return self._session_state_data.domain

    @property
    def login(self) -> AmazonLogin:
        """Return login."""
        return self._login

    @property
    def routines(self) -> list[str]:
        """Return routines."""
        return self._sequence_handler.routines

    @property
    def default_device(self) -> AmazonDevice:
        """Return default device."""
        if self._default_device:
            return self._default_device

        # Get first online device as default if no default device has been set yet
        for device in self._device_handler.devices.values():
            if device.online:
                return device

        raise ValueError("No online devices found")

    @default_device.setter
    def default_device(self, device: AmazonDevice) -> None:
        """Set default device."""
        self._default_device = device

    @property
    async def music_providers(self) -> dict[str, AmazonMusicProvider]:
        """Return music providers."""
        return await self._media_handler.music_providers

    async def _refresh_basic_data(self) -> None:
        """Refresh base data if interval has passed."""
        delta_daily = datetime.now(UTC) - self._last_daily_refresh
        if delta_daily >= timedelta(days=1):
            _LOGGER.debug(
                "Refreshing devices data after %s",
                str(timedelta(minutes=round(delta_daily.total_seconds() / 60))),
            )
            # Request various data that doesn't change that often
            await self._device_handler.get_base_devices()
            await self._media_handler.update_music_providers()
            await self._sequence_handler.update_routines()

            self._last_daily_refresh = datetime.now(UTC)

        # Only refresh endpoint data if we have no endpoints yet
        # or if it's been a while since the last refresh
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
            await self._device_handler.set_device_endpoints_data()
            self._last_endpoint_refresh = datetime.now(UTC)

    async def get_devices_data(
        self,
    ) -> dict[str, AmazonDevice]:
        """Get Amazon devices data."""
        # Perform a refresh to ensure your data is as up-to-date as possible.
        await self._refresh_basic_data()

        dnd_sensors = await self._dnd_handler.get_do_not_disturb_status()
        notifications = await self._notification_handler.get_notifications()
        await self._sensor_handler.update_sensor_data(
            self._device_handler.devices,
            self._device_handler.endpoints,
            dnd_sensors,
            notifications,
        )

        return self._device_handler.devices

    async def start_http2_processing(
        self,
        httpx_client: httpx.AsyncClient,
        on_reauth_required: Callable[[], Coroutine[Any, Any, None]] | None = None,
    ) -> asyncio.Task[None]:
        """Start HTTP2 background processing.

        returns as Task so callers can decide how to handle it.
        awaiting task will block until http2 processing is stopped or errors
        to capture errors without blocking, callers can add a done callback to the task.

        httpx client must have http2 enabled and a timeout of None to
        allow for long-lived connections.
        Caller is responsible for ensuring its properly configured and closed after use.
        """
        if not self._http2_client:
            self._http2_client = AmazonHTTP2Client(
                http_wrapper=self._http_wrapper,
                session_state_data=self._session_state_data,
                httpx_client=httpx_client,
                on_reauth_required=on_reauth_required,
            )
            self._http2_client.on_push_event.append(self._http2_push_event_handler)
            self._http2_client.on_push_event.freeze()

        return await self._http2_client.start_processing()

    async def stop_http2_processing(self) -> None:
        """Stop HTTP2 background processing."""
        if self._http2_client:
            await self._http2_client.stop_processing()
            self._http2_client = None

    async def _http2_push_event_handler(
        self, event_type: str, payload: dict[str, Any]
    ) -> None:
        _LOGGER.debug("Event - %s : Payload - %s", event_type, scrub_fields(payload))
        if event_type == AmazonPushMessage.VolumeChange.value:
            # Ensure initial full sync happens before applying incremental updates
            if not self._device_volumes_initialized:
                await self._media_handler.sync_device_volumes()
                self._device_volumes_initialized = True
            if not self._voice_history_initialized:
                await self._history_handler.get_vocal_history()
                self._voice_history_initialized = True
            serial = payload.get("dopplerId", {}).get("deviceSerialNumber")
            if serial:
                volume = AmazonVolumeState(
                    payload.get("volumeSetting"), payload.get("isMuted")
                )
                self._media_handler.update_cached_device_volume(serial, volume)
            await self._emit_volume_state_event()
            await self._emit_history_event()
            return
        if event_type == AmazonPushMessage.AudioPlayerState.value:
            if not self._device_handler.devices:
                _LOGGER.debug(
                    "Skipping media state sync for push event because devices "
                    "have not been loaded yet"
                )
                return
            await self._media_handler.sync_media_state(self._device_handler.devices)
            await self._emit_media_state_event()
            await self._emit_history_event()
            return

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
        await self._call_alexa_command_per_cluster_member(
            device, AmazonSequenceType.Sound, sound_name
        )

    async def call_alexa_music(
        self,
        device: AmazonDevice,
        search_phrase: str,
        provider_id: str,
    ) -> None:
        """Call Alexa.Music.PlaySearchPhrase to play music."""
        if not (await self._media_handler.music_providers).get(provider_id):
            raise ValueError(f"{provider_id} is not available as a music provider")

        await self._sequence_handler.send_message(
            device, AmazonSequenceType.Music, search_phrase, provider_id
        )

    async def call_alexa_text_command(
        self,
        device: AmazonDevice,
        text_command: str,
    ) -> None:
        """Call Alexa.TextCommand to issue command."""
        await self._call_alexa_command_per_cluster_member(
            device, AmazonSequenceType.TextCommand, text_command
        )

    async def call_alexa_skill(
        self,
        device: AmazonDevice,
        skill_name: str,
    ) -> None:
        """Call Alexa.LaunchSkill to launch a skill."""
        await self._call_alexa_command_per_cluster_member(
            device, AmazonSequenceType.LaunchSkill, skill_name
        )

    async def call_alexa_info_skill(
        self,
        device: AmazonDevice,
        info_skill: str,
    ) -> None:
        """Call Info skill."""
        if info_skill not in ALEXA_INFO_SKILLS:
            raise ValueError(f"Unsupported info skill: {info_skill}")
        await self._call_alexa_command_per_cluster_member(device, info_skill, "")

    async def call_routine(
        self,
        routine_name: str,
    ) -> None:
        """Call routine."""
        # Routines are not device specific
        # but a device is needed to call them anyway.
        await self._call_alexa_command_per_cluster_member(
            self.default_device,
            AmazonSequenceType.Routines,
            routine_name,
        )

    async def set_device_volume(self, device: AmazonDevice, volume: int) -> None:
        """Set device volume."""
        if not (VOLUME_MIN <= volume <= VOLUME_MAX):
            raise ValueError(f"Volume must be between {VOLUME_MIN} and {VOLUME_MAX}")
        await self._call_alexa_command_per_cluster_member(
            device, AmazonSequenceType.Volume, str(volume)
        )

    async def _call_alexa_command_per_cluster_member(
        self,
        device: AmazonDevice,
        message_type: str,
        message_body: str,
        music_provider_id: str | None = None,
    ) -> None:
        """Call Alexa command per cluster member."""
        for cluster_member in device.device_cluster_members:
            await self._sequence_handler.send_message(
                self._device_handler.devices[cluster_member],
                message_type,
                message_body,
                music_provider_id,
            )

    async def update_routines(self) -> None:
        """Update routines."""
        await self._sequence_handler.update_routines()

    async def send_media_command(
        self, device: AmazonDevice, command: AmazonMediaControls
    ) -> None:
        """Send media control command."""
        if command == AmazonMediaControls.Stop:
            await self._call_alexa_command_per_cluster_member(
                device, AmazonSequenceType.Stop, ""
            )
            return
        payload = {"type": command.value}
        query_string = (
            f"deviceSerialNumber={device.serial_number}&deviceType={device.device_type}"
        )
        await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_MEDIA_CONTROL}?{query_string}",
            input_data=payload,
            json_data=True,
        )

    async def set_do_not_disturb(self, device: AmazonDevice, enable: bool) -> None:
        """Set Do Not Disturb status for a device."""
        await self._dnd_handler.set_do_not_disturb(device, enable)

    async def sync_media_state(self) -> None:
        """Sync media state.

        This will be called at startup to sync media state of all devices
        and can be called later to refresh media state.
        """
        await self._media_handler.sync_device_volumes()
        self._device_volumes_initialized = True
        await self._emit_volume_state_event()
        await self._media_handler.sync_media_state(self._device_handler.devices)
        await self._emit_media_state_event()

    async def _emit_media_state_event(self) -> None:
        """Emit media state data to subscribers."""
        if self.on_media_state_event.frozen:
            _LOGGER.debug("Emitting media state event to subscribers")
            await self.on_media_state_event.send(await self._media_handler.media_states)

    async def _emit_volume_state_event(self) -> None:
        """Emit volume event to subscribers."""
        if self.on_volume_state_event.frozen:
            _LOGGER.debug("Emitting volume state event to subscribers")
            await self.on_volume_state_event.send(
                await self._media_handler.device_volumes
            )

    async def sync_history_state(self) -> dict[str, AmazonVocalRecord]:
        """Sync history state.

        This will be called at startup to sync history state of all devices
        and can be called later to refresh history state.
        """
        return await self._history_handler.get_vocal_history()

    async def _emit_history_event(self) -> None:
        """Emit vocal history event to subscribers."""
        if self.on_history_event.frozen:
            _LOGGER.debug("Emitting vocal history event to subscribers")
            await self.on_history_event.send(
                await self._history_handler.get_vocal_history()
            )
