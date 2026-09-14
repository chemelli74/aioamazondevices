# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for smart home light handling."""

import json
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from yarl import URL

from aioamazondevices.implementation.light import (
    AmazonLightHandler,
    apply_light_state,
    build_light_from_appliance,
    nearest_alexa_color,
    parse_capability_states,
)
from aioamazondevices.structures import AmazonDevice

GLOW_SERIAL = "G0713116104301MW"
GLOW_DEVICE_TYPE = "A2OV3VSK41OD7X"
GLOW_ENTITY_ID = "91412129-e2de-495d-8cb4-855ea8d4dbe6"
GLOW_BRIGHTNESS = 30
GLOW_HUE = 12.0
GLOW_SATURATION = 0.5


def _mode(value: str, *names: str) -> dict[str, Any]:
    return {
        "value": value,
        "modeResources": {
            "friendlyNames": [
                {"@type": "text", "value": {"text": name, "locale": "en-US"}}
                for name in names
            ]
        },
    }


GLOW_APPLIANCE: dict[str, Any] = {
    "applianceId": "AAA_SonarCloudService_glow",
    "applianceTypes": ["LIGHT"],
    "friendlyName": "Prima Luce",
    "friendlyDescription": "Amazon branded Smart Light",
    "manufacturerName": "Amazon",
    "modelName": "",
    "entityId": GLOW_ENTITY_ID,
    "aliases": [{"friendlyName": "Echo Glow"}],
    "capabilities": [
        {"interfaceName": "Alexa.PowerController"},
        {"interfaceName": "Alexa.BrightnessController"},
        {"interfaceName": "Alexa.ColorController"},
        {"interfaceName": "Alexa.EndpointHealth"},
        {"interfaceName": "Alexa.ToggleController", "instance": "3"},
        {
            "interfaceName": "Alexa.ModeController",
            "instance": "1",
            "configuration": {
                "supportedModes": [
                    _mode("1", "Solid Color", "Single Color", "Normal"),
                    _mode("2", "Mood Light"),
                    _mode("4", "Campfire"),
                    _mode("5", "Disco"),
                ]
            },
        },
    ],
    "alexaDeviceIdentifierList": [
        {
            "dmsDeviceSerialNumber": GLOW_SERIAL,
            "dmsDeviceTypeId": GLOW_DEVICE_TYPE,
        }
    ],
}

GLOW_CAPABILITY_STATES: list[str] = [
    (
        '{"namespace":"Alexa.ColorPropertiesController","name":"colorProperties",'
        '"value":{"name":"white"},"timeOfSample":"2026-08-31T07:03:23Z"}'
    ),
    (
        '{"namespace":"Alexa.ModeController","name":"mode","instance":"1",'
        '"value":"1","timeOfSample":"2026-08-31T07:03:23Z"}'
    ),
    (
        '{"namespace":"Alexa.ToggleController","name":"toggleState","instance":"3",'
        '"value":"ON","timeOfSample":"2026-08-30T19:53:17Z"}'
    ),
    (
        '{"namespace":"Alexa.EndpointHealth","name":"connectivity",'
        '"value":{"value":"OK"},"timeOfSample":"2026-08-31T07:03:23.025Z"}'
    ),
    (
        '{"namespace":"Alexa.ColorController","name":"color",'
        '"value":{"brightness":1.0,"hue":12.0,"saturation":0.5},'
        '"timeOfSample":"2026-08-31T07:03:23Z"}'
    ),
    (
        '{"namespace":"Alexa.PowerController","name":"powerState","value":"OFF",'
        '"timeOfSample":"2026-08-31T07:03:23Z"}'
    ),
    (
        '{"namespace":"Alexa.BrightnessController","name":"brightness","value":30,'
        '"timeOfSample":"2026-08-31T07:03:23Z"}'
    ),
]


def _glow() -> tuple[AmazonDevice, Any]:
    """Build the Echo Glow device + control data, asserting it is a light."""
    built = build_light_from_appliance(GLOW_APPLIANCE, "customer-id")
    assert built is not None
    return built


