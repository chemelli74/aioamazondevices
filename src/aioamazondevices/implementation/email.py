"""Email parsing utilities for Amazon HTTP/2 push messages."""

from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default
from typing import Any

import orjson

from aioamazondevices.utils import _LOGGER, string_recursive_parse


def email_extract_json_from_part(part: bytes) -> dict[str, Any] | None:
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
    except (TypeError, ValueError, orjson.JSONDecodeError) as exc:
        _LOGGER.warning(
            "Failed to parse multipart section: %s",
            part.decode("utf-8", errors="replace"),
            exc_info=exc,
        )
        return None
    else:
        return parsed


def email_parse_boundary_delimiter(content_type: str) -> bytes | None:
    """Extract the boundary delimiter from a Content-Type header value.

    Returns the full delimiter bytes (with '--' prefix) ready for use
    with bytes.find().
    """
    msg = EmailMessage()
    msg["Content-Type"] = content_type
    if not (boundary := msg.get_boundary()):
        return None
    return f"--{boundary}".encode()
