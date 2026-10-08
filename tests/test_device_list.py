# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GraphQL driven device list."""

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.devices import DEVICE_TYPE_AQM, SPEAKER_GROUP_FAMILY
from aioamazondevices.const.http import ARRAY_WRAPPER
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.implementation.device import AmazonDeviceHandler
from aioamazondevices.structures import AmazonDeviceFeature

from .const import TEST_SERIAL_1, TEST_SERIAL_2

TEST_SERIAL_AQM = "AQM-1"
TEST_SERIAL_GROUP = "GROUP-1"

# the autouse fixture below replaces the lookup, keep the real one to test it
_get_endpoints_features = AmazonDeviceHandler._get_endpoints_features


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


def _feature(**overrides: object) -> AmazonDeviceFeature:
    """Build a feature with empty defaults, overriding the given fields."""
    fields: dict[str, Any] = {
        "supported_operations": [],
        "supported_modes": [],
        "friendly_name": None,
        "minimum_value": None,
        "maximum_value": None,
        "precision": None,
        "unit_of_measure": None,
        "configuration": {},
    }
    return AmazonDeviceFeature(**(fields | overrides))


@pytest.fixture(autouse=True)
def endpoints_features() -> Iterator[AsyncMock]:
    """Replace the endpoint features lookup, returning no features by default."""
    with patch.object(
        AmazonDeviceHandler, "_get_endpoints_features", AsyncMock(return_value={})
    ) as mock:
        yield mock


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


@pytest.mark.anyio
async def test_known_devices_survive_an_empty_endpoint_response(
    api: AmazonEchoApi,
) -> None:
    """A failed GraphQL call must not drop the devices we already know."""
    handler = api._device_handler
    _patch_sources(
        handler,
        devices_endpoints={TEST_SERIAL_1: _endpoint(TEST_SERIAL_1)},
        base_devices={TEST_SERIAL_1: _base_device(TEST_SERIAL_1)},
    )
    await handler.update_devices()
    known_devices = handler.devices
    assert list(known_devices) == [TEST_SERIAL_1]

    # the GraphQL call now returns nothing, devices-v2 is still fine
    base_devices = AsyncMock(return_value={TEST_SERIAL_1: _base_device(TEST_SERIAL_1)})
    handler._get_devices_endpoint_data = AsyncMock(return_value={})  # type: ignore[method-assign]
    handler._get_base_devices_data = base_devices  # type: ignore[method-assign]

    await handler.update_devices()

    assert handler.devices == known_devices
    # nothing is worth fetching from devices-v2 without endpoints to drive it
    base_devices.assert_not_awaited()


@pytest.mark.anyio
async def test_empty_endpoint_response_raises_without_known_devices(
    api: AmazonEchoApi,
) -> None:
    """With nothing to preserve, a failed GraphQL call stops the refresh."""
    handler = api._device_handler
    base_devices = AsyncMock(return_value={TEST_SERIAL_1: _base_device(TEST_SERIAL_1)})
    handler._get_devices_endpoint_data = AsyncMock(return_value={})  # type: ignore[method-assign]
    handler._get_base_devices_data = base_devices  # type: ignore[method-assign]

    with pytest.raises(CannotRetrieveData):
        await handler.update_devices()

    assert not handler.devices
    base_devices.assert_not_awaited()


@pytest.mark.anyio
async def test_features_are_read_for_the_built_devices(
    api: AmazonEchoApi, endpoints_features: AsyncMock
) -> None:
    """Features are keyed by name and instance, for built devices only."""
    handler = api._device_handler
    range_configuration = {
        "friendlyName": _text("Fan level"),
        "supportedRange": {"minimumValue": 1, "maximumValue": 10, "precision": 1},
        "unitOfMeasure": _text("Alexa.Unit.Percent"),
        "presets": None,
    }
    features: list[dict[str, Any]] = [
        {
            "name": "power",
            "instance": None,
            "operations": [{"name": "turnOn"}, {"name": "turnOff"}],
            "configuration": None,
        },
        {
            "name": "mode",
            "instance": "Fan.Speed",
            "operations": [{"name": "setMode"}],
            "configuration": {
                "modeOptions": [{"value": "Low"}, {"value": "High"}],
            },
        },
        {
            "name": "thermostat",
            "instance": None,
            "operations": None,
            "configuration": {"supportedModes": ["HEAT", "OFF"]},
        },
        {
            "name": "range",
            "instance": "Fan.Level",
            "operations": [{"name": "setRangeValue"}],
            "configuration": range_configuration,
        },
        # features without a name are skipped
        {"name": None, "instance": None, "operations": None, "configuration": None},
    ]
    _patch_sources(
        handler,
        devices_endpoints={
            TEST_SERIAL_1: _endpoint(TEST_SERIAL_1),
            TEST_SERIAL_AQM: _endpoint(TEST_SERIAL_AQM, device_type=DEVICE_TYPE_AQM),
            "UNKNOWN": _endpoint("UNKNOWN"),
        },
        base_devices={TEST_SERIAL_1: _base_device(TEST_SERIAL_1)},
    )
    endpoints_features.return_value = {
        f"endpoint-{TEST_SERIAL_1}": {
            "endpointId": f"endpoint-{TEST_SERIAL_1}",
            "features": features,
        }
    }

    await handler.update_devices()

    # only the devices we build are queried
    endpoints_features.assert_awaited_once_with(
        [f"endpoint-{TEST_SERIAL_1}", f"endpoint-{TEST_SERIAL_AQM}"]
    )

    assert handler.devices[TEST_SERIAL_1].features == {
        "power": {"": _feature(supported_operations=["turnOn", "turnOff"])},
        "mode": {
            "Fan.Speed": _feature(
                supported_operations=["setMode"],
                supported_modes=["Low", "High"],
                configuration={
                    "modeOptions": [{"value": "Low"}, {"value": "High"}],
                },
            )
        },
        "thermostat": {
            "": _feature(
                supported_modes=["HEAT", "OFF"],
                configuration={"supportedModes": ["HEAT", "OFF"]},
            )
        },
        "range": {
            "Fan.Level": _feature(
                supported_operations=["setRangeValue"],
                friendly_name="Fan level",
                minimum_value=1,
                maximum_value=10,
                precision=1,
                unit_of_measure="Alexa.Unit.Percent",
                configuration=range_configuration,
            )
        },
    }
    assert handler.devices[TEST_SERIAL_AQM].features == {}


