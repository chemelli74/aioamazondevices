"""Module to handle Alexa vocal history setting."""

from datetime import UTC, datetime, timedelta
from http import HTTPMethod
from typing import Any

from bs4 import Tag

from aioamazondevices.const.http import (
    CSRF_A2Z,
    REFRESH_ACCESS_TOKEN,
    URI_HISTORY_DATA,
    URI_HISTORY_FRONTEND,
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

    async def _obtain_anti_csrftoken_a2z(self) -> None:
        """Find anti-csrftoken-a2z token."""
        bs_resp, _ = await self._http_wrapper.session_request(
            method=HTTPMethod.GET,
            url=f"https://www.amazon.{self._session_state_data.domain}{URI_HISTORY_FRONTEND}",
        )
        token_meta = bs_resp.find("meta", attrs={"name": "csrf-token"})
        if isinstance(token_meta, Tag):
            token = token_meta.get("content")
            if token:
                self._csrf_a2z_token = str(token)
                return
        raise CannotRetrieveData("Cannot find anti-csrftoken-a2z token")

    async def _vocal_history_json(self) -> dict[str, Any]:
        """Request vocal history data."""
        if not self._csrf_a2z_token:
            await self._obtain_anti_csrftoken_a2z()
        await self._http_wrapper.refresh_data(REFRESH_ACCESS_TOKEN)
        access_token = self._session_state_data.login_stored_data[REFRESH_ACCESS_TOKEN]

        start_time = (
            datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
            - timedelta(days=7)
        ).timestamp() * 1000
        end_time = datetime.now(UTC).timestamp() * 1000
        query_string = f"startTime={int(start_time)}&endTime={int(end_time)}"
        _, raw_res = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=f"https://www.amazon.{self._session_state_data.domain}{URI_HISTORY_DATA}?{query_string}",
            input_data={"previousRequestToken": None},
            json_data=True,
            extended_headers={
                "Authorization": f"Bearer {access_token}",
                CSRF_A2Z: self._csrf_a2z_token,
            },
        )
        history = await self._http_wrapper.response_to_json(raw_res)
        _LOGGER.debug("Vocal history data: %s", history)
        return history

    async def vocal_history(self) -> dict[str, Any]:
        """Get vocal history."""
        history_json = await self._vocal_history_json()

        records: dict[str, AmazonVocalRecord] = {}
        for record in history_json["alexaHistoryRecords"]:
            _LOGGER.debug("Processing vocal history record: %s", record)
            serial = record["deviceInfo"]["deviceSerialNumber"]
            utterance_type = record["utteranceType"]
            if utterance_type in [
                "ASR_TIMEOUT",
                "DEVICE_ARBITRATION",
                "NO_EXPRESSED_INTENT",
                "WAKE_WORD_ONLY",
            ]:
                continue
            timestamp = record["timestamp"]
            new_record = AmazonVocalRecord(
                timestamp=timestamp,
                utterance_type=utterance_type,
                intent=record["intent"],
                title=record["title"],
                sub_title=record["subTitle"],
            )
            # Store only the latest record per serial number
            if serial not in records or timestamp > records[serial].timestamp:
                records[serial] = new_record

        return records
