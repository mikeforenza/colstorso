"""ColsTorso API server (FastAPI). Serves the SPA from /static and the JSON API under /api."""
import os, json, csv, io, uuid, datetime as dt, statistics as stats
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
import time, threading
from collections import deque
from . import config as CFG
from . import db
if CFG.DB_PATH: db.DB_PATH = CFG.DB_PATH
from . import engine as E, tasks as T, ai, ingest as I, seed, onboarding as OB, help as HELP
from .playbook import KPIS, ROOT_CAUSES, ACTIONS, GUIDANCE, DEFAULT_PERMISSIONS, ROLE_LABELS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = CFG.PUBLIC_DEMO
app = FastAPI(title="ColsTorso", version="1.0.0", debug=False,
              docs_url=None if PUBLIC else "/docs", redoc_url=None, openapi_url=None if PUBLIC else "/openapi.json")

# ---------- rate limiting, upload cap, security headers ----------
_hits, _lock, _resets = defaultdict(deque), threading.Lock(), deque()
def _client(req):
    if CFG.TRUST_PROXY and req.headers.get("x-forwarded-for"): return req.headers["x-forwarded-for"].split(",")[0].strip()
    return req.client.host if req.client else "?"

def _allow(key, limit, window):
    now = time.time()
    with _lock:
        q = _hits[key]
        while q and q[0] < now - window: q.popleft()
        if len(q) >= limit: return False
        q.append(now); return True

@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if path not in ("/api/health",) and not path.startswith(("/static/", "/design/")):
        ip = _client(request)
        if not _allow(("all", ip), CFG.RATE_LIMIT_PER_MIN, 60):
            return JSONResponse({"detail": "Too many requests – slow down a little."}, status_code=429, headers={"Retry-After": "30"})
        if request.method in ("POST", "PUT", "DELETE") and not _allow(("w", ip), CFG.WRITE_LIMIT_PER_MIN, 60):
            return JSONResponse({"detail": "Too many changes in a minute – try again shortly."}, status_code=429, headers={"Retry-After": "30"})
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > CFG.MAX_UPLOAD_MB * 1024 * 1024 + 4096:
        return JSONResponse({"detail": f"Upload too large (max {CFG.MAX_UPLOAD_MB:g} MB)"}, status_code=413)
    try:
        resp = await call_next(request)
    except Exception:
        import logging; logging.exception("unhandled")
        return JSONResponse({"detail": "Something went wrong on our side."}, status_code=500)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN" if not path.startswith("/embed/") else resp.headers.get("X-Frame-Options", "ALLOWALL")
    if path.startswith("/embed/"): del resp.headers["X-Frame-Options"]
    return resp

@app.on_event("startup")
def _startup():
    c = db.get()
    if CFG.AUTO_SEED and not c.execute("SELECT COUNT(*) FROM stores").fetchone()[0]:
        seed.build(path=db.DB_PATH, quiet=True)
app.mount("/static", StaticFiles(directory=os.path.join(ROOT, "static")), name="static")
os.makedirs(os.path.join(ROOT, "design"), exist_ok=True)
app.mount("/design", StaticFiles(directory=os.path.join(ROOT, "design")), name="design")
DATA_DIR = os.path.dirname(os.path.abspath(db.DB_PATH))          # everything writable lives next to the database
UPLOADS = os.path.join(DATA_DIR, "files"); os.makedirs(UPLOADS, exist_ok=True)
DROP = os.path.join(DATA_DIR, "dropfolder"); os.makedirs(DROP, exist_ok=True)

def C(): return db.get()

def user_of(req: Request):
    uid = req.headers.get("X-User") or req.query_params.get("as")
    if not uid: raise HTTPException(401, "Sign in first")
    u = db.one(C(), "SELECT * FROM users WHERE id=? AND active=1", (int(uid),))
    if not u: raise HTTPException(401, "Unknown user")
    return u

def perms(u):
    return set(db.setting(C(), "permissions", DEFAULT_PERMISSIONS).get(u["role"], []))

def need(u, cap):
    if cap not in perms(u): raise HTTPException(403, f"Your role ({ROLE_LABELS.get(u['role'])}) can't do this ({cap}).")

def scope(u):
    c = C(); r = u["role"]
    if r in ("hq_admin", "central_analyst"): q, a = "SELECT id FROM stores", ()
    elif r == "regional_manager": q, a = "SELECT s.id FROM stores s JOIN districts d ON d.id=s.district_id WHERE d.region_id=?", (u["region_id"],)
    elif r == "district_manager": q, a = "SELECT id FROM stores WHERE district_id=?", (u["district_id"],)
    elif r == "dc_manager": q, a = "SELECT DISTINCT store_id id FROM pallets WHERE dc_id=?", (u["dc_id"],)
    else: q, a = "SELECT id FROM stores WHERE id=?", (u["store_id"] or 0,)
    return [x["id"] for x in db.rows(c, q, a)]

def ids_sql(ids): return ",".join(map(str, ids)) or "0"

def check_store(u, sid):
    if int(sid) not in scope(u): raise HTTPException(403, "That store is outside your scope")

def week(): return db.setting(C(), "current_week")

async def body(req):
    try: return await req.json()
    except Exception: return {}

def enrich(c, m):
    s = db.one(c, "SELECT code, name, format, district_id FROM stores WHERE id=?", (m["store_id"],)) or {}
    m["store_code"], m["store_name"] = s.get("code"), s.get("name")
    o = db.one(c, "SELECT name FROM users WHERE id=?", (m["owner_id"],)) if m.get("owner_id") else None
    m["owner_name"] = o["name"] if o else None
    m["cat_name"] = (db.one(c, "SELECT name FROM categories WHERE id=?", (m["cat_id"],)) or {}).get("name") if m.get("cat_id") else None
    k = KPIS.get(m["kpi"], KPIS["custom"]); m["kpi_label"], m["kpi_group"] = k["label"], k["group"]
    if m["status"] in ("live", "done"):
        m["impact"] = E.mission_impact_summary(c, m["id"]); m["impact"].pop("weeks", None)
    m["root_causes"] = db.J(m.get("root_causes"), [])
    m["label"] = UI_STATUS.get(m["status"], m["status"])
    if m["status"] == "proposed": m["label"] = "Accepted · awaiting approval"
    z = None
    if m.get("opp_id"):
        o = db.one(c, "SELECT z FROM opportunities WHERE id=?", (m["opp_id"],)); z = o and o["z"]
    m["z"] = z
    m["confidence"] = None if z is None else ("High" if abs(z) > 2.5 else "Medium" if abs(z) > 1.5 else "Low")
    m["effort_min"] = EFFORT.get(m["kpi"], 20)
    return m

UI_STATUS = {"incoming": "Suggested", "prelaunch": "Accepted", "proposed": "Accepted", "live": "In progress", "done": "Done",
             "rejected": "Not for us", "snoozed": "Snoozed"}
EFFORT = {"sales": 20, "waste": 20, "labor": 30, "overtime": 30, "conversion": 25, "csat": 20, "attach": 15, "invacc": 30,
          "gapscan": 10, "cash": 15, "equipment": 10, "custom": 20, "dc_quality": 20, "theme": 30}
DEFAULT_ACTION = {"sales": "Fix availability & ordering", "waste": "Ordering reduction", "labor": "Schedule rebalance",
    "overtime": "Schedule rebalance", "conversion": "Schedule rebalance", "csat": "Coach the team", "attach": "Coach the team",
    "invacc": "Process / routine change", "gapscan": "Process / routine change", "cash": "Process / routine change",
    "equipment": "Repair / maintenance ticket"}

def suggest_plan(c, m):
    """Pre-filled plan: proven best practice for this KPI/category if one exists, else the action type with the best measured
    average for the KPI, else a sensible default. Root cause = most common one for the KPI."""
    exact = db.one(c, "SELECT * FROM best_practices WHERE kpi=? AND COALESCE(cat_id,-1)=COALESCE(?,-1) ORDER BY impact_value DESC", (m["kpi"], m["cat_id"]))
    bp = exact or db.one(c, "SELECT * FROM best_practices WHERE kpi=? ORDER BY impact_value DESC", (m["kpi"],))
    st = ai.action_stats(c, m["kpi"])
    at = (bp or {}).get("action_type") or (st[0]["a"] if st else None) or DEFAULT_ACTION.get(m["kpi"], "Process / routine change")
    action = (exact or {}).get("body") or ACTIONS.get(at, "")   # another category's write-up would not fit; reuse only its action type
    owner = m["owner_id"]
    due = (dt.date.fromisoformat(T.today(c)) + dt.timedelta(days=3)).isoformat()
    src = f"best practice #{bp['id']} ({bp['title']}, {'+' if (bp['impact_value'] or 0) >= 0 else ''}${bp['impact_value'] or 0:,.0f} measured)" if bp else \
          (f"best average result for this KPI ({st[0]['a']}, n={st[0]['n']})" if st else "default playbook")
    return dict(root_causes=ROOT_CAUSES.get(m["kpi"], ROOT_CAUSES["custom"])[:1], action_type=at, action=action,
                target_weekly=round(max(m["target_weekly"] or m["baseline_gap"] or 0, 0)), duration=db.setting(c, "mission_duration", 4),
                tasks=[dict(title=f"{at}: {(m.get('cat_name') or m['title'])}", assignee_id=owner, due=due)], source=src)

@app.get("/", response_class=HTMLResponse)
def index(): return FileResponse(os.path.join(ROOT, "static", "index.html"))

@app.get("/api/health")
def health(): return {"ok": True, "week": week()}

@app.get("/api/users")
def users_public():
    return db.rows(C(), """SELECT u.id, u.name, u.role, u.store_id, u.district_id, u.region_id, s.code store_code, d.name district
        FROM users u LEFT JOIN stores s ON s.id=u.store_id LEFT JOIN districts d ON d.id=u.district_id WHERE u.active=1 ORDER BY u.id""")

@app.post("/api/login")
async def login(req: Request):
    b = await body(req); c = C()
    u = db.one(c, "SELECT * FROM users WHERE id=? AND active=1", (int(b.get("user_id", 0)),))
    if not u: raise HTTPException(404, "No such user")
    c.execute("UPDATE users SET last_login=? WHERE id=?", (T.today(c), u["id"]))
    c.execute("INSERT INTO logins VALUES(?,?)", (u["id"], E.now_iso())); c.commit()
    return u

def freshness(c):
    """Daily feeds: fresh < 30h, ageing 30–54h, stale after. Weekly feeds: stale after 8 days (ageing after 7)."""
    now = dt.datetime.now(dt.timezone.utc); out = []
    for f in db.rows(c, "SELECT * FROM feeds ORDER BY name"):
        try: age = (now - dt.datetime.fromisoformat(f["loaded_at"]).astimezone(dt.timezone.utc)).total_seconds() / 3600
        except Exception: age = 1e9
        if f["cadence"] == "daily": state = "fresh" if age < 30 else ("aging" if age < 54 else "stale")
        else: state = "fresh" if age < 7 * 24 else ("aging" if age < 8 * 24 else "stale")
        out.append(dict(f, age_hours=round(age, 1), state=state))
    return out

@app.get("/api/freshness")
def freshness_api(req: Request): user_of(req); return freshness(C())

# ---------------- self-serve onboarding & help ----------------
def _reset_guard():
    now = time.time()
    with _lock:
        while _resets and _resets[0] < now - 3600: _resets.popleft()
        if len(_resets) >= CFG.RESET_LIMIT_PER_HOUR: raise HTTPException(429, "The workspace was rebuilt recently – try again later.")
        _resets.append(now)

@app.post("/api/onboarding/blank")
async def ob_blank(req: Request):
    u = user_of(req)
    if not PUBLIC: need(u, "users")
    b = await body(req); _reset_guard()
    uid = OB.blank((b.get("company") or "My retail company")[:80], (b.get("admin_name") or "HQ admin")[:60])
    return {"ok": True, "user_id": uid}

@app.get("/api/onboarding/status")
def ob_status(req: Request): user_of(req); return OB.status(C())

