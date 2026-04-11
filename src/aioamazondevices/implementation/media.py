"""Module to handle Alexa media."""

from datetime import UTC, datetime
from http import HTTPMethod
from typing import Any

from aioamazondevices.const.http import (
    URI_DEVICE_VOLUMES,
    URI_MEDIA_STATE,
)
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonMediaState,
    AmazonVolumeState,
)


class AmazonMediaHandler:
    """Class to handle Alexa media functionality."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize AmazonMediaHandler class."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper
        self._device_volumes: dict[str, AmazonVolumeState] = {}

    async def get_device_volumes(self) -> dict[str, AmazonVolumeState]:
        """Get all device volumes."""
        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.GET,
            url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_DEVICE_VOLUMES}",
        )

        json_data = await self._http_wrapper.response_to_json(
            raw_resp, "device volumes"
        )
        for device_volume_data in json_data.get("volumes", []):
            self._device_volumes[device_volume_data["dsn"]] = AmazonVolumeState(
                device_volume_data["speakerVolume"], device_volume_data["speakerMuted"]
            )

        return self._device_volumes

    async def set_device_volume(self, device: AmazonDevice, volume: int) -> None:
        """Set device volume."""
        if not self._device_volumes:
            await self.get_device_volumes()
        dev_volume = self._device_volumes.get(device.serial_number)
        if not dev_volume:
            raise ValueError(
                f"Device <{device.serial_number}> not found in device volumes"
            )
        diff = volume - (dev_volume.volume or 0)
        payload = {
            "dsn": device.serial_number,
            "deviceType": device.device_type,
            "amount": diff,
            "volume": volume,
            "muted": True,
            "synchronous": True,
        }
        await self._http_wrapper.session_request(
            method=HTTPMethod.PUT,
            url=f"https://alexa.amazon.{self._session_state_data.domain}/api/devices/{device.device_type}/{device.serial_number}/audio/v2/speakerVolume",
            input_data=payload,
            json_data=True,
        )

    async def _get_media_states(self, device: AmazonDevice) -> dict[str, Any]:
        """Get media state for devices.

        Whilst this takes a device as input it actually returns state for all devices.
        """
        query_string = (
            f"deviceSerialNumber={device.serial_number}&deviceType={device.device_type}"
        )
        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.GET,
            url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_MEDIA_STATE}?{query_string}",
        )

        json_data = await self._http_wrapper.response_to_json(raw_resp, "media state")

        media_sessions = {}
        for session in json_data.get("mediaSessionList") or []:
            for session_device in session.get("endpointList") or []:
                serial_num = session_device.get("id", {}).get("deviceSerialNumber")
                media_sessions[serial_num] = session

        return media_sessions

    async def sync_media_state(
        self, devices: dict[str, AmazonDevice]
    ) -> dict[str, AmazonMediaState]:
        """Return all media state."""
        media_states = {}
        # the endpoint needs a device type / serial but returns all sessions
        media_sessions = await self._get_media_states(next(iter(devices.values())))
        if not media_sessions:
            return {}

        for device in devices.values():
            if not device.media_player_supported:
                continue

            serial_number = device.serial_number
            now_playing = media_sessions.get(serial_number, {}).get(
                "nowPlayingData", {}
            )
            str_media_length = now_playing.get("progress", {}).get("mediaLength")
            str_media_progress = now_playing.get("progress", {}).get("mediaProgress")
            transport = now_playing.get("transport", {})
            provider = now_playing.get("provider", {})
            media_states[serial_number] = AmazonMediaState(
                player_state=now_playing.get("playerState"),
                now_playing_url=now_playing.get("mainArt", {}).get("largeUrl"),
                now_playing_title=now_playing.get("infoText", {}).get("title"),
                now_playing_line1=now_playing.get("infoText", {}).get("subText1"),
                now_playing_line2=now_playing.get("infoText", {}).get("subText2"),
                next_enabled=transport.get("next") == "ENABLED",
                previous_enabled=transport.get("previous") == "ENABLED",
                pause_enabled=transport.get("playPause") == "ENABLED",
                seek_forward_enabled=transport.get("seekForward") == "ENABLED",
                seek_back_enabled=transport.get("seekBack") == "ENABLED",
                shuffle_enabled=transport.get("shuffle") == "ENABLED",
                repeat_enabled=transport.get("repeat") == "ENABLED",
                media_length=(
                    int(str_media_length) // 1000
                    if str_media_length is not None
                    else None
                ),
                media_position=(
                    int(str_media_progress) // 1000
                    if str_media_progress is not None
                    else None
                ),
                media_position_updated_at=datetime.now(UTC),
                media_provider=provider.get("providerName"),
                media_provider_url=provider.get("providerLogo", {}).get("url"),
            )

        return media_states
