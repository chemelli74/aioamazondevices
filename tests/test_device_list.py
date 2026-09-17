# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GraphQL driven device list."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.devices import DEVICE_TYPE_AQM, SPEAKER_GROUP_FAMILY
from aioamazondevices.implementation.device import AmazonDeviceHandler

from .const import TEST_SERIAL_1, TEST_SERIAL_2

TEST_SERIAL_AQM = "AQM-1"
TEST_SERIAL_GROUP = "GROUP-1"


def _text(value: str | None) -> dict[str, Any]:
    return {"value": {"text": value}}


def _base_device(
    serial_number: str,
    *,
    device_type: str = "ECHO_TYPE",
    device_family: str | None = "ECHO",
    capabilities: list[str] | None = None,
    cluster_members: list[str] | None = None,
) -> dict[str, Any]:
    """Build a raw `api/devices-v2/device` entry."""
    return {
        "accountName": f"Device {serial_number}",
        "capabilities": capabilities
        if capabilities is not None
        else ["MICROPHONE", "AUDIO_PLAYER"],
        "deviceFamily": device_family,
        "deviceType": device_type,
        "deviceOwnerCustomerId": "CUSTOMER_ID",
        "serialNumber": serial_number,
        "clusterMembers": cluster_members,
        "parentClusters": [],
        "online": True,
        "softwareVersion": "1234",
        "deviceTypeFriendlyName": None,
    }


def _endpoint(
    serial_number: str,
    *,
    device_type: str = "ECHO_TYPE",
    model: str | None = "Echo Dot (5th Gen)",
    manufacturer: str = "Amazon",
) -> dict[str, Any]:
    """Build a GraphQL endpoint entry."""
    return {
        "endpointId": f"endpoint-{serial_number}",
        "friendlyNameObject": _text(f"Device {serial_number}"),
        "manufacturer": _text(manufacturer),
        "model": _text(model),
        "serialNumber": _text(serial_number),
        "softwareVersion": _text("1234"),
        "legacyIdentifiers": {
            "dmsIdentifier": {"deviceType": _text(device_type)},
            "chrsIdentifier": {"entityId": f"entity-{serial_number}"},
        },
    }


def _patch_sources(
    handler: AmazonDeviceHandler,
    devices_endpoints: dict[str, dict[str, Any]],
    base_devices: dict[str, dict[str, Any]],
) -> None:
    """Replace the two data sources of the device handler."""
    handler._get_devices_endpoint_data = AsyncMock(  # type: ignore[method-assign]
        return_value=devices_endpoints
    )
    handler._get_base_devices_data = AsyncMock(return_value=base_devices)  # type: ignore[method-assign]


@pytest.mark.anyio
async def test_graphql_drives_the_device_list(api: AmazonEchoApi) -> None:
    """Only endpoints backed by devices-v2 data become voice devices."""
    handler = api._device_handler
    _patch_sources(
        handler,
        devices_endpoints={
            TEST_SERIAL_1: _endpoint(TEST_SERIAL_1),
            # endpoint without devices-v2 data and unknown on its own
            "UNKNOWN": _endpoint("UNKNOWN"),
        },
        base_devices={
            TEST_SERIAL_1: _base_device(TEST_SERIAL_1),
            # known to devices-v2 but not exposed as an endpoint
            TEST_SERIAL_2: _base_device(TEST_SERIAL_2),
        },
    )

    await handler.update_devices()

    assert list(handler.devices) == [TEST_SERIAL_1]

    device = handler.devices[TEST_SERIAL_1]
    assert device.endpoint_id == f"endpoint-{TEST_SERIAL_1}"
    assert device.entity_id == f"entity-{TEST_SERIAL_1}"
    assert device.model == "Echo Dot"
    assert device.hardware_version == "5th Gen"
    assert device.manufacturer == "Amazon"
    assert device.media_player_supported
    assert device.voice_control_supported


@pytest.mark.anyio
async def test_air_quality_monitors_are_created(api: AmazonEchoApi) -> None:
    """AQM devices exist in the GraphQL data only and are still created."""
    handler = api._device_handler
    _patch_sources(
        handler,
        devices_endpoints={
            TEST_SERIAL_AQM: _endpoint(
                TEST_SERIAL_AQM,
                device_type=DEVICE_TYPE_AQM,
                model="Amazon Smart Air Quality Monitor",
            )
        },
        base_devices={},
    )

    await handler.update_devices()

    device = handler.devices[TEST_SERIAL_AQM]
    assert device.device_type == DEVICE_TYPE_AQM
    assert device.device_family == "Endpoint Only"
    assert device.manufacturer == "Amazon"
    assert device.model == "Amazon Smart Air Quality Monitor"
    assert device.software_version == "1234"
    assert not device.voice_control_supported
    assert device.endpoint_id == f"endpoint-{TEST_SERIAL_AQM}"


