# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for endpoint feature control in AmazonFeatureHandler."""

import re
from collections.abc import Callable
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import orjson
import pytest

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import CannotSetFeature
from aioamazondevices.implementation.feature import OPERATION_NAME
from aioamazondevices.structures import AmazonDevice, AmazonDeviceFeature

from .const import FIXTURES_DIR, TEST_SERIAL_1

ENDPOINT_ID = "amzn1.alexa.endpoint.00000000-0000-0000-0000-000000000000"
INVALID_ENDPOINT_ID = "amzn1.alexa.endpoint.123"
DEVICE_NAME = f"Echo {TEST_SERIAL_1}"
MALFORMED = "Malformed response received setting"

type JsonBody = dict[str, Any] | list[dict[str, Any]]


def _fixture(name: str) -> list[dict[str, Any]]:
    """Load a captured setEndpointFeatures response."""
    path = FIXTURES_DIR / "set_feature" / f"{name}.json"
    return cast("list[dict[str, Any]]", orjson.loads(path.read_text()))


def _result(result: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    """Wrap a setEndpointFeatures result in a GraphQL response."""
    return [{"data": {OPERATION_NAME: result}}]


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
    return device


@pytest.fixture
def mock_feature_response(
    api: AmazonEchoApi, monkeypatch: pytest.MonkeyPatch
) -> Callable[[JsonBody], AsyncMock]:
    """Return a setter making every request return the given JSON body.

    Only the request is replaced, so the response is still converted by the real
    response_to_json. The setter returns the session_request mock.
    """

    def _mock_feature_response(response: JsonBody) -> AsyncMock:
        raw_resp = MagicMock()
        raw_resp.json = AsyncMock(return_value=response)
        session_request = AsyncMock(return_value=(None, raw_resp))
        monkeypatch.setattr(api._http_wrapper, "session_request", session_request)
        return session_request

    return _mock_feature_response


def _sent_request(session_request: AsyncMock) -> dict[str, Any]:
    """Return the single feature control request that was sent."""
    (request,) = session_request.await_args_list
    payload = request.kwargs["input_data"]
    variables = payload[0]["variables"]["setEndpointFeaturesInput"]
    return dict(variables["featureControlRequests"][0])


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("request_args", "expected_request"),
    [
        pytest.param(
            ("turn_on", "toggle", "turnOn", "11"),
            {
                "featureName": "toggle",
                "featureOperationName": "turnOn",
                "instance": "11",
            },
            id="turn-on-instance",
        ),
        pytest.param(
            ("turn_off", "toggle", "turnOff", "11"),
            {
                "featureName": "toggle",
                "featureOperationName": "turnOff",
                "instance": "11",
            },
            id="turn-off-instance",
        ),
        pytest.param(
            ("power_on", "power", "turnOn", None),
            {"featureName": "power", "featureOperationName": "turnOn"},
            id="no-instance",
        ),
    ],
)
async def test_set_feature_success(
    api: AmazonEchoApi,
    device: AmazonDevice,
    mock_feature_response: Callable[[JsonBody], AsyncMock],
    request_args: tuple[str, str, str, str | None],
    expected_request: dict[str, str],
) -> None:
    """A successful operation sends the request for the feature and instance."""
    fixture, feature, operation, instance = request_args
    session_request = mock_feature_response(_fixture(fixture))

    await api.call_feature_operation(device, feature, operation, instance=instance)

    assert _sent_request(session_request) == {
        "endpointId": ENDPOINT_ID,
        **expected_request,
    }


@pytest.mark.anyio
async def test_set_feature_success_is_logged(
    api: AmazonEchoApi,
    device: AmazonDevice,
    mock_feature_response: Callable[[JsonBody], AsyncMock],
    debug_logs: pytest.LogCaptureFixture,
) -> None:
    """A successful operation logs its response code, with an empty instance."""
    mock_feature_response(_fixture("power_on"))

    await api.call_feature_operation(device, "power", "turnOn")

    assert f"Feature set: power[].turnOn on {ENDPOINT_ID} [SUCCESS]" in (
        debug_logs.text
    )


