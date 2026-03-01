"""Utils module for Amazon devices."""

import logging
import re
from collections.abc import Collection
from typing import Any

from .const.devices import SPEAKER_GROUP_MODEL

_LOGGER = logging.getLogger(__package__)

TO_REDACT = {
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
    "state",
    "street",
    "user_id",
}


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
    if model is None or model == SPEAKER_GROUP_MODEL:
        return model, None

    model = re.sub(r"\bgeneration\b", "Gen", model, flags=re.IGNORECASE).strip()

    # Matching examples:
    #   "Echo Dot (5th gen) with Clock" -> ("Echo Dot with Clock", "5th Gen")
    #   "Fire TV Stick 4K (2nd Gen)" -> ("Fire TV Stick 4K", "2nd Gen")
    match = re.search(
        r"\(\s*(?P<ordinal>\d+(?:st|nd|rd|th))\s*gen\s*\)",  # codespell:ignore nd
        model,
        flags=re.IGNORECASE,
    )
    if match:
        parsed_model = re.sub(match.re, "", model, count=1)
        parsed_model = re.sub(r"\s+", " ", parsed_model).strip()
        return parsed_model, f"{match.group('ordinal').lower()} Gen"

    # Matching example: "2021 Samsung UHD TV" -> "2021"
    match = re.search(r"\b(19|20)\d{2}\b", model)
    if match:
        return model, match.group(0).strip()

    return model, None