@pytest.mark.anyio
async def test_speaker_groups_are_added_from_devices_v2(api: AmazonEchoApi) -> None:
    """Speaker groups have no endpoint, so they come from devices-v2 data."""
    handler = api._device_handler
    _patch_sources(
        handler,
        devices_endpoints={TEST_SERIAL_1: _endpoint(TEST_SERIAL_1)},
        base_devices={
            TEST_SERIAL_1: _base_device(TEST_SERIAL_1),
            TEST_SERIAL_GROUP: _base_device(
                TEST_SERIAL_GROUP,
                device_type="GROUP_TYPE",
                device_family=SPEAKER_GROUP_FAMILY,
                cluster_members=[TEST_SERIAL_1],
            ),
        },
    )

    await handler.update_devices()

    group = handler.devices[TEST_SERIAL_GROUP]
    assert group.device_family == SPEAKER_GROUP_FAMILY
    assert not group.voice_control_supported
    assert group.endpoint_id is None
    assert group.entity_id is None
    # cluster member device types are backfilled
    assert group.device_cluster_members == {TEST_SERIAL_1: "ECHO_TYPE"}
    # speaker groups have no endpoint to query sensors on
    assert group.endpoint_id is None


@pytest.mark.anyio
async def test_device_without_a_family_is_unknown(api: AmazonEchoApi) -> None:
    """A devices-v2 device with no family is unknown, not endpoint only."""
    handler = api._device_handler
    _patch_sources(
        handler,
        devices_endpoints={TEST_SERIAL_1: _endpoint(TEST_SERIAL_1)},
        base_devices={TEST_SERIAL_1: _base_device(TEST_SERIAL_1, device_family=None)},
    )

    await handler.update_devices()

    assert handler.devices[TEST_SERIAL_1].device_family == "Unknown"


@pytest.mark.anyio
async def test_unsupported_endpoint_only_device_is_skipped(api: AmazonEchoApi) -> None:
    """Endpoint-only devices of an unhandled device type are not created."""
    handler = api._device_handler
    _patch_sources(
        handler,
        devices_endpoints={
            TEST_SERIAL_AQM: _endpoint(
                TEST_SERIAL_AQM,
                device_type="ACME_AIR_QUALITY_MONITOR",
                manufacturer="ACME",
            )
        },
        base_devices={},
    )

    await handler.update_devices()

    assert not handler.devices


@pytest.mark.anyio
async def test_endpoint_data_reads_a_single_endpoints_list(api: AmazonEchoApi) -> None:
    """All devices are returned as one list, keyed by serial number."""
    handler = api._device_handler
    app_endpoint = _endpoint("APP-1")
    app_endpoint["alexaEnabledMetadata"] = {"category": "APP"}
    serial_less_endpoint = _endpoint("NO-SERIAL")
    serial_less_endpoint["serialNumber"] = None
    response = {
        "data": {
            "listEndpoints": {
                "endpoints": [
                    _endpoint(TEST_SERIAL_1),
                    _endpoint(TEST_SERIAL_AQM, device_type=DEVICE_TYPE_AQM),
                    app_endpoint,
                    serial_less_endpoint,
                ]
            }
        }
    }
    handler._http_wrapper.session_request = AsyncMock(return_value=(None, None))  # type: ignore[method-assign]
    handler._http_wrapper.response_to_json = AsyncMock(return_value=response)  # type: ignore[method-assign]

    devices_endpoints = await handler._get_devices_endpoint_data()

    assert list(devices_endpoints) == [TEST_SERIAL_1, TEST_SERIAL_AQM]


@pytest.mark.anyio
async def test_devices_v2_data_enriches_the_endpoint_device(api: AmazonEchoApi) -> None:
    """Voice specific data comes from devices-v2, the rest from the endpoint."""
    handler = api._device_handler
    base_device = _base_device(
        TEST_SERIAL_1,
        capabilities=["MICROPHONE", "REMINDERS", "SUPPORTS_SOFTWARE_VERSION"],
    )
    base_device["accountName"] = "This Device"
    # only used when the endpoint reports no model at all
    base_device["deviceTypeFriendlyName"] = "Echo Show 8 (2nd Gen)"
    _patch_sources(
        handler,
        devices_endpoints={TEST_SERIAL_1: _endpoint(TEST_SERIAL_1, model=None)},
        base_devices={TEST_SERIAL_1: base_device},
    )

    await handler.update_devices()

    device = handler.devices[TEST_SERIAL_1]
    # devices-v2 only
    assert device.capabilities == [
        "MICROPHONE",
        "REMINDERS",
        "SUPPORTS_SOFTWARE_VERSION",
    ]
    assert device.device_family == "ECHO"
    assert device.notifications_supported
    assert not device.media_player_supported
    # a device without an endpoint model falls back to the friendly name
    assert device.model == "Echo Show 8"
    assert device.hardware_version == "2nd Gen"
    # the endpoint wins over devices-v2 for everything both of them have
    assert device.account_name == f"Device {TEST_SERIAL_1}"
    assert device.endpoint_id == f"endpoint-{TEST_SERIAL_1}"
    assert device.entity_id == f"entity-{TEST_SERIAL_1}"
    assert device.manufacturer == "Amazon"
    assert device.software_version == "1234"