@pytest.mark.anyio
async def test_set_feature_sends_payload(
    api: AmazonEchoApi,
    device: AmazonDevice,
    mock_feature_response: Callable[[JsonBody], AsyncMock],
) -> None:
    """A command payload is sent with the request."""
    session_request = mock_feature_response(_fixture("turn_on"))

    await api.call_feature_operation(
        device, "toggle", "turnOn", command_payload={"value": 1}, instance="11"
    )

    assert _sent_request(session_request)["payload"] == {"value": 1}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("request_args", "message"),
    [
        pytest.param(
            ("invalid_instance", ENDPOINT_ID, "turnOff", "21"),
            (
                f"Cannot set toggle[21].turnOff on {ENDPOINT_ID}:"
                " NOT_FOUND: Capability not found"
            ),
            id="invalid-instance",
        ),
        pytest.param(
            ("invalid_operation", ENDPOINT_ID, "turnEgg", "11"),
            f"Cannot set toggle[11].turnEgg on {ENDPOINT_ID}.",
            id="invalid-operation",
        ),
        pytest.param(
            ("invalid_endpoint", INVALID_ENDPOINT_ID, "turnOn", "11"),
            (
                f"Cannot set toggle[11].turnOn on {INVALID_ENDPOINT_ID}:"
                " INTERNAL_SERVER_ERROR: An unknown problem on server side"
            ),
            id="invalid-endpoint",
        ),
    ],
)
async def test_set_feature_rejected(
    api: AmazonEchoApi,
    device: AmazonDevice,
    mock_feature_response: Callable[[JsonBody], AsyncMock],
    request_args: tuple[str, str, str, str],
    message: str,
) -> None:
    """Each rejection Amazon returns raises CannotSetFeature."""
    fixture, device.endpoint_id, operation, instance = request_args
    mock_feature_response(_fixture(fixture))

    with pytest.raises(CannotSetFeature, match=re.escape(message)):
        await api.call_feature_operation(device, "toggle", operation, instance=instance)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "message"),
    [
        pytest.param({}, MALFORMED, id="empty-body"),
        pytest.param([{}], MALFORMED, id="no-data"),
        pytest.param(_result(None), MALFORMED, id="no-result"),
        pytest.param(_result([]), MALFORMED, id="result-not-dict"),
        pytest.param([None], MALFORMED, id="entry-not-dict"),
        pytest.param([{"data": []}], MALFORMED, id="data-not-dict"),
        pytest.param(_result({"errors": [None]}), MALFORMED, id="error-not-dict"),
        pytest.param(
            _result({"featureControlResponses": [None]}),
            MALFORMED,
            id="control-response-not-dict",
        ),
        pytest.param(
            _result({"errors": [{}]}),
            "Unknown code: no message",
            id="error-without-details",
        ),
        pytest.param(
            _result({"featureControlResponses": []}),
            "No response received setting",
            id="no-responses",
        ),
    ],
)
async def test_set_feature_malformed_responses_raise(
    api: AmazonEchoApi,
    device: AmazonDevice,
    mock_feature_response: Callable[[JsonBody], AsyncMock],
    response: JsonBody,
    message: str,
) -> None:
    """Responses missing expected fields raise CannotSetFeature."""
    mock_feature_response(response)

    with pytest.raises(CannotSetFeature, match=re.escape(message)):
        await api.call_feature_operation(device, "toggle", "turnOn", instance="11")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("request_args", "message"),
    [
        pytest.param(
            ("light", "turnOn", None),
            f"Device ({DEVICE_NAME}) does not have feature: light.",
            id="unknown-feature",
        ),
        pytest.param(
            ("toggle", "turnOn", "99"),
            f"Device ({DEVICE_NAME}) does not have feature: toggle instance: 99.",
            id="unknown-instance",
        ),
        pytest.param(
            ("toggle", "turnOn", None),
            f"Device ({DEVICE_NAME}) does not have feature: toggle.",
            id="missing-instance",
        ),
        pytest.param(
            ("toggle", "setColor", "11"),
            (
                f"Operation: setColor not valid for device ({DEVICE_NAME})"
                " feature: toggle instance: 11."
            ),
            id="unsupported-operation-with-instance",
        ),
        pytest.param(
            ("power", "setColor", None),
            f"Operation: setColor not valid for device ({DEVICE_NAME}) feature: power.",
            id="unsupported-operation",
        ),
    ],
)
async def test_set_feature_invalid_request_raises(
    api: AmazonEchoApi,
    device: AmazonDevice,
    mock_feature_response: Callable[[JsonBody], AsyncMock],
    request_args: tuple[str, str, str | None],
    message: str,
) -> None:
    """Requests the device does not support raise without contacting Amazon."""
    feature, operation, instance = request_args
    session_request = mock_feature_response(_fixture("turn_on"))

    with pytest.raises(CannotSetFeature, match=re.escape(message)):
        await api.call_feature_operation(device, feature, operation, instance=instance)

    session_request.assert_not_awaited()


@pytest.mark.anyio
async def test_set_feature_without_endpoint_raises(
    api: AmazonEchoApi,
    device: AmazonDevice,
    mock_feature_response: Callable[[JsonBody], AsyncMock],
) -> None:
    """A device without an endpoint ID raises without contacting Amazon."""
    device.endpoint_id = None
    session_request = mock_feature_response(_fixture("turn_on"))

    with pytest.raises(
        CannotSetFeature,
        match=re.escape(f"Device ({DEVICE_NAME}) does not have an endpoint ID."),
    ):
        await api.call_feature_operation(device, "toggle", "turnOn", instance="11")

    session_request.assert_not_awaited()
