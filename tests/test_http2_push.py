# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for HTTP2 push event handling."""

import logging
from collections.abc import Callable
from typing import Any

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.implementation.http2 import _process_rendering_update
from aioamazondevices.structures import AmazonDevice, AmazonPushMessage

from .const import TEST_SERIAL_1

TEST_ENDPOINT_ID = "endpoint-1"
TEST_TEMPERATURE = 21.3


def _smarthome_payload(endpoint_id: str) -> dict[str, Any]:
    return {
        "entity": {"id": endpoint_id},
        "data": {
            "features": [
                {
                    "name": "temperatureSensor",
                    "instance": None,
                    "properties": [
                        {
                            "name": "temperature",
                            "type": "RETRIEVABLE",
                            "error": None,
                            "__typename": "TemperatureSensor",
                            "value": {"value": TEST_TEMPERATURE, "scale": "CELSIUS"},
                        }
                    ],
                }
            ]
        },
    }


@pytest.mark.anyio
async def test_smarthome_event_logs_sensor_for_known_device(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A SmartHome event for a known endpoint is parsed and logged."""
    device = make_device(TEST_SERIAL_1)
    device.endpoint_id = TEST_ENDPOINT_ID
    api._device_handler._final_devices[TEST_SERIAL_1] = device

    await api._http2_push_event_handler(
        AmazonPushMessage.SmartHome.value, _smarthome_payload(TEST_ENDPOINT_ID)
    )

    assert "SmartHome event for" in caplog.text
    assert str(TEST_TEMPERATURE) in caplog.text


@pytest.mark.anyio
async def test_smarthome_event_unknown_endpoint_is_ignored(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A SmartHome event for an unknown endpoint logs nothing."""
    api._device_handler._final_devices[TEST_SERIAL_1] = make_device(TEST_SERIAL_1)

    await api._handle_smarthome_event(_smarthome_payload("other"))

    assert "SmartHome event for" not in caplog.text


@pytest.mark.anyio
async def test_smarthome_event_missing_endpoint_id_is_ignored(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A SmartHome event without an endpoint ID is rejected."""
    caplog.set_level(logging.DEBUG)
    # A device without an endpoint ID must not match an event without one
    api._device_handler._final_devices[TEST_SERIAL_1] = make_device(TEST_SERIAL_1)

    await api._handle_smarthome_event({"entity": {}, "data": {"features": []}})

    assert "Missing endpoint ID in SmartHome event" in caplog.text
    assert "SmartHome event for" not in caplog.text


@pytest.mark.anyio
async def test_smarthome_event_null_entity_raises(api: AmazonEchoApi) -> None:
    """A SmartHome event with a null entity errors so it is logged upstream."""
    with pytest.raises(AttributeError):
        await api._handle_smarthome_event({"entity": None, "data": {"features": []}})


@pytest.mark.anyio
async def test_smarthome_event_without_data_is_ignored(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A SmartHome event for a known device without data logs no sensors."""
    device = make_device(TEST_SERIAL_1)
    device.endpoint_id = TEST_ENDPOINT_ID
    api._device_handler._final_devices[TEST_SERIAL_1] = device

    await api._handle_smarthome_event(
        {"entity": {"id": TEST_ENDPOINT_ID}, "data": None}
    )

    assert "SmartHome event for" not in caplog.text


def test_resource_id_used_for_other_routes() -> None:
    """Updates on other routes are classified by their resourceId."""
    payload: dict[str, Any] = {}
    result = _process_rendering_update(
        {
            "route": "other",
            "resourceId": AmazonPushMessage.DoNotDisturbChange.value,
            "resourceMetadata": {"payload": payload},
        }
    )

    assert result == (AmazonPushMessage.DoNotDisturbChange.value, payload)


def test_fdal_route_maps_to_smarthome() -> None:
    """Updates on the FDAL route are classified as SmartHome events."""
    payload = {"entity": {"id": TEST_ENDPOINT_ID}}
    result = _process_rendering_update(
        {
            "route": "EventBus:AlexaMobile::FDAL",
            "resourceMetadata": {"payload": payload},
        }
    )

    assert result == (AmazonPushMessage.SmartHome.value, payload)
