# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for sensor sync, poll and push handling in AmazonSensorHandler."""

import logging
from collections.abc import Callable
from typing import Any

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.devices import DEVICE_TYPE_AQM, SPEAKER_GROUP_FAMILY
from aioamazondevices.implementation.device import _parse_features
from aioamazondevices.implementation.sensor import AmazonSensorHandler
from aioamazondevices.structures import AmazonDevice

from .const import TEST_SERIAL_1, TEST_SERIAL_2

pytestmark = pytest.mark.anyio

ENDPOINT = "endpoint-1"
SYNCED_TEMPERATURE = 20.0
SYNCED_ILLUMINANCE = 5.0
POLLED_ILLUMINANCE = 7.0
PUSHED_TEMPERATURE = 22.5
EARLIER = "2026-10-15T10:00:00Z"
LATER = "2026-10-15T10:05:00Z"


def _temperature(value: float, time_of_sample: str | None = None) -> dict[str, Any]:
    return {
        "name": "temperatureSensor",
        "instance": None,
        "properties": [
            {
                "name": "temperature",
                "value": {"value": value, "scale": "CELSIUS"},
                "timeOfSample": time_of_sample,
            }
        ],
    }


def _illuminance(value: float) -> dict[str, Any]:
    return {
        "name": "lightSensor",
        "instance": None,
        "properties": [{"name": "illuminance", "illuminanceValue": {"value": value}}],
    }


def _reachability(status: str) -> dict[str, Any]:
    return {
        "name": "connectivity",
        "instance": None,
        "properties": [{"name": "reachability", "reachabilityStatusValue": status}],
    }


def _not_found(feature: dict[str, Any]) -> dict[str, Any]:
    """Return a feature whose properties Amazon reports as NOT_FOUND."""
    return feature | {
        "properties": [
            {"name": prop["name"], "error": {"type": "NOT_FOUND", "message": "x"}}
            for prop in feature["properties"]
        ]
    }


def _supports(device: AmazonDevice, *features: dict[str, Any]) -> AmazonDevice:
    """Set the supported features of a device, as the device handler does."""
    device.features, _ = _parse_features(
        {"features": list(features)}, device.device_type
    )
    return device


def _endpoint(*features: dict[str, Any]) -> dict[str, Any]:
    return {"endpointId": ENDPOINT, "features": list(features)}


def _push(*features: dict[str, Any], endpoint_id: str = ENDPOINT) -> dict[str, Any]:
    """Build an FDAL smart home push payload."""
    return {
        "data": {"__typename": "Endpoint", "features": list(features)},
        "entity": {"__typename": "Endpoint", "id": endpoint_id},
        "fragment": "fragment EndpointState on Endpoint{features{name}}",
    }


def _store(handler: AmazonSensorHandler, *features: dict[str, Any]) -> None:
    """Store the tracked sensor_values of the test endpoint."""
    handler.store_values(handler.parse_endpoint_state(ENDPOINT, _endpoint(*features)))


@pytest.fixture
def devices(make_device: Callable[..., AmazonDevice]) -> dict[str, AmazonDevice]:
    """Return a single device with an endpoint and temperature and illuminance."""
    device = make_device(TEST_SERIAL_1)
    device.endpoint_id = ENDPOINT
    _supports(device, _temperature(0), _illuminance(0))
    return {TEST_SERIAL_1: device}


@pytest.fixture
def handler(
    api: AmazonEchoApi, devices: dict[str, AmazonDevice]
) -> AmazonSensorHandler:
    """Return a handler synced with temperature and illuminance sensors."""
    handler = api._sensor_handler
    handler.full_sensor_sync(
        devices,
        {
            ENDPOINT: _endpoint(
                _temperature(SYNCED_TEMPERATURE), _illuminance(SYNCED_ILLUMINANCE)
            )
        },
    )
    return handler


def _stub_poll(
    monkeypatch: pytest.MonkeyPatch,
    handler: AmazonSensorHandler,
    response: dict[str, dict[str, Any]],
) -> list[list[str]]:
    """Stub the poll query with a response, recording the requested IDs."""
    calls: list[list[str]] = []

    async def _get_polled_sensor_states(endpoint_ids: list[str]) -> dict[str, Any]:
        calls.append(sorted(endpoint_ids))
        return response

    monkeypatch.setattr(handler, "_get_polled_sensor_states", _get_polled_sensor_states)
    return calls


