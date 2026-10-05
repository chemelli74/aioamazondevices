# Copyright 2026 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Test optional display text and announcement batching."""

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
@pytest.mark.parametrize(
    ("display_text", "argument_style", "expected_display"),
    [
        pytest.param(None, "omitted", "Doctor Smith", id="omitted"),
        pytest.param(None, "keyword", "Doctor Smith", id="none-keyword"),
        pytest.param(None, "positional", "Doctor Smith", id="none-positional"),
        pytest.param("", "keyword", "Doctor Smith", id="empty-keyword"),
        pytest.param("", "positional", "Doctor Smith", id="empty-positional"),
        pytest.param("Dr. Smith", "keyword", "Dr. Smith", id="override-keyword"),
        pytest.param("Dr. Smith", "positional", "Dr. Smith", id="override-positional"),
    ],
)
async def test_announcement_display_text(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    display_text: str | None,
    argument_style: str,
    expected_display: str,
) -> None:
    """Display overrides and defaults preserve speech, title, and target devices."""
    api._session_state_data.login_stored_data = {"test": True}
    device = make_device("first")
    device.device_cluster_members = {device.serial_number: device.device_type}
    handler = api._sequence_handler
    spoken = "Doctor Smith"
    original = handler._build_operation_node(
        device, AmazonSequenceType.Announcement, spoken
    )
    with patch.object(handler, "_enqueue_sequence", new_callable=AsyncMock) as enqueue:
        if argument_style == "omitted":
            await api.call_alexa_announcement(device, spoken)
        elif argument_style == "positional":
            await api.call_alexa_announcement(device, spoken, display_text)
        else:
            await api.call_alexa_announcement(device, spoken, display_text=display_text)
    node = enqueue.call_args.args[0]
    expected = original
    expected["operationPayload"]["content"][0]["display"]["body"] = expected_display
    assert node.operation_node == expected
    assert node.operation_node["operationPayload"]["content"][0]["speak"] == {
        "type": "text",
        "value": spoken,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["send_message", "_build_operation_node"])
async def test_sequence_display_text_positional_argument(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    method: str,
) -> None:
    """Sequence methods accept display text after the music provider."""
    api._session_state_data.login_stored_data = {"test": True}
    handler = api._sequence_handler
    device = make_device("first")
    device.device_cluster_members = {device.serial_number: device.device_type}
    if method == "_build_operation_node":
        operation = handler._build_operation_node(
            device, AmazonSequenceType.Announcement, "Doctor Smith", None, "Dr. Smith"
        )
    else:
        with patch.object(
            handler, "_enqueue_sequence", new_callable=AsyncMock
        ) as enqueue:
            await handler.send_message(
                device,
                AmazonSequenceType.Announcement,
                "Doctor Smith",
                None,
                "Dr. Smith",
            )
        operation = enqueue.call_args.args[0].operation_node
    content = operation["operationPayload"]["content"][0]
    assert content["display"]["body"] == "Dr. Smith"
    assert content["speak"] == {"type": "text", "value": "Doctor Smith"}


@pytest.mark.parametrize(
    ("first_display", "second_display", "second_serial", "expected_count"),
    [
        (None, None, "second", 1),
        ("Dr. Smith", "Dr. Smith", "second", 1),
        ("Dr. Smith", "Other", "second", 1),
        (None, "Dr. Smith", "second", 1),
        ("Dr. Smith", "Other", "first", 2),
    ],
)
def test_batch_preserves_display_text(
    make_device: Callable[..., AmazonDevice],
    first_display: str | None,
    second_display: str | None,
    second_serial: str,
    expected_count: int,
) -> None:
    """Parallel groups preserve each display body and do not combine the same device."""
    nodes = [
        AmazonSequenceNode(
            message_type=AmazonSequenceType.Announcement,
            message_body="Doctor Smith",
            music_provider_id=None,
            device=make_device(serial),
            operation_node={"display": display},
        )
        for serial, display in [
            ("first", first_display),
            (second_serial, second_display),
        ]
    ]
    handler = object.__new__(AmazonSequenceHandler)
    result = list(handler._optimise_sequence_nodes(nodes))
    assert len(result) == expected_count
    if expected_count == 1:
        assert result[0]["nodesToExecute"] == [node.operation_node for node in nodes]
    else:
        assert result == [node.operation_node for node in nodes]
