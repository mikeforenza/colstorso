"""CSV ingestion with a column-mapping step, validation/data-quality checks, drop-folder connector and exports."""
import csv, io, json, os, re, shutil, difflib, statistics as stats, datetime as dt
from . import db
from .engine import now_iso, notify, create_mission, run_week

TARGETS = {
  "sales": {"required": ["store_code", "category", "sales"], "optional": ["week", "date", "units", "waste", "ly_sales", "department"]},
  "store": {"required": ["store_code"], "optional": ["week", "date", "traffic", "transactions", "labor_hours", "labor_budget",
            "overtime_hours", "csat", "attach_rate", "cash_over_short", "gap_scan_pct", "inv_accuracy", "budget_sales"]},
  "missions": {"required": ["store_code", "title"], "optional": ["details", "priority", "kpi", "due_week"]},
  "stores": {"required": ["code", "name", "format"], "optional": ["district", "tags", "sqft", "status", "city"]},
}
SYN = {"store_code": ["store", "store_id", "site", "location", "branch", "store number", "store_no"],
       "category": ["subcategory", "sub_category", "cat", "product group", "class"], "sales": ["net sales", "revenue", "amount", "turnover"],
       "week": ["wk", "fiscal week", "week_no"], "date": ["week_start", "day", "period"], "waste": ["shrink", "spoilage", "write off"],
       "labor_hours": ["hours worked", "worked hours", "actual hours", "hours"], "labor_budget": ["budget hours", "scheduled budget"], "title": ["mission", "action", "task"],
       "code": ["store code", "store id", "store number", "site code"], "name": ["store name", "site name"],
       "traffic": ["footfall", "visitors", "door count", "footcount"], "transactions": ["baskets", "receipts", "trans", "tickets"],
       "overtime_hours": ["overtime", "ot hours", "ot"], "csat": ["customer satisfaction", "nps"], "department": ["dept", "division"],
       "district": ["area", "zone"], "format": ["store format", "type", "store type"]}

def parse(text):
    rd = csv.reader(io.StringIO(text))
    rows = list(rd)
    if not rows: return [], []
    return rows[0], rows[1:]

def suggest_mapping(headers, target):
    fields = TARGETS[target]["required"] + TARGETS[target]["optional"]
    out = {}
    norm = {h: re.sub(r"[^a-z0-9]+", " ", h.lower()).strip() for h in headers}
    for f in fields:
        cands = [x.replace("_", " ") for x in [f] + SYN.get(f, [])]
        best, bs = None, 0
        for h, n in norm.items():
            if h in out.values(): continue
            sc = max(difflib.SequenceMatcher(None, n, x).ratio() for x in cands)
            if n in cands: sc = 1.0
            if sc > bs: best, bs = h, sc
        if bs >= 0.72: out[f] = best
    return out

def date_to_week(c, d):
    d = dt.date.fromisoformat(d.strip()[:10])
    last = db.one(c, "SELECT week, start_date FROM weeks ORDER BY week DESC LIMIT 1")
    w, sd = last["week"], dt.date.fromisoformat(last["start_date"])
    if d >= sd:
        while (d - sd).days >= 7:
            w += 1; sd += dt.timedelta(days=7); c.execute("INSERT OR IGNORE INTO weeks VALUES(?,?)", (w, sd.isoformat()))
        return w
    r = db.one(c, "SELECT week FROM weeks WHERE start_date<=? ORDER BY start_date DESC LIMIT 1", (d.isoformat(),))
    return r["week"] if r else 1