@app.get("/api/onboarding/sample/{name}.csv")
def ob_sample(name: str):
    try: txt = OB.sample(name)
    except KeyError: raise HTTPException(404, "Unknown sample")
    return Response(txt, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=sample_{name}.csv"})

@app.post("/api/onboarding/stores_done")
def ob_stores(req: Request):
    u = user_of(req); need(u, "data"); c = C(); n = OB.finish_stores(c); return {"logins_created": n, **OB.status(c)}

@app.post("/api/onboarding/run")
def ob_run(req: Request):
    u = user_of(req); need(u, "data"); c = C(); st = OB.status(c)
    if not st["ready"]: raise HTTPException(400, "Need at least 4 open stores and 2 weeks of sales first")
    t = time.time(); w = c.execute("SELECT MAX(week) FROM fact_sales").fetchone()[0]
    r = E.run_week(c, w); db.set_setting(c, "tenant_kind", "onboarded")
    return {**r, "engine_ms": round((time.time() - t) * 1000), **OB.status(c)}

@app.get("/api/help")
def help_search(req: Request, q: str = ""):
    user_of(req)
    return {"articles": HELP.search(q, 5) if q.strip() else [dict(id=a[0], title=a[1], section=a[2], body=a[3], link=a[4]) for a in HELP.ARTICLES]}

@app.post("/api/help/ask")
async def help_ask(req: Request):
    user_of(req); b = await body(req); q = (b.get("q") or "")[:500]
    h = HELP.answer(q)
    h["answer"] = ai.llm("You are ColsTorso product support. Answer only from the help article.", {"q": q, "articles": h["articles"][:2]}, h["answer"])
    return h

@app.get("/api/meta")
def meta(req: Request):
    u = user_of(req); c = C(); ids = scope(u)
    return dict(user=u, role_label=ROLE_LABELS.get(u["role"]), perms=sorted(perms(u)), week=week(), today=T.today(c),
        week_start=(db.one(c, "SELECT start_date FROM weeks WHERE week=?", (week(),)) or {}).get("start_date"),
        kpis=KPIS, root_causes=ROOT_CAUSES, actions=ACTIONS, roles=ROLE_LABELS,
        categories=db.rows(c, "SELECT * FROM categories ORDER BY parent_id, id"),
        districts=db.rows(c, "SELECT * FROM districts"), regions=db.rows(c, "SELECT * FROM regions"),
        stores=db.rows(c, f"SELECT * FROM stores WHERE id IN ({ids_sql(ids)}) ORDER BY code"),
        all_tags=sorted({t for s in db.rows(c, "SELECT tags FROM stores") for t in db.J(s["tags"], [])}),
        settings={k: db.setting(c, k) for k in ["inbox_size", "window_weeks", "currency", "mission_duration", "require_approval", "brand", "max_must_per_quarter"]},
        freshness=freshness(c), public_demo=PUBLIC, tenant_kind=db.setting(c, 'tenant_kind', 'demo'), company=db.setting(c, 'company'), ui_status=UI_STATUS,
        unread=c.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0", (u["id"],)).fetchone()[0])

def my_missions_filter(u):
    if u["role"] in ("store_manager", "associate"): return f"store_id IN ({ids_sql(scope(u))}) AND (owner_id={u['id']} OR kind!='theme')"
    if u["role"] == "dc_manager": return f"owner_id={u['id']}"
    return f"(store_id IN ({ids_sql(scope(u))}) OR owner_id={u['id']})"

@app.get("/api/home")
def home(req: Request, store: int = None):
    u = user_of(req); c = C(); ids = scope(u)
    if store: check_store(u, store); ids = [store]
    f = my_missions_filter(u) if not store else f"store_id={store} AND (kind!='theme' OR owner_id={u['id']})"
    inbox = [enrich(c, m) for m in db.rows(c, f"""SELECT * FROM missions WHERE status='incoming' AND {f} ORDER BY
        CASE priority WHEN 'Must' THEN 0 WHEN 'Should' THEN 1 ELSE 2 END, baseline_gap DESC LIMIT 60""")]
    tq = f"t.store_id IN ({ids_sql(ids)})" + (f" AND t.assignee_id={u['id']}" if u["role"] == "associate" else "")
    tl = db.rows(c, f"SELECT t.*, s.code store_code FROM tasks t JOIN stores s ON s.id=t.store_id WHERE t.status='open' AND {tq} ORDER BY t.due LIMIT 200")
    buckets = defaultdict(list)
    for t in tl: t["bucket"] = T.priority_bucket(c, t); buckets[t["bucket"]].append(t)
    anns = comms_for(c, u)
    live = [enrich(c, m) for m in db.rows(c, f"SELECT * FROM missions WHERE status='live' AND {f} ORDER BY start_week DESC LIMIT 30")]
    return dict(briefing=ai.briefing(c, u, ids), inbox=inbox, tasks=buckets, announcements=[a for a in anns if not a["read"]][:5],
                live=live, notifications=db.rows(c, "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 15", (u["id"],)),
                capacity=[x for x in E.capacity_status(c) if x["store_id"] in ids][:60])

@app.get("/api/notifications")
def notifs(req: Request):
    u = user_of(req); return db.rows(C(), "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 100", (u["id"],))

@app.post("/api/notifications/read")
def notifs_read(req: Request):
    u = user_of(req); c = C(); c.execute("UPDATE notifications SET read=1 WHERE user_id=?", (u["id"],)); c.commit(); return {"ok": True}

# ---------------- missions ----------------
GAP_KPIS = ("sales", "waste", "cash", *E.STORE_KPIS)

@app.get("/api/missions")
def missions(req: Request, status: str = None, store: int = None, kpi: str = None):
    u = user_of(req); c = C()
    q = f"SELECT * FROM missions WHERE {my_missions_filter(u)}"; a = []
    if store: check_store(u, store); q += " AND store_id=?"; a.append(store)
    if status: q += f" AND status IN ({','.join('?'*len(status.split(',')))})"; a += status.split(",")
    if kpi: q += " AND kpi=?"; a.append(kpi)
    return [enrich(c, m) for m in db.rows(c, q + " ORDER BY id DESC LIMIT 400", a)]

def series(c, m, n=12):
    out = []; w = week()
    for wk in range(max(1, w - n + 1), w + 1):
        wd = E.WeekData(c, wk, 1)
        if m["kpi"] == "equipment" and m.get("cat_id"):
            out.append(dict(week=wk, actual=wd.sales.get((m["store_id"], m["cat_id"]), 0))); continue
        g = E.metric_gap(wd, m["store_id"], m["kpi"], m.get("cat_id")) if m["kpi"] in GAP_KPIS else None
        if g:
            ly = None
            if m["kpi"] == "sales":
                ly = (db.one(c, "SELECT ly_sales FROM fact_sales WHERE store_id=? AND week=? AND cat_id=?", (m["store_id"], wk, m["cat_id"])) or {}).get("ly_sales")
            out.append(dict(week=wk, actual=g["actual"], expected=g["expected"], gap=g["gap"], quart=g.get("quart"), ly=ly))
    return out

def heatmap(c, m, window=1):
    w = week(); weeks = list(range(max(1, w - 7), w + 1)); rows = []
    wds = {wk: E.WeekData(c, wk, window) for wk in weeks}
    wd = wds[w]
    def gp(wk, k, cat=None): return E.metric_gap(wds[wk], m["store_id"], k, cat) or {}
    if m["kpi"] == "sales" and m.get("cat_id"):
        p = wd.parent[m["cat_id"]]
        for cid in wd.children[p]:
            rows.append(dict(label=wd.cat[cid]["name"], cells=[round(gp(wk, "sales", cid).get("gap", 0)) for wk in weeks],
                             actual=[round(wds[wk].sales.get((m["store_id"], cid), 0)) for wk in weeks]))
    else:
        for k in E.STORE_KPIS:
            rows.append(dict(label=KPIS[k]["label"], cells=[round(gp(wk, k).get("gap", 0)) for wk in weeks],
                             actual=[round(gp(wk, k).get("actual", 0), 1) for wk in weeks]))
        for d in [x for x, p in wd.parent.items() if p is None]:
            rows.append(dict(label=f"{wd.cat[d]['name']} waste", cells=[round(gp(wk, "waste", d).get("gap", 0)) for wk in weeks],
                             actual=[round(gp(wk, "waste", d).get("actual", 0), 1) for wk in weeks]))
    return dict(weeks=weeks, rows=rows)

def get_m(u, mid):
    c = C(); m = db.one(c, "SELECT * FROM missions WHERE id=?", (mid,))
    if not m: raise HTTPException(404, "Mission not found")
    if m["store_id"] not in scope(u) and m["owner_id"] != u["id"]: raise HTTPException(403, "Outside your scope")
    return c, m

@app.get("/api/missions/{mid}")
def mission(req: Request, mid: int, window: int = 1):
    u = user_of(req); c, m = get_m(u, mid)
    m = enrich(c, m)
    wd = E.WeekData(c, week(), 1)
    g = E.metric_gap(wd, m["store_id"], m["kpi"], m["cat_id"]) if m["kpi"] in GAP_KPIS else None
    peers = []
    if g:
        st = {s["id"]: s for s in db.rows(c, "SELECT id, code, name FROM stores")}
        peers = [st[p] for p in g["peers"]]
    m.update(series=series(c, m), heatmap=heatmap(c, m, window), peers=peers, scaler=(g or {}).get("scaler"),
             current=dict(actual=g["actual"], expected=g["expected"], gap=g["gap"], z=g["z"]) if g else None,
             opp=db.one(c, "SELECT * FROM opportunities WHERE id=?", (m["opp_id"],)) if m["opp_id"] else None,
             tasks=db.rows(c, "SELECT mt.*, u.name assignee FROM mission_tasks mt LEFT JOIN users u ON u.id=mt.assignee_id WHERE mission_id=?", (mid,)),
             comments=db.rows(c, "SELECT cm.*, u.name author FROM comments cm LEFT JOIN users u ON u.id=cm.user_id WHERE entity='mission' AND entity_id=? ORDER BY id", (mid,)),
             activity=db.rows(c, "SELECT a.*, u.name who FROM activity a LEFT JOIN users u ON u.id=a.user_id WHERE entity='mission' AND entity_id=? ORDER BY id", (mid,)),
             impact_weeks=db.rows(c, "SELECT * FROM impact WHERE mission_id=? ORDER BY week", (mid,)),
             guidance=GUIDANCE.get(m["kpi"], ""), causes=ROOT_CAUSES.get(m["kpi"], ROOT_CAUSES["custom"]),
             store_users=db.rows(c, "SELECT id, name, role FROM users WHERE store_id=? AND active=1", (m["store_id"],)),
             can_approve="approve" in perms(u) and m["status"] == "proposed",
             best_practices=db.rows(c, "SELECT * FROM best_practices WHERE kpi=? ORDER BY impact_value DESC LIMIT 3", (m["kpi"],)))
    return m

def save_plan(c, mid, b):
    c.execute("UPDATE missions SET root_causes=?, action_type=?, action=?, target_weekly=?, duration=? WHERE id=?",
              (json.dumps(b.get("root_causes", [])), b.get("action_type"), b.get("action"), float(b.get("target_weekly") or 0),
               int(b.get("duration") or db.setting(c, "mission_duration", 4)), mid))
    for t in b.get("tasks", []):
        if t.get("title"):
            c.execute("INSERT INTO mission_tasks(mission_id,title,assignee_id,due) VALUES(?,?,?,?)", (mid, t["title"], t.get("assignee_id") or None, t.get("due")))
            if t.get("assignee_id"): E.notify(c, int(t["assignee_id"]), f"Action-plan task: {t['title']}", f"#/mission/{mid}")

@app.post("/api/missions/{mid}/draft")
async def draft(req: Request, mid: int):
    u = user_of(req); c, m = get_m(u, mid); b = await body(req)
    save_plan(c, mid, b); c.execute("UPDATE missions SET status='prelaunch' WHERE id=?", (mid,))
    E.log(c, "mission", mid, u["id"], "saved draft", b.get("action_type") or ""); c.commit(); return {"ok": True}

def launch(c, m, uid):
    """Launch = baseline at the current week; measurement starts with the next data week."""
    w = week(); dur = m.get("duration") or db.setting(c, "mission_duration", 4)
    g = E.metric_gap(E.WeekData(c, w, 1), m["store_id"], m["kpi"], m["cat_id"]) if m["kpi"] in GAP_KPIS else None
    controls = None
    if g:
        treated = {x["store_id"] for x in db.rows(c, "SELECT store_id FROM missions WHERE status IN ('live','prelaunch','proposed') AND kpi=? AND COALESCE(cat_id,0)=COALESCE(?,0) AND id!=?", (m["kpi"], m["cat_id"], m["id"]))}
        controls = json.dumps([s_ for s_ in g["peers"] if s_ not in treated][:12])
    c.execute("""UPDATE missions SET status='live', approval=CASE WHEN approval='pending' THEN 'approved' ELSE approval END,
                 start_week=?, end_week=?, baseline_gap=?, control_ids=?, accepted_at=? WHERE id=?""",
              (w + 1, w + dur, g["gap"] if g else m["baseline_gap"], controls, E.now_iso(), m["id"]))
    E.log(c, "mission", m["id"], uid, "launched", f"measuring weeks {w+1}-{w+dur}")

@app.post("/api/missions/{mid}/accept")
async def accept(req: Request, mid: int):
    u = user_of(req); c, m = get_m(u, mid); b = await body(req)
    if m["status"] not in ("incoming", "prelaunch", "rejected", "snoozed"): raise HTTPException(400, f"Mission is {UI_STATUS.get(m['status'], m['status'])}")
    if not (b.get("action") or "").strip(): raise HTTPException(400, "Describe the action you will take")
    save_plan(c, mid, b)
    m = db.one(c, "SELECT * FROM missions WHERE id=?", (mid,))
    if db.setting(c, "require_approval", False) and u["role"] in ("store_manager", "associate"):
        c.execute("UPDATE missions SET status='proposed', approval='pending' WHERE id=?", (mid,))
        s = db.one(c, "SELECT * FROM stores WHERE id=?", (m["store_id"],))
        dm = T.assignee_for(c, s, "district_manager")
        if dm: E.notify(c, dm, f"Plan to review: {m['title']} ({s['code']})", f"#/mission/{mid}")
        E.log(c, "mission", mid, u["id"], "submitted proposal", b.get("action_type") or "")
    else:
        launch(c, m, u["id"])
    c.commit(); return enrich(c, db.one(c, "SELECT * FROM missions WHERE id=?", (mid,)))

@app.get("/api/missions/{mid}/plan")
def plan_suggestion(req: Request, mid: int):
    u = user_of(req); c, m = get_m(u, mid); return suggest_plan(c, enrich(c, m))

@app.post("/api/missions/{mid}/quick")
async def quick(req: Request, mid: int):
    """One-tap actions from the card: accept (with the pre-filled plan), snooze 1 week, or 'not for my store'."""
    u = user_of(req); c, m = get_m(u, mid); b = await body(req); a = b.get("action")
    if m["status"] not in ("incoming", "snoozed"): raise HTTPException(400, f"Mission is already {UI_STATUS.get(m['status'], m['status'])}")
    if a == "accept":
        plan = suggest_plan(c, enrich(c, dict(m)))
        save_plan(c, mid, plan); E.log(c, "mission", mid, u["id"], "one-tap accept", plan["source"])
        m = db.one(c, "SELECT * FROM missions WHERE id=?", (mid,))
        if db.setting(c, "require_approval", False) and u["role"] in ("store_manager", "associate"):
            c.execute("UPDATE missions SET status='proposed', approval='pending' WHERE id=?", (mid,))
        else:
            launch(c, m, u["id"])
    elif a == "snooze":
        c.execute("UPDATE missions SET status='snoozed', snooze_until=? WHERE id=?", (week() + int(b.get("weeks", 1)), mid))
        E.log(c, "mission", mid, u["id"], "snoozed", f"{b.get('weeks', 1)} week(s)")
    elif a == "not_for_us":
        reason = (b.get("reason") or "Not relevant to my store").strip()
        c.execute("UPDATE missions SET status='rejected', reason=?, snooze_until=? WHERE id=?", (reason, week() + 8, mid))
        E.log(c, "mission", mid, u["id"], "not for us", reason)
    else:
        raise HTTPException(400, "action must be accept, snooze or not_for_us")
    c.commit(); return enrich(c, db.one(c, "SELECT * FROM missions WHERE id=?", (mid,)))

@app.get("/api/pushback")
def pushback(req: Request, weeks: int = 4):
    """HQ/field visibility into store pushback: why missions were turned down or snoozed."""
    u = user_of(req); c = C(); ids = scope(u); w0 = week() - weeks + 1
    rows = db.rows(c, f"""SELECT m.id, m.title, m.kpi, m.status, m.reason, m.created_week, m.campaign_id, s.code, s.name store_name, d.name district
        FROM missions m JOIN stores s ON s.id=m.store_id JOIN districts d ON d.id=s.district_id
        WHERE m.status IN ('rejected','snoozed') AND m.store_id IN ({ids_sql(ids)}) AND COALESCE(m.created_week,0)>=? ORDER BY m.id DESC""", (w0 - 4,))
    for r in rows: r["reason"] = r["reason"] or ("Snoozed" if r["status"] == "snoozed" else "No reason given")
    agg = lambda key: sorted(({"key": k, "n": n} for k, n in __import__("collections").Counter(r[key] for r in rows).items()), key=lambda x: -x["n"])
    tot = c.execute(f"SELECT COUNT(*) FROM missions WHERE store_id IN ({ids_sql(ids)}) AND COALESCE(created_week,0)>=? AND kind!='theme'", (w0 - 4,)).fetchone()[0]
    acc = c.execute(f"SELECT COUNT(*) FROM missions WHERE store_id IN ({ids_sql(ids)}) AND COALESCE(created_week,0)>=? AND status IN ('prelaunch','proposed','live','done') AND kind!='theme'", (w0 - 4,)).fetchone()[0]
    return dict(total=len(rows), by_reason=agg("reason"), by_kpi=[dict(x, key=KPIS.get(x["key"], {}).get("label", x["key"])) for x in agg("kpi")],
                by_district=agg("district"), recent=rows[:40], accept_rate=round(acc / tot * 100) if tot else 0)

@app.post("/api/missions/{mid}/approve")
async def approve(req: Request, mid: int):
    u = user_of(req); need(u, "approve"); c, m = get_m(u, mid); b = await body(req)
    if m["status"] != "proposed": raise HTTPException(400, "Nothing to approve")
    if b.get("comment"): c.execute("INSERT INTO comments(entity,entity_id,user_id,text,ts) VALUES('mission',?,?,?,?)", (mid, u["id"], b["comment"], E.now_iso()))
    if b.get("decision") == "changes":
        c.execute("UPDATE missions SET status='prelaunch', approval='changes' WHERE id=?", (mid,))
        E.log(c, "mission", mid, u["id"], "requested changes", b.get("comment", ""))
        if m["owner_id"]: E.notify(c, m["owner_id"], f"Changes requested on: {m['title']}", f"#/mission/{mid}")
    else:
        c.execute("UPDATE missions SET approver_id=? WHERE id=?", (u["id"], mid)); launch(c, m, u["id"])
        if m["owner_id"]: E.notify(c, m["owner_id"], f"Plan approved and live: {m['title']}", f"#/mission/{mid}")
    c.commit(); return {"ok": True}

@app.post("/api/missions/{mid}/reject")
async def reject(req: Request, mid: int):
    u = user_of(req); c, m = get_m(u, mid); b = await body(req)
    if not (b.get("reason") or "").strip(): raise HTTPException(400, "Give a reason")
    c.execute("UPDATE missions SET status='rejected', reason=?, snooze_until=? WHERE id=?", (b["reason"], week() + int(b.get("snooze_weeks", 4)), mid))
    E.log(c, "mission", mid, u["id"], "rejected", b["reason"]); c.commit(); return {"ok": True}

@app.post("/api/missions/{mid}/comment")
async def comment(req: Request, mid: int):
    u = user_of(req); c, m = get_m(u, mid); b = await body(req)
    if not (b.get("text") or "").strip(): raise HTTPException(400, "Empty comment")
    c.execute("INSERT INTO comments(entity,entity_id,user_id,text,ts) VALUES('mission',?,?,?,?)", (mid, u["id"], b["text"], E.now_iso()))
    for uid in {m["owner_id"], m["approver_id"]} - {None, u["id"]}: E.notify(c, uid, f"{u['name']} commented on {m['title']}", f"#/mission/{mid}")
    c.commit(); return {"ok": True}

@app.post("/api/missions/{mid}/kudos")
def kudos(req: Request, mid: int):
    u = user_of(req); c, m = get_m(u, mid)
    c.execute("UPDATE missions SET kudos=kudos+1 WHERE id=?", (mid,))
    if m["owner_id"]: E.notify(c, m["owner_id"], f"{u['name']} recognised your mission: {m['title']}", f"#/mission/{mid}")
    c.commit(); return {"ok": True}

@app.post("/api/missions/{mid}/followup")
def followup(req: Request, mid: int):
    u = user_of(req); c, m = get_m(u, mid)
    nid = E.create_mission(c, dict(store_id=m["store_id"], owner_id=m["owner_id"], kind=m["kind"], kpi=m["kpi"], cat_id=m["cat_id"],
        title=f"Follow-up: {m['title']}", status="incoming", source="followup", created_by=u["id"], created_week=week(),
        baseline_gap=m["baseline_gap"], target_weekly=m["target_weekly"], priority="Should", comment=f"Follow-up to mission #{mid}"))
    c.commit(); return {"id": nid}

@app.post("/api/missions/{mid}/share")
async def share(req: Request, mid: int):
    u = user_of(req); c, m = get_m(u, mid); b = await body(req)
    imp = E.mission_impact_summary(c, mid)
    bid = c.execute("""INSERT INTO best_practices(mission_id,user_id,store_id,title,body,kpi,cat_id,action_type,impact_value,ts)
        VALUES(?,?,?,?,?,?,?,?,?,?)""", (mid, u["id"], m["store_id"], b.get("title") or f"{m['action_type']}: {m['title']}",
        b.get("body") or m["action"], m["kpi"], m["cat_id"], m["action_type"], imp["cumulative"], E.now_iso())).lastrowid
    E.log(c, "mission", mid, u["id"], "shared best practice", ""); c.commit(); return {"id": bid}

@app.post("/api/missions/{mid}/tasks")
async def add_mtask(req: Request, mid: int):
    u = user_of(req); c, m = get_m(u, mid); b = await body(req)
    if not b.get("title"): raise HTTPException(400, "Task needs a title")
    c.execute("INSERT INTO mission_tasks(mission_id,title,assignee_id,due) VALUES(?,?,?,?)", (mid, b["title"], b.get("assignee_id") or None, b.get("due")))
    if b.get("assignee_id"): E.notify(c, int(b["assignee_id"]), f"Action-plan task: {b['title']}", f"#/mission/{mid}")
    E.log(c, "mission", mid, u["id"], "task added", b["title"]); c.commit(); return {"ok": True}

@app.post("/api/mission_tasks/{tid}/toggle")
def toggle_mtask(req: Request, tid: int):
    u = user_of(req); c = C(); t = db.one(c, "SELECT * FROM mission_tasks WHERE id=?", (tid,))
    if not t: raise HTTPException(404, "No task")
    get_m(u, t["mission_id"])
    c.execute("UPDATE mission_tasks SET done=1-done WHERE id=?", (tid,)); E.log(c, "mission", t["mission_id"], u["id"], "task toggled", t["title"]); c.commit()
    return {"ok": True}

@app.post("/api/missions/send")
async def send_mission(req: Request):
    """Push an opportunity (or a hand-written mission) to the responsible manager, with a comment. Store managers write their own."""
    u = user_of(req); b = await body(req); c = C()
    sid = int(b["store_id"]); check_store(u, sid)
    if u["role"] != "store_manager": need(u, "send_mission")
    s = db.one(c, "SELECT * FROM stores WHERE id=?", (sid,))
    owner = T.assignee_for(c, s, b.get("owner_role", "store_manager"))
    kpi = b.get("kpi") or "custom"; cat = int(b["cat_id"]) if b.get("cat_id") else None
    g = E.metric_gap(E.WeekData(c, week(), 1), sid, kpi, cat) if kpi in GAP_KPIS else None
    mid = E.create_mission(c, dict(store_id=sid, owner_id=owner, kind="opportunity", kpi=kpi, cat_id=cat,
        title=b.get("title") or "Mission from your manager", status="incoming" if u["role"] != "store_manager" else "prelaunch",
        source="manual", created_by=u["id"], created_week=week(), comment=b.get("comment"), priority=b.get("priority", "Should"),
        baseline_gap=g["gap"] if g else 0, target_weekly=max(g["gap"], 0) if g else 0))
    if b.get("comment"): c.execute("INSERT INTO comments(entity,entity_id,user_id,text,ts) VALUES('mission',?,?,?,?)", (mid, u["id"], b["comment"], E.now_iso()))
    c.commit(); return {"id": mid}

# ---------------- business / KPI / P&L / team ----------------
def kpi_value(wd, sid, k):
    if k == "total_sales": return wd.total.get(sid, 0) if sid in wd.m else None
    if k == "sales_vs_budget": return E.store_metric(wd, sid, "sales_vs_budget_pct")
    g = E.metric_gap(wd, sid, k, fresh_id(C()) if k == "waste" else None)
    return g["actual"] if g else None

_FRESH = {}
def fresh_id(c):
    if db.GEN[0] not in _FRESH:
        r = db.one(c, "SELECT id FROM categories WHERE name='Fresh' AND parent_id IS NULL") or db.one(c, "SELECT id FROM categories WHERE parent_id IS NULL")
        _FRESH[db.GEN[0]] = r["id"]
    return _FRESH[db.GEN[0]]

TILE_KPIS = ["total_sales", "sales_vs_budget", "waste", "labor", "overtime", "conversion", "csat", "attach", "invacc", "gapscan"]
TILE_META = {"total_sales": ("Total sales", "$", "higher", "Sales"), "sales_vs_budget": ("Sales vs budget", "%", "higher", "Sales"),
             "waste": ("Fresh waste %", "%", "lower", "Loss")}

def tmeta(k): return TILE_META.get(k) or (KPIS[k]["label"], KPIS[k]["unit"], KPIS[k]["better"], KPIS[k]["group"])

@app.get("/api/business")
def business(req: Request, store: int = None):
    u = user_of(req); c = C(); ids = scope(u)
    if store: check_store(u, store); ids = [store]
    w = week(); wds = {wk: E.WeekData(c, wk, 1) for wk in range(max(1, w - 11), w + 1)}
    allst = wds[w].active(); tiles = []
    for k in TILE_KPIS:
        mt = tmeta(k); hib = mt[2] != "lower"
        trend = []
        for wk, wd in wds.items():
            vals = [v for v in (kpi_value(wd, s, k) for s in ids) if v is not None]
            trend.append(dict(week=wk, value=(sum(vals) if k == "total_sales" else (stats.mean(vals) if vals else None))))
        allv = {s: v for s, v in ((s, kpi_value(wds[w], s, k)) for s in allst) if v is not None}
        order = sorted(allv, key=lambda s: -allv[s] if hib else allv[s])
        prev = {s: v for s, v in ((s, kpi_value(wds[w - 1], s, k)) for s in allst) if v is not None} if (w - 1) in wds else {}
        porder = sorted(prev, key=lambda s: -prev[s] if hib else prev[s])
        avg = stats.mean(allv.values()) if allv else 0
        below = sum(1 for s in ids if s in allv and ((allv[s] < avg) if hib else (allv[s] > avg)))
        kp = "waste" if k == "waste" else ("sales" if k in ("total_sales", "sales_vs_budget") else k)
        lm = db.rows(c, f"SELECT id FROM missions WHERE status='live' AND kpi=? AND store_id IN ({ids_sql(ids)})", (kp,))
        st = [E.mission_impact_summary(c, x["id"])["status"] for x in lm]
        t = dict(kpi=k, label=mt[0], unit=mt[1], better=mt[2], group=mt[3], trend=trend, company_avg=avg, live=len(lm),
                 improving=st.count("green"), declining=st.count("red"), below_avg=below, stores=len(ids))
        if len(ids) == 1 and ids[0] in allv:
            t["rank"] = order.index(ids[0]) + 1; t["of"] = len(order)
            t["rank_change"] = (porder.index(ids[0]) - order.index(ids[0])) if ids[0] in porder else 0
            if k == "total_sales":
                t["budget"] = wds[w].m[ids[0]]["bsales"]
                t["ly"] = c.execute("SELECT SUM(ly_sales) FROM fact_sales WHERE store_id=? AND week=?", (ids[0], w)).fetchone()[0]
        tiles.append(t)
    return dict(tiles=tiles, week=w)

@app.get("/api/kpi/{k}")
def kpi_drill(req: Request, k: str, store: int = None):
    u = user_of(req); c = C(); ids = scope(u)
    if k not in TILE_KPIS: raise HTTPException(404, "Unknown KPI")
    if store: check_store(u, store); ids = [store]
    w = week(); wd = E.WeekData(c, w, 1)
    kp = "sales" if k in ("total_sales", "sales_vs_budget") else k
    vals = {s: v for s, v in ((s, kpi_value(wd, s, k)) for s in wd.active()) if v is not None}
    hib = tmeta(k)[2] != "lower"
    order = sorted(vals, key=lambda s: -vals[s] if hib else vals[s])
    st = {s["id"]: s for s in db.rows(c, "SELECT id, code, name, format FROM stores")}
    graph = []
    for wk in range(max(1, w - 11), w + 1):
        wdk = E.WeekData(c, wk, 1)
        v = sorted(x for x in (kpi_value(wdk, s, k) for s in wdk.active()) if x is not None)
        mine = [x for x in (kpi_value(wdk, s, k) for s in ids) if x is not None]
        q = stats.quantiles(v, n=4) if len(v) >= 4 else [0, 0, 0]
        graph.append(dict(week=wk, mine=(sum(mine) / len(mine)) if mine else None, quart=[v[0], *q, v[-1]] if v else None))
    rank = [dict(rank=i + 1, store_id=s, code=st[s]["code"], name=st[s]["name"], value=vals[s], mine=s in ids) for i, s in enumerate(order)]
    if u["role"] in ("store_manager", "associate"): rank = [r for r in rank if r["mine"]]
    opps = db.rows(c, f"SELECT o.*, s.code FROM opportunities o JOIN stores s ON s.id=o.store_id WHERE week=? AND kpi=? AND store_id IN ({ids_sql(ids)}) ORDER BY score DESC LIMIT 60", (w, kp))
    for o in opps:
        m = db.one(c, "SELECT id,status FROM missions WHERE store_id=? AND kpi=? AND COALESCE(cat_id,0)=COALESCE(?,0) ORDER BY id DESC", (o["store_id"], o["kpi"], o["cat_id"]))
        o["label"] = {"live": "Live Mission", "incoming": "Incoming Mission", "rejected": "Rejected Mission", "proposed": "Awaiting approval", "prelaunch": "Draft"}.get(m["status"]) if m else None
        o["mission_id"] = m["id"] if m else None
    act = [enrich(c, m) for m in db.rows(c, f"SELECT * FROM missions WHERE kpi=? AND store_id IN ({ids_sql(ids)}) AND status IN ('live','done','proposed') ORDER BY id DESC LIMIT 40", (kp,))]
    return dict(kpi=k, label=tmeta(k)[0], unit=tmeta(k)[1], graph=graph, rankings=rank, opportunities=opps, activity=act)

@app.get("/api/pnl")
def pnl(req: Request, store: int = None, mode: str = "tree"):
    u = user_of(req); c = C(); ids = scope(u)
    if store: check_store(u, store); ids = [store]
    w = week(); wd = E.WeekData(c, w, 1)
    if mode == "biggest":
        return db.rows(c, f"SELECT o.*, s.code, s.name store_name FROM opportunities o JOIN stores s ON s.id=o.store_id WHERE week=? AND store_id IN ({ids_sql(ids)}) ORDER BY gap_value DESC LIMIT 200", (w,))
    ly = defaultdict(float)
    for r in c.execute(f"SELECT cat_id, SUM(ly_sales) FROM fact_sales WHERE week=? AND store_id IN ({ids_sql(ids)}) GROUP BY cat_id", (w,)): ly[r[0]] = r[1] or 0
    out = []
    for d in [x for x, p in wd.parent.items() if p is None]:
        kids = []
        for cid in wd.children[d]:
            act = sum(wd.sales.get((s, cid), 0) for s in ids)
            gap = sum(max(0, (E.metric_gap(wd, s, "sales", cid) or {}).get("gap", 0)) for s in ids)
            kids.append(dict(id=cid, name=wd.cat[cid]["name"], actual=act, ly=ly[cid], opportunity=gap))
        out.append(dict(id=d, name=wd.cat[d]["name"], actual=sum(k["actual"] for k in kids), ly=sum(k["ly"] for k in kids),
                        opportunity=sum(k["opportunity"] for k in kids), waste=sum(wd.dept_waste.get((s, d), 0) for s in ids), children=kids))
    return dict(week=w, departments=out, single=ids[0] if len(ids) == 1 else None)

@app.get("/api/countlist")
def countlist(req: Request, store: int):
    """Daily count list: categories where booked vs actual stock is most likely to have drifted."""
    u = user_of(req); check_store(u, store); c = C(); w = week()
    wd = E.WeekData(c, w, 1); acc = wd.m.get(store, {}).get("invacc", .97)
    rows = []
    for cid, p in wd.parent.items():
        if not p: continue
        hist = [r["sales"] for r in db.rows(c, "SELECT sales FROM fact_sales WHERE store_id=? AND cat_id=? AND week BETWEEN ? AND ?", (store, cid, w - 7, w))]
        vol = (stats.pstdev(hist) / stats.mean(hist)) if len(hist) > 2 and stats.mean(hist) else 0
        s_ = wd.sales.get((store, cid), 0); wr = wd.waste.get((store, cid), 0) / s_ if s_ else 0
        rows.append(dict(cat_id=cid, name=wd.cat[cid]["name"], dept=wd.cat[p]["name"], risk=round((1 - acc) * 10 + vol * 3 + wr * 5, 3),
                         volatility=round(vol, 3), waste_ratio=round(wr, 4)))
    return sorted(rows, key=lambda r: -r["risk"])[:10]

@app.get("/api/team")
def team(req: Request):
    u = user_of(req); need(u, "team"); c = C(); ids = scope(u)
    if u["role"] == "store_manager":
        ppl = db.rows(c, "SELECT * FROM users WHERE store_id=? AND role='associate' AND active=1", (u["store_id"],))
    else:
        ppl = db.rows(c, f"""SELECT * FROM users WHERE active=1 AND ((role='store_manager' AND store_id IN ({ids_sql(ids)})) OR
              (role='district_manager' AND district_id IN (SELECT district_id FROM stores WHERE id IN ({ids_sql(ids)}))))""")
        ppl = [p for p in ppl if p["id"] != u["id"]]
    today = dt.date.fromisoformat(T.today(c)); wd = E.WeekData(c, week(), 1); out = []
    for p in ppl:
        sids = [p["store_id"]] if p["store_id"] else [x["id"] for x in db.rows(c, "SELECT id FROM stores WHERE district_id=?", (p["district_id"],))]
        f = f"store_id IN ({ids_sql(sids)})"
        if p["role"] == "associate": f += f" AND assignee_id={p['id']}"
        live = db.rows(c, f"SELECT id FROM missions WHERE status='live' AND store_id IN ({ids_sql(sids)})")
        st = [E.mission_impact_summary(c, x["id"])["status"] for x in live]
        tot = below = 0
        for s in sids:
            for k in E.STORE_KPIS:
                g = E.metric_gap(wd, s, k)
                if g: tot += 1; below += 1 if g["gap"] > 0 else 0
        out.append(dict(id=p["id"], name=p["name"], role=p["role"], store_id=p["store_id"], district_id=p["district_id"],
            store=db.one(c, "SELECT code,name FROM stores WHERE id=?", (p["store_id"],)) if p["store_id"] else None,
            incoming=c.execute(f"SELECT COUNT(*) FROM missions WHERE status='incoming' AND store_id IN ({ids_sql(sids)})").fetchone()[0],
            days_since_login=(today - dt.date.fromisoformat(p["last_login"][:10])).days if p["last_login"] else None,
            live=len(live), green=st.count("green"), red=st.count("red"), grey=st.count("grey"), kpis=tot, kpis_below=below,
            open_tasks=c.execute(f"SELECT COUNT(*) FROM tasks WHERE status='open' AND {f}").fetchone()[0],
            overdue=c.execute(f"SELECT COUNT(*) FROM tasks WHERE status='open' AND due<? AND {f}", (T.today(c),)).fetchone()[0]))
    return out

@app.post("/api/coach")
async def coach(req: Request):
    u = user_of(req); need(u, "team"); b = await body(req); c = C()
    if not (b.get("text") or "").strip(): raise HTTPException(400, "Empty note")
    tgt = int(b["user_id"])
    c.execute("INSERT INTO comments(entity,entity_id,user_id,text,ts) VALUES('coaching',?,?,?,?)", (tgt, u["id"], b["text"], E.now_iso()))
    E.notify(c, tgt, f"Coaching note from {u['name']}: {b['text'][:60]}", "#/coaching"); c.commit(); return {"ok": True}

@app.get("/api/coach/{uid}")
def coach_notes(req: Request, uid: int):
    u = user_of(req); c = C()
    if u["id"] != uid: need(u, "team")
    return db.rows(c, "SELECT cm.*, u.name author FROM comments cm JOIN users u ON u.id=cm.user_id WHERE entity='coaching' AND entity_id=? ORDER BY id DESC", (uid,))

# ---------------- intelligent tasks ----------------
@app.get("/api/tasks")
def task_list(req: Request, status: str = "open", store: int = None, mine: int = 0):
    u = user_of(req); c = C(); ids = scope(u)
    if store: check_store(u, store); ids = [store]
    q = f"""SELECT t.*, s.code store_code, s.name store_name, us.name assignee FROM tasks t JOIN stores s ON s.id=t.store_id
            LEFT JOIN users us ON us.id=t.assignee_id WHERE t.store_id IN ({ids_sql(ids)})"""
    a = []
    if status != "all": q += " AND t.status=?"; a.append(status)
    if mine or u["role"] == "associate": q += " AND t.assignee_id=?"; a.append(u["id"])
    rows = db.rows(c, q + " ORDER BY t.due, t.id LIMIT 500", a)
    for t in rows: t["bucket"] = T.priority_bucket(c, t)
    return rows

@app.get("/api/tasks/analytics")
def task_analytics(req: Request):
    u = user_of(req); c = C(); ids = scope(u); td = T.today(c)
    rows = db.rows(c, f"""SELECT COALESCE(r.name, t.source) rule, COUNT(*) n, SUM(t.status='done') done, SUM(t.escalated) escalated,
        SUM(t.status='open' AND t.due<?) overdue FROM tasks t LEFT JOIN task_rules r ON r.id=t.rule_id WHERE t.store_id IN ({ids_sql(ids)})
        GROUP BY 1 ORDER BY n DESC""", (td,))
    bystore = db.rows(c, f"""SELECT s.code, COUNT(*) n, SUM(t.status='done') done, SUM(t.status='open' AND t.due<?) overdue FROM tasks t
        JOIN stores s ON s.id=t.store_id WHERE t.store_id IN ({ids_sql(ids)}) GROUP BY s.code ORDER BY overdue DESC, n DESC LIMIT 15""", (td,))
    return dict(by_rule=rows, bottlenecks=bystore, capacity=[x for x in E.capacity_status(c) if x["store_id"] in ids])

@app.get("/api/tasks/{tid}")
def task_get(req: Request, tid: int):
    u = user_of(req); c = C(); t = db.one(c, "SELECT * FROM tasks WHERE id=?", (tid,))
    if not t: raise HTTPException(404, "No task")
    check_store(u, t["store_id"])
    t.update(store=db.one(c, "SELECT * FROM stores WHERE id=?", (t["store_id"],)), questions=db.J(t["questions"], []), answers=db.J(t["answers"], {}),
             context=db.J(t["context"], {}), attachments=db.J(t["attachments"], []), bucket=T.priority_bucket(c, t),
             assignee=(db.one(c, "SELECT name FROM users WHERE id=?", (t["assignee_id"],)) or {}).get("name") if t["assignee_id"] else None,
             comments=db.rows(c, "SELECT cm.*, u.name author FROM comments cm LEFT JOIN users u ON u.id=cm.user_id WHERE entity='task' AND entity_id=? ORDER BY id", (tid,)),
             activity=db.rows(c, "SELECT a.*, u.name who FROM activity a LEFT JOIN users u ON u.id=a.user_id WHERE entity='task' AND entity_id=? ORDER BY id", (tid,)))
    return t

def get_t(u, tid):
    c = C(); t = db.one(c, "SELECT * FROM tasks WHERE id=?", (tid,))
    if not t: raise HTTPException(404, "No task")
    check_store(u, t["store_id"]); return c, t

@app.post("/api/tasks/{tid}/complete")
async def task_complete(req: Request, tid: int):
    u = user_of(req); c, t = get_t(u, tid); b = await body(req)
    if t["status"] == "done": raise HTTPException(400, "Already done")
    r = T.complete_task(c, tid, u["id"], b.get("answers", {}))
    if not r["ok"]: raise HTTPException(400, "Required: " + "; ".join(r["missing"]))
    return r

@app.post("/api/tasks/{tid}/comment")
async def task_comment(req: Request, tid: int):
    u = user_of(req); c, t = get_t(u, tid); b = await body(req)
    if not (b.get("text") or b.get("image")): raise HTTPException(400, "Empty comment")
    txt = (b.get("text") or "") + (f"\n![photo]({b['image']})" if b.get("image") else "")
    c.execute("INSERT INTO comments(entity,entity_id,user_id,text,ts) VALUES('task',?,?,?,?)", (tid, u["id"], txt, E.now_iso()))
    E.log(c, "task", tid, u["id"], "commented", txt[:60]); c.commit(); return {"ok": True}

@app.post("/api/tasks/{tid}/reopen")
def task_reopen(req: Request, tid: int):
    u = user_of(req); c, t = get_t(u, tid)
    c.execute("UPDATE tasks SET status='open', completed=NULL WHERE id=?", (tid,)); E.log(c, "task", tid, u["id"], "reopened"); c.commit(); return {"ok": True}

@app.post("/api/tasks")
async def task_create(req: Request):
    """Create a task from a template or ad hoc, targeted at stores by tag/format/district/store; protected stores are skipped."""
    u = user_of(req); b = await body(req); c = C()
    if u["role"] not in ("store_manager", "district_manager", "regional_manager"): need(u, "tasks_admin")
    if b.get("template_id"):
        tpl = db.one(c, "SELECT * FROM task_templates WHERE id=?", (int(b["template_id"]),))
    else:
        if not b.get("title"): raise HTTPException(400, "Title or template required")
        tpl = dict(id=0, title=b["title"], body_md=b.get("body_md", ""), questions=json.dumps(b.get("questions", [])),
                   est_minutes=int(b.get("est_minutes", 15)), assignee_role=b.get("assignee_role", "store_manager"), attachments=json.dumps(b.get("attachments", [])))
    tgt = dict(b.get("target") or {}); my = scope(u)
    tgt["stores"] = [s for s in (tgt.get("stores") or my) if s in my]
    stores, skipped = T.target_stores(c, tgt, throttle=not b.get("ignore_capacity"))
    made = [T.create_task(c, s, tpl, title=b.get("title") or tpl["title"], source="manual", due_days=int(b.get("due_days", 3))) for s in stores]
    c.commit(); return dict(created=len(made), skipped_at_capacity=skipped)

@app.get("/api/task_templates")
def tpl_list(req: Request):
    user_of(req); return [dict(t, questions=db.J(t["questions"], []), attachments=db.J(t["attachments"], [])) for t in db.rows(C(), "SELECT * FROM task_templates")]

@app.post("/api/task_templates")
async def tpl_save(req: Request):
    u = user_of(req); need(u, "tasks_admin"); b = await body(req); c = C()
    vals = (b["name"], b.get("title") or b["name"], b.get("body_md", ""), json.dumps(b.get("questions", [])), int(b.get("est_minutes", 15)),
            b.get("assignee_role", "store_manager"), json.dumps(b.get("attachments", [])))
    if b.get("id"):
        c.execute("UPDATE task_templates SET name=?,title=?,body_md=?,questions=?,est_minutes=?,assignee_role=?,attachments=? WHERE id=?", (*vals, b["id"])); tid = b["id"]
    else:
        tid = c.execute("INSERT INTO task_templates(name,title,body_md,questions,est_minutes,assignee_role,attachments) VALUES(?,?,?,?,?,?,?)", vals).lastrowid
    c.commit(); return {"id": tid}

@app.get("/api/task_rules")
def rules_list(req: Request):
    user_of(req); return [dict(r, config=db.J(r["config"], {}), target=db.J(r["target"], {})) for r in db.rows(C(), "SELECT * FROM task_rules")]

@app.post("/api/task_rules")
async def rule_save(req: Request):
    u = user_of(req); need(u, "tasks_admin"); b = await body(req); c = C()
    vals = (b["name"], b["trigger_type"], json.dumps(b.get("config", {})), int(b["template_id"]), json.dumps(b.get("target", {})),
            int(b.get("due_days", 3)), int(b.get("escalate_after_days", 2)), int(b.get("active", 1)))
    if b.get("id"):
        c.execute("UPDATE task_rules SET name=?,trigger_type=?,config=?,template_id=?,target=?,due_days=?,escalate_after_days=?,active=? WHERE id=?", (*vals, b["id"])); rid = b["id"]
    else:
        rid = c.execute("INSERT INTO task_rules(name,trigger_type,config,template_id,target,due_days,escalate_after_days,active) VALUES(?,?,?,?,?,?,?,?)", vals).lastrowid
    c.commit(); return {"id": rid}

@app.post("/api/task_rules/{rid}/run")
def rule_run(req: Request, rid: int):
    u = user_of(req); need(u, "tasks_admin"); c = C(); r = db.one(c, "SELECT * FROM task_rules WHERE id=?", (rid,))
    if not r: raise HTTPException(404, "No rule")
    n0 = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    if r["trigger_type"] == "condition":
        wd = E.WeekData(c, week(), 1); cfg = db.J(r["config"], {})
        stores, _ = T.target_stores(c, db.J(r["target"], {}))
        for s in stores:
            v = E.store_metric(wd, s["id"], cfg.get("metric", ""))
            if v is not None and E.cmp(v, cfg.get("op", ">"), float(cfg.get("threshold", 0))):
                T.create_task(c, s, r["template_id"], r, context={"metric": cfg["metric"], "value": round(v, 2)}, source="condition")
        c.commit(); return {"created": c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] - n0}
    if r["trigger_type"] == "schedule":
        stores, skipped = T.target_stores(c, db.J(r["target"], {}))
        for s in stores: T.create_task(c, s, r["template_id"], r, source="schedule")
        c.commit(); return {"created": c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] - n0, "skipped_at_capacity": skipped}
    return T.fire_event(c, db.J(r["config"], {}).get("event"), {"message": "Fired manually from the builder"})

