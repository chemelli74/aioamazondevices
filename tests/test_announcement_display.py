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
    ("args", "kwargs", "expected_display"),
    [
        pytest.param((), {}, "Doctor Smith", id="omitted"),
        pytest.param((), {"display_text": None}, "Doctor Smith", id="none-keyword"),
        pytest.param((None,), {}, "Doctor Smith", id="none-positional"),
        pytest.param((), {"display_text": ""}, "Doctor Smith", id="empty-keyword"),
        pytest.param(("",), {}, "Doctor Smith", id="empty-positional"),
        pytest.param(
            (), {"display_text": "Dr. Smith"}, "Dr. Smith", id="override-keyword"
        ),
        pytest.param(("Dr. Smith",), {}, "Dr. Smith", id="override-positional"),
    ],
)
async def test_announcement_display_text(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    args: tuple[str | None, ...],
    kwargs: dict[str, str | None],
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
        await api.call_alexa_announcement(device, spoken, *args, **kwargs)
    node = enqueue.call_args.args[0]
    expected = original
    expected["operationPayload"]["content"][0]["display"]["body"] = expected_display
    assert node.operation_node == expected
    assert node.operation_node["operationPayload"]["content"][0]["speak"] == {
        "type": "text",
        "value": spoken,
    }


@pytest.mark.anyio
async def test_send_message_display_text_positional_argument(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
) -> None:
    """The message sender accepts display text after the music provider."""
    api._session_state_data.login_stored_data = {"test": True}
    handler = api._sequence_handler
    device = make_device("first")
    device.device_cluster_members = {device.serial_number: device.device_type}
    with patch.object(handler, "_enqueue_sequence", new_callable=AsyncMock) as enqueue:
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


@pytest.mark.usefixtures("anyio_backend")
def test_build_operation_node_display_text_positional_argument(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
) -> None:
    """Operation construction accepts display text after the music provider."""
    api._session_state_data.login_stored_data = {"test": True}
    handler = api._sequence_handler
    device = make_device("first")
    device.device_cluster_members = {device.serial_number: device.device_type}
    operation = handler._build_operation_node(
        device, AmazonSequenceType.Announcement, "Doctor Smith", None, "Dr. Smith"
    )
    content = operation["operationPayload"]["content"][0]
    assert content["display"]["body"] == "Dr. Smith"
    assert content["speak"] == {"type": "text", "value": "Doctor Smith"}


@pytest.mark.parametrize(
    ("first_display", "second_display"),
    [
        (None, None),
        ("Dr. Smith", "Dr. Smith"),
        ("Dr. Smith", "Other"),
        (None, "Dr. Smith"),
    ],
)
def test_batch_preserves_display_text(
    make_device: Callable[..., AmazonDevice],
    first_display: str | None,
    second_display: str | None,
) -> None:
    """Parallel groups preserve each display body for different devices."""
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
            ("second", second_display),
        ]
    ]
    handler = object.__new__(AmazonSequenceHandler)
    result = list(handler._optimise_sequence_nodes(nodes))
    assert len(result) == 1
    assert result[0]["nodesToExecute"] == [node.operation_node for node in nodes]


def test_batch_keeps_same_device_operations_separate(
    make_device: Callable[..., AmazonDevice],
) -> None:
    """Announcements for the same device remain separate operations."""
    nodes = [
        AmazonSequenceNode(
            message_type=AmazonSequenceType.Announcement,
            message_body="Doctor Smith",
            music_provider_id=None,
            device=make_device("first"),
            operation_node={"display": display},
        )
        for display in ["Dr. Smith", "Other"]
    ]
    handler = object.__new__(AmazonSequenceHandler)
    result = list(handler._optimise_sequence_nodes(nodes))
    assert result == [node.operation_node for node in nodes]