def test_build_light_from_appliance() -> None:
    """A CustomerSmartHome appliance becomes an AmazonDevice + control data."""
    device, control = _glow()

    assert device.serial_number == GLOW_SERIAL
    assert device.device_type == GLOW_DEVICE_TYPE
    assert device.device_family == "LIGHT"
    assert device.model == "Echo Glow"
    assert device.manufacturer == "Amazon"
    assert device.account_name == "Prima Luce"
    assert device.entity_id == GLOW_ENTITY_ID
    assert device.online is False

    assert device.light is not None
    assert device.light.supports_brightness is True
    assert device.light.supports_color is True
    assert device.light.supports_effects is True
    assert device.light.supports_tap is True
    assert device.light.effects == ["Campfire", "Disco", "Mood Light"]

    assert control.mode_instance == "1"
    assert control.tap_instance == "3"
    assert control.mode_by_name["Campfire"] == "4"
    assert control.mode_by_value["1"] == "Solid Color"


@pytest.mark.parametrize(
    "override",
    [
        pytest.param({"manufacturerName": "Signify"}, id="non-amazon"),
        pytest.param({"applianceTypes": ["SMARTPLUG"]}, id="non-light"),
        pytest.param({"alexaDeviceIdentifierList": []}, id="missing-identity"),
    ],
)
def test_build_light_from_appliance_rejects(override: dict[str, Any]) -> None:
    """Non-Amazon, non-light or identity-less appliances are ignored."""
    assert build_light_from_appliance({**GLOW_APPLIANCE, **override}, None) is None


def test_parse_capability_states() -> None:
    """The list of JSON strings is decoded, instances keep their own key."""
    decoded = parse_capability_states(GLOW_CAPABILITY_STATES)

    assert decoded["Alexa.PowerController"] == "OFF"
    assert decoded["Alexa.BrightnessController"] == GLOW_BRIGHTNESS
    assert decoded["Alexa.ModeController:1"] == "1"
    assert decoded["Alexa.ToggleController:3"] == "ON"
    assert decoded["Alexa.EndpointHealth"] == {"value": "OK"}


def test_parse_capability_states_skips_malformed() -> None:
    """A malformed entry is skipped, the rest still decode."""
    decoded = parse_capability_states(
        ["not-json", '{"namespace":"Alexa.PowerController","value":"ON"}']
    )
    assert decoded == {"Alexa.PowerController": "ON"}


def test_apply_light_state_solid_colour() -> None:
    """Phoenix state is applied onto the light; mode 1 means no effect."""
    device, control = _glow()

    apply_light_state(device, control, GLOW_CAPABILITY_STATES)

    assert device.light is not None
    assert device.light.power is False
    assert device.light.brightness == GLOW_BRIGHTNESS
    assert device.light.hue == GLOW_HUE
    assert device.light.saturation == GLOW_SATURATION
    assert device.light.color_name == "white"
    assert device.light.effect is None
    assert device.light.tap_enabled is True
    assert device.online is True


def test_apply_light_state_active_effect() -> None:
    """A non-solid mode value resolves to its friendly effect name."""
    device, control = _glow()
    states = [
        s.replace('"instance":"1","value":"1"', '"instance":"1","value":"5"')
        for s in GLOW_CAPABILITY_STATES
    ]

    apply_light_state(device, control, states)

    assert device.light is not None
    assert device.light.effect == "Disco"


def _handler_with_glow() -> tuple[AmazonLightHandler, AmazonDevice, MagicMock]:
    http_wrapper = MagicMock()
    http_wrapper.session_request = AsyncMock(return_value=(MagicMock(), MagicMock()))
    session_state_data = MagicMock()
    session_state_data.alexa_website_url = URL("https://alexa.amazon.com")
    session_state_data.account_customer_id = "customer-id"

    handler = AmazonLightHandler(http_wrapper, session_state_data)
    device, control = _glow()
    handler._lights = {device.serial_number: device}
    handler._controls = {device.serial_number: control}
    return handler, device, http_wrapper


