"""Module to handle Alexa sequence operations."""

from http import HTTPMethod
from typing import Any

import orjson

from aioamazondevices.const.metadata import ALEXA_INFO_SKILLS
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonMusicSource,
    AmazonSequenceType,
)
from aioamazondevices.utils import _LOGGER


class AmazonSequenceHandler:
    """Class to handle Alexa sequence operations."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize AmazonSequenceHandler."""
        self._http_wrapper = http_wrapper
        self._session_state_data = session_state_data

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
            "customerId": self._session_state_data.customer_account_id,
        }

        payload: dict[str, Any]
        if message_type == AmazonSequenceType.Speak:
            payload = {
                **base_payload,
                "textToSpeak": message_body,
                "target": {
                    "customerId": self._session_state_data.customer_account_id,
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
            playback_devices: list[dict[str, str | None]] = [
                {
                    "deviceSerialNumber": serial,
                    "deviceTypeId": device.device_cluster_members[serial],
                }
                for serial in device.device_cluster_members
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
                    "customerId": self._session_state_data.customer_account_id,
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
        text_to_speak: str,
    ) -> None:
        """Call Alexa.Speak to send a message."""
        return await self._send_message(device, AmazonSequenceType.Speak, text_to_speak)

    async def call_alexa_announcement(
        self,
        device: AmazonDevice,
        text_to_announce: str,
    ) -> None:
        """Call AlexaAnnouncement to send a message."""
        return await self._send_message(
            device, AmazonSequenceType.Announcement, text_to_announce
        )

    async def call_alexa_sound(
        self,
        device: AmazonDevice,
        sound_name: str,
    ) -> None:
        """Call Alexa.Sound to play sound."""
        return await self._send_message(device, AmazonSequenceType.Sound, sound_name)

    async def call_alexa_music(
        self,
        device: AmazonDevice,
        search_phrase: str,
        music_source: AmazonMusicSource,
    ) -> None:
        """Call Alexa.Music.PlaySearchPhrase to play music."""
        return await self._send_message(
            device, AmazonSequenceType.Music, search_phrase, music_source
        )

    async def call_alexa_text_command(
        self,
        device: AmazonDevice,
        text_command: str,
    ) -> None:
        """Call Alexa.TextCommand to issue command."""
        return await self._send_message(
            device, AmazonSequenceType.TextCommand, text_command
        )

    async def call_alexa_skill(
        self,
        device: AmazonDevice,
        skill_name: str,
    ) -> None:
        """Call Alexa.LaunchSkill to launch a skill."""
        return await self._send_message(
            device, AmazonSequenceType.LaunchSkill, skill_name
        )

    async def call_alexa_info_skill(
        self,
        device: AmazonDevice,
        info_skill_name: str,
    ) -> None:
        """Call Info skill.  See ALEXA_INFO_SKILLS . const."""
        return await self._send_message(device, info_skill_name, "")