@app.post("/api/tasks/csv")
async def tasks_csv(req: Request, file: UploadFile = File(...), template_id: int = Form(...)):
    u = user_of(req); need(u, "tasks_admin"); txt = (await file.read()).decode("utf-8-sig")
    return T.csv_schedule(C(), txt, template_id)

@app.post("/api/agent/run")
def agent_run(req: Request): user_of(req); return {"completed": ai.run_agent(C())}

# ---------------- surveys / store walks / audits / checklists ----------------
@app.get("/api/surveys")
def surveys(req: Request):
    user_of(req)
    return [dict(s, questions=db.J(s["questions"], []), trigger=db.J(s["trigger"], {}), target=db.J(s["target"], {}),
                 responses=C().execute("SELECT COUNT(*) FROM survey_responses WHERE survey_id=?", (s["id"],)).fetchone()[0])
            for s in db.rows(C(), "SELECT * FROM surveys")]

@app.post("/api/surveys")
async def survey_save(req: Request):
    u = user_of(req); need(u, "surveys_admin"); b = await body(req); c = C()
    vals = (b["name"], b.get("kind", "storewalk"), json.dumps(b.get("questions", [])), json.dumps(b.get("trigger", {})), json.dumps(b.get("target", {})), int(b.get("active", 1)))
    if b.get("id"): c.execute("UPDATE surveys SET name=?,kind=?,questions=?,trigger=?,target=?,active=? WHERE id=?", (*vals, b["id"])); sid = b["id"]
    else: sid = c.execute("INSERT INTO surveys(name,kind,questions,trigger,target,active) VALUES(?,?,?,?,?,?)", vals).lastrowid
    c.commit(); return {"id": sid}

