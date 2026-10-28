# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for utility helpers."""

from typing import Any

import pytest

from aioamazondevices.const.http import ARRAY_WRAPPER
from aioamazondevices.utils import (
    check_and_log_graphql_errors,
    parse_device_details,
    scrub_fields,
    validate_graphql_endpoint_shape,
)

TEST_ENDPOINTS = [{"endpointId": "endpoint-1"}]


@pytest.mark.parametrize(
    ("raw_model", "expected_model", "expected_hardware_version"),
    [
        pytest.param(
            "Echo Dot (5th gen) with Clock",
            "Echo Dot with Clock",
            "5th Gen",
            id="generation-mid-name",
        ),
        pytest.param(
            "Echo Dot (4th generation)", "Echo Dot", "4th Gen", id="generation-long"
        ),
        pytest.param("Echo Dot (3rd Gen)", "Echo Dot", "3rd Gen", id="generation"),
        pytest.param(
            "Fire TV Stick 4K (2nd Gen)",
            "Fire TV Stick 4K",
            "2nd Gen",
            id="generation-after-digits",
        ),
        pytest.param(
            "Echo Dot (5th gen)", "Echo Dot", "5th Gen", id="generation-lowercase"
        ),
        pytest.param("2021 Samsung UHD TV", "Samsung UHD TV", "2021", id="year-prefix"),
        pytest.param("LG OLED TV 2023", "LG OLED TV", "2023", id="year-suffix"),
        pytest.param(
            "Panasonic Viera (2019)", "Panasonic Viera", "2019", id="year-bracketed"
        ),
        pytest.param(None, None, None, id="none"),
    ],
)
def test_parse_device_details(
    raw_model: str | None,
    expected_model: str | None,
    expected_hardware_version: str | None,
) -> None:
    """Hardware generations and years are split from the model name."""
    model, hardware_version = parse_device_details(raw_model)

    assert model == expected_model
    assert hardware_version == expected_hardware_version


@pytest.mark.parametrize(
    "response",
    [
        pytest.param({"data": {}}, id="data"),
        pytest.param({"errors": []}, id="empty-errors"),
        pytest.param({ARRAY_WRAPPER: [{"data": {}}]}, id="array-wrapped"),
    ],
)
def test_check_and_log_graphql_errors_no_errors(
    response: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Responses without errors are not flagged."""
    assert not check_and_log_graphql_errors("TEST_QUERY", response)
    assert not caplog.records


@pytest.mark.parametrize(
    ("response", "messages"),
    [
        pytest.param(
            {"errors": [{"message": "Failed", "path": ["listEndpoints"]}, {}]},
            [
                "Error running query: TEST_QUERY - Failed for path ['listEndpoints']",
                "Error running query: TEST_QUERY - Unknown error for path Unknown path",
            ],
            id="every-error",
        ),
        pytest.param(
            {ARRAY_WRAPPER: [{"errors": [{"message": "Boom", "path": "x"}]}]},
            ["Error running query: TEST_QUERY - Boom for path x"],
            id="array-wrapped",
        ),
    ],
)
def test_check_and_log_graphql_errors_logs_errors(
    response: dict[str, Any], messages: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    """Every error is logged with the query name, also inside the array wrapper."""
    assert check_and_log_graphql_errors("TEST_QUERY", response)
    assert [record.getMessage() for record in caplog.records] == messages


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        pytest.param(
            {"data": {"listEndpoints": {"endpoints": TEST_ENDPOINTS}}},
            TEST_ENDPOINTS,
            id="bare",
        ),
        pytest.param(
            {
                ARRAY_WRAPPER: [
                    {"data": {"listEndpoints": {"endpoints": TEST_ENDPOINTS}}}
                ]
            },
            TEST_ENDPOINTS,
            id="array-wrapped",
        ),
        pytest.param(
            {"data": {"listEndpoints": {"endpoints": []}}}, [], id="empty-endpoints"
        ),
    ],
)
def test_validate_graphql_endpoint_shape_returns_endpoints(
    response: dict[str, Any],
    expected: list[dict[str, Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Endpoints are returned as is from bare and array wrapped responses."""
    assert validate_graphql_endpoint_shape("TEST_QUERY", response) == expected
    assert not caplog.records


@pytest.mark.parametrize(
    "response",
    [
        pytest.param({}, id="empty"),
        pytest.param({"data": None}, id="null-data"),
        pytest.param({"data": {}}, id="no-list-endpoints"),
        pytest.param({"data": {"listEndpoints": None}}, id="null-list-endpoints"),
        pytest.param({"data": {"listEndpoints": {}}}, id="no-endpoints"),
        pytest.param(
            {"data": {"listEndpoints": {"endpoints": None}}}, id="null-endpoints"
        ),
        pytest.param(
            {"data": {"listEndpoints": {"endpoints": {"endpointId": "x"}}}},
            id="endpoints-not-a-list",
        ),
        pytest.param({ARRAY_WRAPPER: []}, id="empty-array"),
        pytest.param({ARRAY_WRAPPER: ["not a dict"]}, id="array-item-not-a-dict"),
        pytest.param({ARRAY_WRAPPER: [{"data": {}}]}, id="array-no-list-endpoints"),
    ],
)
def test_validate_graphql_endpoint_shape_malformed(
    response: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Malformed responses are logged with the query name."""
    assert validate_graphql_endpoint_shape("TEST_QUERY", response) is None
    assert "Malformed endpoint data received in TEST_QUERY" in caplog.text


def test_scrub_fields_keeps_feature_names() -> None:
    """Feature and property names stay readable, other names are redacted."""
    payload = {
        "name": "Jane Doe",
        "features": [
            {
                "name": "thermostat",
                "properties": [{"name": "targetSetpoint", "token": "secret"}],
            }
        ],
    }

    assert scrub_fields(payload) == {
        "name": "[REDACTED]",
        "features": [
            {
                "name": "thermostat",
                "properties": [{"name": "targetSetpoint", "token": "[REDACTED]"}],
            }
        ],
    }
