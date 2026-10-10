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
@pytest.mark.parametrize("display_text", [None, "Xplify version 1.32.0", ""])
async def test_announcement_display_text(
    api: AmazonEchoApi,
    make_device: Callable[..., AmazonDevice],
    display_text: str | None,
) -> None:
    """Only the display body changes when an override is supplied."""
    api._session_state_data.login_stored_data = {"test": True}
    device = make_device("first")
    device.device_cluster_members = {device.serial_number: device.device_type}
    handler = api._sequence_handler
    spoken = "Eksplifai version 1 32 0"
    original = handler._build_operation_node(
        device, AmazonSequenceType.Announcement, spoken
    )
    with patch.object(handler, "_enqueue_sequence", new_callable=AsyncMock) as enqueue:
        await api.call_alexa_announcement(device, spoken, display_text=display_text)
    node = enqueue.call_args.args[0]
    expected = original
    expected["operationPayload"]["content"][0]["display"]["body"] = (
        spoken if display_text is None else display_text
    )
    assert node.operation_node == expected
    assert node.display_text == display_text
    assert node.operation_node["operationPayload"]["content"][0]["speak"] == {
        "type": "text",
        "value": spoken,
    }


@pytest.mark.anyio
async def test_announcement_without_display_argument(
    api: AmazonEchoApi, make_device: Callable[..., AmazonDevice]
) -> None:
    """Existing callers keep identical display and speech content."""
    api._session_state_data.login_stored_data = {"test": True}
    handler = api._sequence_handler
    device = make_device("first")
    expected = handler._build_operation_node(
        device, AmazonSequenceType.Announcement, "Dinner is ready"
    )
    with patch.object(handler, "_enqueue_sequence", new_callable=AsyncMock) as enqueue:
        await api.call_alexa_announcement(device, "Dinner is ready")
    assert enqueue.call_args.args[0].operation_node == expected


@pytest.mark.parametrize(
    ("first_display", "second_display", "expected_count"),
    [
        (None, None, 1),
        ("Xplify", "Xplify", 1),
        ("Xplify", "Other", 2),
        (None, "Xplify", 2),
    ],
)
def test_batch_preserves_display_text(
    make_device: Callable[..., AmazonDevice],
    first_display: str | None,
    second_display: str | None,
    expected_count: int,
) -> None:
    """Only announcements with the same display override share a parallel node."""
    nodes = [
        AmazonSequenceNode(
            message_type=AmazonSequenceType.Announcement,
            message_body="Eksplifai",
            music_provider_id=None,
            device=make_device(serial),
            operation_node={"display": display},
            display_text=display,
        )
        for serial, display in [("first", first_display), ("second", second_display)]
    ]
    handler = object.__new__(AmazonSequenceHandler)
    result = list(handler._optimise_sequence_nodes(nodes))
    assert len(result) == expected_count
    if expected_count == 1:
        assert result[0]["nodesToExecute"] == [node.operation_node for node in nodes]
    else:
        assert result == [node.operation_node for node in nodes]
