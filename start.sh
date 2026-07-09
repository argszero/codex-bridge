#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "Starting codex-bridge on http://127.0.0.1:10110 ..."
uv run python -m src.main "$@"
