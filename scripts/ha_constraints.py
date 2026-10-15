#!/usr/bin/env python3
# Copyright 2026 Simone Chemelli and contributors
# SPDX-License-Identifier: Apache-2.0
"""Keep runtime dependencies aligned with Home Assistant package constraints.

Every runtime package (direct or transitive) that Home Assistant pins with
``==`` must appear with the same pin in ``[tool.uv] constraint-dependencies``.

Usage:
    scripts/ha_constraints.py          # check, exit 1 on drift
    scripts/ha_constraints.py --fix    # sync pyproject.toml, renovate.json, uv.lock
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

HA_CONSTRAINTS_URL = os.environ.get(
    "HA_CONSTRAINTS_URL",
    "https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/package_constraints.txt",
)
ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
RENOVATE = ROOT / "renovate.json"
RENOVATE_RULE = "Pinned to Home Assistant package_constraints.txt"
PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==([^\s;#]+)")
BLOCK_RE = re.compile(r"^constraint-dependencies = \[\n(?:.*\n)*?\]\n", re.MULTILINE)
RENOVATE_RE = re.compile(
    rf'("description": "{re.escape(RENOVATE_RULE)}[^"]*",\n'
    r'(?P<indent>[ ]*)"matchPackageNames": \[)[^\]]*\]'
)
FIX_MAX_ROUNDS = 5


def normalize(name: str) -> str:
    """Normalize a package name as per PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pins(text: str) -> dict[str, str]:
    """Return {name: version} for every exact pin in a requirements text."""
    pins: dict[str, str] = {}
    for line in text.splitlines():
        if match := PIN_RE.match(line.strip()):
            pins[normalize(match[1])] = match[2]
    return pins


def ha_pins() -> dict[str, str]:
    """Download Home Assistant exact pins."""
    with urllib.request.urlopen(HA_CONSTRAINTS_URL, timeout=30) as resp:  # noqa: S310
        return parse_pins(resp.read().decode())


def runtime_packages() -> dict[str, str]:
    """Return runtime packages resolved in uv.lock (no dev groups)."""
    output = subprocess.run(
        [  # noqa: S607
            "uv",
            "export",
            "--frozen",
            "--no-dev",
            "--no-hashes",
            "--no-emit-project",
            "--no-header",
            "--no-annotate",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return parse_pins(output)


def current_constraints() -> dict[str, str]:
    """Return the pins in [tool.uv] constraint-dependencies."""
    data = tomllib.loads(PYPROJECT.read_text())
    entries = data.get("tool", {}).get("uv", {}).get("constraint-dependencies", [])
    return parse_pins("\n".join(entries))


def renovate_disabled() -> set[str]:
    """Return the packages renovate is told not to update."""
    for rule in json.loads(RENOVATE.read_text())["packageRules"]:
        if rule.get("description", "").startswith(RENOVATE_RULE):
            return {normalize(name) for name in rule["matchPackageNames"]}
    return set()


def write_constraints(pins: dict[str, str]) -> None:
    """Rewrite the constraint-dependencies block in pyproject.toml."""
    content = PYPROJECT.read_text()
    lines = "".join(f'    "{name}=={pins[name]}",\n' for name in sorted(pins))
    block = f"constraint-dependencies = [\n{lines}]\n"
    if not BLOCK_RE.search(content):
        sys.exit("constraint-dependencies block not found in pyproject.toml")
    PYPROJECT.write_text(BLOCK_RE.sub(block, content, count=1))


def write_renovate(names: list[str]) -> None:
    """Rewrite the package list of the renovate rule, keeping its formatting."""
    content = RENOVATE.read_text()
    if not (match := RENOVATE_RE.search(content)):
        sys.exit(f"renovate.json '{RENOVATE_RULE}' rule not found")
    indent = match["indent"]
    items = ",\n".join(f'{indent}  "{name}"' for name in names)
    RENOVATE.write_text(
        RENOVATE_RE.sub(lambda m: f"{m[1]}\n{items}\n{indent}]", content, count=1)
    )


def expected_pins(ha: dict[str, str]) -> dict[str, str]:
    """Return the HA pins applying to the current lock and constraints."""
    # Keep current entries too: a package may drop out of the lock only
    # because the constraint itself changed the resolution.
    names = runtime_packages().keys() | current_constraints().keys()
    return {name: ha[name] for name in names if name in ha}


def fix(ha: dict[str, str]) -> None:
    """Sync constraints, renovate rule and lock until they are stable."""
    for _ in range(FIX_MAX_ROUNDS):
        expected = expected_pins(ha)
        write_constraints(expected)
        write_renovate(sorted(expected))
        # Relocking can pull in new transitive packages pinned by HA.
        if subprocess.run(["uv", "lock"], check=False).returncode:  # noqa: S607
            sys.exit(
                "uv lock failed: a dependency range in pyproject.toml likely "
                "excludes a Home Assistant pin"
            )
        if expected_pins(ha) == expected:
            return
    sys.exit(f"Constraints did not stabilize after {FIX_MAX_ROUNDS} rounds")


def check(ha: dict[str, str]) -> int:
    """Report drift from Home Assistant pins."""
    runtime = runtime_packages()
    current = current_constraints()
    expected = expected_pins(ha)

    errors = [
        f"{name}: constraint {current.get(name, 'missing')}, Home Assistant {version}"
        for name, version in sorted(expected.items())
        if current.get(name) != version
    ]
    errors += [
        f"{name}: constrained but not pinned by Home Assistant"
        for name in sorted(current.keys() - expected.keys())
    ]
    errors += [
        f"{name}: locked {runtime[name]}, Home Assistant {version}"
        for name, version in sorted(expected.items())
        if name in runtime and runtime[name] != version
    ]
    if renovate_disabled() != expected.keys():
        errors.append(
            f"renovate.json '{RENOVATE_RULE}' rule must list exactly: "
            + ", ".join(sorted(expected))
        )
    if errors:
        print("Dependencies drifted from Home Assistant package_constraints.txt:")
        print("\n".join(f"  - {error}" for error in errors))
        print("Run: scripts/ha_constraints.py --fix")
        return 1

    print(f"OK: {len(expected)} packages aligned with Home Assistant")
    return 0


def main() -> int:
    """Check or fix constraint drift."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fix",
        action="store_true",
        help="update pyproject.toml, renovate.json and uv.lock",
    )
    args = parser.parse_args()

    ha = ha_pins()
    if args.fix:
        fix(ha)
    return check(ha)


if __name__ == "__main__":
    sys.exit(main())
