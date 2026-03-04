#!/usr/bin/env bash
# Setups the repository.

# Stop on errors
set -e

poetry self update
poetry env use python3
poetry sync --with dev
poetry run pre-commit install
poetry run pre-commit install --hook-type commit-msg
cd
npm install @commitlint/config-conventional