@app.post("/api/surveys/{sid}/form")
async def survey_form(req: Request, sid: int, store: int):
    """Questions visible for this store given current answers (conditional, store-attribute and live-performance logic)."""
    u = user_of(req); check_store(u, store); c = C(); b = await body(req)
    sv = db.one(c, "SELECT * FROM surveys WHERE id=?", (sid,))
    if not sv: raise HTTPException(404, "No survey")
    s = db.one(c, "SELECT * FROM stores WHERE id=?", (store,))
    qs = T.visible_questions(db.J(sv["questions"], []), b.get("answers", {}), s, T.survey_perf(c, store, week()))
    prev = db.one(c, "SELECT r.*, u.name who FROM survey_responses r LEFT JOIN users u ON u.id=r.user_id WHERE survey_id=? AND store_id=? ORDER BY id DESC", (sid, store))
    if prev: prev["answers"] = db.J(prev["answers"], {})
    return dict(survey=dict(id=sv["id"], name=sv["name"], kind=sv["kind"]), questions=qs, previous=prev, hidden=len(db.J(sv["questions"], [])) - len(qs))

@app.post("/api/surveys/{sid}/submit")
async def survey_submit(req: Request, sid: int):
    u = user_of(req); b = await body(req); check_store(u, int(b["store_id"])); c = C()
    sv = db.one(c, "SELECT * FROM surveys WHERE id=?", (sid,)); s = db.one(c, "SELECT * FROM stores WHERE id=?", (int(b["store_id"]),))
    vis = T.visible_questions(db.J(sv["questions"], []), b.get("answers", {}), s, T.survey_perf(c, s["id"], week()))
    miss = [q["text"] for q in vis if q.get("required") and b.get("answers", {}).get(q["id"]) in (None, "", [])]
    if miss: raise HTTPException(400, "Required: " + "; ".join(miss))
    r = T.submit_survey(c, sid, int(b["store_id"]), u["id"], b.get("answers", {}), b.get("visit_id"))
    r["themes_missions"] = ai.extract_themes(c, week()); return r

