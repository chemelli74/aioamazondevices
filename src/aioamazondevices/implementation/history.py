# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Module to handle Alexa vocal history setting."""

from datetime import UTC, datetime, timedelta
from http import HTTPMethod
from typing import Any

from bs4 import Tag
from yarl import URL

from aioamazondevices.const.history import (
    EXCLUDED_VOICE_HISTORY_TYPES,
    HISTORY_LOOKBACK_MS,
    HISTORY_MAX_RECORD_SIZE,
    HISTORY_STARTUP_LOOKBACK_MS,
    RECORD_KEY_SERIAL_INDEX,
    WAKE_WORD_PREFIX,
)
from aioamazondevices.const.http import (
    CSRF_A2Z,
    REFRESH_ACCESS_TOKEN,
    URI_HISTORY_DATA,
    URI_HISTORY_FRONTEND,
    URI_VOICE_HISTORY_DATA,
)
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonVocalRecord
from aioamazondevices.utils import _LOGGER


class AmazonHistoryHandler:
    """Class to handle Alexa vocal history functionality."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize AmazonHistoryHandler class."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper
        self._csrf_a2z_token: str = ""
        # force initial refresh
        self._csrf_a2z_refresh_time = datetime.now(UTC) - timedelta(days=2)

    async def get_vocal_history(self) -> dict[str, AmazonVocalRecord]:
        """Fetch recent RVH command or reply records after an EQ push."""
        await self._update_vocal_history_token()
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
                CSRF_A2Z: self._csrf_a2z_token,
                "Referer": str(
                    URL.joinpath(
                        self._session_state_data.retail_site_url,
                        URI_HISTORY_FRONTEND,
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
            self._session_state_data.retail_site_url, URI_HISTORY_DATA
        ).with_query({"startTime": start_ms, "endTime": end_ms})
        _, response = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=url,
            input_data={"previousRequestToken": previous_request_token},
            json_data=True,
            extended_headers={
                "Authorization": f"Bearer {access_token}",
                CSRF_A2Z: self._csrf_a2z_token,
            },
        )
        return await self._http_wrapper.response_to_json(response, "history")

    @classmethod
    def _parse_voice_history(cls, data: dict[str, Any]) -> dict[str, AmazonVocalRecord]:
        """Select the latest usable record per device."""
        latest: dict[str, AmazonVocalRecord] = {}
        raw_records = data.get("customerHistoryRecords")
        if not isinstance(raw_records, list):
            return latest
        for raw in raw_records:
            if not isinstance(raw, dict):
                continue
            serial = cls._record_serial(raw)
            record = cls._parse_record(raw)
            if (
                serial
                and record
                and (
                    serial not in latest or record.timestamp > latest[serial].timestamp
                )
            ):
                latest[serial] = record
        return latest

    @staticmethod
    def _record_serial(raw: dict[str, Any]) -> str | None:
        """Resolve the originating device from RAH or RVH metadata."""
        device_info = raw.get("deviceInfo")
        if isinstance(device_info, list):
            device_info = device_info[0] if device_info else None
        serial = (
            device_info.get("deviceSerialNumber")
            if isinstance(device_info, dict)
            else None
        )
        if not serial:
            record_key = raw.get("recordKey") or raw.get("activityKey")
            parts = record_key.split("#") if isinstance(record_key, str) else []
            if len(parts) > RECORD_KEY_SERIAL_INDEX:
                serial = parts[RECORD_KEY_SERIAL_INDEX]
        return serial if isinstance(serial, str) and serial else None

    @staticmethod
    def _record_text(raw: dict[str, Any]) -> tuple[str, str]:
        """Extract command and reply transcripts, falling back to RAH titles."""
        commands: list[str] = []
        replies: list[str] = []
        items = raw.get("voiceHistoryRecordItems") or []
        if not isinstance(items, list):
            return "", ""
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
        if not commands and isinstance(title := raw.get("title"), str):
            commands.append(title.strip())
        if not replies and isinstance(sub_title := raw.get("subTitle"), str):
            replies.append(sub_title.strip())
        return ", ".join(commands), ", ".join(replies)

    @classmethod
    def _parse_record(cls, raw: dict[str, Any]) -> AmazonVocalRecord | None:
        """Parse a command or reply while retaining Amazon's timestamp."""
        try:
            timestamp = int(raw.get("timestamp") or 0)
        except (TypeError, ValueError):
            return None
        if timestamp <= 0:
            return None
        title, sub_title = cls._record_text(raw)
        if not title and not sub_title:
            return None
        utterance_type = raw.get("utteranceType") or raw.get("recordType") or "Unknown"
        if not isinstance(utterance_type, str):
            utterance_type = str(utterance_type)
        if not sub_title and (
            utterance_type in EXCLUDED_VOICE_HISTORY_TYPES
            or utterance_type.startswith("FALSE_WAKE_WORD")
        ):
            return None
        person_info = raw.get("personsInfo")
        if isinstance(person_info, list):
            person_info = person_info[0] if person_info else None
        if not isinstance(person_info, dict):
            person_info = {}
        return AmazonVocalRecord(
            timestamp=timestamp,
            history_type=utterance_type,
            intent=raw.get("intent") or raw.get("domain") or "Unknown",
            title=title,
            sub_title=sub_title,
            person_first_name=person_info.get("personFirstName"),
            person_type=person_info.get("personType"),
        )

    async def get_startup_vocal_history(
        self, target_serials: set[str]
    ) -> dict[str, AmazonVocalRecord]:
        """Load the latest command or reply per device as a startup baseline."""
        if not target_serials:
            return {}
        await self._update_vocal_history_token()
        refreshed, _ = await self._http_wrapper.refresh_data(REFRESH_ACCESS_TOKEN)
        if not refreshed:
            _LOGGER.warning("Access token refresh failed before history sync")
        access_token = self._session_state_data.login_stored_data[REFRESH_ACCESS_TOKEN]
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        start_ms = now_ms - HISTORY_STARTUP_LOOKBACK_MS
        end_ms = now_ms
        latest: dict[str, AmazonVocalRecord] = {}

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

            # Token pages can repeat boundary records or include records
            # just outside the requested window.
            records = [
                raw
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
            pages,
            len(latest),
            len(target_serials),
        )

        return latest

    async def _update_vocal_history_token(self) -> None:
        """Find anti-csrftoken-a2z token."""
        csrf_token_age = datetime.now(UTC) - self._csrf_a2z_refresh_time
        if csrf_token_age < timedelta(hours=12):
            return

        bs_resp, _ = await self._http_wrapper.session_request(
            method=HTTPMethod.GET,
            url=URL.joinpath(
                self._session_state_data.retail_site_url, URI_HISTORY_FRONTEND
            ),
        )
        token_meta = bs_resp.find("meta", attrs={"name": "csrf-token"})
        if isinstance(token_meta, Tag):
            token = token_meta.get("content")
            if token:
                self._csrf_a2z_token = str(token)
                self._csrf_a2z_refresh_time = datetime.now(UTC)
                return
        raise CannotRetrieveData("Cannot find anti-csrftoken-a2z token")
