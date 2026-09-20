# Copyright 2024 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0

"""Endpoint feature control module for Amazon devices."""

from http import HTTPMethod
from typing import Any

from yarl import URL

from aioamazondevices.const.http import ARRAY_WRAPPER, REQUEST_AGENT, URI_NEXUS_GRAPHQL
from aioamazondevices.const.queries import MUTATION_SET_ENDPOINT_FEATURES
from aioamazondevices.exceptions import CannotSetFeature
from aioamazondevices.http_wrapper import AmazonHttpWrapper, AmazonSessionStateData
from aioamazondevices.utils import _LOGGER

OPERATION_NAME = "setEndpointFeaturesV2"


def _describe(request: dict[str, Any]) -> str:
    """Return a human readable description of a feature control request."""
    instance = request.get("instance")
    feature = request["featureName"]
    if instance:
        feature = f"{feature}[{instance}]"
    return f"{feature}.{request['featureOperationName']} on {request['endpointId']}"


def _graphql_errors(response: dict[str, Any]) -> list[str]:
    """Return the top level GraphQL error messages, if any."""
    if arr := response.get(ARRAY_WRAPPER):
        errors = arr[0].get("errors", [])
    else:
        errors = response.get("errors", [])

    return [
        f"{error.get('message', 'Unknown error')}"
        f" for path {error.get('path', 'Unknown path')}"
        for error in errors
    ]


class AmazonFeatureHandler:
    """Class to handle Alexa endpoint feature control."""

    def __init__(
        self,
        http_wrapper: AmazonHttpWrapper,
        session_state_data: AmazonSessionStateData,
    ) -> None:
        """Initialize AmazonFeatureHandler class."""
        self._session_state_data = session_state_data
        self._http_wrapper = http_wrapper

    async def set_feature(
        self,
        endpoint_id: str,
        feature_name: str,
        operation_name: str,
        payload: dict[str, Any] | None = None,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Invoke a feature operation on an endpoint.

        Wraps the `setEndpointFeaturesV2` GraphQL mutation with a single
        feature control request, and returns the matching feature control
        response.

        Raises CannotSetFeature when the mutation, or the single request it
        carries, is rejected.
        """
        request: dict[str, Any] = {
            "endpointId": endpoint_id,
            "featureName": feature_name,
            "featureOperationName": operation_name,
        }
        if instance is not None:
            request["instance"] = instance
        if payload is not None:
            request["payload"] = payload

        gql_payload = [
            {
                "operationName": OPERATION_NAME,
                "variables": {"input": {"featureControlRequests": [request]}},
                "query": MUTATION_SET_ENDPOINT_FEATURES,
            }
        ]

        _, raw_resp = await self._http_wrapper.session_request(
            method=HTTPMethod.POST,
            url=URL.joinpath(
                self._session_state_data.alexa_website_url, URI_NEXUS_GRAPHQL
            ),
            input_data=gql_payload,
            json_data=True,
            extended_headers={"User-Agent": REQUEST_AGENT["Amazon"]},
        )

        response = await self._http_wrapper.response_to_json(raw_resp, "set_feature")

        return self._parse_response(response, request)

    def _parse_response(
        self, response: dict[str, Any], request: dict[str, Any]
    ) -> dict[str, Any]:
        """Return the feature control response, raising on any reported error."""
        described = _describe(request)

        if errors := _graphql_errors(response):
            raise CannotSetFeature(f"Cannot set {described}: {'; '.join(errors)}")

        if (
            not (arr := response.get(ARRAY_WRAPPER))
            or not (data := arr[0].get("data"))
            or (result := data.get(OPERATION_NAME)) is None
        ):
            raise CannotSetFeature(
                f"Malformed response received setting {described}: {response}"
            )

        if failures := result.get("errors"):
            messages = "; ".join(
                f"{failure.get('code', 'Unknown code')}:"
                f" {failure.get('message', 'no message')}"
                for failure in failures
            )
            raise CannotSetFeature(f"Cannot set {described}: {messages}")

        if not (responses := result.get("featureControlResponses")):
            raise CannotSetFeature(f"No response received setting {described}")

        _LOGGER.debug("Feature set: %s [%s]", described, responses[0].get("code"))

        return dict(responses[0])
