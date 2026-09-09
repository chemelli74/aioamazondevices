# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Smart home light handling for Amazon devices (e.g. Echo Glow).

Lights are not returned by ``api/devices-v2/device``; they are discovered
through the ``CustomerSmartHome`` GraphQL query. State is read from
``api/phoenix/state``; control goes through the behaviors Sequence API as
an ``Alexa.SmartHome.Batch`` operation (the write side of phoenix is being
phased out).
"""

import colorsys
from dataclasses import dataclass
from http import HTTPMethod
from typing import Any, cast

import orjson
from yarl import URL

from aioamazondevices.const.devices import (
    DEVICE_FAMILY_LIGHT,
    DEVICE_TYPES_HARDCODED_METADATA,
)
from aioamazondevices.const.http import (
    REQUEST_AGENT,
    URI_BEHAVIORS_PREVIEW,
    URI_NEXUS_GRAPHQL,
    URI_PHOENIX_STATE,
)
from aioamazondevices.const.light import (
    ALEXA_COLOR_NAMES,
    LIGHT_BRIGHTNESS_MAX,
    LIGHT_BRIGHTNESS_MIN,
    LIGHT_INTERFACE_BRIGHTNESS,
    LIGHT_INTERFACE_COLOR,
    LIGHT_INTERFACE_COLOR_PROPERTIES,
    LIGHT_INTERFACE_HEALTH,
    LIGHT_INTERFACE_MODE,
    LIGHT_INTERFACE_POWER,
    LIGHT_INTERFACE_TOGGLE,
    LIGHT_MODE_SOLID_COLOR,
    SMARTHOME_BATCH_SKILL_ID,
)
from aioamazondevices.const.queries import QUERY_SMART_HOME
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonDeviceLight,
    build_endpoint_device,
)
from aioamazondevices.utils import _LOGGER, format_graphql_error


@dataclass
class _LightControl:
    """Per-light data needed to build smart home control operations."""

    entity_id: str
    mode_instance: str | None
    mode_by_name: dict[str, str]
    mode_by_value: dict[str, str]
    tap_instance: str | None


def _first_friendly_name(entries: list[dict[str, Any]]) -> str | None:
    """Return the first plain-text friendly name from an Alexa resources list."""
    for entry in entries:
        if entry.get("@type") != "text":
            continue
        text = (entry.get("value") or {}).get("text")
        if isinstance(text, str) and text:
            return text
    return None


def nearest_alexa_color(hue: float, saturation: float) -> str:
    """Return the Alexa colour name closest to a given HS colour.

    Alexa's ``setColor`` only accepts a named colour, so an arbitrary HS
    value is matched with a red-mean weighted distance.
    """
    r1, g1, b1 = colorsys.hsv_to_rgb(
        (hue % 360) / 360, max(0.0, min(1.0, saturation)), 1.0
    )
    best_name = "white"
    best_distance = float("inf")
    for name, (name_hue, name_sat, name_val) in ALEXA_COLOR_NAMES.items():
        r2, g2, b2 = colorsys.hsv_to_rgb(name_hue / 360, name_sat / 100, name_val / 100)
        red_mean = (r1 + r2) / 2
        distance = (
            (2 + red_mean) * (r1 - r2) ** 2
            + 4 * (g1 - g2) ** 2
            + (3 - red_mean) * (b1 - b2) ** 2
        )
        if distance < best_distance:
            best_distance = distance
            best_name = name
    return best_name


def parse_capability_states(raw_states: list[str]) -> dict[str, Any]:
    """Decode a phoenix ``capabilityStates`` list (a list of JSON strings).

    Keys are the interface namespace, or ``namespace:instance`` when the
    capability state carries an instance.
    """
    decoded: dict[str, Any] = {}
    for raw in raw_states:
        try:
            entry = orjson.loads(raw)
        except orjson.JSONDecodeError:
            _LOGGER.debug("Skipping malformed capability state: %s", raw)
            continue
        if not (namespace := entry.get("namespace")):
            continue
        instance = entry.get("instance")
        key = f"{namespace}:{instance}" if instance is not None else namespace
        decoded[key] = entry.get("value")
    return decoded


def build_light_from_appliance(
    appliance: dict[str, Any], customer_id: str | None
) -> tuple[AmazonDevice, _LightControl] | None:
    """Build an AmazonDevice + control data from a CustomerSmartHome appliance.

    Returns ``None`` for anything that is not an Amazon-branded light.
    """
    if appliance.get("manufacturerName") != "Amazon":
        return None
    if DEVICE_FAMILY_LIGHT not in (appliance.get("applianceTypes") or []):
        return None

    identifiers = appliance.get("alexaDeviceIdentifierList") or []
    identity = identifiers[0] if identifiers else {}
    serial = identity.get("dmsDeviceSerialNumber")
    device_type = identity.get("dmsDeviceTypeId")
    entity_id = appliance.get("entityId")
    if not serial or not device_type or not entity_id:
        _LOGGER.debug("Skipping light with incomplete identity: %s", appliance)
        return None

    supports_brightness = supports_color = supports_tap = False
    mode_instance: str | None = None
    tap_instance: str | None = None
    mode_by_value: dict[str, str] = {}
    for capability in appliance.get("capabilities") or []:
        interface = capability.get("interfaceName")
        if interface == LIGHT_INTERFACE_BRIGHTNESS:
            supports_brightness = True
        elif interface == LIGHT_INTERFACE_COLOR:
            supports_color = True
        elif interface == LIGHT_INTERFACE_MODE:
            mode_instance = capability.get("instance")
            supported_modes = capability.get("configuration", {}).get(
                "supportedModes", []
            )
            for mode in supported_modes:
                value = mode.get("value")
                name = _first_friendly_name(
                    mode.get("modeResources", {}).get("friendlyNames", [])
                )
                if value is not None and name:
                    mode_by_value[str(value)] = name
        elif interface == LIGHT_INTERFACE_TOGGLE:
            tap_instance = capability.get("instance")
            supports_tap = True

    effects = sorted(
        name for value, name in mode_by_value.items() if value != LIGHT_MODE_SOLID_COLOR
    )

    name = appliance.get("friendlyName")
    if not name:
        aliases = appliance.get("aliases") or []
        name = next(
            (
                alias.get("friendlyName")
                for alias in aliases
                if alias.get("friendlyName")
            ),
            None,
        )
    hardcoded = DEVICE_TYPES_HARDCODED_METADATA.get(device_type, {})

    light = AmazonDeviceLight(
        power=False,
        brightness=None,
        hue=None,
        saturation=None,
        color_name=None,
        effect=None,
        effects=effects,
        supports_brightness=supports_brightness,
        supports_color=supports_color,
        supports_effects=bool(effects),
        supports_tap=supports_tap,
        tap_enabled=None,
    )

    device = build_endpoint_device(
        account_name=name or hardcoded.get("model") or "Light",
        device_family=DEVICE_FAMILY_LIGHT,
        device_type=device_type,
        serial_number=serial,
        customer_id=customer_id,
        online=False,
        manufacturer=hardcoded.get("manufacturer", "Amazon"),
        model=hardcoded.get("model"),
        entity_id=entity_id,
        endpoint_id=f"amzn1.alexa.endpoint.{entity_id}",
        light=light,
    )

    control = _LightControl(
        entity_id=entity_id,
        mode_instance=mode_instance,
        mode_by_name={name: value for value, name in mode_by_value.items()},
        mode_by_value=mode_by_value,
        tap_instance=tap_instance,
    )
    return device, control


def apply_light_state(
    device: AmazonDevice, control: _LightControl, raw_states: list[str]
) -> None:
    """Apply a phoenix ``capabilityStates`` payload onto ``device.light``."""
    light = device.light
    if light is None:
        return

    decoded = parse_capability_states(raw_states)

    light.power = decoded.get(LIGHT_INTERFACE_POWER) == "ON"

    brightness = decoded.get(LIGHT_INTERFACE_BRIGHTNESS)
    light.brightness = int(brightness) if isinstance(brightness, (int, float)) else None

    color = decoded.get(LIGHT_INTERFACE_COLOR) or {}
    light.hue = color.get("hue")
    light.saturation = color.get("saturation")

    color_properties = decoded.get(LIGHT_INTERFACE_COLOR_PROPERTIES) or {}
    light.color_name = color_properties.get("name")

    if control.mode_instance is not None:
        mode_value = decoded.get(f"{LIGHT_INTERFACE_MODE}:{control.mode_instance}")
        if mode_value is None or str(mode_value) == LIGHT_MODE_SOLID_COLOR:
            light.effect = None
        else:
            light.effect = control.mode_by_value.get(str(mode_value))

    if control.tap_instance is not None:
        tap = decoded.get(f"{LIGHT_INTERFACE_TOGGLE}:{control.tap_instance}")
        light.tap_enabled = tap == "ON" if tap is not None else None

    health = decoded.get(LIGHT_INTERFACE_HEALTH) or {}
    device.online = health.get("value") == "OK"


class AmazonLightHandler:
    """Discover and control Amazon smart home lights."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize AmazonLightHandler class."""
        self._http_wrapper = http_wrapper
        self._session_state_data = session_state_data
        self._lights: dict[str, AmazonDevice] = {}
        self._controls: dict[str, _LightControl] = {}

    @property
    def lights(self) -> dict[str, AmazonDevice]:
        """Return the discovered lights, keyed by serial number."""
        return self._lights

    async def discover_lights(self) -> dict[str, AmazonDevice]:
        """Discover Amazon smart home lights via the CustomerSmartHome query."""
        payload = {"operationName": "CustomerSmartHome", "query": QUERY_SMART_HOME}

        try:
            _, raw_resp = await self._http_wrapper.session_request(
                method=HTTPMethod.POST,
                url=URL.joinpath(
                    self._session_state_data.alexa_website_url, URI_NEXUS_GRAPHQL
                ),
                input_data=payload,
                json_data=True,
                extended_headers={"User-Agent": REQUEST_AGENT["Amazon"]},
            )
            response = await self._http_wrapper.response_to_json(raw_resp, "smart_home")
        except (CannotRetrieveData, ValueError) as exc:
            _LOGGER.warning("Unable to retrieve smart home lights: %s", exc)
            return self._lights

        if not (data := response.get("data")) or not data.get("endpoints"):
            format_graphql_error(response)
            return self._lights

        lights: dict[str, AmazonDevice] = {}
        controls: dict[str, _LightControl] = {}
        for item in data["endpoints"].get("items", []):
            appliance = item.get("legacyAppliance") or {}
            built = build_light_from_appliance(
                appliance, self._session_state_data.account_customer_id
            )
            if built is None:
                continue
            device, control = built
            lights[device.serial_number] = device
            controls[device.serial_number] = control

        self._lights = lights
        self._controls = controls
        _LOGGER.debug("Discovered %s Amazon smart home light(s)", len(lights))
        return self._lights

    async def update_lights_state(self) -> None:
        """Refresh the live state of every discovered light."""
        for serial, device in self._lights.items():
            if not (control := self._controls.get(serial)):
                continue
            raw_states = await self._get_light_state(control.entity_id)
            if raw_states is None:
                device.online = False
                continue
            apply_light_state(device, control, raw_states)

    async def _get_light_state(self, entity_id: str) -> list[str] | None:
        """Return the ``capabilityStates`` list for a light, or ``None``."""
        payload = {"stateRequests": [{"entityId": entity_id, "entityType": "ENTITY"}]}

        try:
            _, raw_resp = await self._http_wrapper.session_request(
                method=HTTPMethod.POST,
                url=URL.joinpath(
                    self._session_state_data.alexa_website_url, URI_PHOENIX_STATE
                ),
                input_data=payload,
                json_data=True,
                extended_headers={"User-Agent": REQUEST_AGENT["Amazon"]},
            )
            response = await self._http_wrapper.response_to_json(
                raw_resp, "phoenix_state"
            )
        except (CannotRetrieveData, ValueError) as exc:
            _LOGGER.warning("Unable to read light state for %s: %s", entity_id, exc)
            return None

        for device_state in response.get("deviceStates", []):
            if device_state.get("entity", {}).get("entityId") == entity_id:
                return cast("list[str]", device_state.get("capabilityStates", []))

        if errors := response.get("errors"):
            _LOGGER.debug("Light %s state unavailable: %s", entity_id, errors)
        return None

    async def set_power(self, device: AmazonDevice, power_on: bool) -> None:
        """Turn a light on or off."""
        await self._control(
            self._control_for(device).entity_id,
            {"type": "turnOn" if power_on else "turnOff"},
        )

    async def set_brightness(self, device: AmazonDevice, brightness: int) -> None:
        """Set a light's brightness as a percentage (0-100)."""
        if not (LIGHT_BRIGHTNESS_MIN <= brightness <= LIGHT_BRIGHTNESS_MAX):
            raise ValueError(
                f"Brightness must be between {LIGHT_BRIGHTNESS_MIN} "
                f"and {LIGHT_BRIGHTNESS_MAX}"
            )
        await self._control(
            self._control_for(device).entity_id,
            {"type": "setBrightness", "brightness": brightness},
        )

    async def set_color(
        self, device: AmazonDevice, hue: float, saturation: float
    ) -> None:
        """Set a light's colour from HS hue (0-360) and saturation (0-1).

        Alexa's ``setColor`` only accepts a fixed palette of named colours
        (there is no raw-HSB path), so the HS value is snapped to the
        closest one.
        """
        await self._control(
            self._control_for(device).entity_id,
            {"type": "setColor", "colorName": nearest_alexa_color(hue, saturation)},
        )

    async def set_effect(self, device: AmazonDevice, effect: str | None) -> None:
        """Select a light show, or ``None`` for plain solid colour."""
        control = self._control_for(device)
        if control.mode_instance is None:
            raise ValueError("Light does not support effects")
        if effect is None:
            mode_value: str | None = LIGHT_MODE_SOLID_COLOR
        else:
            mode_value = control.mode_by_name.get(effect)
        if mode_value is None:
            raise ValueError(f"Unsupported effect: {effect}")
        await self._control(
            control.entity_id,
            {
                "type": "setModeValue",
                "instance": control.mode_instance,
                "mode": mode_value,
            },
        )

    async def set_tap(self, device: AmazonDevice, enabled: bool) -> None:
        """Enable or disable tap-to-change-colour."""
        control = self._control_for(device)
        if control.tap_instance is None:
            raise ValueError("Light does not support tap control")
        await self._control(
            control.entity_id,
            {
                "type": "setToggleStateValue",
                "instance": control.tap_instance,
                "toggleState": "ON" if enabled else "OFF",
            },
        )

    def _control_for(self, device: AmazonDevice) -> _LightControl:
        """Return the control data for a known light."""
        if not (control := self._controls.get(device.serial_number)):
            raise ValueError(f"Unknown light: {device.serial_number}")
        return control

    async def _control(self, entity_id: str, operation: dict[str, Any]) -> None:
        """Send one smart home operation via the behaviors Sequence API.

        This replaces the older ``api/phoenix/state`` endpoint, which Amazon
        is phasing out in favour of GraphQL / the behaviors path.
        """
        node = {
            "@type": "com.amazon.alexa.behaviors.model.OpaquePayloadOperationNode",
            "type": "Alexa.SmartHome.Batch",
            "skillId": SMARTHOME_BATCH_SKILL_ID,
            "operationPayload": {
                "target": entity_id,
                "customerId": self._session_state_data.account_customer_id,
                "operations": [operation],
            },
        }
        sequence = {
            "@type": "com.amazon.alexa.behaviors.model.Sequence",
            "startNode": {
                "@type": "com.amazon.alexa.behaviors.model.SerialNode",
                "nodesToExecute": [node],
            },
        }
        payload = {
            "behaviorId": "PREVIEW",
            "sequenceJson": orjson.dumps(sequence).decode("utf-8"),
            "status": "ENABLED",
        }
        await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=URL.joinpath(
                self._session_state_data.alexa_website_url, URI_BEHAVIORS_PREVIEW
            ),
            input_data=payload,
            json_data=True,
            extended_headers={"User-Agent": REQUEST_AGENT["Amazon"]},
        )
