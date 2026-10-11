# ColsTorso

Open-source (MIT) store-operations platform for multi-store retailers. ColsTorso compares every store with similar stores,
turns the biggest gaps into a short list of **missions** (at most 3 per store), helps the manager accept them with a
pre-filled action plan, tracks the tasks, and **measures the impact** against a comparison group that is fixed when the mission is accepted.

It is built to cost very little to run with 1–5 operators: one container, SQLite, batch engine runs only when data loads,
LLM optional and cached (rule-based answers by default).

## Run it

| How | Command | Notes |
|---|---|---|
| Local, one command | `./run.sh` → http://localhost:8000 | Python 3.11+. Seeds the synthetic demo on first start |
| Docker | `docker compose up --build` → http://localhost:8000 | Data in the `colstorso-data` volume |
| Docker (no compose) | `docker build -t colstorso . && docker run -p 8000:8000 -v colstorso:/data colstorso` | Health check: `GET /api/health` |
| No server at all | `python scripts/build_browser.py`, then serve `dist/browser/` from any static host | The same Python app + SQLite running in WebAssembly (Pyodide), saved in the browser's IndexedDB |
| Publish free | `gh auth login` then `scripts/deploy_pages.sh` | Public repo + GitHub Pages at `https://<user>.github.io/colstorso/` |

Demo logins: pick a persona on the login screen (store manager, district/regional manager, HQ admin, analyst, DC manager…).
All data is synthetic. **Reset demo data** sits in the freshness strip under the top bar.

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | 8000 | HTTP port |
| `COLSTORSO_DB` | `./data/colstorso.db` (`/data/colstorso.db` in Docker) | SQLite file; uploads and the drop folder live next to it |
| `COLSTORSO_PUBLIC_DEMO` | 1 | Demo personas, API docs off, anyone signed in can reset the demo |
| `COLSTORSO_RATE_LIMIT` / `COLSTORSO_WRITE_RATE_LIMIT` | 240 / 60 | Requests per minute per IP (all / writes) |
| `COLSTORSO_RESET_LIMIT` | 6 | Demo resets or blank workspaces per hour (global) |
| `COLSTORSO_MAX_UPLOAD_MB` | 5 | Upload cap |
| `COLSTORSO_AUTO_SEED` | 1 | Build the demo on first start if the DB is empty |
| `COLSTORSO_LLM_URL`, `COLSTORSO_LLM_KEY`, `COLSTORSO_LLM_MODEL` | unset | Optional OpenAI-compatible endpoint. Answers are cached (`COLSTORSO_LLM_CACHE_HOURS`, default 168) and capped (`COLSTORSO_LLM_MAX_CALLS_PER_PROCESS`, 500) |

Postgres: not supported yet (roadmap). SQLite holds years of weekly data for hundreds of stores comfortably.

## What's in it

* **Ingest**: CSV upload with automatic column mapping, row-level validation, data-quality log, new stores/categories/districts created on the fly, file-drop folder, event hub (`POST /api/events`).
* **Self-serve onboarding** (`Get started`): blank workspace → stores CSV → weekly sales CSV → optional store KPIs → first missions. With the sample files it takes about 1 minute; tested end to end in the browser.
* **Mission engine** (`colstorso/engine.py`): peer groups by format and space share; gaps in $/week for category sales, waste, labor, overtime, conversion, CSAT, attachment, inventory accuracy, gap scans, cash; confidence from z-scores; substitution check (siblings selling more relative to the rest of the store); anomaly alerts; no-code rules; learned multipliers from past results; HQ campaigns (Gentle / Standard / Must-do, max 3 Must-do per quarter, configurable); blackouts; capacity-aware limit of 3 suggestions per store.
* **Mission lifecycle**: Suggested → Accepted → In progress → Done, or Not for us (internal: incoming / prelaunch / live / done / rejected; plus Snoozed). One-tap Accept (pre-filled plan from the best proven practice or best-performing action type), Snooze, and "Not for my store" with a reason.
* **Impact**: weekly difference-in-differences against up to 12 comparison stores fixed at accept; point estimate per week and in total plus a 90% likely range (placebo spread of the comparison stores); verdicts Worked / No clear change / Got worse; erosion after the mission ends.
* **HQ visibility into pushback**: Store feedback page and the campaigns side panel group turn-down reasons by reason, KPI and district.
* **Tasks & store walks**: templates with checklists, conditional survey questions, follow-up tasks, schedules, condition rules, events, CSV schedules, escalation of overdue tasks.
* **Field tools**: district/regional comparisons, visits with checklists, coaching notes, best-practice library, comms with read receipts, DC load-quality flags.
* **Ask ColsTorso + Help**: rule-based answers over live data that always list their sources; help centre with search and a support assistant; optional cached LLM polish.
* **Data age everywhere**: daily feeds fresh < 30h, ageing 30–54h, stale after; weekly labor stale after 8 days.
* **Design**: Portal UX Studio kit (`design/`): tokens, components, light/dark (follows the device, manual toggle).

## Tests

```
pip install -r requirements-dev.txt
pytest -q                          # 18 tests: engine maths, prioritisation limits, ingest→recompute, one-tap actions, onboarding, rate limit…
python scripts/e2e.py http://localhost:8000              # browser walk-through of every page for 4 roles + screenshots
python scripts/e2e_onboarding.py http://localhost:8000   # wizard end to end (wipes the workspace – use a throwaway server)
python scripts/e2e_browser.py http://localhost:8300/browser/   # the static WebAssembly build
```

## Costs

One small container (≈60–120 MB RAM) or a static site. The engine runs once per data load (≈25 ms for 16 stores, ≈1–2 s for 50 stores × 52 weeks of history on the demo). No LLM calls unless configured.

## Known gaps / roadmap

* Postgres option, multi-tenant hosting, SSO/real authentication (the demo uses persona switching only).
* Daily (not weekly) granularity for sales; native POS/WFM connectors (today: CSV, drop folder, event API).
* Push notifications / native mobile app (the web app is responsive).
* In the browser build: each visitor gets their own copy of the data (saved in their browser); the embed preview opens as a local page; first load downloads ≈15 MB from the Pyodide CDN.

## Licence

MIT, see `LICENSE`. Third-party: see `DEPENDENCIES.md`.
