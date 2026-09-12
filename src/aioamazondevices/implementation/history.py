# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Module to handle Alexa vocal history setting."""

import asyncio
from datetime import UTC, datetime, timedelta
from http import HTTPMethod
from typing import Any

from bs4 import Tag
from yarl import URL

from aioamazondevices.const.http import (
    CSRF_A2Z,
    REFRESH_ACCESS_TOKEN,
    URI_HISTORY_DATA,
    URI_HISTORY_FRONTEND,
)
from aioamazondevices.const.metadata import UTTERANCE_TYPES_TO_SKIP
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import AmazonVocalRecord
from aioamazondevices.utils import _LOGGER

BACKEND_REFRESH_WAIT_SECONDS = 2

# Amazon formats activityKey as:
# <customerId>#<timestamp>#<deviceType>#<deviceSerialNumber>
ACTIVITY_KEY_PARTS = 4
ACTIVITY_KEY_SERIAL_INDEX = 3


def _serial_from_activity_key(activity_key: object) -> str | None:
    """Extract the device serial number from an activityKey."""
    if not isinstance(activity_key, str):
        return None

    parts = activity_key.split("#")
    if len(parts) != ACTIVITY_KEY_PARTS:
        return None

    return parts[ACTIVITY_KEY_SERIAL_INDEX] or None


def _serial_from_device_info(device_info: object) -> str | None:
    """Extract the device serial number from a record deviceInfo."""
    if isinstance(device_info, list):
        device_info = device_info[0] if device_info else None

    if not isinstance(device_info, dict):
        return None

    serial = device_info.get("deviceSerialNumber")
    return serial if isinstance(serial, str) and serial else None


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

    async def _vocal_history_json(self) -> dict[str, Any]:
        """Request vocal history data."""
        await self._update_vocal_history_token()

        refresh_successful, _ = await self._http_wrapper.refresh_data(
            REFRESH_ACCESS_TOKEN
        )
        if not refresh_successful:
            _LOGGER.warning("Access token refresh failed")

        access_token = self._session_state_data.login_stored_data[REFRESH_ACCESS_TOKEN]

        start_time = (
            datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
            - timedelta(days=7)
        ).timestamp() * 1000
        end_time = datetime.now(UTC).timestamp() * 1000
        query_string = {
            "startTime": int(start_time),
            "endTime": int(end_time),
        }
        url = URL.joinpath(self._session_state_data.retail_site_url, URI_HISTORY_DATA)
        url = url.with_query(query_string)
        _, raw_res = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=url,
            input_data={"previousRequestToken": None},
            json_data=True,
            extended_headers={
                "Authorization": f"Bearer {access_token}",
                CSRF_A2Z: self._csrf_a2z_token,
            },
        )
        history = await self._http_wrapper.response_to_json(raw_res, "history")
        _LOGGER.debug("Vocal history data: %s", history)
        return history

    async def get_vocal_history(
        self, known_serials: set[str] | None = None
    ) -> dict[str, AmazonVocalRecord]:
        """Get vocal history.

        When known_serials is provided, records whose serial number can only be
        recovered from the activityKey are kept only if that serial belongs to a
        known device.
        """
        # Give backend the time to update
        await asyncio.sleep(BACKEND_REFRESH_WAIT_SECONDS)

        history_json = await self._vocal_history_json()

        records: dict[str, AmazonVocalRecord] = {}
        for record in history_json["alexaHistoryRecords"]:
            _LOGGER.debug("Processing vocal history record: %s", record)
            utterance_type = record.get("utteranceType")
            if utterance_type in UTTERANCE_TYPES_TO_SKIP:
                continue

            serial = self._serial_from_record(record, known_serials)
            if serial is None:
                continue

            timestamp = record["timestamp"]
            new_record = AmazonVocalRecord(
                timestamp=timestamp,
                history_type=utterance_type or record.get("recordType") or "Unknown",
                intent=record.get("intent") or "Unknown",
                title=record["title"],
                sub_title=record["subTitle"],
            )
            # Store only the latest record per serial number
            if serial not in records or timestamp > records[serial].timestamp:
                records[serial] = new_record

        return records

    def _serial_from_record(
        self, record: dict[str, Any], known_serials: set[str] | None
    ) -> str | None:
        """Resolve the device serial number a history record belongs to."""
        if serial := _serial_from_device_info(record.get("deviceInfo")):
            return serial

        # Some devices, such as Sonos speakers with Alexa, return records
        # without deviceInfo. The serial number is still carried by activityKey.
        serial = _serial_from_activity_key(record.get("activityKey"))
        if serial is None:
            return None

        if known_serials is not None and serial not in known_serials:
            _LOGGER.debug(
                "Discarding vocal history record for unknown device %s", serial
            )
            return None

        return serial

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
