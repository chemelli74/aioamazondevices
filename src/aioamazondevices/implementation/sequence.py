"""Module to handle Alexa sequence operations."""

from collections.abc import Generator
from http import HTTPMethod
from itertools import groupby
from typing import Any

import orjson

from aioamazondevices.const.metadata import ALEXA_INFO_SKILLS, SEQUENCE_BATCH_DELAY
from aioamazondevices.exceptions import CannotConnect
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.implementation.sequence_batcher import SequenceBatcher
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonMusicSource,
    AmazonSequenceNode,
    AmazonSequenceType,
)
from aioamazondevices.utils import _LOGGER


class AmazonSequenceHandler:
    """Class to handle Alexa sequence (routine) operations."""

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

    async def _send_sequences(self, sequences: list[AmazonSequenceNode]) -> None:
        """Send batched sequence operations to Amazon API.

        Args:
            sequences: List of sequence nodes to execute in sequence

        """
        if not self._session_state_data.login_stored_data:
            _LOGGER.warning("No login data available, cannot send sequences")
            return

        operation_nodes = list(self._optimise_sequence_nodes(sequences))

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

        _LOGGER.debug("Sending sequence with %s operations", len(sequences))
        await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=f"https://alexa.amazon.{self._session_state_data.domain}/api/behaviors/preview",
            input_data=node_data,
            json_data=True,
        )

    def _optimise_sequence_nodes(
        self, sequences: list[AmazonSequenceNode]
    ) -> Generator[dict[str, Any], None, None]:
        """Optimise sequence nodes by wrapping similar operations in parallel nodes.

        Args:
            sequences: List of sequence nodes to optimise

        """
        # list will be in the order nodes were added
        # group by message type, body and source to find similar operations
        # then wrap in parallel node if from different devices
        for _, group_iter in groupby(
            sequences,
            key=lambda x: (x.message_type, x.message_body, x.message_source),
        ):
            group = list(group_iter)
            if len(group) > 1 and len(
                {sequence.device.serial_number for sequence in group}
            ) == len(group):
                yield {
                    "@type": "com.amazon.alexa.behaviors.model.ParallelNode",
                    "nodesToExecute": [sequence.operation_node for sequence in group],
                }
            else:
                yield from (sequence.operation_node for sequence in group)

    def _build_operation_node(
        self,
        device: AmazonDevice,
        message_type: str,
        message_body: str | float | None = None,
        message_source: AmazonMusicSource | None = None,
    ) -> dict[str, Any]:
        """Convert message to operation node."""
        if not self._session_state_data.login_stored_data:
            _LOGGER.warning("No login data available, cannot send message")
            raise CannotConnect(
                "Cannot perform %s action on %s as not logged in",
                message_type,
                device.serial_number,
            )

        base_payload = {
            "deviceType": device.device_type,
            "deviceSerialNumber": device.serial_number,
            "locale": self._session_state_data.language,
            "customerId": self._session_state_data.account_customer_id,
        }

        payload: dict[str, Any]
        if message_type == AmazonSequenceType.Speak:
            payload = {
                **base_payload,
                "textToSpeak": message_body,
                "target": {
                    "customerId": self._session_state_data.account_customer_id,
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
                    "customerId": self._session_state_data.account_customer_id,
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

    async def send_message(
        self,
        device: AmazonDevice,
        message_type: str,
        message_body: str | float | None = None,
        message_source: AmazonMusicSource | None = None,
    ) -> None:
        """Send message to specific device."""
        node = self._build_operation_node(
            device, message_type, message_body, message_source
        )
        await self._sequence_batcher.enqueue(
            AmazonSequenceNode(
                message_type=message_type,
                message_body=message_body,
                message_source=message_source,
                device=device,
                operation_node=node,
            )
        )
