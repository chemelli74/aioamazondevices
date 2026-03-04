#!/usr/bin/env bash
# Setups the repository.

# Stop on errors
set -e

poetry self update
poetry env activate
pre-commit install
pre-commit install --hook-type commit-msg
cd
npm install @commitlint/config-conventional