@pytest.mark.usefixtures("handler")
async def test_sync_builds_store(api: AmazonEchoApi) -> None:
    """A sync fills the store keyed by serial and sensor key."""
    assert set(api.sensors[TEST_SERIAL_1]) == {"temperature", "illuminance"}


async def test_sync_missing_endpoint_drops_sensors(
    api: AmazonEchoApi,
    handler: AmazonSensorHandler,
    devices: dict[str, AmazonDevice],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A device missing from a sync loses its sensors and is logged as an error."""
    handler.full_sensor_sync(devices, {"other-endpoint": {"features": []}})

    assert TEST_SERIAL_1 not in api.sensors
    assert not handler.is_tracked_endpoint(ENDPOINT)
    assert f"Devices missing from sensor sync: ['{TEST_SERIAL_1}']" in caplog.text


async def test_older_sync_does_not_overwrite_push(
    api: AmazonEchoApi,
    handler: AmazonSensorHandler,
    devices: dict[str, AmazonDevice],
) -> None:
    """A device refresh fetched before a push does not revert it."""
    _store(handler, _temperature(PUSHED_TEMPERATURE, LATER))

    handler.full_sensor_sync(devices, {ENDPOINT: _endpoint(_temperature(1.0, EARLIER))})

    assert api.sensors[TEST_SERIAL_1]["temperature"].value == PUSHED_TEMPERATURE


async def test_poll_only_updates_polled_sensors(
    api: AmazonEchoApi,
    handler: AmazonSensorHandler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A poll writes polled sensors and leaves pushed ones alone."""
    calls = _stub_poll(
        monkeypatch,
        handler,
        {ENDPOINT: _endpoint(_illuminance(POLLED_ILLUMINANCE))},
    )

    await handler.update_polled_sensors()

    assert calls == [[ENDPOINT]]
    assert api.sensors[TEST_SERIAL_1]["illuminance"].value == POLLED_ILLUMINANCE
    assert api.sensors[TEST_SERIAL_1]["temperature"].value == SYNCED_TEMPERATURE


async def test_poll_only_requests_endpoints_with_polled_sensors(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Endpoints whose sensors are all pushed are left out of the poll."""
    polled = _supports(make_device(TEST_SERIAL_1), _illuminance(0))
    polled.endpoint_id = ENDPOINT
    pushed_only = _supports(make_device(TEST_SERIAL_2), _temperature(0))
    pushed_only.endpoint_id = "endpoint-2"
    handler = api._sensor_handler
    handler.full_sensor_sync(
        {TEST_SERIAL_1: polled, TEST_SERIAL_2: pushed_only},
        {
            ENDPOINT: _endpoint(_illuminance(SYNCED_ILLUMINANCE)),
            "endpoint-2": {
                "endpointId": "endpoint-2",
                "features": [_temperature(SYNCED_TEMPERATURE)],
            },
        },
    )
    calls = _stub_poll(monkeypatch, handler, {})

    await handler.update_polled_sensors()

    assert calls == [[ENDPOINT]]


async def test_poll_without_polled_sensors_makes_no_request(
    api: AmazonEchoApi,
    devices: dict[str, AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No query is sent when no endpoint has a polled sensor."""
    _supports(devices[TEST_SERIAL_1], _temperature(0))
    handler = api._sensor_handler
    handler.full_sensor_sync(
        devices, {ENDPOINT: _endpoint(_temperature(SYNCED_TEMPERATURE))}
    )
    calls = _stub_poll(monkeypatch, handler, {})

    await handler.update_polled_sensors()

    assert calls == []


async def test_poll_ignores_unselected_properties(
    api: AmazonEchoApi,
    handler: AmazonSensorHandler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Properties outside the poll fragments come back empty and are skipped."""
    unselected: dict[str, Any] = {
        "name": "temperatureSensor",
        "instance": None,
        "properties": [{}],
    }
    _stub_poll(
        monkeypatch,
        handler,
        {ENDPOINT: _endpoint(unselected, _illuminance(POLLED_ILLUMINANCE))},
    )

    await handler.update_polled_sensors()

    assert api.sensors[TEST_SERIAL_1]["illuminance"].value == POLLED_ILLUMINANCE
    assert api.sensors[TEST_SERIAL_1]["temperature"].value == SYNCED_TEMPERATURE


async def test_poll_missing_endpoint_flags_polled_errored(
    api: AmazonEchoApi,
    handler: AmazonSensorHandler,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed poll flags only polled sensors as errored."""
    _stub_poll(monkeypatch, handler, {})

    await handler.update_polled_sensors()

    assert api.sensors[TEST_SERIAL_1]["illuminance"].error
    assert not api.sensors[TEST_SERIAL_1]["temperature"].error
    assert "Sensors missing from poll" in caplog.text


async def test_poll_missing_sensor_flags_errored(
    api: AmazonEchoApi,
    handler: AmazonSensorHandler,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A polled sensor missing from its endpoint's response is flagged as errored."""
    _stub_poll(monkeypatch, handler, {ENDPOINT: _endpoint()})

    await handler.update_polled_sensors()

    assert api.sensors[TEST_SERIAL_1]["illuminance"].error
    assert f"Sensors missing from poll: [('{TEST_SERIAL_1}', 'illuminance')]" in (
        caplog.text
    )


async def test_poll_error_flags_errored(
    api: AmazonEchoApi,
    handler: AmazonSensorHandler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A polled sensor Amazon reports an error for is stored as errored."""
    errored = {
        "name": "lightSensor",
        "instance": None,
        "properties": [
            {"name": "illuminance", "error": {"type": "TIMEOUT", "message": "x"}}
        ],
    }
    _stub_poll(monkeypatch, handler, {ENDPOINT: _endpoint(errored)})

    await handler.update_polled_sensors()

    assert api.sensors[TEST_SERIAL_1]["illuminance"].error
    assert api.sensors[TEST_SERIAL_1]["illuminance"].error_type == "TIMEOUT"


async def test_poll_not_found_flags_errored_without_warning(
    api: AmazonEchoApi,
    handler: AmazonSensorHandler,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A polled NOT_FOUND sensor is errored, not missing, and recovers on a value."""
    _stub_poll(monkeypatch, handler, {ENDPOINT: _endpoint(_not_found(_illuminance(0)))})

    await handler.update_polled_sensors()

    sensor = api.sensors[TEST_SERIAL_1]["illuminance"]
    assert sensor.error
    assert sensor.error_type == "NOT_FOUND"
    assert "Sensors missing from poll" not in caplog.text

    _stub_poll(
        monkeypatch, handler, {ENDPOINT: _endpoint(_illuminance(POLLED_ILLUMINANCE))}
    )
    await handler.update_polled_sensors()

    sensor = api.sensors[TEST_SERIAL_1]["illuminance"]
    assert not sensor.error
    assert sensor.value == POLLED_ILLUMINANCE


async def test_sync_keeps_not_found_supported_sensor(
    api: AmazonEchoApi,
    devices: dict[str, AmazonDevice],
) -> None:
    """A supported sensor that is NOT_FOUND at sync is stored as errored."""
    handler = api._sensor_handler
    handler.full_sensor_sync(
        devices,
        {
            ENDPOINT: _endpoint(
                _temperature(SYNCED_TEMPERATURE), _not_found(_illuminance(0))
            )
        },
    )

    sensor = api.sensors[TEST_SERIAL_1]["illuminance"]
    assert sensor.error
    assert sensor.error_type == "NOT_FOUND"

    _store(handler, _illuminance(POLLED_ILLUMINANCE))

    assert api.sensors[TEST_SERIAL_1]["illuminance"].value == POLLED_ILLUMINANCE


async def test_sync_tracks_supported_sensor_without_value(
    api: AmazonEchoApi,
    devices: dict[str, AmazonDevice],
) -> None:
    """A supported sensor absent from the sync is tracked, and filled by a push."""
    handler = api._sensor_handler
    handler.full_sensor_sync(
        devices, {ENDPOINT: _endpoint(_illuminance(SYNCED_ILLUMINANCE))}
    )
    assert "temperature" not in api.sensors[TEST_SERIAL_1]

    sensor_values = handler.parse_endpoint_state(
        ENDPOINT, _endpoint(_temperature(PUSHED_TEMPERATURE))
    )
    assert handler.has_changes(sensor_values)
    handler.store_values(sensor_values)

    assert api.sensors[TEST_SERIAL_1]["temperature"].value == PUSHED_TEMPERATURE


async def test_sync_only_tracks_supported_features(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
) -> None:
    """A templated property is not tracked unless it is a supported feature."""
    device = make_device(TEST_SERIAL_1)
    device.endpoint_id = ENDPOINT
    handler = api._sensor_handler
    handler.full_sensor_sync(
        {TEST_SERIAL_1: device},
        {ENDPOINT: _endpoint(_temperature(SYNCED_TEMPERATURE))},
    )

    assert TEST_SERIAL_1 not in api.sensors
    assert not handler.is_tracked_endpoint(ENDPOINT)


async def test_sync_skips_features_without_definition(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
) -> None:
    """A feature with no sensor definition for the device type is not tracked."""
    aqm_humidity = {
        "name": "range",
        "instance": "4",
        "properties": [{"name": "rangeValue", "rangeValue": {"value": 40}}],
    }
    device = make_device(TEST_SERIAL_1)
    device.endpoint_id = ENDPOINT
    device.device_type = DEVICE_TYPE_AQM
    _supports(device, aqm_humidity)
    # range sensors are only defined for the air quality monitor
    device.device_type = "OTHER"

    handler = api._sensor_handler
    handler.full_sensor_sync({TEST_SERIAL_1: device}, {ENDPOINT: _endpoint()})

    assert not handler.is_tracked_endpoint(ENDPOINT)


async def test_poll_missing_sensor_without_value_is_not_created(
    api: AmazonEchoApi,
    devices: dict[str, AmazonDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A polled sensor that never had a value is not created by a failed poll."""
    handler = api._sensor_handler
    handler.full_sensor_sync(
        devices, {ENDPOINT: _endpoint(_temperature(SYNCED_TEMPERATURE))}
    )
    _stub_poll(monkeypatch, handler, {})

    await handler.update_polled_sensors()

    assert "illuminance" not in api.sensors[TEST_SERIAL_1]


async def test_speaker_group_online_follows_members(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
) -> None:
    """A speaker group is online only when all its members are."""
    group = make_device("GROUP", device_family=SPEAKER_GROUP_FAMILY)
    group.device_cluster_members = {TEST_SERIAL_1: None, TEST_SERIAL_2: None}
    devices = {
        "GROUP": group,
        TEST_SERIAL_1: make_device(TEST_SERIAL_1, online=True),
        TEST_SERIAL_2: make_device(TEST_SERIAL_2, online=False),
    }

    api._sensor_handler.update_device_online_statuses(devices)
    assert not group.online

    devices[TEST_SERIAL_2].online = True
    api._sensor_handler.update_device_online_statuses(devices)
    assert group.online


@pytest.mark.usefixtures("handler")
async def test_malformed_smart_home_event_is_logged(
    api: AmazonEchoApi, caplog: pytest.LogCaptureFixture
) -> None:
    """Events without an entity ID or data are logged and change nothing."""
    payloads: list[dict[str, Any]] = [
        {"data": {"features": []}},
        {"entity": {"id": ENDPOINT}},
        {"entity": None, "data": {}},
    ]
    for payload in payloads:
        await api._http2_push_event_handler("FDAL_UPDATE", payload)

    assert caplog.text.count("Received malformed smart home event") == len(payloads)
    assert api.sensors[TEST_SERIAL_1]["temperature"].value == SYNCED_TEMPERATURE


async def test_unknown_push_event_is_ignored(
    api: AmazonEchoApi, caplog: pytest.LogCaptureFixture
) -> None:
    """Push events of an unknown type are logged and otherwise ignored."""
    caplog.set_level(logging.DEBUG)

    await api._http2_push_event_handler("UNKNOWN_EVENT", {})

    assert "Unhandled push event type: UNKNOWN_EVENT" in caplog.text


async def test_is_tracked_endpoint(handler: AmazonSensorHandler) -> None:
    """Only endpoints with a tracked sensor are tracked."""
    assert handler.is_tracked_endpoint(ENDPOINT)
    assert not handler.is_tracked_endpoint("lightbulb")


async def test_push_for_untracked_property_is_dropped(
    api: AmazonEchoApi, handler: AmazonSensorHandler
) -> None:
    """Properties not in the device's supported features give no sensor_values."""
    assert handler.parse_endpoint_state(ENDPOINT, _endpoint(_reachability("OK"))) == []
    assert "reachability" not in api.sensors[TEST_SERIAL_1]


async def test_parse_endpoint_state_does_not_store(
    api: AmazonEchoApi, handler: AmazonSensorHandler
) -> None:
    """Parsing an endpoint state leaves the stored sensors alone."""
    sensor_values = handler.parse_endpoint_state(
        ENDPOINT, _endpoint(_temperature(PUSHED_TEMPERATURE))
    )

    assert [sensor_value.sensor.value for sensor_value in sensor_values] == [
        PUSHED_TEMPERATURE
    ]
    assert api.sensors[TEST_SERIAL_1]["temperature"].value == SYNCED_TEMPERATURE


async def test_push_updates_tracked_sensor(
    api: AmazonEchoApi, handler: AmazonSensorHandler
) -> None:
    """A new value is a change, and once stored a repeated value is not."""
    sensor_values = handler.parse_endpoint_state(
        ENDPOINT, _endpoint(_temperature(PUSHED_TEMPERATURE))
    )
    assert handler.has_changes(sensor_values)

    handler.store_values(sensor_values)

    assert api.sensors[TEST_SERIAL_1]["temperature"].value == PUSHED_TEMPERATURE
    assert not handler.has_changes(sensor_values)


async def test_newer_sample_of_same_value_is_stored(
    api: AmazonEchoApi, handler: AmazonSensorHandler
) -> None:
    """A newer sample of the same value is not a change, but its time is kept."""
    _store(handler, _temperature(PUSHED_TEMPERATURE, EARLIER))
    sensor_values = handler.parse_endpoint_state(
        ENDPOINT, _endpoint(_temperature(PUSHED_TEMPERATURE, LATER))
    )

    assert not handler.has_changes(sensor_values)
    handler.store_values(sensor_values)

    sensor = api.sensors[TEST_SERIAL_1]["temperature"]
    assert sensor.time_of_sample == sensor_values[0].sensor.time_of_sample


async def test_older_push_is_ignored(
    api: AmazonEchoApi, handler: AmazonSensorHandler
) -> None:
    """A push sampled before the value already held is dropped."""
    _store(handler, _temperature(PUSHED_TEMPERATURE, LATER))
    sensor_values = handler.parse_endpoint_state(
        ENDPOINT, _endpoint(_temperature(1.0, EARLIER))
    )

    assert not handler.has_changes(sensor_values)
    handler.store_values(sensor_values)

    assert api.sensors[TEST_SERIAL_1]["temperature"].value == PUSHED_TEMPERATURE


async def test_reachability_sets_online(
    api: AmazonEchoApi, devices: dict[str, AmazonDevice]
) -> None:
    """A polled reachability change is reflected in the device online status."""
    _supports(devices[TEST_SERIAL_1], _reachability("OK"))
    handler = api._sensor_handler
    handler.full_sensor_sync(devices, {ENDPOINT: _endpoint(_reachability("OK"))})
    handler.update_device_online_statuses(devices)
    assert devices[TEST_SERIAL_1].online

    _store(handler, _reachability("UNREACHABLE"))
    handler.update_device_online_statuses(devices)

    assert not devices[TEST_SERIAL_1].online


@pytest.mark.usefixtures("handler")
async def test_smart_home_event_is_emitted(
    api: AmazonEchoApi,
    devices: dict[str, AmazonDevice],
) -> None:
    """Subscribers are notified of a changed sensor only.

    Repeated sensor_values, untracked endpoints and malformed events notify nothing.
    """
    api._device_handler._final_devices = devices
    events = 0

    async def _on_sensor_event() -> None:
        nonlocal events
        events += 1

    api.on_sensor_event.append(_on_sensor_event)
    api.on_sensor_event.freeze()

    payload = _push(_temperature(PUSHED_TEMPERATURE))
    await api._http2_push_event_handler("FDAL_UPDATE", payload)
    await api._http2_push_event_handler("FDAL_UPDATE", payload)
    await api._http2_push_event_handler(
        "FDAL_UPDATE", _push(_temperature(1.0), endpoint_id="lightbulb")
    )
    await api._http2_push_event_handler("FDAL_UPDATE", {"data": {}})

    assert events == 1
    assert api.sensors[TEST_SERIAL_1]["temperature"].value == PUSHED_TEMPERATURE
