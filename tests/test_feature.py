# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for endpoint feature control in AmazonFeatureHandler."""

import logging
import re
from collections.abc import Callable, Mapping
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import orjson
import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotSetFeature
from aioamazondevices.implementation.feature import OPERATION_NAME
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonDeviceFeature,
    AmazonRTCSession,
)

from .const import FIXTURES_DIR, TEST_SERIAL_1

ENDPOINT_ID = "amzn1.alexa.endpoint.00000000-0000-0000-0000-000000000000"
INVALID_ENDPOINT_ID = "amzn1.alexa.endpoint.123"
DEVICE_NAME = f"Echo {TEST_SERIAL_1}"
RTC_SESSION_ID = "2ab54ad2-9600-4f33-a72e-3c77a0ef2534"
RTC_SESSION_DOMAIN = "amzn1.alexa.rtc.session.test"
RTC_OFFER_SDP = "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\n"
RTC_ANSWER_SDP = "v=0\r\no=- 2 2 IN IP4 127.0.0.1\r\n"

type JsonBody = dict[str, Any] | list[dict[str, Any]]


def _fixture(name: str) -> list[dict[str, Any]]:
    """Load a captured setEndpointFeatures response."""
    path = FIXTURES_DIR / "set_feature" / f"{name}.json"
    return cast("list[dict[str, Any]]", orjson.loads(path.read_text()))


def _result(result: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    """Wrap a setEndpointFeatures result in a GraphQL response."""
    return [{"data": {OPERATION_NAME: result}}]


def _success(response_payload: Mapping[str, object] | None) -> list[dict[str, Any]]:
    """Build a successful feature operation response with a response payload."""
    return _result(
        {
            "featureControlResponses": [
                {"code": "SUCCESS", "responsePayload": response_payload}
            ],
            "errors": [],
        }
    )


def _feature(*operations: str) -> AmazonDeviceFeature:
    """Build a feature supporting the given operations."""
    return AmazonDeviceFeature(
        properties=[],
        sensor_keys={},
        supported_operations=list(operations),
        supported_modes={},
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
    device = make_device(TEST_SERIAL_1)
    device.endpoint_id = ENDPOINT_ID
    # turnEgg is declared so Amazon's rejection of it can still be exercised
    toggle = _feature("turnOn", "turnOff", "turnEgg")
    device.features = {
        "toggle": {"11": toggle, "21": toggle},
        "power": {"": _feature("turnOn", "turnOff")},
    }
    device.unsupported_features = {
        "rtcSession": {"": _feature("initiateSessionWithOffer", "disconnectSession")}
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


@pytest.mark.anyio
async def test_initiate_rtc_session_returns_sdp_answer(
    api: AmazonEchoApi, device: AmazonDevice
) -> None:
    """RTC initiation supports an operation-only feature and returns its answer."""
    response_payload = {
        "type": "AnswerGeneratedForSessionResponse",
        "sessionId": RTC_SESSION_ID,
        "sessionDomain": RTC_SESSION_DOMAIN,
        "answer": {"format": "SDP", "value": RTC_ANSWER_SDP},
    }
    session_request = _mock_response(api, _success(response_payload))

    session = await api.initiate_rtc_session(device, RTC_SESSION_ID, RTC_OFFER_SDP)

    assert session == AmazonRTCSession(
        session_id=RTC_SESSION_ID,
        session_domain=RTC_SESSION_DOMAIN,
        answer_sdp=RTC_ANSWER_SDP,
    )
    assert _sent_request(session_request) == {
        "endpointId": ENDPOINT_ID,
        "featureName": "rtcSession",
        "featureOperationName": "initiateSessionWithOffer",
        "payload": {
            "sessionId": RTC_SESSION_ID,
            "offer": {"format": "SDP", "value": RTC_OFFER_SDP},
        },
    }


@pytest.mark.anyio
async def test_disconnect_rtc_session(api: AmazonEchoApi, device: AmazonDevice) -> None:
    """RTC disconnection sends the session identifier."""
    session_request = _mock_response(api, _success(None))

    await api.disconnect_rtc_session(device, RTC_SESSION_ID)

    assert _sent_request(session_request) == {
        "endpointId": ENDPOINT_ID,
        "featureName": "rtcSession",
        "featureOperationName": "disconnectSession",
        "payload": {"sessionId": RTC_SESSION_ID},
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response_payload",
    [
        None,
        {"sessionId": 1},
        {"sessionId": RTC_SESSION_ID, "sessionDomain": 1},
        {
            "sessionId": RTC_SESSION_ID,
            "sessionDomain": RTC_SESSION_DOMAIN,
            "answer": "invalid",
        },
        {
            "sessionId": RTC_SESSION_ID,
            "sessionDomain": RTC_SESSION_DOMAIN,
            "answer": {"format": "JSON", "value": RTC_ANSWER_SDP},
        },
        {
            "sessionId": RTC_SESSION_ID,
            "sessionDomain": RTC_SESSION_DOMAIN,
            "answer": {"format": "SDP", "value": 1},
        },
    ],
)
async def test_initiate_rtc_session_rejects_malformed_response(
    api: AmazonEchoApi,
    device: AmazonDevice,
    response_payload: Mapping[str, object] | None,
) -> None:
    """RTC initiation rejects responses without a valid SDP answer."""
    _mock_response(api, _success(response_payload))

    with pytest.raises(CannotSetFeature, match="Malformed RTC session response"):
        await api.initiate_rtc_session(device, RTC_SESSION_ID, RTC_OFFER_SDP)


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
        (_result([]), "Malformed response received setting"),
        ([None], "Malformed response received setting"),
        ([{"data": []}], "Malformed response received setting"),
        (_result({"errors": [None]}), "Malformed response received setting"),
        (
            _result({"featureControlResponses": [None]}),
            "Malformed response received setting",
        ),
        (
            _result({"featureControlResponses": [{"responsePayload": "invalid"}]}),
            "Malformed response received setting",
        ),
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
        "result_not_dict",
        "entry_not_dict",
        "data_not_dict",
        "error_not_dict",
        "control_response_not_dict",
        "response_payload_not_dict",
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
            f"Device ({DEVICE_NAME}) does not have feature: light.",
        ),
        (
            ("toggle", "turnOn", "99"),
            f"Device ({DEVICE_NAME}) does not have feature: toggle instance: 99.",
        ),
        (
            ("toggle", "turnOn", None),
            f"Device ({DEVICE_NAME}) does not have feature: toggle.",
        ),
        (
            ("toggle", "setColor", "11"),
            (
                f"Operation: setColor not valid for device ({DEVICE_NAME})"
                " feature: toggle instance: 11."
            ),
        ),
        (
            ("power", "setColor", None),
            f"Operation: setColor not valid for device ({DEVICE_NAME}) feature: power.",
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
        match=re.escape(f"Device ({DEVICE_NAME}) does not have an endpoint ID."),
    ):
        await api.call_feature_operation(device, "toggle", "turnOn", instance="11")

    session_request.assert_not_called()
