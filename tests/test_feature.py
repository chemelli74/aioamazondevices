# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for endpoint feature control in AmazonFeatureHandler."""

import logging
import re
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import ARRAY_WRAPPER
from aioamazondevices.exceptions import CannotSetFeature
from aioamazondevices.implementation.feature import OPERATION_NAME

ENDPOINT_ID = "endpoint-1"


def _result(result: dict[str, Any] | None) -> dict[str, Any]:
    """Wrap a setEndpointFeatures result in a GraphQL response."""
    return {ARRAY_WRAPPER: [{"data": {OPERATION_NAME: result}}]}


def _mock_response(api: AmazonEchoApi, response: dict[str, Any]) -> AsyncMock:
    """Mock the HTTP layer to return the given response."""
    http_wrapper = api._feature_handler._http_wrapper
    session_request = AsyncMock(return_value=(None, None))
    http_wrapper.session_request = session_request  # type: ignore[method-assign]
    http_wrapper.response_to_json = AsyncMock(return_value=response)  # type: ignore[method-assign]
    return session_request


def _sent_request(session_request: AsyncMock) -> dict[str, Any]:
    """Return the single feature control request that was sent."""
    payload = session_request.call_args.kwargs["input_data"]
    variables = payload[0]["variables"]["setEndpointFeaturesInput"]
    return dict(variables["featureControlRequests"][0])


@pytest.mark.anyio
async def test_set_feature_success_logs_every_response(
    api: AmazonEchoApi,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A successful response logs each response code."""
    session_request = _mock_response(
        api,
        _result(
            {
                "errors": [],
                "featureControlResponses": [{"code": "SUCCESS"}, {"code": "EXTRA"}],
            }
        ),
    )

    with caplog.at_level(logging.DEBUG):
        await api._feature_handler.set_feature(ENDPOINT_ID, "power", "turnOn")

    assert _sent_request(session_request) == {
        "endpointId": ENDPOINT_ID,
        "featureName": "power",
        "featureOperationName": "turnOn",
    }
    assert f"Feature set: power[].turnOn on {ENDPOINT_ID} [SUCCESS]" in caplog.text
    assert f"Feature set: power[].turnOn on {ENDPOINT_ID} [EXTRA]" in caplog.text


@pytest.mark.anyio
async def test_set_feature_sends_instance_and_payload(
    api: AmazonEchoApi,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Instance and payload are sent and the instance is logged."""
    session_request = _mock_response(
        api, _result({"featureControlResponses": [{"code": "SUCCESS"}]})
    )

    with caplog.at_level(logging.DEBUG):
        await api._feature_handler.set_feature(
            ENDPOINT_ID,
            "toggle",
            "turnOn",
            command_payload={"value": 1},
            instance="mode",
        )

    request = _sent_request(session_request)
    assert request["instance"] == "mode"
    assert request["payload"] == {"value": 1}
    assert f"Feature set: toggle[mode].turnOn on {ENDPOINT_ID}" in caplog.text


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            {"errors": [{"message": "Boom", "path": [OPERATION_NAME]}]},
            f"Cannot set power[].turnOn on {ENDPOINT_ID}.",
        ),
        ({}, "Malformed response received setting"),
        ({ARRAY_WRAPPER: [{}]}, "Malformed response received setting"),
        (_result(None), "Malformed response received setting"),
        (
            _result({"errors": [{"code": "NOT_ALLOWED", "message": "Nope"}, {}]}),
            "NOT_ALLOWED: Nope; Unknown code: no message",
        ),
        (_result({"featureControlResponses": []}), "No response received setting"),
    ],
    ids=[
        "graphql_errors",
        "no_array_wrapper",
        "no_data",
        "no_result",
        "feature_errors",
        "no_responses",
    ],
)
@pytest.mark.anyio
async def test_set_feature_failures_raise(
    api: AmazonEchoApi,
    response: dict[str, Any],
    message: str,
) -> None:
    """Each reported failure raises CannotSetFeature."""
    _mock_response(api, response)

    with pytest.raises(CannotSetFeature, match=re.escape(message)):
        await api._feature_handler.set_feature(ENDPOINT_ID, "power", "turnOn")
