"""Module to handle Alexa sequence operations."""

from http import HTTPMethod
from typing import Any

import orjson

from aioamazondevices.const.metadata import ALEXA_INFO_SKILLS, SEQUENCE_BATCH_DELAY
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.implementation.sequence_batcher import SequenceBatcher
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
        self._sequence_batcher = SequenceBatcher(
            batch_delay=SEQUENCE_BATCH_DELAY,
            send_callback=self._send_sequences,
        )

    async def _send_sequences(self, operation_nodes: list[dict[str, Any]]) -> None:
        """Send batched sequence operations to Amazon API.

        Args:
            operation_nodes: List of operation nodes to execute in sequence

        """
        if not self._session_state_data.login_stored_data:
            _LOGGER.warning("No login data available, cannot send sequences")
            return

        sequence = {
            "@type": "com.amazon.alexa.behaviors.model.Sequence",
            "startNode": {
                "@type": "com.amazon.alexa.behaviors.model.SerialNode",
                "nodesToExecute": operation_nodes,
            },
        }

        node_data = {
            "behaviorId": "PREVIEW",
            "sequenceJson": orjson.dumps(sequence).decode("utf-8"),
            "status": "ENABLED",
        }

        _LOGGER.debug("Sending sequence with %s operations", len(operation_nodes))
        await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=f"https://alexa.amazon.{self._session_state_data.domain}/api/behaviors/preview",
            input_data=node_data,
            json_data=True,
        )

    async def _build_operation_node(
        self,
        device: AmazonDevice,
        message_type: str,
        message_body: str | float | None = None,
        message_source: AmazonMusicSource | None = None,
    ) -> dict[str, Any]:
        """Send message to specific device."""
        if not self._session_state_data.login_stored_data:
            _LOGGER.warning("No login data available, cannot send message")
            return {}

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
                    "uri": "connection://AMAZON.Launch/" + str(message_body),
                },
            }
        elif message_type in ALEXA_INFO_SKILLS:
            payload = {
                **base_payload,
            }
        else:
            raise ValueError(f"Message type <{message_type}> is not recognised")

        return {
            "@type": "com.amazon.alexa.behaviors.model.OpaquePayloadOperationNode",
            "type": message_type,
            "operationPayload": payload,
        }

    async def call_alexa_speak(
        self,
        device: AmazonDevice,
        text_to_speak: str,
    ) -> None:
        """Call Alexa.Speak to send a message."""
        node = await self._build_operation_node(
            device, AmazonSequenceType.Speak, text_to_speak
        )
        await self._sequence_batcher.enqueue(node)

    async def call_alexa_announcement(
        self,
        device: AmazonDevice,
        text_to_announce: str,
    ) -> None:
        """Call AlexaAnnouncement to send a message."""
        node = await self._build_operation_node(
            device, AmazonSequenceType.Announcement, text_to_announce
        )
        await self._sequence_batcher.enqueue(node)

    async def call_alexa_sound(
        self,
        device: AmazonDevice,
        sound_name: str,
    ) -> None:
        """Call Alexa.Sound to play sound."""
        node = await self._build_operation_node(
            device, AmazonSequenceType.Sound, sound_name
        )
        await self._sequence_batcher.enqueue(node)

    async def call_alexa_music(
        self,
        device: AmazonDevice,
        search_phrase: str,
        music_source: AmazonMusicSource,
    ) -> None:
        """Call Alexa.Music.PlaySearchPhrase to play music."""
        node = await self._build_operation_node(
            device, AmazonSequenceType.Music, search_phrase, music_source
        )
        await self._sequence_batcher.enqueue(node)

    async def call_alexa_text_command(
        self,
        device: AmazonDevice,
        text_command: str,
    ) -> None:
        """Call Alexa.TextCommand to issue command."""
        node = await self._build_operation_node(
            device, AmazonSequenceType.TextCommand, text_command
        )
        await self._sequence_batcher.enqueue(node)

    async def call_alexa_skill(
        self,
        device: AmazonDevice,
        skill_name: str,
    ) -> None:
        """Call Alexa.LaunchSkill to launch a skill."""
        node = await self._build_operation_node(
            device, AmazonSequenceType.LaunchSkill, skill_name
        )
        await self._sequence_batcher.enqueue(node)

    async def call_alexa_info_skill(
        self,
        device: AmazonDevice,
        info_skill_name: str,
    ) -> None:
        """Call Info skill.  See ALEXA_INFO_SKILLS . const."""
        node = await self._build_operation_node(device, info_skill_name)
        await self._sequence_batcher.enqueue(node)
