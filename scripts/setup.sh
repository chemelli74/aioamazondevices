#!/usr/bin/env bash
# Setups the repository.

# Stop on errors
set -e

POETRY_VERSION="2.3.2" # renovate: depName=poetry datasource=pypi

poetry self update "$POETRY_VERSION"
poetry env use python3
poetry sync --with dev
poetry run pre-commit install
poetry run pre-commit install --hook-type commit-msg
cd
npm install @commitlint/config-conventional
