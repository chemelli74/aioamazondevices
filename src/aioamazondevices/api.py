# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Main module for Amazon devices."""

import asyncio
import re
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from http import HTTPMethod
from typing import Any, cast

import httpx
import orjson
from aiohttp import ClientSession
from aiosignal import Signal
from anyio import Path
from yarl import URL

from aioamazondevices.implementation.communication import AlexaCommunicationsHandler
from aioamazondevices.implementation.device import AmazonDeviceHandler
from aioamazondevices.implementation.media import AmazonMediaHandler
from aioamazondevices.implementation.sensor import AmazonSensorHandler
from aioamazondevices.implementation.todo import AmazonToDoHandler

from . import __version__
from .const.http import (
    CSRF_A2Z,
    DEFAULT_SITE,
    REFRESH_ACCESS_TOKEN,
)
from .const.metadata import (
    ALEXA_INFO_SKILLS,
    VOLUME_MAX,
    VOLUME_MIN,
)
from .exceptions import NoOnlineDevicesError
from .http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from .implementation.dnd import AmazonDnDHandler
from .implementation.history import AmazonHistoryHandler
from .implementation.http2 import AmazonHTTP2Client
from .implementation.notification import AmazonNotificationHandler
from .implementation.sequence import AmazonSequenceHandler
from .login import AmazonLogin
from .structures import (
    AmazonDevice,
    AmazonDropInStatus,
    AmazonListEvent,
    AmazonListEventType,
    AmazonListInfo,
    AmazonListItem,
    AmazonMediaControls,
    AmazonMediaState,
    AmazonMusicProvider,
    AmazonPushMessage,
    AmazonSaveDataConfig,
    AmazonSequenceType,
    AmazonVocalRecord,
    AmazonVolumeState,
)
from .utils import _LOGGER, scrub_fields

SETTINGS_FILENAME = "settings.json"
SETTINGS_DEFAULT_DEVICE = "default_device"
# Allow the RVH voice record to appear after an EQ push, then retry at a
# measured pace if Amazon has not published it yet.
HISTORY_PROBE_DELAY_SECONDS = 3.5
HISTORY_RETRY_DELAY_SECONDS = 4
HISTORY_PROBE_ATTEMPTS = 4
HISTORY_STALE_FUDGE_MS = 10_000
HISTORY_LOOKBACK_MS = 15 * 60 * 1000
HISTORY_MAX_RECORD_SIZE = 20
HISTORY_STARTUP_LOOKBACK_MS = 7 * 24 * 60 * 60 * 1000
URI_VOICE_HISTORY_DATA = "alexa-privacy/apd/rvh/customer-history-records-v2"
URI_RAH_HISTORY_DATA = "alexa-privacy/apd/rah/alexa-history-records-v2"
EXCLUDED_VOICE_HISTORY_TYPES = {
    "ASR_TIMEOUT",
    "DEVICE_ARBITRATION",
    "NO_EXPRESSED_INTENT",
    "WAKE_WORD_ONLY",
}
WAKE_WORD_PREFIX = re.compile(
    r"^(?:alexa|amazon|computer|echo|ziggy)(?:[\s,.:!?]+)(.*)$",
    re.IGNORECASE,
)


