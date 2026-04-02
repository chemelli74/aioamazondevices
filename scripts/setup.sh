#!/usr/bin/env bash
# Setups the repository.

# Stop on errors
set -e

UV_VERSION="0.8.22" # renovate: depName=uv datasource=pypi

if ! python3 -m uv --version 2>/dev/null | grep -q "$UV_VERSION"; then
    python3 -m pip install --disable-pip-version-check --no-cache-dir "uv==$UV_VERSION"
fi
if ! python3 -m pre-commit --version 2>/dev/null; then
    python3 -m pip install --disable-pip-version-check --no-cache-dir "pre-commit"
fi
python3 -m uv sync --frozen --group dev
python3 -m uv run pre-commit install
python3 -m uv run pre-commit install --hook-type commit-msg
cd
npm install @commitlint/config-conventional
