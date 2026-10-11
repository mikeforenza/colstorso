# Dependencies and licences

| Component | Use | Licence |
|---|---|---|
| FastAPI | web framework | MIT |
| Starlette | ASGI toolkit (via FastAPI) | BSD-3-Clause |
| Pydantic / pydantic-core | validation (via FastAPI) | MIT |
| Uvicorn | server | BSD-3-Clause |
| python-multipart | CSV uploads | Apache-2.0 |
| anyio, sniffio, typing-extensions, annotated-types | FastAPI deps | MIT / MIT-or-Apache-2.0 / PSF |
| SQLite (Python stdlib) | database | Public domain |
| Pyodide (browser build only, loaded from jsDelivr) | Python in WebAssembly | MPL-2.0 |
| Manrope, Inter fonts | UI type | SIL OFL 1.1 |
| Lucide icons | UI icons | ISC |
| pytest, httpx, Playwright (dev only) | tests, screenshots | MIT / BSD-3-Clause / Apache-2.0 |

No frontend framework: the UI is plain JavaScript and SVG charts.
