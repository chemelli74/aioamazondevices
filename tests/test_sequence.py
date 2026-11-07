# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Alexa sequence handler and the API calls that use it."""

import asyncio
from collections.abc import Callable
from http import HTTPMethod
from typing import Any
from unittest.mock import AsyncMock, call

import orjson
import pytest
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import ARRAY_WRAPPER, URI_BEHAVIORS_PREVIEW
from aioamazondevices.const.metadata import ALEXA_INFO_SKILLS
from aioamazondevices.exceptions import CannotConnect
from aioamazondevices.implementation import sequence
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonSequenceNode,
    AmazonSequenceType,
)

from .const import TEST_SERIAL_1, TEST_SERIAL_2

TEST_CUSTOMER_ID = "CUSTOMER_ID"
TEST_PROVIDER_ID = "AMAZON_MUSIC"
TEST_SERIAL_GROUP = "GROUP-1"
OPAQUE_NODE = "com.amazon.alexa.behaviors.model.OpaquePayloadOperationNode"
PARALLEL_NODE = "com.amazon.alexa.behaviors.model.ParallelNode"


@pytest.fixture
def device(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> AmazonDevice:
    """Log in and return a device."""
    api._session_state_data.login_stored_data = {
        "account_customer_id": TEST_CUSTOMER_ID
    }
    return make_device(TEST_SERIAL_1)


@pytest.fixture
def post_sequences(api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Send batches immediately and replace posting them, returning the mock."""
    monkeypatch.setattr(sequence, "SEQUENCE_BATCH_DELAY", 0)
    post_sequences = AsyncMock()
    monkeypatch.setattr(api._sequence_handler, "_post_sequences", post_sequences)
    return post_sequences


@pytest.fixture
def send_message(api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Replace the sequence handler's send_message and return the mock."""
    send_message = AsyncMock()
    monkeypatch.setattr(api._sequence_handler, "send_message", send_message)
    return send_message


@pytest.fixture
def speaker_group(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> AmazonDevice:
    """Register two member devices and return a speaker group containing them."""
    group = make_device(TEST_SERIAL_GROUP)
    group.device_cluster_members = {TEST_SERIAL_1: None, TEST_SERIAL_2: None}
    api._device_handler._final_devices = {
        TEST_SERIAL_1: make_device(TEST_SERIAL_1),
        TEST_SERIAL_2: make_device(TEST_SERIAL_2),
        TEST_SERIAL_GROUP: group,
    }
    return group


def _node(
    device: AmazonDevice, message_type: str, message_body: str
) -> AmazonSequenceNode:
    """Build a sequence node whose operation node identifies its inputs."""
    return AmazonSequenceNode(
        message_type=message_type,
        message_body=message_body,
        music_provider_id=None,
        device=device,
        operation_node={"device": device.serial_number, "body": message_body},
    )


async def _wait_for_batches(api: AmazonEchoApi) -> None:
    """Wait for all pending batches to be processed."""
    await asyncio.gather(*api._sequence_handler._tasks)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message_type", "message_body", "expected"),
    [
        pytest.param(
            AmazonSequenceType.Speak,
            "Hello",
            {
                "textToSpeak": "Hello",
                "target": {
                    "customerId": TEST_CUSTOMER_ID,
                    "devices": [
                        {"deviceSerialNumber": TEST_SERIAL_1, "deviceTypeId": "A1B2C3"}
                    ],
                },
                "skillId": "amzn1.ask.1p.saysomething",
            },
            id="speak",
        ),
        pytest.param(
            AmazonSequenceType.Sound,
            "bell_02",
            {"soundStringId": "bell_02", "skillId": "amzn1.ask.1p.sound"},
            id="sound",
        ),
        pytest.param(
            AmazonSequenceType.Music,
            "jazz",
            {
                "searchPhrase": "jazz",
                "sanitizedSearchPhrase": "jazz",
                "musicProviderId": TEST_PROVIDER_ID,
            },
            id="music",
        ),
        pytest.param(
            AmazonSequenceType.TextCommand,
            "turn on the lights",
            {"skillId": "amzn1.ask.1p.tellalexa", "text": "turn on the lights"},
            id="text-command",
        ),
        pytest.param(
            AmazonSequenceType.LaunchSkill,
            "amzn1.ask.skill.123",
            {
                "targetDevice": {
                    "deviceType": "A1B2C3",
                    "deviceSerialNumber": TEST_SERIAL_1,
                },
                "connectionRequest": {
                    "uri": "connection://AMAZON.Launch/amzn1.ask.skill.123"
                },
            },
            id="launch-skill",
        ),
        pytest.param(ALEXA_INFO_SKILLS[0], "", {}, id="info-skill"),
        pytest.param(AmazonSequenceType.Volume, "35", {"value": "35"}, id="volume"),
        pytest.param(
            AmazonSequenceType.Stop,
            "",
            {
                "devices": [
                    {"deviceSerialNumber": TEST_SERIAL_1, "deviceType": "A1B2C3"}
                ],
                "skillId": "amzn1.ask.1p.alexadevicecontrols",
            },
            id="stop",
        ),
    ],
)
async def test_build_operation_node(
    api: AmazonEchoApi,
    device: AmazonDevice,
    message_type: str,
    message_body: str,
    expected: dict[str, Any],
) -> None:
    """Each message type builds its own payload on top of the device details.

    The music provider is passed to every type but used only by music.
    """
    node = api._sequence_handler._build_operation_node(
        device, message_type, message_body, TEST_PROVIDER_ID
    )

    assert node == {
        "@type": OPAQUE_NODE,
        "type": message_type,
        "operationPayload": {
            "deviceType": "A1B2C3",
            "deviceSerialNumber": TEST_SERIAL_1,
            "locale": api._session_state_data.language,
            "customerId": TEST_CUSTOMER_ID,
            **expected,
        },
    }


@pytest.mark.anyio
async def test_build_operation_node_unknown_type_raises(
    api: AmazonEchoApi, device: AmazonDevice
) -> None:
    """An unrecognised message type is rejected."""
    with pytest.raises(ValueError, match="is not recognised"):
        api._sequence_handler._build_operation_node(device, "Alexa.Unknown", "")


@pytest.mark.anyio
async def test_build_operation_node_requires_login(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """A message cannot be built before logging in."""
    with pytest.raises(CannotConnect, match="as not logged in"):
        api._sequence_handler._build_operation_node(
            make_device(TEST_SERIAL_1), AmazonSequenceType.Speak, "Hello"
        )


@pytest.mark.anyio
async def test_build_operation_node_routine_replaces_placeholders(
    api: AmazonEchoApi, device: AmazonDevice
) -> None:
    """A routine's start node is used with its device placeholders filled in."""
    start_node = {
        "nodesToExecute": [
            {
                "operationPayload": {
                    "deviceSerialNumber": "ALEXA_CURRENT_DSN",
                    "deviceType": "ALEXA_CURRENT_DEVICE_TYPE",
                    "text": "Good morning",
                }
            }
        ]
    }
    handler = api._sequence_handler
    handler._routines = {"Morning": {"startNode": start_node}}

    node = handler._build_operation_node(device, AmazonSequenceType.Routines, "Morning")

    assert node == {
        "nodesToExecute": [
            {
                "operationPayload": {
                    "deviceSerialNumber": TEST_SERIAL_1,
                    "deviceType": "A1B2C3",
                    "text": "Good morning",
                }
            }
        ]
    }
    # The stored routine is left unchanged for the next device.
    payload = start_node["nodesToExecute"][0]["operationPayload"]
    assert payload["deviceSerialNumber"] == "ALEXA_CURRENT_DSN"


@pytest.mark.anyio
async def test_update_routines_keeps_enabled_routines(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """Only enabled routines are stored, keyed by name."""
    mock_json_response(
        {
            ARRAY_WRAPPER: [
                {"name": "Morning", "status": "ENABLED", "sequence": {"id": 1}},
                {"name": "Night", "status": "DISABLED", "sequence": {"id": 2}},
                {"name": "Evening", "status": "ENABLED", "sequence": {"id": 3}},
            ]
        }
    )

    await api.update_routines()

    assert api.routines == ["Morning", "Evening"]
    assert api._sequence_handler._routines["Evening"] == {"id": 3}


@pytest.mark.anyio
async def test_update_routines_without_routines(
    api: AmazonEchoApi, mock_json_response: Callable[[dict[str, Any]], AsyncMock]
) -> None:
    """A response with no routines list clears the routines."""
    mock_json_response({})
    api._sequence_handler._routines = {"Morning": {}}

    await api.update_routines()

    assert api.routines == []


@pytest.mark.anyio
async def test_post_sequences_groups_devices_in_parallel(
    api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    make_device: Callable[..., AmazonDevice],
    device: AmazonDevice,
) -> None:
    """The same message to different devices runs in parallel, others in series."""
    session_request = mock_json_response({})
    other_device = make_device(TEST_SERIAL_2)
    nodes = [
        _node(device, AmazonSequenceType.Speak, "Hello"),
        _node(other_device, AmazonSequenceType.Speak, "Hello"),
        _node(device, AmazonSequenceType.Speak, "Goodbye"),
    ]

    await api._sequence_handler._post_sequences(nodes)

    (request,) = session_request.await_args_list
    kwargs = request.kwargs
    assert kwargs["method"] == HTTPMethod.POST
    assert kwargs["url"] == URL.joinpath(
        api._session_state_data.alexa_website_url, URI_BEHAVIORS_PREVIEW
    )
    assert kwargs["json_data"] is True
    input_data = kwargs["input_data"]
    assert input_data["behaviorId"] == "PREVIEW"
    assert input_data["status"] == "ENABLED"
    assert orjson.loads(input_data["sequenceJson"]) == {
        "@type": "com.amazon.alexa.behaviors.model.Sequence",
        "startNode": {
            "@type": "com.amazon.alexa.behaviors.model.SerialNode",
            "nodesToExecute": [
                {
                    "@type": PARALLEL_NODE,
                    "nodesToExecute": [
                        nodes[0].operation_node,
                        nodes[1].operation_node,
                    ],
                },
                nodes[2].operation_node,
            ],
        },
    }


@pytest.mark.anyio
async def test_post_sequences_requires_login(
    api: AmazonEchoApi,
    mock_json_response: Callable[[dict[str, Any]], AsyncMock],
    make_device: Callable[..., AmazonDevice],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Nothing is posted before logging in."""
    session_request = mock_json_response({})

    await api._sequence_handler._post_sequences(
        [_node(make_device(TEST_SERIAL_1), AmazonSequenceType.Speak, "Hello")]
    )

    session_request.assert_not_awaited()
    assert "No login data available, cannot send sequences" in caplog.text


@pytest.mark.anyio
async def test_send_message_batches_messages(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    device: AmazonDevice,
    post_sequences: AsyncMock,
) -> None:
    """Messages sent together are posted as one batch, later ones as another."""
    handler = api._sequence_handler
    other_device = make_device(TEST_SERIAL_2)

    await handler.send_message(device, AmazonSequenceType.Speak, "Hello")
    await handler.send_message(other_device, AmazonSequenceType.Speak, "Hello")
    await _wait_for_batches(api)
    await handler.send_message(device, AmazonSequenceType.Volume, "20")
    await _wait_for_batches(api)

    batches = [batch.args[0] for batch in post_sequences.await_args_list]
    assert [[node.device for node in batch] for batch in batches] == [
        [device, other_device],
        [device],
    ]
    assert batches[1][0] == AmazonSequenceNode(
        message_type=AmazonSequenceType.Volume,
        message_body="20",
        music_provider_id=None,
        device=device,
        operation_node=handler._build_operation_node(
            device, AmazonSequenceType.Volume, "20"
        ),
    )
    assert handler._buffer == []
    assert not handler._batch_pending


@pytest.mark.anyio
async def test_process_batch_logs_failure(
    api: AmazonEchoApi,
    device: AmazonDevice,
    post_sequences: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed post is logged rather than raised, and later batches still run."""
    post_sequences.side_effect = [CannotConnect("boom"), None]
    handler = api._sequence_handler

    await handler.send_message(device, AmazonSequenceType.Speak, "Hello")
    await _wait_for_batches(api)
    await handler.send_message(device, AmazonSequenceType.Speak, "Again")
    await _wait_for_batches(api)

    assert "Failed to send batch of 1 operations" in caplog.text
    assert [
        [node.message_body for node in batch.args[0]]
        for batch in post_sequences.await_args_list
    ] == [["Hello"], ["Again"]]


@pytest.mark.anyio
async def test_process_batch_with_empty_buffer_posts_nothing(
    api: AmazonEchoApi, post_sequences: AsyncMock
) -> None:
    """A batch with nothing buffered does not post."""
    await api._sequence_handler._process_batch()

    post_sequences.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "message_type"),
    [
        pytest.param("call_alexa_sound", AmazonSequenceType.Sound, id="sound"),
        pytest.param(
            "call_alexa_text_command",
            AmazonSequenceType.TextCommand,
            id="text-command",
        ),
        pytest.param("call_alexa_skill", AmazonSequenceType.LaunchSkill, id="skill"),
    ],
)
async def test_api_calls_send_to_each_member(
    api: AmazonEchoApi,
    send_message: AsyncMock,
    speaker_group: AmazonDevice,
    method: str,
    message_type: AmazonSequenceType,
) -> None:
    """Commands to a speaker group are sent to every member."""
    devices = api._device_handler.devices
    argument = "test argument"

    await getattr(api, method)(speaker_group, argument)

    assert send_message.await_args_list == [
        call(devices[TEST_SERIAL_1], message_type, argument, None),
        call(devices[TEST_SERIAL_2], message_type, argument, None),
    ]


@pytest.mark.anyio
async def test_call_alexa_info_skill_sends_to_each_member(
    api: AmazonEchoApi, send_message: AsyncMock, speaker_group: AmazonDevice
) -> None:
    """An info skill is sent to every member with an empty body."""
    devices = api._device_handler.devices
    info_skill = ALEXA_INFO_SKILLS[0]

    await api.call_alexa_info_skill(speaker_group, info_skill)

    assert send_message.await_args_list == [
        call(devices[TEST_SERIAL_1], info_skill, "", None),
        call(devices[TEST_SERIAL_2], info_skill, "", None),
    ]


@pytest.mark.anyio
async def test_call_alexa_info_skill_unknown_raises(
    api: AmazonEchoApi, send_message: AsyncMock, speaker_group: AmazonDevice
) -> None:
    """An unsupported info skill is rejected before anything is sent."""
    with pytest.raises(ValueError, match="Unsupported info skill"):
        await api.call_alexa_info_skill(speaker_group, "Alexa.Nope")

    send_message.assert_not_awaited()


@pytest.mark.anyio
async def test_call_alexa_speak_sends_to_device(
    api: AmazonEchoApi, send_message: AsyncMock, speaker_group: AmazonDevice
) -> None:
    """Speak is sent once to the device itself, not to each member."""
    await api.call_alexa_speak(speaker_group, "Hello")

    send_message.assert_awaited_once_with(
        speaker_group, AmazonSequenceType.Speak, "Hello"
    )


@pytest.mark.anyio
async def test_call_routine_uses_default_device(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    send_message: AsyncMock,
) -> None:
    """Routines are run on the default device."""
    default_device = make_device(TEST_SERIAL_1)
    default_device.device_cluster_members = {TEST_SERIAL_1: None}
    api._device_handler._final_devices = {TEST_SERIAL_1: default_device}
    api._default_device_serial = TEST_SERIAL_1

    await api.call_routine("Morning")

    send_message.assert_awaited_once_with(
        default_device, AmazonSequenceType.Routines, "Morning", None
    )
