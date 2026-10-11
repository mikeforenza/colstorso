"""Runs the unmodified ColsTorso FastAPI app inside Pyodide (WebAssembly). The browser's fetch() calls for /api/* are turned
into ASGI requests against the same app, engine and SQLite schema that the server uses. No threads in WebAssembly, so the
thread-pool hop for sync endpoints is replaced by a direct call."""
import os, sys, asyncio
os.environ.setdefault("COLSTORSO_DB", "/data/colstorso.db")
os.environ.setdefault("COLSTORSO_PUBLIC_DEMO", "1")
os.environ.setdefault("COLSTORSO_RATE_LIMIT", "100000")
os.environ.setdefault("COLSTORSO_WRITE_RATE_LIMIT", "100000")
os.environ.setdefault("COLSTORSO_RESET_LIMIT", "1000")
os.environ["COLSTORSO_TRUST_PROXY"] = "0"
for d in ("/app/static", "/app/design", "/data"): os.makedirs(d, exist_ok=True)
sys.path.insert(0, "/app")

async def _direct(func, *a, **k): return func(*a, **k)
import starlette.concurrency as _sc
_sc.run_in_threadpool = _direct
import starlette.routing, starlette.datastructures, fastapi.routing, fastapi.dependencies.utils, fastapi.concurrency
for _m in (starlette.routing, starlette.datastructures, fastapi.routing, fastapi.dependencies.utils, fastapi.concurrency):
    if hasattr(_m, "run_in_threadpool"): _m.run_in_threadpool = _direct

from colstorso import db
_orig_connect = db.connect
def _connect(path=None):
    c = _orig_connect(path)
    try: c.execute("PRAGMA journal_mode=MEMORY")       # no WAL/shared memory in the browser FS
    except Exception: pass
    return c
db.connect = _connect
from colstorso.main import app   # noqa: E402  (the real app)

def stamp_fresh():
    """First open of the shipped demo snapshot: the data 'loads' into this browser now."""
    from colstorso.engine import now_iso
    c = db.get(); c.execute("UPDATE feeds SET loaded_at=?", (now_iso(),))

async def handle(method, path, headers, body):
    if hasattr(headers, "to_py"): headers = headers.to_py()
    if body is not None and hasattr(body, "to_bytes"): body = body.to_bytes()
    elif body is not None and hasattr(body, "to_py"): body = body.to_py()
    raw_path, _, qs = path.partition("?")
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "https",
             "path": raw_path, "raw_path": raw_path.encode(), "query_string": qs.encode(), "root_path": "",
             "headers": [(k.lower().encode(), v.encode()) for k, v in headers], "client": ("browser", 0), "server": ("browser", 443)}
    body = bytes(body or b"")
    sent = {"done": False}
    async def receive():
        if sent["done"]: return {"type": "http.disconnect"}
        sent["done"] = True; return {"type": "http.request", "body": body, "more_body": False}
    out = {"status": 500, "headers": [], "body": bytearray()}
    async def send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]; out["headers"] = [(k.decode(), v.decode()) for k, v in msg.get("headers", [])]
        elif msg["type"] == "http.response.body":
            out["body"].extend(msg.get("body", b""))
    await app(scope, receive, send)
    return out["status"], out["headers"], bytes(out["body"])

def snapshot():
    return db.get().serialize()
