#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting Python + Node dev cleanup..."

# ----- Python bytecode -----
echo "Removing __pycache__ and *.py[co]..."
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.py[co]" -delete
find . -type f -name '*$py.class' -delete

# ----- Tool caches -----
echo "Removing Python tool caches..."
for cache in .mypy_cache .ruff_cache .pytest_cache .hypothesis .pytype .isort_cache .tox .nox .cache .pyre .pybuilder cython_debug __pypackages__; do
    [ -d "$cache" ] && rm -rf "$cache"
done

for file in .dmypy.json dmypy.json; do
    [ -f "$file" ] && rm -f "$file"
done

# ----- Virtual environments -----
echo "Removing virtual environments..."
deactivate 2>/dev/null || true
for venv in .venv venv env ENV env.bak venv.bak; do
    [ -d "$venv" ] && rm -rf "$venv"
done

# ----- Build artifacts -----
echo "Removing build artifacts..."
for build in .Python build develop-eggs dist downloads eggs .eggs lib lib64 parts sdist var wheels share/python-wheels target out site docs/_build *.egg-info *.egg; do
    [ -e "$build" ] && rm -rf "$build"
done

for file in .installed.cfg MANIFEST; do
    [ -e "$file" ] && rm -rf "$file"
done

find . -type f \( -name '*.so' -o -name '*.manifest' -o -name '*.spec' \) -delete

# ----- IDE / project folders -----
echo "Removing IDE folders..."
for ide in .idea .ipynb_checkpoints profile_default .spyderproject .spyproject .ropeproject; do
    [ -d "$ide" ] && rm -rf "$ide"
done

[ -f ipython_config.py ] && rm -f ipython_config.py

# ----- Coverage files -----
echo "Removing coverage files..."
for coverage in .coverage coverage.xml nosetests.xml; do
    [ -f "$coverage" ] && rm -f "$coverage"
done

for coverage_dir in htmlcov cover; do
    [ -e "$coverage_dir" ] && rm -rf "$coverage_dir"
done

find . -maxdepth 1 -type f \( -name '.coverage.*' -o -name '*.cover' -o -name '*.py,cover' \) -delete

# ----- Runtime / local files -----
echo "Removing runtime and local files..."
for runtime_dir in instance .webassets-cache .scrapy; do
    [ -d "$runtime_dir" ] && rm -rf "$runtime_dir"
done

for runtime_file in celerybeat-schedule celerybeat.pid db.sqlite3 db.sqlite3-journal pip-log.txt pip-delete-this-directory.txt local_settings.py .env; do
    [ -e "$runtime_file" ] && rm -rf "$runtime_file"
done

find . -type f \( -name '*.mo' -o -name '*.pot' -o -name '*.log' \) -delete

# ----- Node.js -----
echo "Removing Node.js..."
if [ -d "node_modules" ]; then
    rm -rf node_modules
fi

echo "✅ Cleanup complete!"
