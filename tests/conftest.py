# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared pytest fixtures for aioamazondevices tests."""

from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
from aiohttp import ClientSession

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.structures import AmazonDevice, AmazonSaveDataConfig

from .const import TEST_EMAIL, TEST_PASSWORD


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
def make_device() -> Callable[..., AmazonDevice]:
    """Return a factory that builds a minimal AmazonDevice for tests."""

    def _make_device(serial: str, *, online: bool = True) -> AmazonDevice:
        return AmazonDevice(
            account_name=f"Echo {serial}",
            capabilities=[],
            device_family="ECHO",
            device_type="A1B2C3",
            device_owner_customer_id="CUSTOMER_ID",
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
            sensors={},
            notifications_supported=False,
            notifications={},
            media_player_supported=False,
            communication_settings={},
        )

    return _make_device
