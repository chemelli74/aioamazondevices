# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for endpoint feature control in AmazonFeatureHandler."""

import json
import logging
import re
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotSetFeature
from aioamazondevices.implementation.feature import OPERATION_NAME

from .const import FIXTURES_DIR

ENDPOINT_ID = "amzn1.alexa.endpoint.00000000-0000-0000-0000-000000000000"
INVALID_ENDPOINT_ID = "amzn1.alexa.endpoint.123"

type JsonBody = dict[str, Any] | list[dict[str, Any]]


def _fixture(name: str) -> list[dict[str, Any]]:
    """Load a captured setEndpointFeatures response."""
    path = FIXTURES_DIR / "set_feature" / f"{name}.json"
    return cast("list[dict[str, Any]]", json.loads(path.read_text()))


def _result(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Wrap a setEndpointFeatures result in a GraphQL response."""
    return [{"data": {OPERATION_NAME: result}}]


def _mock_response(api: AmazonEchoApi, response: JsonBody) -> AsyncMock:
    """Mock the HTTP session to return the given JSON body."""
    raw_resp = MagicMock()
    raw_resp.json = AsyncMock(return_value=response)
    session_request = AsyncMock(return_value=(None, raw_resp))
    api._feature_handler._http_wrapper.session_request = session_request  # type: ignore[method-assign]
    return session_request


def _sent_request(session_request: AsyncMock) -> dict[str, Any]:
    """Return the single feature control request that was sent."""
    payload = session_request.call_args.kwargs["input_data"]
    variables = payload[0]["variables"]["setEndpointFeaturesInput"]
    return dict(variables["featureControlRequests"][0])


@pytest.mark.parametrize(
    ("fixture", "operation"),
    [("turn_on", "turnOn"), ("turn_off", "turnOff")],
)
@pytest.mark.anyio
async def test_set_feature_success(
    api: AmazonEchoApi,
    caplog: pytest.LogCaptureFixture,
    fixture: str,
    operation: str,
) -> None:
    """A successful toggle sends the request and logs the response code."""
    session_request = _mock_response(api, _fixture(fixture))

    with caplog.at_level(logging.DEBUG):
        await api.async_set_feature(ENDPOINT_ID, "toggle", operation, instance="11")

    assert _sent_request(session_request) == {
        "endpointId": ENDPOINT_ID,
        "featureName": "toggle",
        "featureOperationName": operation,
        "instance": "11",
    }
    assert (
        f"Feature set: toggle[11].{operation} on {ENDPOINT_ID} [SUCCESS]" in caplog.text
    )


@pytest.mark.anyio
async def test_set_feature_sends_payload(api: AmazonEchoApi) -> None:
    """A command payload is sent with the request."""
    session_request = _mock_response(api, _fixture("turn_on"))

    await api.async_set_feature(
        ENDPOINT_ID, "toggle", "turnOn", command_payload={"value": 1}
    )

    assert _sent_request(session_request)["payload"] == {"value": 1}


@pytest.mark.parametrize(
    ("fixture", "request_args", "message"),
    [
        (
            "invalid_instance",
            (ENDPOINT_ID, "turnOff", "21"),
            (
                f"Cannot set toggle[21].turnOff on {ENDPOINT_ID}:"
                " NOT_FOUND: Capability not found"
            ),
        ),
        (
            "invalid_operation",
            (ENDPOINT_ID, "turnEgg", "11"),
            f"Cannot set toggle[11].turnEgg on {ENDPOINT_ID}.",
        ),
        (
            "invalid_endpoint",
            (INVALID_ENDPOINT_ID, "turnOn", "11"),
            (
                f"Cannot set toggle[11].turnOn on {INVALID_ENDPOINT_ID}:"
                " INTERNAL_SERVER_ERROR: An unknown problem on server side"
            ),
        ),
    ],
)
@pytest.mark.anyio
async def test_set_feature_rejected(
    api: AmazonEchoApi,
    fixture: str,
    request_args: tuple[str, str, str],
    message: str,
) -> None:
    """Each rejection Amazon returns raises CannotSetFeature."""
    endpoint_id, operation, instance = request_args
    _mock_response(api, _fixture(fixture))

    with pytest.raises(CannotSetFeature, match=re.escape(message)):
        await api.async_set_feature(endpoint_id, "toggle", operation, instance=instance)


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ({}, "Malformed response received setting"),
        ([{}], "Malformed response received setting"),
        (_result(None), "Malformed response received setting"),
        (
            _result({"errors": [{}]}),
            "Unknown code: no message",
        ),
        (_result({"featureControlResponses": []}), "No response received setting"),
    ],
    ids=[
        "empty_body",
        "no_data",
        "no_result",
        "error_without_details",
        "no_responses",
    ],
)
@pytest.mark.anyio
async def test_set_feature_malformed_responses_raise(
    api: AmazonEchoApi,
    response: JsonBody,
    message: str,
) -> None:
    """Responses missing expected fields raise CannotSetFeature."""
    _mock_response(api, response)

    with pytest.raises(CannotSetFeature, match=re.escape(message)):
        await api.async_set_feature(ENDPOINT_ID, "toggle", "turnOn")