@app.get("/api/surveys/{sid}/responses")
def survey_responses(req: Request, sid: int):
    u = user_of(req); c = C(); ids = scope(u)
    rows = db.rows(c, f"""SELECT r.*, s.code, u.name who FROM survey_responses r JOIN stores s ON s.id=r.store_id LEFT JOIN users u ON u.id=r.user_id
                         WHERE survey_id=? AND store_id IN ({ids_sql(ids)}) ORDER BY r.id DESC LIMIT 200""", (sid,))
    for r in rows: r["answers"] = db.J(r["answers"], {})
    return rows

# ---------------- store visits & coaching ----------------
@app.get("/api/visits")
def visits(req: Request):
    u = user_of(req); c = C()
    return db.rows(c, f"""SELECT v.*, s.code, s.name store_name, u.name dm FROM visits v JOIN stores s ON s.id=v.store_id
                         LEFT JOIN users u ON u.id=v.dm_id WHERE v.store_id IN ({ids_sql(scope(u))}) ORDER BY date DESC""")

@app.get("/api/visits/suggest")
def visit_suggest(req: Request):
    """Where am I needed most: Must tasks, incoming opportunity value, days since last visit."""
    u = user_of(req); need(u, "visits"); c = C(); out = []; td = dt.date.fromisoformat(T.today(c))
    for s in db.rows(c, f"SELECT * FROM stores WHERE id IN ({ids_sql(scope(u))})"):
        must = [t for t in db.rows(c, "SELECT * FROM tasks WHERE store_id=? AND status='open'", (s["id"],)) if T.priority_bucket(c, t) == "Must"]
        val = c.execute("SELECT COALESCE(SUM(baseline_gap),0) FROM missions WHERE store_id=? AND status='incoming'", (s["id"],)).fetchone()[0]
        last = db.one(c, "SELECT MAX(date) d FROM visits WHERE store_id=? AND status='done'", (s["id"],))["d"]
        days = (td - dt.date.fromisoformat(last)).days if last else 99
        planned = db.one(c, "SELECT date FROM visits WHERE store_id=? AND status='planned' ORDER BY date", (s["id"],))
        out.append(dict(store_id=s["id"], code=s["code"], name=s["name"], must=len(must), opp_value=round(val), days_since_visit=days,
                        planned=planned["date"] if planned else None, score=round(len(must) * 400 + val + days * 30)))
    return sorted(out, key=lambda x: -x["score"])

@app.post("/api/visits")
async def visit_create(req: Request):
    u = user_of(req); need(u, "visits"); b = await body(req); check_store(u, int(b["store_id"])); c = C()
    if not b.get("date"): raise HTTPException(400, "Pick a date")
    vid = c.execute("INSERT INTO visits(dm_id,store_id,date,status) VALUES(?,?,?,?)", (u["id"], int(b["store_id"]), b["date"], "planned")).lastrowid
    sm = T.assignee_for(c, db.one(c, "SELECT * FROM stores WHERE id=?", (int(b["store_id"]),)), "store_manager")
    if sm: E.notify(c, sm, f"{u['name']} is visiting on {b['date']}", f"#/visit/{vid}")
    c.commit(); return {"id": vid}

