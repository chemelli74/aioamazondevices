"""Utils module for Amazon devices."""

import re
from collections.abc import Collection
from typing import Any

from .const import TO_REDACT


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


def normalize_device_model_name(model: str | None) -> str | None:
    """Normalize device model name by uniforming generation notation."""
    if model is None:
        return None
    return model.replace("generation", "Gen").strip()


def parse_device_hardware_version(model: str | None) -> str | None:
    """Parse hardware version from model name."""
    if model is None:
        return None

    # Matching example: "Echo Dot (4th Gen)"
    match = re.search(r"\(([^)]+ Gen)[^)]*\)", model)
    if match:
        return match.group(1).strip()

    # Matching example: "2021 Samsung UHD TV"
    match = re.search(r"\b(19|20)\d{2}\b", model)
    if match:
        return match.group(0).strip()

    return None
