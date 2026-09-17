# Copyright 2026 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Test opt-in SSML announcements without changing plain text behavior."""

from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.implementation.sequence import AmazonSequenceHandler
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonSequenceNode,
    AmazonSequenceType,
)


@pytest.mark.anyio
async def test_ssml_payload(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """Pass valid SSML unchanged and keep the screen content separate."""
    api._session_state_data.login_stored_data = {"test": True}
    handler = api._sequence_handler
    ssml = '<speak><sub alias="Example">EXAMPLE</sub><break time="1s"/></speak>'
    with patch.object(handler, "_enqueue_sequence", new_callable=AsyncMock) as enqueue:
        await api.call_alexa_announcement(
            make_device("first"), ssml, display_text="EXAMPLE", speech_type="ssml"
        )
    node = enqueue.call_args.args[0]
    content = node.operation_node["operationPayload"]["content"][0]
    assert content["speak"] == {"type": "ssml", "value": ssml}
    assert content["display"]["body"] == "EXAMPLE"
    assert node.speech_type == "ssml"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("speech_type", "message", "display"),
    [
        ("xml", "Hello", "Hello"),
        ("ssml", "<speak>Hello</speak>", None),
        ("ssml", "<speak>Hello", "Hello"),
        ("ssml", "<sub>Hello</sub>", "Hello"),
        ("ssml", '<!DOCTYPE speak [<!ENTITY a "Hello">]><speak>&a;</speak>', "Hello"),
    ],
)
async def test_invalid_ssml_not_queued(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    speech_type: str,
    message: str,
    display: str | None,
) -> None:
    """Reject invalid input before it can reach Amazon."""
    api._session_state_data.login_stored_data = {"test": True}
    with (
        patch.object(
            api._sequence_handler, "_enqueue_sequence", new_callable=AsyncMock
        ) as enqueue,
        pytest.raises(ValueError, match=r"Speech type|SSML"),
    ):
        await api.call_alexa_announcement(
            make_device("first"),
            message,
            display_text=display,
            speech_type=speech_type,
        )
    enqueue.assert_not_awaited()


def test_batch_separates_speech_types(make_device: Callable[..., AmazonDevice]) -> None:
    """Never combine text and SSML as equivalent messages."""
    nodes = [
        AmazonSequenceNode(
            message_type=AmazonSequenceType.Announcement,
            message_body="<speak>Hello</speak>",
            music_provider_id=None,
            device=make_device(serial),
            operation_node={"speech_type": speech_type},
            display_text="Hello",
            speech_type=speech_type,
        )
        for serial, speech_type in [("first", "text"), ("second", "ssml")]
    ]
    handler = object.__new__(AmazonSequenceHandler)
    assert list(handler._optimise_sequence_nodes(nodes)) == [
        node.operation_node for node in nodes
    ]
