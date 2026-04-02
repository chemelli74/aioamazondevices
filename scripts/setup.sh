#!/usr/bin/env bash
# Setups the repository.

# Stop on errors
set -e

UV_VERSION="0.8.22" # renovate: depName=uv datasource=pypi

if ! uv --version 2>/dev/null | grep -q "$UV_VERSION"; then
    pipx install "uv==$UV_VERSION"
fi
if ! prek --version 2>/dev/null; then
    uv tool install prek
fi
uv sync --frozen --group dev
prek install
prek install --hook-type commit-msg

npm install @commitlint/config-conventional
