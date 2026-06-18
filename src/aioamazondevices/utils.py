"""Utils module for Amazon devices."""

import logging
import re
import traceback
from collections.abc import Collection
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default
from typing import Any

import orjson

from aioamazondevices.const.http import ARRAY_WRAPPER
from aioamazondevices.exceptions import CannotRetrieveData
from aioamazondevices.structures import AmazonDevice

_LOGGER = logging.getLogger(__package__)
_MAX_JSON_PARSE_DEPTH = 10

TO_REDACT = {
    "access_token",
    "address",
    "address1",
    "address2",
    "address3",
    "city",
    "county",
    "customerId",
    "deviceAccountId",
    "deviceAddress",
    "deviceOwnerCustomerId",
    "given_name",
    "name",
    "password",
    "postalCode",
    "searchCustomerId",
    "source_token",
    "state",
    "street",
    "token",
    "user_id",
}


def http2_extract_json_from_part(part: bytes) -> dict[str, Any] | None:
    """Extract JSON using MIME parser."""

    def _validate_content_type(content_type: str) -> None:
        if content_type != "application/json":
            raise ValueError(f"Unexpected content-type: {content_type!r}")

    def _get_payload(msg: EmailMessage) -> bytes:
        payload = msg.get_payload(decode=True)
        if payload is None:
            raise ValueError("No payload")
        if not isinstance(payload, bytes):
            raise TypeError(f"Expected bytes payload, got {type(payload)!r}")
        return payload

    def _validate_json_object(parsed: Any) -> dict[str, Any]:  # noqa: ANN401
        if not isinstance(parsed, dict):
            raise TypeError(f"Expected JSON object, got {type(parsed)!r}")
        return parsed

    try:
        msg = BytesParser(policy=default).parsebytes(part + b"\r\n")
        _validate_content_type(msg.get_content_type())
        body = _get_payload(msg)
        parsed = _validate_json_object(string_recursive_parse(orjson.loads(body)))
    except (TypeError, ValueError, orjson.JSONDecodeError):
        _LOGGER.warning(
            "Failed to parse multipart section: %s",
            part.decode("utf-8", errors="replace"),
            exc_info=True,
        )
        return None
    else:
        return parsed


def http2_parse_boundary_delimiter(content_type: str) -> bytes:
    """Extract the boundary delimiter from a Content-Type header value.

    Returns the full delimiter bytes (with '--' prefix) ready for use
    with bytes.find().
    """
    msg = EmailMessage()
    msg["Content-Type"] = content_type
    if not (boundary := msg.get_boundary()):
        raise CannotRetrieveData("Missing multipart boundary")
    return f"--{boundary}".encode()


def obfuscate_email(email: str) -> str:
    """Obfuscate an email address partially."""
    try:
        username, domain = email.split("@")
        domain_name, domain_ext = domain.rsplit(".", 1)

        def obfuscate_part(part: str, visible: int = 1) -> str:
            if len(part) <= visible:
                return "*" * len(part)
            return part[:visible] + "*" * (len(part) - visible)

        # Obfuscate username and domain parts
        obf_user = ".".join(obfuscate_part(u, 1) for u in username.split("."))
        obf_domain = obfuscate_part(domain_name, 1)

    except (SyntaxError, ValueError):
        return "[invalid email]"
    else:
        return f"{obf_user}@{obf_domain}.{domain_ext}"


