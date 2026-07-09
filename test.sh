#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "Running tests..."
uv run python -m unittest discover -s tests -v
