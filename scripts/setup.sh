#!/usr/bin/env bash
set -e

POETRY_VERSION="2.3.2" # renovate: depName=poetry datasource=pypi

pipx install poetry==${POETRY_VERSION}
pipx install pre-commit
poetry config virtualenvs.in-project true
poetry sync --with dev
pre-commit install
pre-commit install --hook-type commit-msg

npm install