def scrub_fields(
    obj: Any,  # noqa: ANN401
    field_names: Collection[str] = TO_REDACT,
    replacement: str = "[REDACTED]",
) -> Any:  # noqa: ANN401
    """Return a deep-copied version of *obj* with redacted keys."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            # If the key itself is sensitive → overwrite its value
            if k == "email":
                result[k] = obfuscate_email(v)
            elif k in field_names:
                result[k] = replacement
            else:
                # Otherwise keep walking
                result[k] = scrub_fields(v, field_names, replacement)
        return result

    if isinstance(obj, list):
        return [scrub_fields(item, field_names, replacement) for item in obj]

    if isinstance(obj, tuple):
        return tuple(scrub_fields(item, field_names, replacement) for item in obj)

    if isinstance(obj, set):
        # Note: a set cannot contain mutable/unhashable items like dicts,
        # so we assume its members are hashable after scrubbing.
        return {scrub_fields(item, field_names, replacement) for item in obj}

    return obj


def parse_device_details(model: str | None) -> tuple[str | None, str | None]:
    """Parse device model to extract a normalized version and its hardware revision."""
    if model is None:
        return None, None

    model = re.sub(r"\bgeneration\b", "Gen", model, flags=re.IGNORECASE).strip()

    # Matching examples:
    #   "Echo Dot (5th gen) with Clock" -> ("Echo Dot with Clock", "5th Gen")
    #   "Fire TV Stick 4K (2nd Gen)"    -> ("Fire TV Stick 4K", "2nd Gen")
    match = re.search(
        r"\(\s*(?P<ordinal>\d+(?:st|nd|rd|th))\s*gen\s*\)",  # codespell:ignore nd
        model,
        flags=re.IGNORECASE,
    )
    if match:
        parsed_model = re.sub(match.re, "", model, count=1)
        parsed_model = re.sub(r"\s+", " ", parsed_model).strip()
        return parsed_model, f"{match.group('ordinal').lower()} Gen"

    # Matching examples:
    #   "2021 Samsung UHD TV"    -> ("Samsung UHD TV", "2021")
    #   "Panasonic Viera (2019)" -> ("Panasonic Viera", "2019")
    match = re.search(r"\b(19|20)\d{2}\b", model)
    if match:
        year = match.group(0)
        parsed_model = re.sub(
            rf"\(\s*{re.escape(year)}\s*\)|\b{re.escape(year)}\b",
            "",
            model,
            count=1,
        )
        parsed_model = re.sub(r"\s+", " ", parsed_model).strip()
        return parsed_model, year.strip()

    return model, None


def format_graphql_error(graphql_response: dict[str, Any]) -> bool:
    """Format human readable e rror from malformed data."""
    if graphql_response.get(ARRAY_WRAPPER):
        error = graphql_response[ARRAY_WRAPPER][0].get("errors", [])
    else:
        error = graphql_response.get("errors", [])

    if not error:
        return False

    msg = error[0].get("message", "Unknown error")
    path = error[0].get("path", "Unknown path")
    _LOGGER.error("Error retrieving devices state: %s for path %s", msg, path)
    return True


def string_recursive_parse(
    obj: dict[str, Any] | str | list[Any], _depth: int = 0
) -> dict[str, Any] | list[Any] | str:
    """Recursively parse strings inside dicts/lists if they are valid JSON.

    A max depth is applied to avoid resource issues with deeply nested JSON.
    This should only be used with trusted sources to avoid resource exhaustion.
    """
    if _depth >= _MAX_JSON_PARSE_DEPTH:
        return obj

    if isinstance(obj, dict):
        return {k: string_recursive_parse(v, _depth + 1) for k, v in obj.items()}

    if isinstance(obj, list):
        return [string_recursive_parse(i, _depth + 1) for i in obj]

    if isinstance(obj, str) and obj.startswith(("{", "[")):
        try:
            return string_recursive_parse(orjson.loads(obj), _depth + 1)
        except orjson.JSONDecodeError:
            return obj

    return obj


def replace_routine_placeholders(
    obj: dict[str, Any],
    device: AmazonDevice,
) -> dict[str, Any]:
    """Replace placeholder values in a routine payload with actual device details."""

    def _replace(
        value: dict[str, Any] | str | list[Any],
    ) -> dict[str, Any] | str | list[Any]:

        if isinstance(value, dict):
            return {k: _replace(v) for k, v in value.items()}

        if isinstance(value, list):
            return [_replace(i) for i in value]

        if isinstance(value, str):
            if value in (
                "ALEXA_CURRENT_DSN",
                "<$Trigger.Alexa.Trigger.Alarms.NotificationStopped.$.payload.object.device.deviceSerialNumber$>",
            ):
                return device.serial_number

            if value in (
                "ALEXA_CURRENT_DEVICE_TYPE",
                "<$Trigger.Alexa.Trigger.Alarms.NotificationStopped.$.payload.object.device.productId$>",
            ):
                return device.device_type

        return value

    return {k: _replace(v) for k, v in obj.items()}


def get_innermost_frame(exc: BaseException) -> str:
    """Innermost frame still inside our own code, e.g. '_ping:531'."""
    for frame in reversed(traceback.extract_tb(exc.__traceback__)):
        if "aioamazondevices" in frame.filename:
            return f"{frame.name}:{frame.lineno}"
    return "unknown"


def get_deepest_cause(exc: BaseException) -> BaseException:
    """Get the deepest cause of an exception."""
    while exc.__cause__ is not None:
        exc = exc.__cause__
    return exc
