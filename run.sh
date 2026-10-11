#!/usr/bin/env sh
# One-command local start: creates a venv, installs deps, seeds demo data on first run, serves on :8000
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -q -r requirements.txt
exec .venv/bin/python -m uvicorn colstorso.main:app --host "${COLSTORSO_HOST:-0.0.0.0}" --port "${PORT:-8000}"
