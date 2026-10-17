# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for sensor sync, poll and push handling in AmazonSensorHandler."""

from collections.abc import Callable
from typing import Any

import pytest

from aioamazondevices.api import AmazonEchoApi
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
    """Return a single device with an endpoint."""
    device = make_device(TEST_SERIAL_1)
    device.endpoint_id = ENDPOINT
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
    polled = make_device(TEST_SERIAL_1)
    polled.endpoint_id = ENDPOINT
    pushed_only = make_device(TEST_SERIAL_2)
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


async def test_is_tracked_endpoint(handler: AmazonSensorHandler) -> None:
    """Only endpoints with a tracked sensor are tracked."""
    assert handler.is_tracked_endpoint(ENDPOINT)
    assert not handler.is_tracked_endpoint("lightbulb")


async def test_push_for_untracked_property_is_dropped(
    api: AmazonEchoApi, handler: AmazonSensorHandler
) -> None:
    """Properties not seen at sync time give no sensor_values."""
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
    """A pushed reachability change is reflected in the device online status."""
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
