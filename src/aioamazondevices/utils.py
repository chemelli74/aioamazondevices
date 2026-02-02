"""Utils module for Amazon devices."""

import logging
from collections.abc import Collection
from typing import Any

from aioamazondevices.const.http import ARRAY_WRAPPER

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


async def format_graphql_error(graphql_response: dict) -> bool:
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
