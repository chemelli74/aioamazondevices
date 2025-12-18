"""Support for Amazon devices."""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from http import HTTPMethod
from typing import Any

from aiohttp import ClientSession

from . import __version__
from .const.devices import (
    DEVICE_TO_IGNORE,
    DEVICE_TYPE_TO_MODEL,
    SPEAKER_GROUP_FAMILY,
)
from .const.http import (
    ARRAY_WRAPPER,
    DEFAULT_SITE,
    URI_DEVICES,
    URI_NEXUS_GRAPHQL,
)
from .const.metadata import SENSORS
from .const.queries import QUERY_DEVICE_DATA, QUERY_SENSOR_STATE
from .const.schedules import (
    NOTIFICATION_ALARM,
    NOTIFICATION_REMINDER,
    NOTIFICATION_TIMER,
)
from .exceptions import (
    CannotRetrieveData,
)
from .http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from .implementation.dnd import AmazonDnDHandler
from .implementation.notification import AmazonNotificationHandler
from .implementation.sequence import AmazonSequenceHandler
from .login import AmazonLogin
from .structures import (
    AmazonDevice,
    AmazonDeviceSensor,
    AmazonMusicSource,
    AmazonSequenceType,
)
from .utils import _LOGGER


class AmazonEchoApi:
    """Queries Amazon for Echo devices."""

    def __init__(
        self,
        client_session: ClientSession,
        login_email: str,
        login_password: str,
        login_data: dict[str, Any] | None = None,
        save_to_file: Callable[[str | dict, str, str], Coroutine[Any, Any, None]]
        | None = None,
    ) -> None:
        """Initialize the scanner."""
        _LOGGER.debug("Initialize library v%s", __version__)

        # Check if there is a previous login, otherwise use default (US)
        site = login_data.get("site", DEFAULT_SITE) if login_data else DEFAULT_SITE
        _LOGGER.debug("Using site: %s", site)

        self._session_state_data = AmazonSessionStateData(
            site, login_email, login_password, login_data
        )

        self._http_wrapper = AmazonHttpWrapper(
            client_session,
            self._session_state_data,
            save_to_file,
        )

        self._login = AmazonLogin(
            http_wrapper=self._http_wrapper,
            session_state_data=self._session_state_data,
        )

        self._notification_handler = AmazonNotificationHandler(
            http_wrapper=self._http_wrapper,
            session_state_data=self._session_state_data,
        )

        self._sequence_handler = AmazonSequenceHandler(
            http_wrapper=self._http_wrapper,
            session_state_data=self._session_state_data,
        )

        self._dnd_handler = AmazonDnDHandler(
            http_wrapper=self._http_wrapper, session_state_data=self._session_state_data
        )

        self._final_devices: dict[str, AmazonDevice] = {}
        self._endpoints: dict[str, str] = {}  # endpoint ID to serial number map

        initial_time = datetime.now(UTC) - timedelta(days=2)  # force initial refresh
        self._last_devices_refresh: datetime = initial_time
        self._last_endpoint_refresh: datetime = initial_time

    @property
    def domain(self) -> str:
        """Return current Amazon domain."""
        return self._session_state_data.domain

    @property
    def login(self) -> AmazonLogin:
        """Return login."""
        return self._login

    async def _get_sensors_states(self) -> dict[str, dict[str, AmazonDeviceSensor]]:
        """Retrieve devices sensors states."""
        devices_sensors: dict[str, dict[str, AmazonDeviceSensor]] = {}

        if not self._endpoints:
            return {}

        endpoint_ids = list(self._endpoints.keys())
        payload = [
            {
                "operationName": "getEndpointState",
                "variables": {
                    "endpointIds": endpoint_ids,
                },
                "query": QUERY_SENSOR_STATE,
            }
        ]

        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_NEXUS_GRAPHQL}",
            input_data=payload,
            json_data=True,
        )

        sensors_state = await self._http_wrapper.response_to_json(raw_resp, "sensors")

        if await self._format_human_error(sensors_state):
            # Explicit error in returned data
            return {}

        if (
            not (arr := sensors_state.get(ARRAY_WRAPPER))
            or not (data := arr[0].get("data"))
            or not (endpoints_list := data.get("listEndpoints"))
            or not (endpoints := endpoints_list.get("endpoints"))
        ):
            _LOGGER.error("Malformed sensor state data received: %s", sensors_state)
            return {}

        for endpoint in endpoints:
            serial_number = self._endpoints[endpoint.get("endpointId")]

            if serial_number in self._final_devices:
                devices_sensors[serial_number] = self._get_device_sensor_state(
                    endpoint, serial_number
                )

        return devices_sensors

    def _get_device_sensor_state(
        self, endpoint: dict[str, Any], serial_number: str
    ) -> dict[str, AmazonDeviceSensor]:
        device_sensors: dict[str, AmazonDeviceSensor] = {}
        for feature in endpoint.get("features", {}):
            if (sensor_template := SENSORS.get(feature["name"])) is None:
                # Skip sensors that are not in the predefined list
                continue

            if not (name := sensor_template["name"]):
                raise CannotRetrieveData("Unable to read sensor template")

            for feature_property in feature.get("properties"):
                if sensor_template["name"] != feature_property.get("name"):
                    continue

                value: str | int | float = "n/a"
                scale: str | None = None

                # "error" can be None, missing, or a dict
                api_error = feature_property.get("error") or {}
                error = bool(api_error)
                error_type = api_error.get("type")
                error_msg = api_error.get("message")
                if not error:
                    try:
                        value_raw = feature_property[sensor_template["key"]]
                        if not value_raw:
                            _LOGGER.warning(
                                "Sensor %s [device %s] ignored due to empty value",
                                name,
                                serial_number,
                            )
                            continue
                        scale = (
                            value_raw[scale_template]
                            if (scale_template := sensor_template["scale"])
                            else None
                        )
                        value = (
                            value_raw[subkey_template]
                            if (subkey_template := sensor_template["subkey"])
                            else value_raw
                        )

                    except (KeyError, ValueError) as exc:
                        _LOGGER.warning(
                            "Sensor %s [device %s] ignored due to errors in feature %s: %s",  # noqa: E501
                            name,
                            serial_number,
                            feature_property,
                            repr(exc),
                        )
                if error:
                    _LOGGER.debug(
                        "error in sensor %s - %s - %s", name, error_type, error_msg
                    )

                if error_type != "NOT_FOUND":
                    device_sensors[name] = AmazonDeviceSensor(
                        name,
                        value,
                        error,
                        error_type,
                        error_msg,
                        scale,
                    )

        return device_sensors

    async def _get_devices_endpoint_data(self) -> dict[str, dict[str, Any]]:
        """Get Devices endpoint data."""
        payload = {
            "operationName": "getDevicesBaseData",
            "query": QUERY_DEVICE_DATA,
        }

        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_NEXUS_GRAPHQL}",
            input_data=payload,
            json_data=True,
        )

        endpoint_data = await self._http_wrapper.response_to_json(raw_resp, "endpoint")

        if not (data := endpoint_data.get("data")) or not data.get("listEndpoints"):
            await self._format_human_error(endpoint_data)
            return {}

        endpoints = data["listEndpoints"]
        devices_endpoints: dict[str, dict[str, Any]] = {}
        for endpoint in endpoints.get("endpoints"):
            # save looking up sensor data on apps
            if endpoint.get("alexaEnabledMetadata", {}).get("category") == "APP":
                continue

            if endpoint.get("serialNumber"):
                serial_number = endpoint["serialNumber"]["value"]["text"]
                devices_endpoints[serial_number] = endpoint
                self._endpoints[endpoint["endpointId"]] = serial_number

        return devices_endpoints

    async def get_devices_data(
        self,
    ) -> dict[str, AmazonDevice]:
        """Get Amazon devices data."""
        delta_devices = datetime.now(UTC) - self._last_devices_refresh
        if delta_devices >= timedelta(days=1):
            _LOGGER.debug(
                "Refreshing devices data after %s",
                str(timedelta(minutes=round(delta_devices.total_seconds() / 60))),
            )
            # Request base device data
            await self._get_base_devices()
            self._last_devices_refresh = datetime.now(UTC)

        # Only refresh endpoint data if we have no endpoints yet
        delta_endpoints = datetime.now(UTC) - self._last_endpoint_refresh
        endpoint_refresh_needed = delta_endpoints >= timedelta(days=1)
        endpoints_recently_checked = delta_endpoints < timedelta(minutes=30)
        if (
            not self._endpoints and not endpoints_recently_checked
        ) or endpoint_refresh_needed:
            _LOGGER.debug(
                "Refreshing endpoint data after %s",
                str(timedelta(minutes=round(delta_endpoints.total_seconds() / 60))),
            )
            # Set device endpoint data
            await self._set_device_endpoints_data()
            self._last_endpoint_refresh = datetime.now(UTC)

        await self._get_sensor_data()

        return self._final_devices

    async def _get_sensor_data(self) -> None:
        devices_sensors = await self._get_sensors_states()
        dnd_sensors = await self._dnd_handler.get_do_not_disturb_status()
        notifications = await self._notification_handler.get_notifications()
        for device in self._final_devices.values():
            # Update sensors
            sensors = devices_sensors.get(device.serial_number, {})
            if sensors:
                device.sensors = sensors
            else:
                for device_sensor in device.sensors.values():
                    device_sensor.error = True
            if (
                device_dnd := dnd_sensors.get(device.serial_number)
            ) and device.device_family != SPEAKER_GROUP_FAMILY:
                device.sensors["dnd"] = device_dnd

            if notifications is None:
                continue  # notifications were not obtained, do not update

            # Clear old notifications to handle cancelled ones
            device.notifications = {}

            # Update notifications
            device_notifications = notifications.get(device.serial_number, {})

            # Add only supported notification types
            for capability, notification_type in [
                ("REMINDERS", NOTIFICATION_REMINDER),
                ("TIMERS_AND_ALARMS", NOTIFICATION_ALARM),
                ("TIMERS_AND_ALARMS", NOTIFICATION_TIMER),
            ]:
                if (
                    capability in device.capabilities
                    and notification_type in device_notifications
                    and (
                        notification_object := device_notifications.get(
                            notification_type
                        )
                    )
                ):
                    device.notifications[notification_type] = notification_object

    async def _set_device_endpoints_data(self) -> None:
        """Set device endpoint data."""
        devices_endpoints = await self._get_devices_endpoint_data()
        for serial_number in self._final_devices:
            device_endpoint = devices_endpoints.get(serial_number, {})
            endpoint_device = self._final_devices[serial_number]
            endpoint_device.entity_id = (
                device_endpoint["legacyIdentifiers"]["chrsIdentifier"]["entityId"]
                if device_endpoint
                else None
            )
            endpoint_device.endpoint_id = (
                device_endpoint["endpointId"] if device_endpoint else None
            )

    async def _get_base_devices(self) -> None:
        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.GET,
            url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_DEVICES}",
        )

        json_data = await self._http_wrapper.response_to_json(raw_resp, "devices")

        final_devices_list: dict[str, AmazonDevice] = {}
        serial_to_device_type: dict[str, str] = {}
        for device in json_data["devices"]:
            # Remove stale, orphaned and virtual devices
            if not device or (device.get("deviceType") in DEVICE_TO_IGNORE):
                continue

            account_name: str = device["accountName"]
            capabilities: list[str] = device["capabilities"]
            # Skip devices that cannot be used with voice features
            if "MICROPHONE" not in capabilities:
                _LOGGER.debug(
                    "Skipping device without microphone capabilities: %s", account_name
                )
                continue

            serial_number: str = device["serialNumber"]

            final_devices_list[serial_number] = AmazonDevice(
                account_name=account_name,
                capabilities=capabilities,
                device_family=device["deviceFamily"],
                device_type=device["deviceType"],
                device_owner_customer_id=device["deviceOwnerCustomerId"],
                household_device=device["deviceOwnerCustomerId"]
                == self._session_state_data.account_customer_id,
                device_cluster_members=dict.fromkeys(
                    device["clusterMembers"] or [serial_number]
                ),
                online=device["online"],
                serial_number=serial_number,
                software_version=device["softwareVersion"],
                entity_id=None,
                endpoint_id=None,
                sensors={},
                notifications={},
            )

            serial_to_device_type[serial_number] = device["deviceType"]

        # backfill device types for cluster members
        for device in final_devices_list.values():
            for member_serial in device.device_cluster_members:
                device.device_cluster_members[member_serial] = (
                    serial_to_device_type.get(member_serial)
                )

        self._final_devices = final_devices_list

    def get_model_details(self, device: AmazonDevice) -> dict[str, str | None] | None:
        """Return model datails."""
        model_details: dict[str, str | None] | None = DEVICE_TYPE_TO_MODEL.get(
            device.device_type
        )
        if not model_details:
            _LOGGER.warning(
                "Unknown device type '%s' for %s: please read https://github.com/chemelli74/aioamazondevices/wiki/Unknown-Device-Types",
                device.device_type,
                device.account_name,
            )

        return model_details

    async def call_alexa_speak(
        self,
        device: AmazonDevice,
        text_to_speak: str,
    ) -> None:
        """Call Alexa.Speak to send a message."""
        await self._sequence_handler.send_message(
            device, AmazonSequenceType.Speak, text_to_speak
        )

    async def call_alexa_announcement(
        self,
        device: AmazonDevice,
        text_to_announce: str,
    ) -> None:
        """Call AlexaAnnouncement to send a message."""
        await self._sequence_handler.send_message(
            device, AmazonSequenceType.Announcement, text_to_announce
        )

    async def call_alexa_sound(
        self,
        device: AmazonDevice,
        sound_name: str,
    ) -> None:
        """Call Alexa.Sound to play sound."""
        await self._sequence_handler.send_message(
            device, AmazonSequenceType.Sound, sound_name
        )

    async def call_alexa_music(
        self,
        device: AmazonDevice,
        search_phrase: str,
        music_source: AmazonMusicSource,
    ) -> None:
        """Call Alexa.Music.PlaySearchPhrase to play music."""
        await self._sequence_handler.send_message(
            device, AmazonSequenceType.Music, search_phrase, music_source
        )

    async def call_alexa_text_command(
        self,
        device: AmazonDevice,
        text_command: str,
    ) -> None:
        """Call Alexa.TextCommand to issue command."""
        await self._sequence_handler.send_message(
            device, AmazonSequenceType.TextCommand, text_command
        )

    async def call_alexa_skill(
        self,
        device: AmazonDevice,
        skill_name: str,
    ) -> None:
        """Call Alexa.LaunchSkill to launch a skill."""
        await self._sequence_handler.send_message(
            device, AmazonSequenceType.LaunchSkill, skill_name
        )

    async def call_alexa_info_skill(
        self,
        device: AmazonDevice,
        info_skill_name: str,
    ) -> None:
        """Call Info skill.  See ALEXA_INFO_SKILLS . const."""
        await self._sequence_handler.send_message(device, info_skill_name, "")

    async def _format_human_error(self, sensors_state: dict) -> bool:
        """Format human readable error from malformed data."""
        if sensors_state.get(ARRAY_WRAPPER):
            error = sensors_state[ARRAY_WRAPPER][0].get("errors", [])
        else:
            error = sensors_state.get("errors", [])

        if not error:
            return False

        msg = error[0].get("message", "Unknown error")
        path = error[0].get("path", "Unknown path")
        _LOGGER.error("Error retrieving devices state: %s for path %s", msg, path)
        return True

    async def set_do_not_disturb(self, device: AmazonDevice, enable: bool) -> None:
        """Set Do Not Disturb status for a device."""
        await self._dnd_handler.set_do_not_disturb(device, enable)
