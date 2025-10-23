"""Utils module for Amazon devices."""

from collections.abc import Collection
from pathlib import Path
from typing import Any

import orjson
from langcodes import Language, standardize_tag

from .const.common import _LOGGER, BIN_EXTENSION, HTML_EXTENSION, SAVE_PATH, TO_REDACT


def country_specific_data(domain: str) -> dict[str, str]:
    """Set country specific data."""
    # Force lower case
    domain = domain.replace("https://www.amazon.", "").lower()
    country_code = domain.split(".")[-1] if domain != "com" else "us"

    lang_object = Language.make(territory=country_code.upper())
    lang_maximized = lang_object.maximize()

    language = f"{lang_maximized.language}-{lang_maximized.territory}"

    return {
        "domain": domain,
        "country": country_code,
        "language": standardize_tag(language),
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


async def save_to_file(
    raw_data: str | dict,
    url: str,
    extension: str = HTML_EXTENSION,
    output_path: str = SAVE_PATH,
) -> None:
    """Save response data to disk."""
    if not raw_data:
        return

    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    if url.startswith("http"):
        url_split = url.split("/")
        base_filename = f"{url_split[3]}-{url_split[4].split('?')[0]}"
    else:
        base_filename = url
    fullpath = Path(output_dir, base_filename + extension)

    data: str
    if isinstance(raw_data, dict):
        data = orjson.dumps(raw_data, option=orjson.OPT_INDENT_2).decode("utf-8")
    elif extension in [HTML_EXTENSION, BIN_EXTENSION]:
        data = raw_data
    else:
        data = orjson.dumps(
            orjson.loads(raw_data),
            option=orjson.OPT_INDENT_2,
        ).decode("utf-8")

    i = 2
    while fullpath.exists():
        filename = f"{base_filename}_{i!s}{extension}"
        fullpath = Path(output_dir, filename)
        i += 1

    _LOGGER.warning("Saving data to %s", fullpath)

    with Path.open(fullpath, mode="w", encoding="utf-8") as file:
        file.write(data)
        file.write("\n")