@pytest.mark.anyio
async def test_known_features_survive_a_failed_features_lookup(
    api: AmazonEchoApi, endpoints_features: AsyncMock
) -> None:
    """A failed features lookup must not drop the features we already know."""
    handler = api._device_handler
    _patch_sources(
        handler,
        devices_endpoints={TEST_SERIAL_1: _endpoint(TEST_SERIAL_1)},
        base_devices={TEST_SERIAL_1: _base_device(TEST_SERIAL_1)},
    )
    endpoints_features.return_value = {
        f"endpoint-{TEST_SERIAL_1}": {
            "features": [{"name": "power", "operations": [{"name": "turnOn"}]}],
        }
    }
    await handler.update_devices()
    known_features = handler.devices[TEST_SERIAL_1].features
    assert known_features == {"power": {"": _feature(supported_operations=["turnOn"])}}

    endpoints_features.return_value = {}
    await handler.update_devices()

    assert handler.devices[TEST_SERIAL_1].features == known_features


@pytest.mark.anyio
async def test_endpoints_features_are_keyed_by_endpoint_id(
    api: AmazonEchoApi,
) -> None:
    """Endpoint features are read from the wrapped GraphQL response."""
    handler = api._device_handler
    endpoint = {"endpointId": f"endpoint-{TEST_SERIAL_1}", "features": []}
    response = {
        ARRAY_WRAPPER: [
            {
                "data": {
                    "listEndpoints": {
                        "endpoints": [endpoint, {"endpointId": None, "features": []}]
                    }
                }
            }
        ]
    }
    session_request = AsyncMock(return_value=(None, None))
    handler._http_wrapper.session_request = session_request  # type: ignore[method-assign]
    handler._http_wrapper.response_to_json = AsyncMock(return_value=response)  # type: ignore[method-assign]

    endpoints_features = await _get_endpoints_features(
        handler, [f"endpoint-{TEST_SERIAL_1}"]
    )

    assert endpoints_features == {f"endpoint-{TEST_SERIAL_1}": endpoint}
    assert session_request.await_args
    payload = session_request.await_args.kwargs["input_data"]
    assert payload[0]["variables"] == {"endpointIds": [f"endpoint-{TEST_SERIAL_1}"]}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        {ARRAY_WRAPPER: [{"errors": [{"message": "boom", "path": ["x"]}]}]},
        {},
        {ARRAY_WRAPPER: [{"data": None}]},
        {ARRAY_WRAPPER: [{"data": {"listEndpoints": None}}]},
        {ARRAY_WRAPPER: [{"data": {"listEndpoints": {"endpoints": []}}}]},
    ],
)
async def test_bad_endpoints_features_response_returns_nothing(
    api: AmazonEchoApi, response: dict[str, Any]
) -> None:
    """GraphQL errors and malformed data give no features."""
    handler = api._device_handler
    handler._http_wrapper.session_request = AsyncMock(return_value=(None, None))  # type: ignore[method-assign]
    handler._http_wrapper.response_to_json = AsyncMock(return_value=response)  # type: ignore[method-assign]

    assert await _get_endpoints_features(handler, ["endpoint-1"]) == {}


@pytest.mark.anyio
async def test_no_endpoints_skips_the_features_request(api: AmazonEchoApi) -> None:
    """Nothing is requested when there are no endpoints to query."""
    handler = api._device_handler
    session_request = AsyncMock()
    handler._http_wrapper.session_request = session_request  # type: ignore[method-assign]

    assert await _get_endpoints_features(handler, []) == {}
    session_request.assert_not_awaited()