def _sent_operation(http_wrapper: MagicMock) -> dict[str, Any]:
    """Return the smart home operation from the sent behaviors Sequence."""
    payload = http_wrapper.session_request.await_args.kwargs["input_data"]
    sequence = json.loads(payload["sequenceJson"])
    node = sequence["startNode"]["nodesToExecute"][0]
    return cast("dict[str, Any]", node["operationPayload"]["operations"][0])


@pytest.mark.anyio
async def test_set_brightness_builds_smarthome_batch() -> None:
    """set_brightness POSTs an Alexa.SmartHome.Batch behaviors Sequence."""
    handler, device, http_wrapper = _handler_with_glow()

    await handler.set_brightness(device, 55)

    call = http_wrapper.session_request.await_args
    assert call.kwargs["method"] == "POST"
    assert call.kwargs["url"].path == "/api/behaviors/preview"
    payload = call.kwargs["input_data"]
    assert payload["behaviorId"] == "PREVIEW"
    node = json.loads(payload["sequenceJson"])["startNode"]["nodesToExecute"][0]
    assert node["type"] == "Alexa.SmartHome.Batch"
    assert node["skillId"] == "amzn1.ask.1p.smarthome"
    assert node["operationPayload"]["target"] == GLOW_ENTITY_ID
    assert node["operationPayload"]["customerId"] == "customer-id"
    assert node["operationPayload"]["operations"] == [
        {"type": "setBrightness", "brightness": 55}
    ]


@pytest.mark.anyio
async def test_set_brightness_rejects_out_of_range() -> None:
    """set_brightness validates the 0-100 range."""
    handler, device, _ = _handler_with_glow()

    with pytest.raises(ValueError, match="between 0 and 100"):
        await handler.set_brightness(device, 150)


@pytest.mark.parametrize(
    ("hue", "saturation", "expected"),
    [
        pytest.param(0.0, 1.0, "red", id="red"),
        pytest.param(240.0, 1.0, "blue", id="blue"),
        pytest.param(0.0, 0.0, "white", id="white"),
        pytest.param(49.0, 1.0, "gold", id="gold"),
    ],
)
def test_nearest_alexa_color(hue: float, saturation: float, expected: str) -> None:
    """An HS colour snaps to the closest Alexa colour name."""
    assert nearest_alexa_color(hue, saturation) == expected


@pytest.mark.anyio
async def test_set_color_snaps_to_named_colour() -> None:
    """set_color maps the HS value to a colorName parameter."""
    handler, device, http_wrapper = _handler_with_glow()

    await handler.set_color(device, 0.0, 1.0)

    assert _sent_operation(http_wrapper) == {"type": "setColor", "colorName": "red"}


@pytest.mark.anyio
async def test_set_effect_maps_name_to_mode_value() -> None:
    """set_effect translates the effect name to its ModeController value."""
    handler, device, http_wrapper = _handler_with_glow()

    await handler.set_effect(device, "Disco")

    assert _sent_operation(http_wrapper) == {
        "type": "setModeValue",
        "instance": "1",
        "mode": "5",
    }


@pytest.mark.anyio
async def test_set_effect_none_selects_solid_colour() -> None:
    """Clearing the effect selects the solid-colour mode."""
    handler, device, http_wrapper = _handler_with_glow()

    await handler.set_effect(device, None)

    assert _sent_operation(http_wrapper)["mode"] == "1"


@pytest.mark.anyio
async def test_set_effect_rejects_unknown() -> None:
    """An unknown effect name raises."""
    handler, device, _ = _handler_with_glow()

    with pytest.raises(ValueError, match="Unsupported effect"):
        await handler.set_effect(device, "Nope")


@pytest.mark.anyio
async def test_set_tap_uses_toggle_instance() -> None:
    """set_tap targets the ToggleController instance."""
    handler, device, http_wrapper = _handler_with_glow()

    await handler.set_tap(device, enabled=False)

    assert _sent_operation(http_wrapper) == {
        "type": "setToggleStateValue",
        "instance": "3",
        "toggleState": "OFF",
    }
