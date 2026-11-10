# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared pytest fixtures for aioamazondevices tests."""

import logging
from collections.abc import AsyncIterator, Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientSession

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import REFRESH_ACCESS_TOKEN
from aioamazondevices.implementation.device import _parse_features
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonDeviceSensor,
    AmazonSaveDataConfig,
)

from .const import (
    TEST_ACCESS_TOKEN,
    TEST_CUSTOMER_ID,
    TEST_DEVICE_TYPE,
    TEST_EMAIL,
    TEST_PASSWORD,
    TEST_SERIAL_1,
    TEST_SERIAL_2,
    TEST_SERIAL_GROUP,
)

SYNC_ENDPOINT = "sync-endpoint"


@pytest.fixture
def anyio_backend() -> str:
    """Restrict anyio-marked tests to the asyncio backend."""
    return "asyncio"


@pytest.fixture
async def client_session() -> AsyncIterator[ClientSession]:
    """Provide a real aiohttp ClientSession, closed after the test."""
    async with ClientSession() as session:
        yield session


@pytest.fixture
def api(client_session: ClientSession, tmp_path: Path) -> AmazonEchoApi:
    """Build an AmazonEchoApi backed by a temp settings directory."""
    return AmazonEchoApi(
        client_session,
        TEST_EMAIL,
        TEST_PASSWORD,
        save_data=AmazonSaveDataConfig(path=tmp_path),
    )


@pytest.fixture
def logged_in(api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch) -> AmazonEchoApi:
    """Store login data so the API acts as logged in, and return the API.

    Refreshing the access token succeeds without a request, keeping the stored one.
    """
    api._session_state_data.login_stored_data = {
        "account_customer_id": TEST_CUSTOMER_ID,
        REFRESH_ACCESS_TOKEN: TEST_ACCESS_TOKEN,
    }
    monkeypatch.setattr(
        api._http_wrapper, "refresh_data", AsyncMock(return_value=(True, {}))
    )
    return api


@pytest.fixture
def debug_logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """Capture debug logs as well as warnings."""
    caplog.set_level(logging.DEBUG)
    return caplog


@pytest.fixture
def mock_json_response(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> Callable[[dict[str, Any]], AsyncMock]:
    """Return a setter making every request return the given JSON response.

    The response has status 200 unless another status is given. The setter
    returns the session_request mock, to assert on the request.
    """

    def _mock_json_response(
        response: dict[str, Any], status: int = HTTPStatus.OK
    ) -> AsyncMock:
        session_request = AsyncMock(return_value=(None, MagicMock(status=status)))
        monkeypatch.setattr(api._http_wrapper, "session_request", session_request)
        monkeypatch.setattr(
            api._http_wrapper, "response_to_json", AsyncMock(return_value=response)
        )
        return session_request

    return _mock_json_response


@pytest.fixture
def send_message(api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Replace the sequence handler's send_message and return the mock."""
    send_message = AsyncMock()
    monkeypatch.setattr(api._sequence_handler, "send_message", send_message)
    return send_message


@pytest.fixture
def make_device() -> Callable[..., AmazonDevice]:
    """Return a factory that builds a minimal AmazonDevice for tests."""

    def _make_device(  # noqa: PLR0913
        serial: str,
        *,
        online: bool = True,
        capabilities: list[str] | None = None,
        device_family: str = "ECHO",
        device_type: str = TEST_DEVICE_TYPE,
        voice_control_supported: bool = True,
        media_player_supported: bool = False,
    ) -> AmazonDevice:
        return AmazonDevice(
            account_name=f"Echo {serial}",
            capabilities=capabilities if capabilities is not None else [],
            device_family=device_family,
            device_type=device_type,
            primary_display_category="ALEXA_VOICE_ENABLED",
            device_owner_customer_id=TEST_CUSTOMER_ID,
            household_device=False,
            device_cluster_members={},
            online=online,
            serial_number=serial,
            manufacturer=None,
            model=None,
            software_version=None,
            hardware_version=None,
            entity_id=None,
            endpoint_id=None,
            notifications_supported=False,
            notifications={},
            media_player_supported=media_player_supported,
            communication_settings={},
            parent_clusters=[],
            voice_control_supported=voice_control_supported,
            features={},
            unsupported_features={},
        )

    return _make_device


@pytest.fixture
def speaker_group(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> AmazonDevice:
    """Register two member devices and return a speaker group containing them."""
    group = make_device(TEST_SERIAL_GROUP)
    group.device_cluster_members = {TEST_SERIAL_1: None, TEST_SERIAL_2: None}
    api._device_handler._final_devices = {
        TEST_SERIAL_1: make_device(TEST_SERIAL_1),
        TEST_SERIAL_2: make_device(TEST_SERIAL_2),
        TEST_SERIAL_GROUP: group,
    }
    return group


@pytest.fixture
def sync_sensors(
    api: AmazonEchoApi,
) -> Callable[[dict[str, Any], AmazonDevice], dict[str, AmazonDeviceSensor]]:
    """Return a helper that syncs one endpoint state and returns its sensors.

    The endpoint state also sets the device features, as the device handler does.
    """

    def _sync_sensors(
        endpoint_state: dict[str, Any], device: AmazonDevice
    ) -> dict[str, AmazonDeviceSensor]:
        device.endpoint_id = SYNC_ENDPOINT
        device.features, _ = _parse_features(endpoint_state, device.device_type)
        handler = api._sensor_handler
        handler.full_sensor_sync(
            {device.serial_number: device}, {SYNC_ENDPOINT: endpoint_state}
        )
        return handler.sensors.get(device.serial_number, {})

    return _sync_sensors
