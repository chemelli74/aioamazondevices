"""Utils module for Amazon devices."""

from typing import Any


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


def obfuscate_dict_field(data: dict[str, Any], key: str = "password") -> dict[str, Any]:
    """Obfuscate the value associated with the key in a dictionary."""
    result = data.copy()
    if key in result and isinstance(result[key], str):
        result[key] = "*" * len(result[key])
    return result
