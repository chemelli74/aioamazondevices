#!/usr/bin/env bash
# Setups the repository.

# Stop on errors
set -e

# Use copy mode for UV to avoid hardlink warnings on different filesystems
export UV_LINK_MODE=copy

UV_VERSION="0.11.6" # renovate: depName=uv datasource=pypi

if ! uv --version 2>/dev/null | grep -q "$UV_VERSION"; then
    pipx install "uv==$UV_VERSION"
fi
if ! prek --version 2>/dev/null; then
    uv tool install prek
fi
uv sync --frozen --group dev
prek install --overwrite
prek install --hook-type commit-msg --overwrite

npm install @commitlint/config-conventional
