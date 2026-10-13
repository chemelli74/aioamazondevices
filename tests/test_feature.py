# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for endpoint feature control in AmazonFeatureHandler."""

import json
import logging
import re
from collections.abc import Callable
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotSetFeature
from aioamazondevices.implementation.feature import OPERATION_NAME
from aioamazondevices.structures import AmazonDevice, AmazonDeviceFeature

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


def _feature(*operations: str) -> AmazonDeviceFeature:
    """Build a feature supporting the given operations."""
    return AmazonDeviceFeature(
        properties=[],
        supported_operations=list(operations),
        supported_modes=[],
        friendly_name=None,
        minimum_value=None,
        maximum_value=None,
        precision=None,
        unit_of_measure=None,
        raw_configuration={},
    )


@pytest.fixture
def device(make_device: Callable[..., AmazonDevice]) -> AmazonDevice:
    """Return a device exposing a toggle (with instances) and a power feature."""
    device = make_device("SERIAL")
    device.endpoint_id = ENDPOINT_ID
    # turnEgg is declared so Amazon's rejection of it can still be exercised
    toggle = _feature("turnOn", "turnOff", "turnEgg")
    device.features = {
        "toggle": {"11": toggle, "21": toggle},
        "power": {"": _feature("turnOn", "turnOff")},
    }
    return device


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
    ("fixture", "request_args"),
    [
        ("turn_on", ("toggle", "turnOn", "11")),
        ("turn_off", ("toggle", "turnOff", "11")),
        ("power_on", ("power", "turnOn", None)),
    ],
)
@pytest.mark.anyio
async def test_set_feature_success(
    api: AmazonEchoApi,
    device: AmazonDevice,
    caplog: pytest.LogCaptureFixture,
    fixture: str,
    request_args: tuple[str, str, str | None],
) -> None:
    """A successful operation sends the request and logs the response code."""
    feature, operation, instance = request_args
    session_request = _mock_response(api, _fixture(fixture))

    with caplog.at_level(logging.DEBUG):
        await api.call_feature_operation(device, feature, operation, instance=instance)

    expected_request = {
        "endpointId": ENDPOINT_ID,
        "featureName": feature,
        "featureOperationName": operation,
    }
    if instance is not None:
        expected_request["instance"] = instance
    assert _sent_request(session_request) == expected_request
    assert (
        f"Feature set: {feature}[{instance or ''}].{operation} on {ENDPOINT_ID}"
        " [SUCCESS]" in caplog.text
    )


@pytest.mark.anyio
async def test_set_feature_sends_payload(
    api: AmazonEchoApi, device: AmazonDevice
) -> None:
    """A command payload is sent with the request."""
    session_request = _mock_response(api, _fixture("turn_on"))

    await api.call_feature_operation(
        device, "toggle", "turnOn", command_payload={"value": 1}, instance="11"
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
    device: AmazonDevice,
    fixture: str,
    request_args: tuple[str, str, str],
    message: str,
) -> None:
    """Each rejection Amazon returns raises CannotSetFeature."""
    device.endpoint_id, operation, instance = request_args
    _mock_response(api, _fixture(fixture))

    with pytest.raises(CannotSetFeature, match=re.escape(message)):
        await api.call_feature_operation(device, "toggle", operation, instance=instance)


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
    device: AmazonDevice,
    response: JsonBody,
    message: str,
) -> None:
    """Responses missing expected fields raise CannotSetFeature."""
    _mock_response(api, response)

    with pytest.raises(CannotSetFeature, match=re.escape(message)):
        await api.call_feature_operation(device, "toggle", "turnOn", instance="11")


@pytest.mark.parametrize(
    ("request_args", "message"),
    [
        (
            ("light", "turnOn", None),
            "Device (Echo SERIAL) does not have feature: light.",
        ),
        (
            ("toggle", "turnOn", "99"),
            "Device (Echo SERIAL) does not have feature: toggle instance: 99.",
        ),
        (
            ("toggle", "turnOn", None),
            "Device (Echo SERIAL) does not have feature: toggle.",
        ),
        (
            ("toggle", "setColor", "11"),
            (
                "Operation: setColor not valid for device (Echo SERIAL)"
                " feature: toggle instance: 11."
            ),
        ),
        (
            ("power", "setColor", None),
            "Operation: setColor not valid for device (Echo SERIAL) feature: power.",
        ),
    ],
    ids=[
        "unknown_feature",
        "unknown_instance",
        "missing_instance",
        "unsupported_operation_with_instance",
        "unsupported_operation",
    ],
)
@pytest.mark.anyio
async def test_set_feature_invalid_request_raises(
    api: AmazonEchoApi,
    device: AmazonDevice,
    request_args: tuple[str, str, str | None],
    message: str,
) -> None:
    """Requests the device does not support raise without contacting Amazon."""
    feature, operation, instance = request_args
    session_request = _mock_response(api, _fixture("turn_on"))

    with pytest.raises(CannotSetFeature, match=re.escape(message)):
        await api.call_feature_operation(device, feature, operation, instance=instance)

    session_request.assert_not_called()


@pytest.mark.anyio
async def test_set_feature_without_endpoint_raises(
    api: AmazonEchoApi, device: AmazonDevice
) -> None:
    """A device without an endpoint ID raises without contacting Amazon."""
    device.endpoint_id = None
    session_request = _mock_response(api, _fixture("turn_on"))

    with pytest.raises(
        CannotSetFeature,
        match=re.escape("Device (Echo SERIAL) does not have an endpoint ID."),
    ):
        await api.call_feature_operation(device, "toggle", "turnOn", instance="11")

    session_request.assert_not_called()