def anchor_weeks(c, data, get, numeric):
    """Blank workspace: create the week calendar from the first file. Dates -> Monday-based weeks numbered from 1;
    plain week numbers -> the highest week in the file is the week just finished."""
    mon = lambda d: d - dt.timedelta(days=d.weekday())
    if numeric:
        ws = [int(num(get(r, "week"))) for r in data if get(r, "week") and num(get(r, "week")) is not None]
        hi = max(ws) if ws else 1
        last = mon(dt.date.today()) - dt.timedelta(days=7)
        for w in range(1, hi + 1): c.execute("INSERT OR IGNORE INTO weeks VALUES(?,?)", (w, (last - dt.timedelta(days=7 * (hi - w))).isoformat()))
    else:
        ds = []
        for r in data:
            try: ds.append(dt.date.fromisoformat((get(r, "date") or "").strip()[:10]))
            except ValueError: pass
        first = mon(min(ds)) if ds else mon(dt.date.today())
        c.execute("INSERT OR IGNORE INTO weeks VALUES(1,?)", (first.isoformat(),))

def num(v):
    v = (v or "").strip().replace(",", "").replace("$", "").replace("%", "")
    return float(v) if v not in ("", "-") else None

def ingest(c, text, target, mapping, filename="upload.csv", recompute=True):
    headers, data = parse(text)
    idx = {h: i for i, h in enumerate(headers)}
    issues = []; ok = 0; weeks = set()
    up = c.execute("INSERT INTO uploads(ts,filename,target,rows,mapping,status) VALUES(?,?,?,?,?,?)",
                   (now_iso(), filename, target, len(data), json.dumps(mapping), "processing")).lastrowid
    miss = [f for f in TARGETS[target]["required"] if f not in mapping]
    if target in ("sales", "store") and not ({"week", "date"} & set(mapping)): miss.append("week or date")
    if miss:
        c.execute("UPDATE uploads SET status=? WHERE id=?", ("failed: missing " + ", ".join(miss), up)); c.commit()
        return dict(ok=False, error="Missing required mapping: " + ", ".join(miss), upload_id=up)
    get = lambda row, f: row[idx[mapping[f]]] if f in mapping and mapping[f] in idx and idx[mapping[f]] < len(row) else None
    stores = {s["code"]: s for s in db.rows(c, "SELECT * FROM stores")}
    cats = {x["name"].lower(): x for x in db.rows(c, "SELECT * FROM categories")}
    hq = [u["id"] for u in db.rows(c, "SELECT id FROM users WHERE role IN ('hq_admin','central_analyst')")]
    def issue(sev, msg):
        if len(issues) < 200: issues.append(dict(severity=sev, message=msg))
        c.execute("INSERT INTO data_issues(ts,upload_id,severity,message) VALUES(?,?,?,?)", (now_iso(), up, sev, msg))
    if target in ("sales", "store") and not db.one(c, "SELECT 1 FROM weeks"):
        anchor_weeks(c, data, get, "week" in mapping)
    for ln, row in enumerate(data, 2):
        if not any(x.strip() for x in row): continue
        try:
            if target == "stores":
                dn = (get(row, "district") or "").strip()
                d = db.one(c, "SELECT id FROM districts WHERE name=?", (dn,))
                if not d and dn:
                    rg = db.one(c, "SELECT id FROM regions ORDER BY id LIMIT 1") or {"id": c.execute("INSERT INTO regions(name) VALUES('Region 1')").lastrowid}
                    d = {"id": c.execute("INSERT INTO districts(name,region_id) VALUES(?,?)", (dn, rg["id"])).lastrowid}
                    issue("info", f"line {ln}: new district '{dn}' created")
                code = get(row, "code").strip()
                tags = [t.strip() for t in (get(row, "tags") or "").split("|") if t.strip()]
                if code in stores:
                    c.execute("UPDATE stores SET name=?, format=?, tags=?, status=COALESCE(?,status) WHERE code=?",
                              (get(row, "name"), get(row, "format"), json.dumps(tags), get(row, "status"), code))
                else:
                    c.execute("INSERT INTO stores(code,name,district_id,format,sqft,status,tags,city) VALUES(?,?,?,?,?,?,?,?)",
                              (code, get(row, "name"), d["id"] if d else 1, get(row, "format"), int(num(get(row, "sqft")) or 0),
                               get(row, "status") or "New", json.dumps(tags), get(row, "city")))
                    issue("info", f"line {ln}: new store {code} created (status New until switched to Open)")
                    stores[code] = {"code": code}
                ok += 1; continue
            code = (get(row, "store_code") or "").strip()
            s = stores.get(code)
            if not s: issue("error", f"line {ln}: unknown store '{code}' – row skipped"); continue
            if target == "missions":
                create_mission(c, dict(store_id=s["id"], owner_id=(db.one(c, "SELECT id FROM users WHERE role='store_manager' AND store_id=?", (s["id"],)) or {}).get("id"),
                    kind="opportunity", kpi=get(row, "kpi") or "custom", title=get(row, "title"), status="incoming", source="csv",
                    created_week=db.setting(c, "current_week"), priority=get(row, "priority") or "Should",
                    comment=get(row, "details"), baseline_gap=0, target_weekly=0))
                ok += 1; continue
            w = int(num(get(row, "week"))) if get(row, "week") else date_to_week(c, get(row, "date"))
            while not db.one(c, "SELECT 1 FROM weeks WHERE week=?", (w,)):
                lw = db.one(c, "SELECT week, start_date FROM weeks ORDER BY week DESC LIMIT 1")
                c.execute("INSERT INTO weeks VALUES(?,?)", (lw["week"] + 1, (dt.date.fromisoformat(lw["start_date"]) + dt.timedelta(days=7)).isoformat()))
            weeks.add(w)
            if target == "sales":
                cn = get(row, "category").strip()
                cat = cats.get(cn.lower())
                if not cat:
                    dn = (get(row, "department") or "Uncategorised").strip()
                    dep = cats.get(dn.lower())
                    if not dep:
                        nid = c.execute("INSERT INTO categories(name,parent_id,first_seen_week) VALUES(?,?,?)", (dn, None, w)).lastrowid
                        dep = cats[dn.lower()] = dict(id=nid, name=dn, parent_id=None)
                    nid = c.execute("INSERT INTO categories(name,parent_id,first_seen_week) VALUES(?,?,?)", (cn, dep["id"], w)).lastrowid
                    cat = cats[cn.lower()] = dict(id=nid, name=cn, parent_id=dep["id"])
                    issue("warning", f"line {ln}: new category '{cn}' seen for the first time (under {dep['name']})")
                    for u in hq: notify(c, u, f"New category first seen in data: {cn}", "#/architect")
                sales = num(get(row, "sales"))
                if sales is None: issue("error", f"line {ln}: sales not numeric – skipped"); continue
                if sales < 0: issue("warning", f"line {ln}: negative sales {sales} at {code}")
                prev = db.one(c, "SELECT AVG(sales) a FROM fact_sales WHERE store_id=? AND cat_id=? AND week BETWEEN ? AND ?", (s["id"], cat["id"], w - 8, w - 1))
                if prev and prev["a"] and sales > 5 * prev["a"]: issue("warning", f"line {ln}: {code}/{cn} sales {sales:,.0f} is >5x its 8-week average")
                c.execute("INSERT OR REPLACE INTO fact_sales VALUES(?,?,?,?,?,?,?)", (s["id"], w, cat["id"], sales, num(get(row, "units")) or 0,
                          num(get(row, "waste")) or 0, num(get(row, "ly_sales")) or 0))
                if not db.one(c, "SELECT 1 FROM space WHERE store_id=? AND cat_id=?", (s["id"], cat["id"])):
                    n = c.execute("SELECT COUNT(*) FROM categories WHERE parent_id=?", (cat["parent_id"],)).fetchone()[0]
                    c.execute("INSERT INTO space VALUES(?,?,?)", (s["id"], cat["id"], round(1 / max(n, 1), 4)))
            else:
                cur = db.one(c, "SELECT * FROM fact_store WHERE store_id=? AND week=?", (s["id"], w)) or {}
                vals = {f: num(get(row, f)) for f in TARGETS["store"]["optional"] if f not in ("week", "date") and f in mapping}
                merged = {f: (vals.get(f) if vals.get(f) is not None else cur.get(f)) for f in TARGETS["store"]["optional"] if f not in ("week", "date")}
                c.execute("INSERT OR REPLACE INTO fact_store VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (s["id"], w, *[merged[f] for f in
                    ["traffic", "transactions", "labor_hours", "labor_budget", "overtime_hours", "csat", "attach_rate", "cash_over_short",
                     "gap_scan_pct", "inv_accuracy", "budget_sales"]]))
            ok += 1
        except Exception as e:
            issue("error", f"line {ln}: {e}")
    c.execute("UPDATE uploads SET status=? WHERE id=?", (f"loaded {ok} rows", up))
    if ok and target in ("sales", "store"):
        feed = "Sales & waste" if target == "sales" else "Store ops & labor"
        thru = db.one(c, "SELECT date(start_date,'+6 day') d FROM weeks WHERE week=?", (max(weeks),))["d"] if weeks else None
        c.execute("INSERT OR REPLACE INTO feeds VALUES(?,?,?,?)", (feed, "daily" if target == "sales" else "weekly", now_iso(), thru))
    c.commit()
    res = dict(ok=True, upload_id=up, loaded=ok, issues=issues, weeks=sorted(weeks))
    if recompute and weeks and target in ("sales", "store"):
        res["recompute"] = run_week(c, max(max(weeks), db.setting(c, "current_week") or 0))
    return res

