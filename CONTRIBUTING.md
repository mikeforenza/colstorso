# Contributing

1. `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`
2. `./run.sh` (or `.venv/bin/python -m uvicorn colstorso.main:app --reload`) and open http://localhost:8000
3. `pytest -q` must stay green; add a test with every engine change (`tests/test_engine.py`).
4. UI code uses only design tokens (`--ct-*` from `design/tokens.css`). Don't hard-code colours.
5. Keep it cheap to run: no new always-on services, no per-page-view computation, LLM calls optional and cached.
6. Only permissively licensed dependencies (MIT/BSD/Apache/ISC/OFL); list them in `DEPENDENCIES.md`.
7. Demo data must stay synthetic. Never commit real retailer data or secrets.

Layout: `colstorso/` (API `main.py`, engine, tasks, AI, help, ingest, onboarding, seed/generator), `static/` (SPA), `design/` (brand kit),
`browser/` (WebAssembly runtime), `scripts/` (build, deploy, e2e), `tests/`.
