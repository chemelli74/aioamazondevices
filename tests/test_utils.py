# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for utility helpers."""

from typing import Any

import pytest

from aioamazondevices.const.http import ARRAY_WRAPPER
from aioamazondevices.utils import (
    check_and_log_graphql_errors,
    parse_device_details,
    validate_graphql_endpoint_shape,
)

TEST_ENDPOINTS = [{"endpointId": "endpoint-1"}]


@pytest.mark.parametrize(
    ("raw_model", "expected_model", "expected_hardware_version"),
    [
        (
            "Echo Dot (5th gen) with Clock",
            "Echo Dot with Clock",
            "5th Gen",
        ),
        (
            "Echo Dot (4th generation)",
            "Echo Dot",
            "4th Gen",
        ),
        (
            "Echo Dot (3rd Gen)",
            "Echo Dot",
            "3rd Gen",
        ),
        (
            "Fire TV Stick 4K (2nd Gen)",
            "Fire TV Stick 4K",
            "2nd Gen",
        ),
        (
            "Echo Dot (5th gen)",
            "Echo Dot",
            "5th Gen",
        ),
        (
            "2021 Samsung UHD TV",
            "Samsung UHD TV",
            "2021",
        ),
        (
            "LG OLED TV 2023",
            "LG OLED TV",
            "2023",
        ),
        (
            "Panasonic Viera (2019)",
            "Panasonic Viera",
            "2019",
        ),
    ],
)
def test_parse_device_details_hardware_generation(
    raw_model: str,
    expected_model: str,
    expected_hardware_version: str,
) -> None:
    """Validate parsing and normalization of hardware generation strings."""
    model, hardware_version = parse_device_details(raw_model)

    assert model == expected_model
    assert hardware_version == expected_hardware_version


def test_parse_device_details_none() -> None:
    """Validate null model handling."""
    model, hardware_version = parse_device_details(None)

    assert model is None
    assert hardware_version is None


@pytest.mark.parametrize(
    "response",
    [
        {"data": {}},
        {"errors": []},
        {ARRAY_WRAPPER: [{"data": {}}]},
    ],
)
def test_check_and_log_graphql_errors_no_errors(
    response: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Responses without errors are not flagged."""
    assert not check_and_log_graphql_errors("TEST_QUERY", response)
    assert not caplog.records


def test_check_and_log_graphql_errors_logs_every_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every error is logged with the query name."""
    response = {
        "errors": [
            {"message": "First failure", "path": ["listEndpoints"]},
            {},
        ]
    }

    assert check_and_log_graphql_errors("TEST_QUERY", response)
    assert [record.getMessage() for record in caplog.records] == [
        "Error running query: TEST_QUERY - First failure for path ['listEndpoints']",
        "Error running query: TEST_QUERY - Unknown error for path Unknown path",
    ]


def test_check_and_log_graphql_errors_array_wrapper(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Errors nested in the array wrapper are found."""
    response = {ARRAY_WRAPPER: [{"errors": [{"message": "Boom", "path": "x"}]}]}

    assert check_and_log_graphql_errors("TEST_QUERY", response)
    assert "Error running query: TEST_QUERY - Boom for path x" in caplog.text


@pytest.mark.parametrize(
    "response",
    [
        {"data": {"listEndpoints": {"endpoints": TEST_ENDPOINTS}}},
        {ARRAY_WRAPPER: [{"data": {"listEndpoints": {"endpoints": TEST_ENDPOINTS}}}]},
    ],
)
def test_validate_graphql_endpoint_shape_returns_endpoints(
    response: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Endpoints are returned from both bare and array wrapped responses."""
    assert validate_graphql_endpoint_shape("TEST_QUERY", response) == TEST_ENDPOINTS
    assert not caplog.records


def test_validate_graphql_endpoint_shape_empty_endpoints(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An empty endpoints list is valid and returned as is."""
    response: dict[str, Any] = {"data": {"listEndpoints": {"endpoints": []}}}

    assert validate_graphql_endpoint_shape("TEST_QUERY", response) == []
    assert not caplog.records


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"data": None},
        {"data": {}},
        {"data": {"listEndpoints": None}},
        {"data": {"listEndpoints": {}}},
        {"data": {"listEndpoints": {"endpoints": None}}},
        {"data": {"listEndpoints": {"endpoints": {"endpointId": "x"}}}},
        {ARRAY_WRAPPER: []},
        {ARRAY_WRAPPER: ["not a dict"]},
        {ARRAY_WRAPPER: [{"data": {}}]},
    ],
)
def test_validate_graphql_endpoint_shape_malformed(
    response: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Malformed responses are logged with the query name."""
    assert validate_graphql_endpoint_shape("TEST_QUERY", response) is None
    assert "Malformed endpoint data received in TEST_QUERY" in caplog.text