@app.get("/api/visits/{vid}")
def visit_get(req: Request, vid: int):
    u = user_of(req); c = C(); v = db.one(c, "SELECT * FROM visits WHERE id=?", (vid,))
    if not v: raise HTTPException(404, "No visit")
    check_store(u, v["store_id"]); sid = v["store_id"]
    lw = db.one(c, "SELECT r.*, sv.name survey, sv.questions qs FROM survey_responses r JOIN surveys sv ON sv.id=r.survey_id WHERE store_id=? ORDER BY r.id DESC", (sid,))
    if lw:
        qs = {q["id"]: q["text"] for q in db.J(lw.pop("qs"), [])}
        lw["answers"] = {qs.get(k, k): v_ for k, v_ in db.J(lw["answers"], {}).items()}
    v.update(store=db.one(c, "SELECT * FROM stores WHERE id=?", (sid,)), coaching=db.J(v["coaching"], []), agreed_actions=db.J(v["agreed_actions"], []),
        missions=[enrich(c, m) for m in db.rows(c, "SELECT * FROM missions WHERE store_id=? AND status IN ('incoming','proposed','live','prelaunch') ORDER BY status", (sid,))],
        tasks=db.rows(c, "SELECT * FROM tasks WHERE store_id=? AND status='open' ORDER BY due", (sid,)), last_walk=lw,
        last_visit=db.one(c, "SELECT * FROM visits WHERE store_id=? AND status='done' AND id!=? ORDER BY date DESC", (sid, vid)),
        dm=(db.one(c, "SELECT name FROM users WHERE id=?", (v["dm_id"],)) or {}).get("name"))
    if v["last_visit"]: v["last_visit"]["agreed_actions"] = db.J(v["last_visit"]["agreed_actions"], [])
    return v

@app.post("/api/visits/{vid}/complete")
async def visit_complete(req: Request, vid: int):
    u = user_of(req); need(u, "visits"); b = await body(req); c = C()
    v = db.one(c, "SELECT * FROM visits WHERE id=?", (vid,))
    if not v: raise HTTPException(404, "No visit")
    check_store(u, v["store_id"])
    acts = [a for a in b.get("agreed_actions", []) if a.strip()]
    c.execute("UPDATE visits SET status='done', notes=?, coaching=?, agreed_actions=? WHERE id=?", (b.get("notes", ""), json.dumps(b.get("coaching", [])), json.dumps(acts), vid))
    if b.get("notes"): c.execute("INSERT INTO comments(entity,entity_id,user_id,text,ts) VALUES('visit',?,?,?,?)", (vid, u["id"], b["notes"], E.now_iso()))
    s = db.one(c, "SELECT * FROM stores WHERE id=?", (v["store_id"],))
    made = [T.create_task(c, s, dict(id=0, title=a, body_md=f"Agreed during {u['name']}'s visit on {v['date']}.", questions="[]", est_minutes=20,
                                     assignee_role="store_manager", attachments="[]"), source="visit", due_days=5) for a in acts]
    sm = T.assignee_for(c, s, "store_manager")
    for note in b.get("coaching", []):
        if sm and note.strip(): c.execute("INSERT INTO comments(entity,entity_id,user_id,text,ts) VALUES('coaching',?,?,?,?)", (sm, u["id"], note, E.now_iso()))
    c.commit(); ai.extract_themes(c, week()); return {"ok": True, "tasks": made}

# ---------------- best practice ----------------
@app.get("/api/bestpractices")
def bps(req: Request, kpi: str = None):
    user_of(req); c = C()
    q = """SELECT b.*, u.name author, s.code, s.name store_name, (SELECT COUNT(*) FROM bp_adopt a WHERE a.bp_id=b.id) adopted
           FROM best_practices b LEFT JOIN users u ON u.id=b.user_id LEFT JOIN stores s ON s.id=b.store_id"""
    return db.rows(c, q + (" WHERE kpi=?" if kpi else "") + " ORDER BY impact_value DESC, likes DESC", (kpi,) if kpi else ())

@app.post("/api/bestpractices/{bid}/like")
def bp_like(req: Request, bid: int):
    user_of(req); c = C(); c.execute("UPDATE best_practices SET likes=likes+1 WHERE id=?", (bid,)); c.commit(); return {"ok": True}

@app.post("/api/bestpractices/{bid}/adopt")
async def bp_adopt(req: Request, bid: int):
    """Adopt a practice: a draft mission in my store pre-filled with the proven action and today's real gap."""
    u = user_of(req); b = await body(req); c = C(); bp = db.one(c, "SELECT * FROM best_practices WHERE id=?", (bid,))
    if not bp: raise HTTPException(404, "No practice")
    sid = int(b.get("store_id") or u["store_id"] or 0); check_store(u, sid)
    g = E.metric_gap(E.WeekData(c, week(), 1), sid, bp["kpi"], bp["cat_id"]) if bp["kpi"] in GAP_KPIS else None
    owner = T.assignee_for(c, db.one(c, "SELECT * FROM stores WHERE id=?", (sid,)), "store_manager")
    cat = (db.one(c, "SELECT name FROM categories WHERE id=?", (bp["cat_id"],)) or {}).get("name") if bp["cat_id"] else None
    mid = E.create_mission(c, dict(store_id=sid, owner_id=owner, kind="opportunity", kpi=bp["kpi"], cat_id=bp["cat_id"],
        title=f"Adopted practice: {cat or KPIS[bp['kpi']]['label']}", status="prelaunch", source="best_practice", created_by=u["id"],
        created_week=week(), action_type=bp["action_type"], action=bp["body"], baseline_gap=g["gap"] if g else 0,
        target_weekly=max(g["gap"], 0) if g else 0, comment=f"Adopted from best practice #{bid}"))
    c.execute("INSERT INTO bp_adopt VALUES(?,?,?,?,?)", (bid, sid, u["id"], mid, E.now_iso())); c.commit(); return {"mission_id": mid}

# ---------------- comms ----------------
def comms_for(c, u):
    S = E.store_rows(c); my = scope(u); out = []
    for a in db.rows(c, "SELECT a.*, us.name author FROM announcements a LEFT JOIN users us ON us.id=a.author_id ORDER BY id DESC"):
        tgt = db.J(a["target"], {})
        if tgt.get("roles") and u["role"] not in tgt["roles"] and u["role"] not in ("hq_admin", "central_analyst"): continue
        st_t = {k: v for k, v in tgt.items() if k != "roles"}
        if u["role"] not in ("hq_admin", "central_analyst") and not any(E.store_matches(S[s], st_t) for s in my): continue
        a["read"] = bool(db.one(c, "SELECT 1 FROM announcement_reads WHERE ann_id=? AND user_id=?", (a["id"], u["id"])))
        a["target"] = tgt; a["reads"] = c.execute("SELECT COUNT(*) FROM announcement_reads WHERE ann_id=?", (a["id"],)).fetchone()[0]
        out.append(a)
    return out

@app.get("/api/comms")
def comms(req: Request): u = user_of(req); return comms_for(C(), u)

@app.post("/api/comms")
async def comms_post(req: Request):
    u = user_of(req); need(u, "comms"); b = await body(req); c = C()
    if not b.get("title") or not b.get("body"): raise HTTPException(400, "Title and message required")
    aid = c.execute("INSERT INTO announcements(title,body,target,author_id,ts,priority,require_ack) VALUES(?,?,?,?,?,?,?)",
                    (b["title"], b["body"], json.dumps(b.get("target", {})), u["id"], E.now_iso(), b.get("priority", "normal"), int(b.get("require_ack", 0)))).lastrowid
    S = E.store_rows(c); tgt = b.get("target", {}); n = 0
    for x in db.rows(c, "SELECT * FROM users WHERE active=1 AND store_id IS NOT NULL"):
        if tgt.get("roles") and x["role"] not in tgt["roles"]: continue
        if E.store_matches(S[x["store_id"]], {k: v for k, v in tgt.items() if k != "roles"}): E.notify(c, x["id"], f"Announcement: {b['title']}", "#/comms"); n += 1
    c.commit(); return {"id": aid, "recipients": n}

@app.post("/api/comms/{aid}/read")
def comms_read(req: Request, aid: int):
    u = user_of(req); c = C(); c.execute("INSERT OR IGNORE INTO announcement_reads VALUES(?,?,?)", (aid, u["id"], E.now_iso())); c.commit(); return {"ok": True}

# ---------------- campaigns / blackouts (HQ steering) ----------------
@app.get("/api/campaigns")
def camps(req: Request):
    user_of(req); c = C(); out = []
    for x in db.rows(c, "SELECT * FROM campaigns ORDER BY id DESC"):
        ms = db.rows(c, "SELECT id, status FROM missions WHERE campaign_id=?", (x["id"],))
        acc = sum(1 for m in ms if m["status"] in ("prelaunch", "proposed", "live", "done"))
        x.update(kpis=db.J(x["kpis"], []), categories=db.J(x["categories"], []), target=db.J(x["target"], {}), missions=len(ms),
                 holdout=db.J(x.get("holdout"), []), accept_rate=round(acc / len(ms) * 100) if ms else 0,
                 launched=sum(1 for m in ms if m["status"] in ("live", "done")),
                 impact=round(sum(E.mission_impact_summary(c, m["id"])["cumulative"] for m in ms if m["status"] in ("live", "done")), 2))
        out.append(x)
    return out

def reprioritise(c):
    """Re-score this week's opportunities with the new steering and refresh untouched engine inbox items."""
    w = week()
    c.execute("DELETE FROM missions WHERE status='incoming' AND source='engine' AND created_week=?", (w,))
    E.compute_opportunities(c, w); r = E.prioritise(c, w); c.commit(); return r

PUSH_BOOST = {"gentle": 1.2, "standard": 1.6, "must": 3.0}

