#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting Python + Node dev cleanup..."

# ----- Python bytecode -----
echo "Removing __pycache__ and *.py[co]..."
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.py[co]" -delete

# ----- Tool caches -----
echo "Removing Python tool caches..."
for cache in .mypy_cache .ruff_cache .pytest_cache .hypothesis .pytype .isort_cache; do
    [ -d "$cache" ] && rm -rf "$cache" && echo "Removed $cache"
done

# ----- Virtual environments -----
echo "Removing virtual environments..."
for venv in .venv venv env; do
    [ -d "$venv" ] && rm -rf "$venv" && echo "Removed $venv"
done

# ----- Build artifacts -----
echo "Removing build artifacts..."
for build in build dist *.egg-info; do
    [ -e "$build" ] && rm -rf "$build" && echo "Removed $build"
done

# ----- IDE / project folders -----
echo "Removing IDE folders..."
for ide in .idea; do
    [ -d "$ide" ] && rm -rf "$ide" && echo "Removed $ide"
done

# ----- Coverage files -----
echo "Removing coverage files..."
for coverage in .coverage coverage.xml; do
    [ -f "$coverage" ] && rm -f "$coverage" && echo "Removed $coverage"
done

# ----- Node.js caches -----
echo "Removing Node.js caches..."
if [ -d "node_modules/.cache" ]; then
    rm -rf node_modules/.cache
    echo "Removed node_modules/.cache"
fi

echo "✅ Cleanup complete!"
