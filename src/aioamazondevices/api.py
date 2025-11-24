"""Support for Amazon devices."""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from http import HTTPMethod
from typing import Any

import orjson
from aiohttp import ClientSession
from dateutil.parser import parse
from dateutil.rrule import rrulestr

from . import __version__
from .const.devices import (
    DEVICE_TO_IGNORE,
    DEVICE_TYPE_TO_MODEL,
    SPEAKER_GROUP_FAMILY,
)
from .const.http import (
    AMAZON_DEVICE_TYPE,
    ARRAY_WRAPPER,
    DEFAULT_SITE,
    URI_DEVICES,
    URI_DND,
    URI_NEXUS_GRAPHQL,
    URI_NOTIFICATIONS,
)
from .const.metadata import ALEXA_INFO_SKILLS, SENSORS
from .const.queries import QUERY_DEVICE_DATA, QUERY_SENSOR_STATE
from .const.schedules import (
    COUNTRY_GROUPS,
    NOTIFICATION_ALARM,
    NOTIFICATION_MUSIC_ALARM,
    NOTIFICATION_REMINDER,
    NOTIFICATION_TIMER,
    NOTIFICATIONS_SUPPORTED,
    RECURRING_PATTERNS,
    WEEKEND_EXCEPTIONS,
)
from .exceptions import (
    CannotRetrieveData,
)
from .http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from .login import AmazonLogin
from .structures import (
    AmazonDevice,
    AmazonDeviceSensor,
    AmazonMusicSource,
    AmazonSchedule,
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

        self._account_owner_customer_id: str | None = None
        self._list_for_clusters: dict[str, str] = {}

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

    async def _get_notifications(self) -> dict[str, dict[str, AmazonSchedule]] | None:
        final_notifications: dict[str, dict[str, AmazonSchedule]] = {}

        try:
            _, raw_resp = await self._http_wrapper.session_request(
                HTTPMethod.GET,
                url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_NOTIFICATIONS}",
            )
        except CannotRetrieveData:
            _LOGGER.warning(
                "Failed to obtain notification data.  Timers and alarms have not been updated"  # noqa: E501
            )
            return None

        notifications = await self._http_wrapper.response_to_json(
            raw_resp, "notifications"
        )

        for schedule in notifications["notifications"]:
            schedule_type: str = schedule["type"]
            schedule_device_serial = schedule["deviceSerialNumber"]

            if schedule_device_serial in DEVICE_TO_IGNORE:
                continue

            if schedule_type not in NOTIFICATIONS_SUPPORTED:
                _LOGGER.debug(
                    "Unsupported schedule type %s for device %s",
                    schedule_type,
                    schedule_device_serial,
                )
                continue

            if schedule_type == NOTIFICATION_MUSIC_ALARM:
                # Structure is the same as standard Alarm
                schedule_type = NOTIFICATION_ALARM
                schedule["type"] = NOTIFICATION_ALARM
            label_desc = schedule_type.lower() + "Label"
            if (schedule_status := schedule["status"]) == "ON" and (
                next_occurrence := await self._parse_next_occurence(schedule)
            ):
                schedule_notification_list = final_notifications.get(
                    schedule_device_serial, {}
                )
                schedule_notification_by_type = schedule_notification_list.get(
                    schedule_type
                )
                # Replace if no existing notification
                # or if existing.next_occurrence is None
                # or if new next_occurrence is earlier
                if (
                    not schedule_notification_by_type
                    or schedule_notification_by_type.next_occurrence is None
                    or next_occurrence < schedule_notification_by_type.next_occurrence
                ):
                    final_notifications.update(
                        {
                            schedule_device_serial: {
                                **schedule_notification_list
                                | {
                                    schedule_type: AmazonSchedule(
                                        type=schedule_type,
                                        status=schedule_status,
                                        label=schedule[label_desc],
                                        next_occurrence=next_occurrence,
                                    ),
                                }
                            }
                        }
                    )

        return final_notifications

    async def _parse_next_occurence(
        self,
        schedule: dict[str, Any],
    ) -> datetime | None:
        """Parse RFC5545 rule set for next iteration."""
        # Local timezone
        tzinfo = datetime.now().astimezone().tzinfo
        # Current time
        actual_time = datetime.now(tz=tzinfo)
        # Reference start date
        today_midnight = actual_time.replace(hour=0, minute=0, second=0, microsecond=0)
        # Reference time (1 minute ago to avoid edge cases)
        now_reference = actual_time - timedelta(minutes=1)

        # Schedule data
        original_date = schedule.get("originalDate")
        original_time = schedule.get("originalTime")

        recurring_rules: list[str] = []
        if schedule.get("rRuleData"):
            recurring_rules = schedule["rRuleData"]["recurrenceRules"]
        if schedule.get("recurringPattern"):
            recurring_rules.append(schedule["recurringPattern"])

        # Recurring events
        if recurring_rules:
            next_candidates: list[datetime] = []
            for recurring_rule in recurring_rules:
                # Already in RFC5545 format
                if "FREQ=" in recurring_rule:
                    rule = await self._add_hours_minutes(recurring_rule, original_time)

                    # Add date to candidates list
                    next_candidates.append(
                        rrulestr(rule, dtstart=today_midnight).after(
                            now_reference, True
                        ),
                    )
                    continue

                if recurring_rule not in RECURRING_PATTERNS:
                    _LOGGER.warning(
                        "Unknown recurring rule <%s> for schedule type <%s>",
                        recurring_rule,
                        schedule["type"],
                    )
                    return None

                # Adjust recurring rules for country specific weekend exceptions
                recurring_pattern = RECURRING_PATTERNS.copy()
                for group, countries in COUNTRY_GROUPS.items():
                    if self._session_state_data.country_code in countries:
                        recurring_pattern |= WEEKEND_EXCEPTIONS[group]
                        break

                rule = await self._add_hours_minutes(
                    recurring_pattern[recurring_rule], original_time
                )

                # Add date to candidates list
                next_candidates.append(
                    rrulestr(rule, dtstart=today_midnight).after(now_reference, True),
                )

            return min(next_candidates) if next_candidates else None

        # Single events
        if schedule["type"] == NOTIFICATION_ALARM:
            timestamp = parse(f"{original_date} {original_time}").replace(tzinfo=tzinfo)

        elif schedule["type"] == NOTIFICATION_TIMER:
            # API returns triggerTime in milliseconds since epoch
            timestamp = datetime.fromtimestamp(
                schedule["triggerTime"] / 1000, tz=tzinfo
            )

        elif schedule["type"] == NOTIFICATION_REMINDER:
            # API returns alarmTime in milliseconds since epoch
            timestamp = datetime.fromtimestamp(schedule["alarmTime"] / 1000, tz=tzinfo)

        else:
            _LOGGER.warning(("Unknown schedule type: %s"), schedule["type"])
            return None

        if timestamp > now_reference:
            return timestamp

        return None

    async def _add_hours_minutes(
        self,
        recurring_rule: str,
        original_time: str | None,
    ) -> str:
        """Add hours and minutes to a RFC5545 string."""
        rule = recurring_rule.removesuffix(";")

        if not original_time:
            return rule

        # Add missing BYHOUR, BYMINUTE if needed (Alarms only)
        if "BYHOUR=" not in recurring_rule:
            hour = int(original_time.split(":")[0])
            rule += f";BYHOUR={hour}"
        if "BYMINUTE=" not in recurring_rule:
            minute = int(original_time.split(":")[1])
            rule += f";BYMINUTE={minute}"

        return rule

    async def _get_account_owner_customer_id(self, data: dict[str, Any]) -> str | None:
        """Get account owner customer ID."""
        if data["deviceType"] != AMAZON_DEVICE_TYPE:
            return None

        account_owner_customer_id: str | None = None

        this_device_serial = self._session_state_data.login_stored_data["device_info"][
            "device_serial_number"
        ]

        for subdevice in data["appDeviceList"]:
            if subdevice["serialNumber"] == this_device_serial:
                account_owner_customer_id = data["deviceOwnerCustomerId"]
                _LOGGER.debug(
                    "Setting account owner: %s",
                    account_owner_customer_id,
                )
                break

        return account_owner_customer_id

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
        dnd_sensors = await self._get_dnd_status()

        notifications = await self._get_notifications()

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

        for data in json_data["devices"]:
            dev_serial = data.get("serialNumber")
            if not dev_serial:
                _LOGGER.warning(
                    "Skipping device without serial number: %s", data["accountName"]
                )
                continue
            if not self._account_owner_customer_id:
                self._account_owner_customer_id = (
                    await self._get_account_owner_customer_id(data)
                )

        if not self._account_owner_customer_id:
            raise CannotRetrieveData("Cannot find account owner customer ID")

        final_devices_list: dict[str, AmazonDevice] = {}
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
                == self._account_owner_customer_id,
                device_cluster_members=(device["clusterMembers"] or [serial_number]),
                online=device["online"],
                serial_number=serial_number,
                software_version=device["softwareVersion"],
                entity_id=None,
                endpoint_id=None,
                sensors={},
                notifications={},
            )

        self._list_for_clusters.update(
            {
                device.serial_number: device.device_type
                for device in final_devices_list.values()
            }
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

    async def _send_message(
        self,
        device: AmazonDevice,
        message_type: str,
        message_body: str,
        message_source: AmazonMusicSource | None = None,
    ) -> None:
        """Send message to specific device."""
        if not self._session_state_data.login_stored_data:
            _LOGGER.warning("No login data available, cannot send message")
            return

        base_payload = {
            "deviceType": device.device_type,
            "deviceSerialNumber": device.serial_number,
            "locale": self._session_state_data.language,
            "customerId": self._account_owner_customer_id,
        }

        payload: dict[str, Any]
        if message_type == AmazonSequenceType.Speak:
            payload = {
                **base_payload,
                "textToSpeak": message_body,
                "target": {
                    "customerId": self._account_owner_customer_id,
                    "devices": [
                        {
                            "deviceSerialNumber": device.serial_number,
                            "deviceTypeId": device.device_type,
                        },
                    ],
                },
                "skillId": "amzn1.ask.1p.saysomething",
            }
        elif message_type == AmazonSequenceType.Announcement:
            playback_devices: list[dict[str, str]] = [
                {
                    "deviceSerialNumber": serial,
                    "deviceTypeId": self._list_for_clusters[serial],
                }
                for serial in device.device_cluster_members
                if serial in self._list_for_clusters
            ]

            payload = {
                **base_payload,
                "expireAfter": "PT5S",
                "content": [
                    {
                        "locale": self._session_state_data.language,
                        "display": {
                            "title": "Home Assistant",
                            "body": message_body,
                        },
                        "speak": {
                            "type": "text",
                            "value": message_body,
                        },
                    }
                ],
                "target": {
                    "customerId": self._account_owner_customer_id,
                    "devices": playback_devices,
                },
                "skillId": "amzn1.ask.1p.routines.messaging",
            }
        elif message_type == AmazonSequenceType.Sound:
            payload = {
                **base_payload,
                "soundStringId": message_body,
                "skillId": "amzn1.ask.1p.sound",
            }
        elif message_type == AmazonSequenceType.Music:
            payload = {
                **base_payload,
                "searchPhrase": message_body,
                "sanitizedSearchPhrase": message_body,
                "musicProviderId": message_source,
            }
        elif message_type == AmazonSequenceType.TextCommand:
            payload = {
                **base_payload,
                "skillId": "amzn1.ask.1p.tellalexa",
                "text": message_body,
            }
        elif message_type == AmazonSequenceType.LaunchSkill:
            payload = {
                **base_payload,
                "targetDevice": {
                    "deviceType": device.device_type,
                    "deviceSerialNumber": device.serial_number,
                },
                "connectionRequest": {
                    "uri": "connection://AMAZON.Launch/" + message_body,
                },
            }
        elif message_type in ALEXA_INFO_SKILLS:
            payload = {
                **base_payload,
            }
        else:
            raise ValueError(f"Message type <{message_type}> is not recognised")

        sequence = {
            "@type": "com.amazon.alexa.behaviors.model.Sequence",
            "startNode": {
                "@type": "com.amazon.alexa.behaviors.model.SerialNode",
                "nodesToExecute": [
                    {
                        "@type": "com.amazon.alexa.behaviors.model.OpaquePayloadOperationNode",  # noqa: E501
                        "type": message_type,
                        "operationPayload": payload,
                    },
                ],
            },
        }

        node_data = {
            "behaviorId": "PREVIEW",
            "sequenceJson": orjson.dumps(sequence).decode("utf-8"),
            "status": "ENABLED",
        }

        _LOGGER.debug("Preview data payload: %s", node_data)
        await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=f"https://alexa.amazon.{self._session_state_data.domain}/api/behaviors/preview",
            input_data=node_data,
            json_data=True,
        )

        return

    async def call_alexa_speak(
        self,
        device: AmazonDevice,
        message_body: str,
    ) -> None:
        """Call Alexa.Speak to send a message."""
        return await self._send_message(device, AmazonSequenceType.Speak, message_body)

    async def call_alexa_announcement(
        self,
        device: AmazonDevice,
        message_body: str,
    ) -> None:
        """Call AlexaAnnouncement to send a message."""
        return await self._send_message(
            device, AmazonSequenceType.Announcement, message_body
        )

    async def call_alexa_sound(
        self,
        device: AmazonDevice,
        message_body: str,
    ) -> None:
        """Call Alexa.Sound to play sound."""
        return await self._send_message(device, AmazonSequenceType.Sound, message_body)

    async def call_alexa_music(
        self,
        device: AmazonDevice,
        message_body: str,
        message_source: AmazonMusicSource,
    ) -> None:
        """Call Alexa.Music.PlaySearchPhrase to play music."""
        return await self._send_message(
            device, AmazonSequenceType.Music, message_body, message_source
        )

    async def call_alexa_text_command(
        self,
        device: AmazonDevice,
        message_body: str,
    ) -> None:
        """Call Alexa.TextCommand to issue command."""
        return await self._send_message(
            device, AmazonSequenceType.TextCommand, message_body
        )

    async def call_alexa_skill(
        self,
        device: AmazonDevice,
        message_body: str,
    ) -> None:
        """Call Alexa.LaunchSkill to launch a skill."""
        return await self._send_message(
            device, AmazonSequenceType.LaunchSkill, message_body
        )

    async def call_alexa_info_skill(
        self,
        device: AmazonDevice,
        message_type: str,
    ) -> None:
        """Call Info skill.  See ALEXA_INFO_SKILLS . const."""
        return await self._send_message(device, message_type, "")

    async def set_do_not_disturb(self, device: AmazonDevice, state: bool) -> None:
        """Set do_not_disturb flag."""
        payload = {
            "deviceSerialNumber": device.serial_number,
            "deviceType": device.device_type,
            "enabled": state,
        }
        url = f"https://alexa.amazon.{self._session_state_data.domain}/api/dnd/status"
        await self._http_wrapper.session_request(
            method="PUT",
            url=url,
            input_data=payload,
            json_data=True,
        )

    async def _get_dnd_status(self) -> dict[str, AmazonDeviceSensor]:
        dnd_status: dict[str, AmazonDeviceSensor] = {}
        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.GET,
            url=f"https://alexa.amazon.{self._session_state_data.domain}{URI_DND}",
        )

        dnd_data = await self._http_wrapper.response_to_json(raw_resp, "dnd")

        for dnd in dnd_data.get("doNotDisturbDeviceStatusList", {}):
            dnd_status[dnd.get("deviceSerialNumber")] = AmazonDeviceSensor(
                name="dnd",
                value=dnd.get("enabled"),
                error=False,
                error_type=None,
                error_msg=None,
                scale=None,
            )
        return dnd_status

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