def must_count(c, start_week, exclude=None):
    q = (start_week - 1) // 13
    return sum(1 for x in db.rows(c, "SELECT id, start_week FROM campaigns WHERE active=1 AND push='must'")
               if (x["start_week"] - 1) // 13 == q and x["id"] != exclude)

def campaign_match(c, target, kpis, cats):
    S = E.store_rows(c)
    stores = [s for s in S.values() if s["status"] == "Open" and E.store_matches(s, target)]
    cap = {x["store_id"]: x for x in E.capacity_status(c)}
    full = [s["code"] for s in stores if c.execute("SELECT COUNT(*) FROM missions WHERE store_id=? AND status='incoming'", (s["id"],)).fetchone()[0] >= db.setting(c, "inbox_size", 3)]
    opp = 0
    if kpis or cats:
        ph = ",".join("?" * len(kpis)) or "''"
        q = f"SELECT COUNT(DISTINCT store_id) FROM opportunities WHERE week=? AND (kpi IN ({ph})" + (f" OR cat_id IN ({','.join('?'*len(cats))}) OR cat_id IN (SELECT id FROM categories WHERE parent_id IN ({','.join('?'*len(cats))}))" if cats else "") + ")"
        opp = c.execute(q, (week(), *kpis, *cats, *cats)).fetchone()[0]
    return dict(stores=len(stores), regions=len({s["region_id"] for s in stores}), at_limit=full, with_gap=opp,
                at_capacity=[s["code"] for s in stores if cap.get(s["id"], {}).get("at_capacity")], ids=[s["id"] for s in stores])

@app.post("/api/campaigns/preview")
async def camp_preview(req: Request):
    u = user_of(req); need(u, "campaigns"); b = await body(req); c = C()
    r = campaign_match(c, b.get("target", {}), b.get("kpis", []), [int(x) for x in b.get("categories", [])])
    r.pop("ids"); r["must_used"] = must_count(c, int(b.get("start_week", week())), b.get("id")); r["must_max"] = db.setting(c, "max_must_per_quarter", 3)
    return r

@app.post("/api/campaigns")
async def camp_save(req: Request):
    u = user_of(req); need(u, "campaigns"); b = await body(req); c = C()
    if not (b.get("name") or "").strip(): raise HTTPException(400, "Name the campaign")
    push = b.get("push", "standard")
    if push not in PUSH_BOOST: raise HTTPException(400, "push must be gentle, standard or must")
    sw = int(b.get("start_week", week()))
    mx = db.setting(c, "max_must_per_quarter", 3)
    if push == "must" and int(b.get("active", 1)) and must_count(c, sw, b.get("id")) >= mx:
        raise HTTPException(400, f"Only {mx} Must-do campaigns can be active per quarter. Pause one or use Standard.")
    cats = [int(x) for x in b.get("categories", [])]
    holdout = b.get("holdout")
    if holdout is None and not b.get("id"):
        import random
        ids_ = campaign_match(c, b.get("target", {}), b.get("kpis", []), cats)["ids"]
        holdout = sorted(random.Random(hash(b["name"]) & 0xffff).sample(ids_, min(len(ids_) // 6, 8))) if len(ids_) >= 12 else []
    vals = (b["name"], json.dumps(b.get("kpis", [])), json.dumps(cats), float(b.get("boost") or PUSH_BOOST[push]),
            sw, int(b.get("end_week", week() + 4)), json.dumps(b.get("target", {})), int(b.get("active", 1)), u["id"], b.get("message", ""), push)
    if b.get("id"):
        c.execute("UPDATE campaigns SET name=?,kpis=?,categories=?,boost=?,start_week=?,end_week=?,target=?,active=?,created_by=?,message=?,push=? WHERE id=?", (*vals, b["id"])); cid = b["id"]
    else:
        cid = c.execute("INSERT INTO campaigns(name,kpis,categories,boost,start_week,end_week,target,active,created_by,message,push,holdout) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (*vals, json.dumps(holdout or []))).lastrowid
    c.commit(); res = {"id": cid}
    if b.get("reprioritise", True): res["recompute"] = reprioritise(c)
    return res

@app.post("/api/admin/reprioritise")
def reprio(req: Request): u = user_of(req); need(u, "campaigns"); return reprioritise(C())

@app.get("/api/blackouts")
def blk(req: Request): user_of(req); return [dict(b, target=db.J(b["target"], {})) for b in db.rows(C(), "SELECT * FROM blackouts")]

@app.post("/api/blackouts")
async def blk_save(req: Request):
    u = user_of(req); need(u, "campaigns"); b = await body(req); c = C()
    if not (b.get("name") and b.get("start_date") and b.get("end_date")): raise HTTPException(400, "Name and dates required")
    bid = c.execute("INSERT INTO blackouts(name,start_date,end_date,target) VALUES(?,?,?,?)", (b["name"], b["start_date"], b["end_date"], json.dumps(b.get("target", {})))).lastrowid
    c.commit(); return {"id": bid}

@app.delete("/api/blackouts/{bid}")
def blk_del(req: Request, bid: int):
    u = user_of(req); need(u, "campaigns"); c = C(); c.execute("DELETE FROM blackouts WHERE id=?", (bid,)); c.commit(); return {"ok": True}

# ---------------- impact & engagement ----------------
@app.get("/api/impact")
def impact(req: Request):
    u = user_of(req); c = C(); ids = scope(u)
    ms = db.rows(c, f"""SELECT m.*, s.code, s.district_id, d.region_id FROM missions m JOIN stores s ON s.id=m.store_id
                       JOIN districts d ON d.id=s.district_id WHERE m.store_id IN ({ids_sql(ids)}) AND m.status IN ('live','done')""")
    by = {k: defaultdict(lambda: dict(n=0, value=0.0, wins=0)) for k in ("kpi", "action_type", "district_id", "region_id")}
    total = erosion = 0; weekly = defaultdict(float); per_store = defaultdict(float); wins = 0
    for m in ms:
        s = E.mission_impact_summary(c, m["id"]); total += s["cumulative"]; erosion += s["erosion"]; per_store[m["store_id"]] += s["cumulative"]
        wins += 1 if s["cumulative"] > 0 else 0
        for k in by:
            b = by[k][m[k] or "—"]; b["n"] += 1; b["value"] += s["cumulative"]; b["wins"] += 1 if s["cumulative"] > 0 else 0
        for r in s["weeks"]:
            if r["week"] <= (m["end_week"] or 999): weekly[r["week"]] += r["net"]
    dn = {d["id"]: d["name"] for d in db.rows(c, "SELECT * FROM districts")}; rn = {r["id"]: r["name"] for r in db.rows(c, "SELECT * FROM regions")}
    def fmt(k, names=None):
        return sorted([dict(key=(names or {}).get(x, KPIS.get(x, {}).get("label", x) if k == "kpi" else x), n=v["n"], value=round(v["value"], 2),
                            win_rate=round(v["wins"] / v["n"] * 100) if v["n"] else 0) for x, v in by[k].items()], key=lambda r: -r["value"])
    eng = db.rows(c, f"""SELECT s.id, s.code, s.name, u.name manager, u.last_login,
        SUM(m.status IN ('live','done','proposed')) accepted, SUM(m.status='rejected') rejected, SUM(m.status='incoming') waiting
        FROM stores s LEFT JOIN users u ON u.store_id=s.id AND u.role='store_manager' LEFT JOIN missions m ON m.store_id=s.id AND m.kind!='theme'
        WHERE s.id IN ({ids_sql(ids)}) GROUP BY s.id ORDER BY accepted DESC""")
    for e in eng:
        tot = sum(e[k] or 0 for k in ("accepted", "rejected", "waiting"))
        e["action_rate"] = round(((e["accepted"] or 0) + (e["rejected"] or 0)) / tot * 100) if tot else 0
    wd = E.WeekData(c, week(), 1)
    st = {s["id"]: s for s in db.rows(c, "SELECT * FROM stores")}
    mgr = {x["store_id"]: x["name"] for x in db.rows(c, "SELECT * FROM users WHERE role='store_manager'")}
    leaders = sorted([dict(store=st[s]["code"], manager=mgr.get(s), impact=round(v), per_100k=round(v / max(wd.total.get(s, 1) / 1e5, 1e-9), 1))
                      for s, v in per_store.items()], key=lambda r: -r["per_100k"])[:10]
    return dict(total=round(total, 2), missions=len(ms), win_rate=round(wins / len(ms) * 100) if ms else 0, erosion=round(erosion, 2),
                by_kpi=fmt("kpi"), by_action=fmt("action_type"), by_district=fmt("district_id", dn), by_region=fmt("region_id", rn),
                weekly=[dict(week=k, value=round(v, 2)) for k, v in sorted(weekly.items())], engagement=eng, leaders=leaders,
                active_users=c.execute("SELECT COUNT(DISTINCT user_id) FROM logins").fetchone()[0])

# ---------------- architect (no-code builder, data, users, settings) ----------------
@app.get("/api/mission_rules")
def mrules(req: Request): user_of(req); return [dict(r, target=db.J(r["target"], {})) for r in db.rows(C(), "SELECT * FROM mission_rules")]

@app.post("/api/mission_rules")
async def mrule_save(req: Request):
    u = user_of(req); need(u, "architect"); b = await body(req); c = C()
    if b.get("metric") not in list(E.RULE_METRICS) and not str(b.get("metric", "")).startswith("waste_pct:"): raise HTTPException(400, "Unknown metric")
    vals = (b["name"], b["metric"], b["op"], float(b["threshold"]), b.get("kind", "alert"), b["title"], b.get("guidance", ""), json.dumps(b.get("target", {})),
            b.get("assignee_role", "store_manager"), b.get("priority", "Must"), int(b.get("active", 1)))
    if b.get("id"):
        c.execute("UPDATE mission_rules SET name=?,metric=?,op=?,threshold=?,kind=?,title=?,guidance=?,target=?,assignee_role=?,priority=?,active=? WHERE id=?", (*vals, b["id"])); rid = b["id"]
    else:
        rid = c.execute("INSERT INTO mission_rules(name,metric,op,threshold,kind,title,guidance,target,assignee_role,priority,active) VALUES(?,?,?,?,?,?,?,?,?,?,?)", vals).lastrowid
    c.commit()
    preview = [o for o in E.rule_alerts(c, E.WeekData(c, week(), 1)) if db.J(o["detail"], {}).get("rule_id") == rid]
    codes = {s["id"]: s["code"] for s in db.rows(c, "SELECT id, code FROM stores")}
    return {"id": rid, "would_fire": len(preview), "stores": [codes[o["store_id"]] for o in preview][:30]}

@app.post("/api/mission_rules/deploy")
def mrule_deploy(req: Request):
    u = user_of(req); need(u, "architect"); c = C(); w = week()
    E.compute_opportunities(c, w); r = E.prioritise(c, w); c.commit(); return r

@app.get("/api/admin/stores")
def adm_stores(req: Request):
    u = user_of(req); need(u, "architect"); return db.rows(C(), "SELECT s.*, d.name district FROM stores s JOIN districts d ON d.id=s.district_id ORDER BY code")

@app.post("/api/admin/stores/{sid}")
async def adm_store(req: Request, sid: int):
    u = user_of(req); need(u, "architect"); b = await body(req); c = C()
    if "status" in b:
        if b["status"] not in ("New", "Open", "Closed"): raise HTTPException(400, "Status must be New, Open or Closed")
        c.execute("UPDATE stores SET status=? WHERE id=?", (b["status"], sid)); E.log(c, "store", sid, u["id"], "status", b["status"])
    if "tags" in b: c.execute("UPDATE stores SET tags=? WHERE id=?", (json.dumps([t.strip() for t in b["tags"] if t.strip()]), sid))
    if "capacity_hours" in b: c.execute("UPDATE stores SET capacity_hours=? WHERE id=?", (float(b["capacity_hours"]), sid))
    c.commit(); return {"ok": True}

@app.get("/api/admin/users")
def adm_users(req: Request): u = user_of(req); need(u, "users"); return db.rows(C(), "SELECT * FROM users ORDER BY id")

@app.post("/api/admin/users")
async def adm_user_save(req: Request):
    u = user_of(req); need(u, "users"); b = await body(req); c = C()
    if not b.get("name") or b.get("role") not in ROLE_LABELS: raise HTTPException(400, "Name and a valid role required")
    sid = int(b["store_id"]) if b.get("store_id") else None
    did = int(b["district_id"]) if b.get("district_id") else (db.one(c, "SELECT district_id FROM stores WHERE id=?", (sid,)) or {}).get("district_id") if sid else None
    rid = int(b["region_id"]) if b.get("region_id") else ((db.one(c, "SELECT region_id FROM districts WHERE id=?", (did,)) or {}).get("region_id") if did else None)
    if b.get("id"):
        c.execute("UPDATE users SET name=?, role=?, store_id=?, district_id=?, region_id=? WHERE id=?", (b["name"], b["role"], sid, did, rid, b["id"])); uid = b["id"]
    else:
        uid = c.execute("INSERT INTO users(name,email,role,store_id,district_id,region_id) VALUES(?,?,?,?,?,?)", (b["name"], b.get("email"), b["role"], sid, did, rid)).lastrowid
        if b["role"] == "store_manager" and sid:
            c.execute("UPDATE users SET active=0 WHERE role='store_manager' AND store_id=? AND id!=?", (sid, uid))
            T.fire_event(c, "new_manager", {"store_codes": [db.one(c, "SELECT code FROM stores WHERE id=?", (sid,))["code"]], "message": f"Welcome {b['name']}!"})
    c.commit(); return {"id": uid}

@app.post("/api/admin/users/{uid}/remove")
def adm_user_remove(req: Request, uid: int):
    """Deactivate and anonymise a user's personal data (deletion request)."""
    u = user_of(req); need(u, "users"); c = C()
    if uid == u["id"]: raise HTTPException(400, "You can't remove yourself")
    c.execute("UPDATE users SET active=0, name=?, email=NULL WHERE id=?", (f"Former user #{uid}", uid)); c.commit(); return {"ok": True}

CAPS = ["architect", "campaigns", "approve", "send_mission", "tasks_admin", "surveys_admin", "comms", "data", "users", "impact", "visits", "team", "dc"]

@app.get("/api/admin/permissions")
def adm_perms(req: Request):
    u = user_of(req); need(u, "users"); return dict(permissions=db.setting(C(), "permissions", DEFAULT_PERMISSIONS), roles=ROLE_LABELS, capabilities=CAPS)

@app.post("/api/admin/permissions")
async def adm_perms_save(req: Request):
    u = user_of(req); need(u, "users"); b = await body(req); c = C(); p = b["permissions"]
    if "users" not in p.get("hq_admin", []): raise HTTPException(400, "HQ admin must keep 'users' so nobody gets locked out")
    db.set_setting(c, "permissions", {r: [x for x in v if x in CAPS] for r, v in p.items()}); return {"ok": True}

@app.post("/api/admin/settings")
async def adm_settings(req: Request):
    u = user_of(req); need(u, "architect"); b = await body(req); c = C()
    for k in ["inbox_size", "window_weeks", "currency", "mission_duration", "require_approval", "max_must_per_quarter"]:
        if k in b: db.set_setting(c, k, b[k])
    return {"ok": True}

@app.post("/api/admin/next_week")
def adm_next(req: Request): u = user_of(req); need(u, "data"); return seed.next_week(C())

@app.post("/api/admin/recompute")
def adm_recompute(req: Request): u = user_of(req); need(u, "data"); return E.run_week(C(), week())

@app.post("/api/admin/reset")
def adm_reset(req: Request):
    u = user_of(req)
    if not PUBLIC: need(u, "users")
    now = time.time()
    with _lock:
        while _resets and _resets[0] < now - 3600: _resets.popleft()
        if len(_resets) >= CFG.RESET_LIMIT_PER_HOUR: raise HTTPException(429, "Demo data was reset recently – try again later.")
        _resets.append(now)
    seed.build(quiet=True); return {"ok": True}

@app.get("/api/capacity")
def capacity(req: Request): u = user_of(req); ids = scope(u); return [x for x in E.capacity_status(C()) if x["store_id"] in ids]

@app.post("/api/data/preview")
async def data_preview(req: Request, file: UploadFile = File(...), target: str = Form(...)):
    u = user_of(req); need(u, "data")
    if target not in I.TARGETS: raise HTTPException(400, "Unknown target")
    txt = (await file.read()).decode("utf-8-sig"); h, rows = I.parse(txt)
    if not h: raise HTTPException(400, "Empty file")
    tok = uuid.uuid4().hex; open(os.path.join(UPLOADS, tok + ".csv"), "w").write(txt)
    return dict(token=tok, filename=file.filename, headers=h, sample=rows[:8], rows=len(rows), suggested=I.suggest_mapping(h, target), fields=I.TARGETS[target])

@app.post("/api/data/ingest")
async def data_ingest(req: Request):
    u = user_of(req); need(u, "data"); b = await body(req)
    p = os.path.join(UPLOADS, os.path.basename(b["token"]) + ".csv")
    if not os.path.exists(p): raise HTTPException(404, "Upload expired – preview again")
    return I.ingest(C(), open(p).read(), b["target"], {k: v for k, v in b["mapping"].items() if v}, b.get("filename", "upload.csv"))

@app.get("/api/data/uploads")
def data_uploads(req: Request):
    u = user_of(req); need(u, "data"); c = C()
    return dict(uploads=db.rows(c, "SELECT * FROM uploads ORDER BY id DESC LIMIT 30"), issues=db.rows(c, "SELECT * FROM data_issues ORDER BY id DESC LIMIT 100"),
                dropfolder=sorted(f for f in os.listdir(DROP) if f.endswith(".csv")), events=db.rows(c, "SELECT * FROM events ORDER BY id DESC LIMIT 20"),
                weeks=db.one(c, "SELECT MIN(week) a, MAX(week) b, COUNT(*) n FROM weeks"), rows=c.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0],
                drop_path="data/dropfolder" if PUBLIC else DROP)

TEMPLATES = {"sales": "store_code,week_start,category,department,sales,units,waste\nS001,2026-10-12,Dog Food,Pet,5321.50,900,12.0\n",
    "store": "store_code,week_start,traffic,transactions,labor_hours,labor_budget,overtime_hours,csat,attach_rate,cash_over_short,gap_scan_pct,inv_accuracy,budget_sales\nS001,2026-10-12,9000,4800,1500,1400,40,82,0.18,-12,0.95,0.97,430000\n",
    "missions": "store_code,title,details,priority,kpi\nS001,Check Dog Food bay after reset,Analytics found facings lost after the reset,Must,sales\n",
    "stores": "code,name,format,district,tags,sqft,status,city\nS051,Newtown Standard,Standard,Lakes,Pharmacy|Near Campus,44000,New,Newtown\n"}

@app.get("/api/data/template/{target}")
def data_template(target: str):
    if target not in TEMPLATES: raise HTTPException(404)
    return PlainTextResponse(TEMPLATES[target], media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={target}_template.csv"})

@app.post("/api/connectors/dropfolder")
def dropfolder(req: Request): u = user_of(req); need(u, "data"); return I.run_dropfolder(C(), DROP)

@app.post("/api/events")
async def events(req: Request):
    """Event hub: external systems post {type, store_codes|target, message}; matching event rules create tasks."""
    u = user_of(req); need(u, "data"); b = await body(req)
    if not b.get("type"): raise HTTPException(400, "type required")
    return T.fire_event(C(), b["type"], b)

@app.get("/api/export/{name}.csv")
def export(req: Request, name: str):
    u = user_of(req); need(u, "data")
    if name not in I.EXPORTS: raise HTTPException(404, "Unknown export")
    return PlainTextResponse(I.export_csv(C(), name), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={name}.csv"})

@app.post("/api/files")
async def files(req: Request, file: UploadFile = File(...)):
    user_of(req); ext = os.path.splitext(file.filename or "")[1][:8]; fid = uuid.uuid4().hex + ext
    open(os.path.join(UPLOADS, fid), "wb").write(await file.read())
    c = C(); c.execute("INSERT INTO files(name,path,mime,ts) VALUES(?,?,?,?)", (file.filename, fid, file.content_type, E.now_iso())); c.commit()
    return {"url": f"/files/{fid}", "name": file.filename, "mime": file.content_type}

@app.get("/files/{fid}")
def file_get(fid: str):
    p = os.path.join(UPLOADS, os.path.basename(fid))
    if not os.path.exists(p): raise HTTPException(404)
    return FileResponse(p)

# ---------------- AI layer ----------------
@app.get("/api/ai/explain/{mid}")
def ai_explain(req: Request, mid: int): u = user_of(req); get_m(u, mid); return ai.explain_mission(C(), mid)

@app.post("/api/ai/ask")
async def ai_ask(req: Request):
    u = user_of(req); b = await body(req); return ai.ask(C(), u, b.get("q", ""), scope(u))

@app.get("/api/ai/themes")
def ai_themes(req: Request):
    user_of(req); c = C()
    return [dict(t, keywords=db.J(t["keywords"], []), stores=db.J(t["stores"], [])) for t in db.rows(c, "SELECT * FROM themes ORDER BY week DESC, count DESC LIMIT 50")]

@app.post("/api/ai/themes/run")
def ai_themes_run(req: Request): user_of(req); return {"missions_created": ai.extract_themes(C(), week())}

@app.get("/api/ai/context")
def ai_ctx(req: Request): user_of(req); return ai.org_context(C())

# ---------------- distribution centres ----------------
@app.get("/api/dc")
def dc(req: Request):
    u = user_of(req); c = C(); ids = scope(u)
    q, a = ("WHERE p.dc_id=?", (u["dc_id"],)) if u["role"] == "dc_manager" else (f"WHERE f.store_id IN ({ids_sql(ids)})", ())
    flags = db.rows(c, f"""SELECT f.*, p.dc_id, p.picker, p.loader, p.shift, p.picker_tenure_m, s.code, d.name dc FROM load_flags f
        JOIN pallets p ON p.id=f.pallet_id JOIN stores s ON s.id=f.store_id JOIN dcs d ON d.id=p.dc_id {q} ORDER BY f.id DESC""", a)
    pallets = db.rows(c, f"SELECT id, store_id FROM pallets WHERE store_id IN ({ids_sql(ids)}) ORDER BY id LIMIT 60")
    return dict(flags=flags, pallets=pallets, dcs=db.rows(c, "SELECT * FROM dcs"),
                missions=[enrich(c, m) for m in db.rows(c, "SELECT * FROM missions WHERE kpi='dc_quality' AND owner_id=? ORDER BY id DESC", (u["id"],))])

@app.post("/api/dc/flags")
async def dc_flag(req: Request):
    """A store flags a load-quality issue; the pallet links to DC, picker, loader, shift and history; a mission routes to the DC manager."""
    u = user_of(req); b = await body(req); c = C()
    p = db.one(c, "SELECT * FROM pallets WHERE id=?", ((b.get("pallet_id") or "").strip().upper(),))
    if not p: raise HTTPException(404, "Unknown pallet ID")
    sid = int(b.get("store_id") or p["store_id"]); check_store(u, sid)
    if not b.get("issue_type"): raise HTTPException(400, "Pick an issue type")
    fid = c.execute("INSERT INTO load_flags(pallet_id,store_id,user_id,issue_type,note,photo,ts) VALUES(?,?,?,?,?,?,?)",
                    (p["id"], sid, u["id"], b["issue_type"], b.get("note", ""), b.get("photo"), E.now_iso())).lastrowid
    hist = c.execute("SELECT COUNT(*) FROM load_flags f JOIN pallets x ON x.id=f.pallet_id WHERE x.dc_id=? AND f.issue_type=?", (p["dc_id"], b["issue_type"])).fetchone()[0]
    ph = c.execute("SELECT COUNT(*) FROM load_flags f JOIN pallets x ON x.id=f.pallet_id WHERE x.picker=?", (p["picker"],)).fetchone()[0]
    dcm = db.one(c, "SELECT id FROM users WHERE role='dc_manager' AND dc_id=? AND active=1", (p["dc_id"],))
    s = db.one(c, "SELECT * FROM stores WHERE id=?", (sid,))
    ctx = (f"Pallet {p['id']} to {s['code']} ({p['shift']} shift). Picker {p['picker']}: {p['picker_tenure_m']} months tenure, {ph} flag(s) in total. "
           f"Loader {p['loader']}. This DC has {hist} '{b['issue_type']}' flag(s) recently. Store note: {b.get('note', '')}")
    mid = E.create_mission(c, dict(store_id=sid, owner_id=dcm["id"] if dcm else None, kind="alert", kpi="dc_quality", title=f"Load quality: {b['issue_type']} on {p['id']}",
                                   status="incoming", source="load_flag", created_by=u["id"], created_week=week(), priority="Must", comment=ctx, baseline_gap=0, target_weekly=0))
    c.execute("UPDATE load_flags SET mission_id=? WHERE id=?", (mid, fid)); c.commit()
    return {"id": fid, "mission_id": mid, "context": ctx}

@app.post("/api/dc/flags/{fid}/resolve")
async def dc_resolve(req: Request, fid: int):
    u = user_of(req); need(u, "dc"); b = await body(req); c = C(); f = db.one(c, "SELECT * FROM load_flags WHERE id=?", (fid,))
    if not f: raise HTTPException(404, "No flag")
    c.execute("UPDATE load_flags SET status='resolved', resolution=? WHERE id=?", (b.get("resolution", ""), fid))
    if f["mission_id"]: c.execute("UPDATE missions SET status='done', action=? WHERE id=?", (b.get("resolution", ""), f["mission_id"]))
    E.notify(c, f["user_id"], f"DC acted on your load flag {f['pallet_id']}: {b.get('resolution', '')}", "#/dc")
    E.log(c, "load_flag", fid, u["id"], "resolved", b.get("resolution", "")); c.commit(); return {"ok": True}

# ---------------- MCP-style tool endpoint (JSON-RPC 2.0) ----------------
MCP_TOOLS = [
  {"name": "list_opportunities", "description": "Top opportunities this week, optionally for one store code.",
   "inputSchema": {"type": "object", "properties": {"store_code": {"type": "string"}, "limit": {"type": "integer"}}}},
  {"name": "get_store_summary", "description": "KPI gaps vs peers for a store.",
   "inputSchema": {"type": "object", "properties": {"store_code": {"type": "string"}}, "required": ["store_code"]}},
  {"name": "list_live_missions", "description": "Live missions with net impact.", "inputSchema": {"type": "object", "properties": {}}},
  {"name": "create_mission", "description": "Push a mission into a store manager's inbox.", "inputSchema": {"type": "object",
   "properties": {"store_code": {"type": "string"}, "title": {"type": "string"}, "details": {"type": "string"}}, "required": ["store_code", "title"]}},
]

@app.post("/mcp")
async def mcp(req: Request):
    u = user_of(req); b = await body(req); c = C(); rid = b.get("id"); m = b.get("method")
    def ok(r): return {"jsonrpc": "2.0", "id": rid, "result": r}
    def err(code, msg): return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}
    if m == "initialize": return ok({"protocolVersion": "2025-06-18", "serverInfo": {"name": "colstorso", "version": "1.0"}, "capabilities": {"tools": {}}})
    if m == "tools/list": return ok({"tools": MCP_TOOLS})
    if m != "tools/call": return err(-32601, "method not found")
    n, a = b["params"]["name"], b["params"].get("arguments", {}); ids = scope(u)
    if n == "list_opportunities":
        q = f"SELECT s.code, o.title, ROUND(o.gap_value) gap, ROUND(o.score) score FROM opportunities o JOIN stores s ON s.id=o.store_id WHERE week=? AND store_id IN ({ids_sql(ids)})"
        args = [week()]
        if a.get("store_code"): q += " AND s.code=?"; args.append(a["store_code"])
        data = db.rows(c, q + " ORDER BY score DESC LIMIT ?", (*args, int(a.get("limit", 10))))
    elif n == "get_store_summary":
        s = db.one(c, "SELECT * FROM stores WHERE code=?", (a["store_code"],))
        if not s: return err(-32602, "unknown store")
        check_store(u, s["id"]); wd = E.WeekData(c, week(), 1)
        data = {}
        for k in E.STORE_KPIS:
            g = E.metric_gap(wd, s["id"], k)
            data[k] = dict(actual=round(g["actual"], 2), peers=round(g["expected"], 2), gap=round(g["gap"])) if g else None
    elif n == "list_live_missions":
        data = [dict(id=x["id"], store=x["store_code"], title=x["title"], net=x["impact"]["cumulative"])
                for x in (enrich(c, m_) for m_ in db.rows(c, f"SELECT * FROM missions WHERE status='live' AND store_id IN ({ids_sql(ids)})"))]
    elif n == "create_mission":
        need(u, "send_mission"); s = db.one(c, "SELECT * FROM stores WHERE code=?", (a["store_code"],))
        if not s: return err(-32602, "unknown store")
        check_store(u, s["id"])
        data = {"mission_id": E.create_mission(c, dict(store_id=s["id"], owner_id=T.assignee_for(c, s, "store_manager"), kind="opportunity", kpi="custom",
                 title=a["title"], status="incoming", source="mcp", created_by=u["id"], created_week=week(), comment=a.get("details"), baseline_gap=0, target_weekly=0))}
        c.commit()
    else:
        return err(-32601, "unknown tool")
    return ok({"content": [{"type": "text", "text": json.dumps(data, default=str)}]})

# ---------------- embeddable widget (iframe into BI / comms tools) ----------------
@app.get("/embed/store/{code}", response_class=HTMLResponse)
def embed(code: str, request: Request):
    u = user_of(request); c = C(); s = db.one(c, "SELECT * FROM stores WHERE code=?", (code,))
    if not s: raise HTTPException(404)
    check_store(u, s["id"])
    ms = [enrich(c, m) for m in db.rows(c, "SELECT * FROM missions WHERE store_id=? AND status IN ('incoming','live') ORDER BY status, baseline_gap DESC LIMIT 8", (s["id"],))]
    esc = lambda x: str(x).replace("&", "&amp;").replace("<", "&lt;")
    li = "".join(f"<li><b>{esc(m['label'])}</b> {esc(m['title'])} <span class='muted'>${(m['baseline_gap'] or 0):,.0f}/wk</span></li>" for m in ms)
    return f"""<!doctype html><html><head><link rel=stylesheet href="/static/tokens.css"><link rel=stylesheet href="/static/app.css"></head>
      <body class="embed"><h3>{esc(s['name'])}: this week's missions</h3><ul class="embed-list">{li}</ul>
      <a target=_top href="/#/home">Open ColsTorso</a></body></html>"""
