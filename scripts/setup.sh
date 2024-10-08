#!/usr/bin/env bash
# Setups the repository.

# Stop on errors
set -e

cd
pre-commit install
pre-commit install --hook-type commit-msg
npm install @commitlint/config-conventional
