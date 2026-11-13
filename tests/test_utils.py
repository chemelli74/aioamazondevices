# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for utility helpers."""

from collections.abc import Callable
from typing import Any

import pytest

from aioamazondevices.const.http import ARRAY_WRAPPER
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.structures import AmazonDevice
from aioamazondevices.utils import (
    check_and_log_graphql_errors,
    get_innermost_frame,
    http2_extract_json_from_part,
    http2_parse_boundary_delimiter,
    obfuscate_email,
    parse_device_details,
    replace_routine_placeholders,
    scrub_fields,
    string_recursive_parse,
    validate_graphql_endpoint_shape,
)

TEST_ENDPOINTS = [{"endpointId": "endpoint-1"}]


def _raise_outside_library() -> None:
    raise ValueError("test")


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


def test_extract_json_from_part_rejects_non_object() -> None:
    """A JSON part that is not an object is rejected."""
    part = b"Content-Type: application/json\r\n\r\n[1, 2]"

    assert http2_extract_json_from_part(part) is None


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        pytest.param("john.d@example.com", "j***.*@e******.com", id="short-part"),
        pytest.param("not-an-email", "[invalid email]", id="invalid"),
    ],
)
def test_obfuscate_email(email: str, expected: str) -> None:
    """Each part keeps its first character, and invalid emails are not shown."""
    assert obfuscate_email(email) == expected


def test_scrub_fields() -> None:
    """Sensitive keys are redacted inside every kind of container."""
    data = {
        "email": "john@example.com",
        "items": (
            {"user_id": "secret", "volume": "kept"},
            ["kept"],
        ),
        "tags": {"kept"},
    }

    assert scrub_fields(data) == {
        "email": "j***@e******.com",
        "items": (
            {"user_id": "[REDACTED]", "volume": "kept"},
            ["kept"],
        ),
        "tags": {"kept"},
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param('{"a": "[1]"}', {"a": [1]}, id="nested-json"),
        pytest.param("{not json", "{not json", id="not-json"),
    ],
)
def test_string_recursive_parse(value: str, expected: object) -> None:
    """JSON strings are parsed recursively, other strings are kept."""
    assert string_recursive_parse(value) == expected


def test_string_recursive_parse_max_depth() -> None:
    """Strings nested beyond the maximum depth are not parsed."""
    deep: Any = '{"a": 1}'
    for _ in range(10):
        deep = [deep]

    assert string_recursive_parse(deep) == deep


def test_replace_routine_placeholders_keeps_other_values(
    make_device: Callable[..., AmazonDevice],
) -> None:
    """Values that are not placeholders are left unchanged."""
    payload = {"volume": 5, "text": "hello", "flag": None}

    assert replace_routine_placeholders(payload, make_device("1234")) == payload


def test_get_innermost_frame() -> None:
    """The innermost frame inside the library is named, others are unknown."""
    with pytest.raises(CannotRetrieveData) as library_error:
        http2_parse_boundary_delimiter("text/plain")
    with pytest.raises(ValueError, match="test") as test_error:
        _raise_outside_library()

    assert get_innermost_frame(library_error.value).startswith(
        "http2_parse_boundary_delimiter:"
    )
    assert get_innermost_frame(test_error.value) == "unknown"


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