def run_dropfolder(c, folder):
    """'SFTP-style' file drop connector: sales_*.csv / store_*.csv / missions_*.csv are auto-mapped and loaded."""
    out = []
    os.makedirs(os.path.join(folder, "processed"), exist_ok=True)
    for f in sorted(os.listdir(folder)):
        p = os.path.join(folder, f)
        if not f.endswith(".csv") or not os.path.isfile(p): continue
        target = next((t for t in ("sales", "store", "missions", "stores") if f.startswith(t + "_")), None)
        if not target: out.append(dict(file=f, error="name must start with sales_/store_/missions_/stores_")); continue
        text = open(p, encoding="utf-8-sig").read()
        h, _ = parse(text)
        r = ingest(c, text, target, suggest_mapping(h, target), f)
        shutil.move(p, os.path.join(folder, "processed", f))
        out.append(dict(file=f, target=target, loaded=r.get("loaded"), error=r.get("error")))
    return out

EXPORTS = {
  "missions": """SELECT m.id, s.code store, m.kind, m.kpi, m.title, m.status, m.priority, m.action_type, m.action, m.baseline_gap,
                 m.target_weekly, m.start_week, m.end_week, m.source, u.name owner FROM missions m JOIN stores s ON s.id=m.store_id
                 LEFT JOIN users u ON u.id=m.owner_id ORDER BY m.id""",
  "impact": """SELECT i.mission_id, s.code store, m.kpi, m.title, i.week, ROUND(i.gap,2) gap, ROUND(i.improvement,2) improvement,
               ROUND(i.control_improvement,2) control_improvement, ROUND(i.net,2) net FROM impact i JOIN missions m ON m.id=i.mission_id
               JOIN stores s ON s.id=m.store_id ORDER BY i.mission_id, i.week""",
  "tasks": """SELECT t.id, s.code store, t.title, t.status, t.due, t.completed, t.escalated, t.source, t.answers FROM tasks t
              JOIN stores s ON s.id=t.store_id ORDER BY t.id""",
  "surveys": """SELECT r.id, v.name survey, s.code store, r.week, r.score, r.answers FROM survey_responses r JOIN surveys v ON v.id=r.survey_id
                JOIN stores s ON s.id=r.store_id ORDER BY r.id""",
  "opportunities": """SELECT o.week, s.code store, o.kind, o.kpi, o.title, ROUND(o.actual,2) actual, ROUND(o.expected,2) expected,
                      ROUND(o.gap_value,2) gap, ROUND(o.z,2) z, ROUND(o.score,2) score, o.peer_count, o.prioritized FROM opportunities o
                      JOIN stores s ON s.id=o.store_id WHERE o.week=(SELECT MAX(week) FROM opportunities) ORDER BY o.score DESC""",
}

def export_csv(c, name):
    rows = db.rows(c, EXPORTS[name])
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    return buf.getvalue()