class AmazonEchoApi:
    """Queries Amazon for Echo devices."""

    def __init__(
        self,
        client_session: ClientSession,
        login_email: str,
        login_password: str,
        *,
        save_data: AmazonSaveDataConfig,
        login_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the scanner."""
        _LOGGER.debug("Initialize library v%s", __version__)

        self._settings_file = Path(save_data.path, SETTINGS_FILENAME)
        self._default_device_serial: str = ""

        # Check if there is a previous login, otherwise use default (US)
        site = login_data.get("site", DEFAULT_SITE) if login_data else DEFAULT_SITE
        _LOGGER.debug("Using site: %s", site)

        self._session_state_data = AmazonSessionStateData(
            site, login_email, login_password, login_data
        )

        self._http_wrapper = AmazonHttpWrapper(
            client_session,
            self._session_state_data,
            save_data,
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

        self._todo_handler = AmazonToDoHandler(
            http_wrapper=self._http_wrapper,
            session_state_data=self._session_state_data,
        )

        self._communication_handler = AlexaCommunicationsHandler(
            http_wrapper=self._http_wrapper,
            session_state_data=self._session_state_data,
        )

        self._device_volumes_initialized: bool = False
        self._dnd_initialized: bool = False
        self._dnd_lock = asyncio.Lock()
        self._http2_client: AmazonHTTP2Client | None = None
        self._history_probe_tasks: dict[str, asyncio.Task[None]] = {}
        self._last_emitted_history: dict[str, int] = {}
        self._history_fetch_task: asyncio.Task[dict[str, AmazonVocalRecord]] | None = (
            None
        )

        # force initial refresh
        initial_time = datetime.now(UTC) - timedelta(days=2)
        self._last_daily_refresh: datetime = initial_time
        self._last_endpoint_refresh: datetime = initial_time

        self.on_media_state_event = Signal[dict[str, AmazonMediaState]](self)
        self.on_volume_state_event = Signal[dict[str, AmazonVolumeState]](self)
        self.on_history_event = Signal[dict[str, AmazonVocalRecord]](self)
        self.on_todo_event = Signal[AmazonListEvent](self)
        self.on_dnd_event = Signal[dict[str, bool]](self)

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
    def todo_lists(self) -> list[AmazonListInfo]:
        """Return ToDo lists."""
        return self._todo_handler.lists

    async def get_default_device(self) -> AmazonDevice:
        """Return default device."""
        return self._device_handler.devices[self._default_device_serial]

    async def set_default_device(self, device: AmazonDevice) -> None:
        """Set default device and persist its serial number."""
        self._default_device_serial = device.serial_number
        await self._save_settings(
            {SETTINGS_DEFAULT_DEVICE: self._default_device_serial}
        )

    async def _init_default_device(self) -> None:
        """Resolve default device serial from settings or the first online device."""
        if self._default_device_serial in self._device_handler.devices:
            return
        self._default_device_serial = ""

        settings = await self._load_settings()
        if (
            serial_number := settings.get(SETTINGS_DEFAULT_DEVICE)
        ) and serial_number in self._device_handler.devices:
            self._default_device_serial = serial_number
            return

        # Use first online device as default if no default device has been set yet
        for device in self._device_handler.devices.values():
            if device.online:
                self._default_device_serial = device.serial_number
                return

        raise NoOnlineDevicesError("No online devices found")

    async def _load_settings(self) -> dict[str, Any]:
        """Load persisted settings from disk."""
        if not await self._settings_file.exists():
            return {}

        try:
            settings = orjson.loads(await self._settings_file.read_bytes())
        except orjson.JSONDecodeError:
            _LOGGER.warning("Ignoring invalid settings file: %s", self._settings_file)
            return {}

        if not isinstance(settings, dict):
            _LOGGER.warning(
                "Ignoring non-object settings file: %s", self._settings_file
            )
            return {}

        return cast("dict[str, Any]", settings)

    async def _save_settings(self, settings: dict[str, Any]) -> None:
        """Persist settings to disk."""
        await self._settings_file.parent.mkdir(parents=True, exist_ok=True)
        await self._settings_file.write_bytes(orjson.dumps(settings))

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
            await self._todo_handler.update_lists()

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

        # Resolve the default device only once base and endpoint devices are
        # loaded: sensor-only devices (e.g. Amazon Air Quality Monitor) are
        # created by set_device_endpoints_data() and would otherwise be missed,
        # aborting the refresh with NoOnlineDevicesError.
        await self._init_default_device()

    async def get_devices_data(
        self,
    ) -> dict[str, AmazonDevice]:
        """Get Amazon devices data."""
        # Perform a refresh to ensure your data is as up-to-date as possible.
        await self._refresh_basic_data()

        notifications = await self._notification_handler.get_notifications()
        communications = (
            await self._communication_handler.get_communication_preferences(
                list(self._device_handler.devices.values())
            )
        )
        await self._sensor_handler.update_sensor_data(
            self._device_handler.devices,
            self._device_handler.endpoints,
            notifications,
            communications,
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
        tasks = list(self._history_probe_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._history_probe_tasks.clear()
        if self._history_fetch_task is not None:
            self._history_fetch_task.cancel()
            await asyncio.gather(self._history_fetch_task, return_exceptions=True)
            self._history_fetch_task = None
        if self._http2_client:
            await self._http2_client.stop_processing()
            self._http2_client = None

    async def _http2_push_event_handler(
        self, event_type: str, payload: dict[str, Any]
    ) -> None:
        _LOGGER.debug("Event - %s : Payload - %s", event_type, scrub_fields(payload))

        match event_type:
            case AmazonPushMessage.VolumeChange.value:
                await self._handle_volume_change_event(payload)
            case AmazonPushMessage.EqualizerStateChange.value:
                await self._handle_eq_event_as_history_proxy(payload)
            case AmazonPushMessage.AudioPlayerState.value:
                await self._handle_audio_player_state_event()
            case AmazonPushMessage.ItemChange.value:
                await self._handle_item_change_event(payload)
            case AmazonPushMessage.DoNotDisturbChange.value:
                await self._handle_dnd_event(payload)
            case _:
                _LOGGER.debug("Unhandled push event type: %s", event_type)

    async def _handle_volume_change_event(self, payload: dict[str, Any]) -> None:
        # Ensure initial full sync happens before applying incremental updates
        if not self._device_volumes_initialized:
            await self._media_handler.sync_device_volumes()
            self._device_volumes_initialized = True

        serial = payload.get("dopplerId", {}).get("deviceSerialNumber")
        if serial:
            volume = AmazonVolumeState(
                payload.get("volumeSetting"), payload.get("isMuted")
            )
            # check if device is part of a cluster
            self._media_handler.update_cached_device_volume(serial, volume)
            volume_device: AmazonDevice | None = self._device_handler.devices.get(
                serial, None
            )
            if volume_device:
                for parent_serial in volume_device.parent_clusters:
                    if parent_cluster := (
                        self._device_handler.devices.get(parent_serial, None)
                    ):
                        self._media_handler.update_cached_speaker_group_volume(
                            parent_serial,
                            list(parent_cluster.device_cluster_members),
                        )

        await self._emit_volume_state_event()

    async def _handle_eq_event_as_history_proxy(
        self, payload: dict[str, Any]
    ) -> None:
        if not self.on_history_event.frozen:
            _LOGGER.debug("No vocal history subscribers, skipping fetch")
            return
        serial = payload.get("dopplerId", {}).get("deviceSerialNumber")
        destination_user_id = payload.get("destinationUserId")

        if not serial:
            _LOGGER.debug("EQ history proxy: missing device serial, skipping")
            return

        _LOGGER.debug(
            "EQ history proxy: serial=%s user=%s",
            serial,
            destination_user_id,
        )

        # Several EQ pushes can belong to the same interaction. Keep the first
        # candidate and let the probe run independently of the HTTP2 reader.
        if (task := self._history_probe_tasks.get(serial)) and not task.done():
            return
        activity_timestamp_ms = int(datetime.now(UTC).timestamp() * 1000)
        self._history_probe_tasks[serial] = asyncio.create_task(
            self._probe_vocal_history(serial, activity_timestamp_ms)
        )

    async def _probe_vocal_history(
        self, serial: str, activity_timestamp_ms: int
    ) -> None:
        """Wait for a fresh history record for the Echo that sent the EQ push."""
        try:
            await asyncio.sleep(HISTORY_PROBE_DELAY_SECONDS)
            for attempt in range(1, HISTORY_PROBE_ATTEMPTS + 1):
                if not self.on_history_event.frozen:
                    return

                # All Echo candidates in this round can examine one response.
                vocal_history = await self._shared_vocal_history_fetch()
                record = vocal_history.get(serial)
                if (
                    record is not None
                    and record.timestamp
                    >= activity_timestamp_ms - HISTORY_STALE_FUDGE_MS
                    and record.timestamp > self._last_emitted_history.get(serial, 0)
                ):
                    self._last_emitted_history[serial] = record.timestamp
                    _LOGGER.debug(
                        "Emitting history for EQ serial=%s timestamp=%s type=%s",
                        serial,
                        record.timestamp,
                        record.history_type,
                    )
                    await self._emit_history_event({serial: record})
                    return

                _LOGGER.debug(
                    "No fresh completed history for EQ serial=%s (attempt %s/%s)",
                    serial,
                    attempt,
                    HISTORY_PROBE_ATTEMPTS,
                )
                if attempt < HISTORY_PROBE_ATTEMPTS:
                    await asyncio.sleep(HISTORY_RETRY_DELAY_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("History probe failed for EQ serial=%s", serial)
        finally:
            if self._history_probe_tasks.get(serial) is asyncio.current_task():
                self._history_probe_tasks.pop(serial, None)

    async def _shared_vocal_history_fetch(self) -> dict[str, AmazonVocalRecord]:
        """Share an in-flight history request among simultaneous Echo probes."""
        if self._history_fetch_task is None or self._history_fetch_task.done():
            self._history_fetch_task = asyncio.create_task(self._fetch_voice_history())
        return await asyncio.shield(self._history_fetch_task)

    async def _fetch_voice_history(self) -> dict[str, AmazonVocalRecord]:
        """Fetch recent RVH command or reply records after an EQ push."""
        await self._history_handler._update_vocal_history_token()
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        data = await self._request_voice_history(
            now_ms - HISTORY_LOOKBACK_MS, now_ms + HISTORY_LOOKBACK_MS
        )
        return self._parse_voice_history(data)

    async def _request_voice_history(
        self, start_ms: int, end_ms: int
    ) -> dict[str, Any]:
        """Request the newest RVH voice records in a time window."""
        url = URL.joinpath(
            self._session_state_data.retail_site_url, URI_VOICE_HISTORY_DATA
        ).with_query(
            {
                "startTime": start_ms,
                "endTime": end_ms,
                "recordType": "VOICE_HISTORY",
                "maxRecordSize": HISTORY_MAX_RECORD_SIZE,
            }
        )
        _, response = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=url,
            input_data={"previousRequestToken": None},
            json_data=True,
            extended_headers={
                CSRF_A2Z: self._history_handler._csrf_a2z_token,
                "Referer": str(
                    URL.joinpath(
                        self._session_state_data.retail_site_url,
                        "alexa-privacy/apd/rvh",
                    )
                ),
            },
        )
        return await self._http_wrapper.response_to_json(response, "voice history")

    async def _request_rah_history(
        self,
        start_ms: int,
        end_ms: int,
        access_token: str,
        previous_request_token: str | None,
    ) -> dict[str, Any]:
        """Request a page of voice history for the startup baseline."""
        url = URL.joinpath(
            self._session_state_data.retail_site_url, URI_RAH_HISTORY_DATA
        ).with_query({"startTime": start_ms, "endTime": end_ms})
        _, response = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=url,
            input_data={"previousRequestToken": previous_request_token},
            json_data=True,
            extended_headers={
                "Authorization": f"Bearer {access_token}",
                CSRF_A2Z: self._history_handler._csrf_a2z_token,
            },
        )
        return await self._http_wrapper.response_to_json(response, "history")

    @staticmethod
    def _parse_voice_history(data: dict[str, Any]) -> dict[str, AmazonVocalRecord]:
        """Convert history with a command or reply into Alexa Devices events."""
        latest: dict[str, AmazonVocalRecord] = {}
        raw_records = data.get("customerHistoryRecords")
        if not isinstance(raw_records, list):
            return latest

        for raw in raw_records:
            if not isinstance(raw, dict):
                continue
            record_key = raw.get("recordKey")
            parts = record_key.split("#") if isinstance(record_key, str) else []
            if len(parts) < 4 or not (serial := parts[3]):
                continue
            utterance_type = raw.get("utteranceType")
            try:
                timestamp = int(raw.get("timestamp") or 0)
            except (TypeError, ValueError):
                continue
            if timestamp <= 0:
                continue

            items = raw.get("voiceHistoryRecordItems") or []
            if not isinstance(items, list):
                continue
            commands: list[str] = []
            replies: list[str] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                kind = item.get("recordItemType")
                spoken = item.get("transcriptText")
                if not isinstance(spoken, str) or not (spoken := spoken.strip()):
                    continue
                if kind in {"CUSTOMER_TRANSCRIPT", "ASR_REPLACEMENT_TEXT"}:
                    if match := WAKE_WORD_PREFIX.match(spoken):
                        spoken = match.group(1).strip()
                    if spoken:
                        commands.append(spoken)
                elif kind in {"ALEXA_RESPONSE", "TTS_REPLACEMENT_TEXT"}:
                    replies.append(spoken)
            if not commands and isinstance(raw.get("title"), str):
                title = raw["title"].strip()
                if title:
                    commands.append(title)
            if not replies and isinstance(raw.get("subTitle"), str):
                sub_title = raw["subTitle"].strip()
                if sub_title:
                    replies.append(sub_title)
            if not commands and not replies:
                continue
            if not replies and (
                utterance_type in EXCLUDED_VOICE_HISTORY_TYPES
                or isinstance(utterance_type, str)
                and utterance_type.startswith("FALSE_WAKE_WORD")
            ):
                continue

            person_info = raw.get("personsInfo")
            if isinstance(person_info, list):
                person_info = person_info[0] if person_info else None
            if not isinstance(person_info, dict):
                person_info = {}
            record = AmazonVocalRecord(
                timestamp=timestamp,
                history_type=utterance_type or "VOICE_HISTORY",
                intent=raw.get("intent") or raw.get("domain") or "Unknown",
                title=", ".join(commands),
                sub_title=", ".join(replies),
                person_first_name=person_info.get("personFirstName"),
                person_type=person_info.get("personType"),
            )
            if serial not in latest or timestamp > latest[serial].timestamp:
                latest[serial] = record

        return latest

    async def _handle_audio_player_state_event(self) -> None:
        if not self._device_handler.devices:
            _LOGGER.debug(
                "Skipping media state sync for push event because devices "
                "have not been loaded yet"
            )
            return

        await self._media_handler.sync_media_state(self._device_handler.devices)
        await self._emit_media_state_event()

    async def _handle_item_change_event(self, payload: dict[str, Any]) -> None:
        list_id = payload.get("listId")
        item_id = payload.get("listItemId")
        event_name = payload.get("eventName")

        if list_id is None or item_id is None or event_name is None:
            _LOGGER.warning("Received malformed ItemChange payload: %s", payload)
            return

        _LOGGER.debug("Received ItemChange for %s: %s", list_id, event_name)

        if event_name not in AmazonListEventType:
            _LOGGER.warning("Received unsupported list event type: %s", event_name)
            return

        list_event_type = AmazonListEventType(event_name)

        items = None
        if list_event_type != AmazonListEventType.DELETED:
            list_items = await self.get_todo_list_items(list_id)
            items = list_items[item_id]

        list_event = AmazonListEvent(list_id, item_id, list_event_type, items=items)

        await self._emit_todo_event(list_event)

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
            self._device_handler.devices[self._default_device_serial],
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
        await self._media_handler.send_media_command(device, command)

    async def set_do_not_disturb(self, device: AmazonDevice, enable: bool) -> None:
        """Set Do Not Disturb status for a device."""
        await self._dnd_handler.set_do_not_disturb(device, enable)

    async def set_communication_status(
        self, device: AmazonDevice, enable: bool
    ) -> None:
        """Set communication enabled status for a device."""
        await self._communication_handler.set_communication_status(device, enable)

    async def set_dropin_status(
        self, device: AmazonDevice, dropin: AmazonDropInStatus
    ) -> None:
        """Set communication drop-in enabled status for a device."""
        await self._communication_handler.set_dropin_status(device, dropin)

    async def set_announcement_status(self, device: AmazonDevice, enable: bool) -> None:
        """Set announcements enabled status for a device."""
        await self._communication_handler.set_announcement_status(device, enable)

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

    async def _emit_todo_event(self, list_event: AmazonListEvent) -> None:
        """Emit todo event to subscribers."""
        if self.on_todo_event.frozen:
            _LOGGER.debug("Emitting todo event: %s", list_event)
            await self.on_todo_event.send(list_event)

    async def sync_history_state(self) -> dict[str, AmazonVocalRecord]:
        """Load the latest command or reply per device as a startup baseline."""
        await self._history_handler._update_vocal_history_token()
        refreshed, _ = await self._http_wrapper.refresh_data(REFRESH_ACCESS_TOKEN)
        if not refreshed:
            _LOGGER.warning("Access token refresh failed before history sync")
        access_token = self._session_state_data.login_stored_data[REFRESH_ACCESS_TOKEN]
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        start_ms = now_ms - HISTORY_STARTUP_LOOKBACK_MS
        end_ms = now_ms
        latest: dict[str, AmazonVocalRecord] = {}
        target_serials = {
            serial
            for serial, device in self._device_handler.devices.items()
            if device.voice_control_supported
        }
        if not target_serials:
            return latest

        token: str | None = None
        seen_tokens: set[str] = set()
        pages = 0
        while True:
            data = await self._request_rah_history(
                start_ms, end_ms, access_token, token
            )
            pages += 1
            raw_records = data.get("alexaHistoryRecords")
            if not isinstance(raw_records, list):
                break

            # RAH's activityKey has the same serial-bearing format as RVH's
            # recordKey. Reuse the event parser while retaining Amazon's
            # original timestamp. The token page can repeat a boundary record
            # and even include a record just outside the requested window.
            records = [
                {**raw, "recordKey": raw.get("activityKey")}
                for raw in raw_records
                if isinstance(raw, dict)
                and isinstance(raw.get("timestamp"), (int, float))
                and start_ms <= raw["timestamp"] <= end_ms
            ]
            for serial, record in self._parse_voice_history(
                {"customerHistoryRecords": records}
            ).items():
                if serial in target_serials and (
                    serial not in latest or record.timestamp > latest[serial].timestamp
                ):
                    latest[serial] = record

            if target_serials <= latest.keys():
                break
            next_token = data.get("paginationToken")
            if not isinstance(next_token, str) or not next_token:
                break
            if next_token in seen_tokens:
                _LOGGER.warning("RAH history repeated pagination token; stopping")
                break
            seen_tokens.add(next_token)
            token = next_token

        _LOGGER.info(
            "Startup voice history: %s RAH pages, %s/%s devices with events",
            pages, len(latest), len(target_serials),
        )

        self._last_emitted_history.update(
            (serial, record.timestamp) for serial, record in latest.items()
        )
        return latest

    async def _emit_history_event(
        self, vocal_history: dict[str, AmazonVocalRecord]
    ) -> None:
        """Emit vocal history event to subscribers."""
        if self.on_history_event.frozen:
            _LOGGER.debug("Emitting vocal history event to subscribers")
            await self.on_history_event.send(vocal_history)

    async def set_todo_list_item_checked_status(
        self, list_id: str, item_id: str, checked: bool, version: int
    ) -> None:
        """Set ToDo list item checked status."""
        await self._todo_handler.set_item_checked_status(
            list_id, item_id, checked, version
        )

    async def add_todo_list_item(self, list_id: str, item_name: str) -> None:
        """Add item to a ToDo list."""
        await self._todo_handler.add_item(list_id, item_name)

    async def delete_todo_list_item(
        self, list_id: str, item_id: str, version: int
    ) -> None:
        """Delete item from a ToDo list."""
        await self._todo_handler.delete_item(list_id, item_id, version)

    async def rename_todo_list_item(
        self, list_id: str, item_id: str, new_name: str, version: int
    ) -> None:
        """Rename ToDo list item."""
        await self._todo_handler.rename_item(list_id, item_id, new_name, version)

    async def get_todo_list_items(self, list_id: str) -> dict[str, AmazonListItem]:
        """Return ToDo all list items."""
        items = await self._todo_handler.get_list_items(list_id)

        return {item.id: item for item in items}

    async def restart_device(self, device: AmazonDevice) -> None:
        """Restart a device."""
        await self._device_handler.restart_device(device)

    async def sync_dnd_state(self) -> None:
        """Sync Do Not Disturb state for all devices."""
        async with self._dnd_lock:
            await self._dnd_handler.sync_do_not_disturb_status()
            self._dnd_initialized = True

        await self._emit_dnd_state_event()

    async def _handle_dnd_event(self, payload: dict[str, Any]) -> None:
        serial = payload.get("dopplerId", {}).get("deviceSerialNumber")
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            _LOGGER.warning(
                "Received DND event with no 'enabled' field: %s", scrub_fields(payload)
            )
            return
        if not serial:
            return

        # The lock serializes the full sync with incremental updates, so that a
        # sync response predating this event cannot overwrite it.
        async with self._dnd_lock:
            # Ensure initial full sync happens before applying incremental updates
            if not self._dnd_initialized:
                await self._dnd_handler.sync_do_not_disturb_status()
                self._dnd_initialized = True

            self._dnd_handler.update_cached_dnd_state(serial, enabled)

        await self._emit_dnd_state_event()

    async def _emit_dnd_state_event(self) -> None:
        """Emit dnd event to subscribers."""
        if self.on_dnd_event.frozen:
            _LOGGER.debug("Emitting dnd state event to subscribers")
            await self.on_dnd_event.send(self._dnd_handler.dnd_states)
