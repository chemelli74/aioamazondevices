#!/usr/bin/env bash
# Setups the repository.

# Stop on errors
set -e

UV_VERSION="0.8.22" # renovate: depName=uv datasource=pypi

python3 -m pip install --disable-pip-version-check --no-cache-dir "uv==$UV_VERSION"
uv sync --group dev
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
cd
npm install @commitlint/config-conventional
