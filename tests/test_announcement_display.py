# Copyright 2026 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Test optional display text and announcement batching."""

from collections.abc import Callable
from unittest.mock import AsyncMock, _Call, call

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.implementation.sequence import AmazonSequenceHandler
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonSequenceNode,
    AmazonSequenceType,
)

from .const import TEST_SERIAL_1, TEST_SERIAL_2


@pytest.fixture
def device(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> AmazonDevice:
    """Return a logged in device that is its own cluster member."""
    api._session_state_data.login_stored_data = {"test": True}
    device = make_device(TEST_SERIAL_1)
    device.device_cluster_members = {device.serial_number: device.device_type}
    return device


@pytest.fixture
def enqueue(api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Replace enqueueing a sequence, returning the mock to assert on."""
    enqueue_sequence = AsyncMock()
    monkeypatch.setattr(api._sequence_handler, "_enqueue_sequence", enqueue_sequence)
    return enqueue_sequence


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("display_text", "expected_display"),
    [
        pytest.param(call(), "Doctor Smith", id="omitted"),
        pytest.param(call(display_text=None), "Doctor Smith", id="none-keyword"),
        pytest.param(call(None), "Doctor Smith", id="none-positional"),
        pytest.param(call(display_text=""), "Doctor Smith", id="empty-keyword"),
        pytest.param(call(""), "Doctor Smith", id="empty-positional"),
        pytest.param(
            call(display_text="Dr. Smith"), "Dr. Smith", id="override-keyword"
        ),
        pytest.param(call("Dr. Smith"), "Dr. Smith", id="override-positional"),
    ],
)
async def test_announcement_display_text(
    api: AmazonEchoApi,
    device: AmazonDevice,
    display_text: _Call,
    expected_display: str,
    enqueue: AsyncMock,
) -> None:
    """Display overrides and defaults preserve speech, title, and target devices."""
    handler = api._sequence_handler
    spoken = "Doctor Smith"
    original = handler._build_operation_node(
        device, AmazonSequenceType.Announcement, spoken
    )
    await api.call_alexa_announcement(
        device, spoken, *display_text.args, **display_text.kwargs
    )

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
    device: AmazonDevice,
    enqueue: AsyncMock,
) -> None:
    """The message sender accepts display text after the music provider."""
    handler = api._sequence_handler
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
    device: AmazonDevice,
) -> None:
    """Operation construction accepts display text after the music provider."""
    handler = api._sequence_handler
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
            (TEST_SERIAL_1, first_display),
            (TEST_SERIAL_2, second_display),
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
            device=make_device(TEST_SERIAL_1),
            operation_node={"display": display},
        )
        for display in ["Dr. Smith", "Other"]
    ]
    handler = object.__new__(AmazonSequenceHandler)
    result = list(handler._optimise_sequence_nodes(nodes))
    assert result == [node.operation_node for node in nodes]
