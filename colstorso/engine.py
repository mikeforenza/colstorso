"""Mission engine: peer benchmarking, opportunity scoring, prioritisation, impact measurement.

Method (original implementation of a common retail-analytics approach):
* Peer set   – same format, open stores; for category KPIs also similar space allocation
               (|space share diff| <= SPACE_TOL, falling back to the nearest stores by space).
* Normalise  – compare *share of parent* (e.g. Dog Food / Pet) so traffic, size, weather and holidays that
               move the whole department cancel out. Expected = peer mean share x my parent sales.
* Gap ($/wk) – expected - actual (or KPI-specific dollarisation for store KPIs).
* Score      – gap x confidence(z) x campaign boost x learned-effectiveness x substitution penalty.
* Inbox      – top-N per store per week, diversified, suppressing live/snoozed items, blackouts,
               and throttled when the store is at capacity (workload balancing).
* Impact     – gap closed since launch minus the average gap change of untreated control stores
               (difference-in-differences), measured weekly, with post-mission erosion tracking.
"""
import math, json, statistics as stats, datetime as dt
from collections import defaultdict
from . import db
from .playbook import KPIS

SPACE_TOL = 0.04
MIN_PEERS = 5
WAGE, OT_PREMIUM = 19.0, 9.5
MIN_GAP = 120.0

class WeekData:
    """In-memory snapshot of one week (optionally averaged over a window)."""
    def __init__(self, c, week, window=1):
        self.week = week
        wk = (week - window + 1, week)
        self.stores = {s["id"]: s for s in db.rows(c, "SELECT * FROM stores")}
        cats = db.rows(c, "SELECT * FROM categories")
        self.cat = {x["id"]: x for x in cats}
        self.parent = {x["id"]: x["parent_id"] for x in cats}
        self.children = defaultdict(list)
        for x in cats:
            if x["parent_id"]: self.children[x["parent_id"]].append(x["id"])
        self.space = {(r["store_id"], r["cat_id"]): r["share"] for r in db.rows(c, "SELECT * FROM space")}
        n = max(1, window)
        self.sales, self.waste = defaultdict(float), defaultdict(float)
        for r in c.execute("SELECT store_id,cat_id,SUM(sales),SUM(waste) FROM fact_sales WHERE week BETWEEN ? AND ? GROUP BY store_id,cat_id", wk):
            self.sales[(r[0], r[1])] = r[2] / n; self.waste[(r[0], r[1])] = r[3] / n
        self.dept_sales, self.dept_waste, self.total = defaultdict(float), defaultdict(float), defaultdict(float)
        for (s, cid), v in list(self.sales.items()):
            p = self.parent.get(cid)
            if p:
                self.dept_sales[(s, p)] += v; self.dept_waste[(s, p)] += self.waste[(s, cid)]; self.total[s] += v
        self.m = {}
        for r in db.rows(c, """SELECT store_id, AVG(traffic) traffic, AVG(transactions) trans, AVG(labor_hours) hours,
              AVG(labor_budget) budget, AVG(overtime_hours) ot, AVG(csat) csat, AVG(attach_rate) attach,
              AVG(cash_over_short) cash, AVG(gap_scan_pct) gapscan, AVG(inv_accuracy) invacc, AVG(budget_sales) bsales
              FROM fact_store WHERE week BETWEEN ? AND ? GROUP BY store_id""", wk):
            sid = r["store_id"]
            for k_ in ("traffic", "trans", "hours", "budget", "ot", "csat", "attach", "cash", "gapscan", "invacc", "bsales"):
                if r[k_] is None: r[k_] = 0.0
            r["conversion"] = r["trans"] / r["traffic"] if r["traffic"] else 0
            r["labor"] = r["hours"] / r["budget"] if r["budget"] else 1
            r["overtime"] = r["ot"] / r["hours"] if r["hours"] else 0
            r["atv"] = self.total[sid] / r["trans"] if r["trans"] else 0
            self.m[sid] = r

    def active(self):
        # a store is benchmarkable this week if it reported sales or store KPIs (feeds can arrive separately)
        if not hasattr(self, "_act"):
            self._act = [s for s, v in self.stores.items() if v["status"] == "Open" and (s in self.m or self.total.get(s))]
        return self._act

    def peers(self, sid, cat=None):
        f = self.stores[sid]["format"]
        cand = [s for s in self.active() if s != sid and self.stores[s]["format"] == f]
        if cat is None: return [s for s in cand if s in self.m]
        if self.cat.get(cat, {}).get("parent_id") is None: return cand
        mine = self.space.get((sid, cat))
        if mine is None: return cand
        close = [s for s in cand if abs(self.space.get((s, cat), -9) - mine) <= SPACE_TOL]
        if len(close) >= MIN_PEERS: return close
        return sorted(cand, key=lambda s: abs(self.space.get((s, cat), 9) - mine))[:max(MIN_PEERS, 8)]

def _z(mine, vals, higher_is_better=True):
    if len(vals) < 2: return 0.0
    mu, sd = stats.mean(vals), stats.pstdev(vals) or 1e-9
    return ((mu - mine) if higher_is_better else (mine - mu)) / sd

def metric_gap(wd, sid, kpi, cat=None):
    """Return dict(actual, expected, gap($/wk, positive = opportunity), z, peers, scaler) or None."""
    if kpi not in ("sales", "waste") and sid not in wd.m: return None
    m = wd.m.get(sid, {})
    if kpi == "sales":
        p = wd.parent.get(cat)
        if not p: return None
        ps = wd.dept_sales[(sid, p)]
        if ps <= 0: return None
        share = wd.sales[(sid, cat)] / ps
        peers = [s for s in wd.peers(sid, cat) if wd.dept_sales[(s, p)] > 0]
        vals = [wd.sales[(s, cat)] / wd.dept_sales[(s, p)] for s in peers]
        if len(vals) < 3: return None
        exp_share = stats.mean(vals)
        return dict(actual=wd.sales[(sid, cat)], expected=exp_share * ps, gap=(exp_share - share) * ps,
                    z=_z(share, vals), peers=peers, share=share, peer_share=exp_share,
                    quart=_quartiles([v * ps for v in vals]),
                    scaler=f"{wd.cat[cat]['name']} as share of {wd.cat[p]['name']} sales")
    if kpi == "waste":
        d = cat
        ds = wd.dept_sales[(sid, d)]
        if ds <= 0: return None
        r = wd.dept_waste[(sid, d)] / ds
        peers = [s for s in wd.peers(sid, d) if wd.dept_sales[(s, d)] > 0]
        vals = [wd.dept_waste[(s, d)] / wd.dept_sales[(s, d)] for s in peers]
        if len(vals) < 3: return None
        mu = stats.mean(vals)
        return dict(actual=r * 100, expected=mu * 100, gap=(r - mu) * ds, z=_z(r, vals, False), peers=peers,
                    quart=_quartiles([v * 100 for v in vals]), scaler=f"waste as % of {wd.cat[d]['name']} sales")
    peers = [s for s in wd.peers(sid)]
    pm = [wd.m[s] for s in peers]
    if len(pm) < 3: return None
    T = wd.total[sid]
    def pack(act, vals, gap, hib, scale=100, scaler=""):
        return dict(actual=act * scale, expected=stats.mean(vals) * scale, gap=gap, z=_z(act, vals, hib), peers=peers,
                    quart=_quartiles([v * scale for v in vals]), scaler=scaler)
    if kpi == "labor":
        vals = [x["labor"] for x in pm]
        return pack(m["labor"], vals, (m["hours"] - m["budget"]) * WAGE, False, scaler="worked / budgeted hours")
    if kpi == "overtime":
        vals = [x["overtime"] for x in pm]
        return pack(m["overtime"], vals, (m["overtime"] - stats.mean(vals)) * m["hours"] * OT_PREMIUM, False,
                    scaler="overtime as % of worked hours")
    if kpi == "conversion":
        vals = [x["conversion"] for x in pm]
        return pack(m["conversion"], vals, (stats.mean(vals) - m["conversion"]) * m["traffic"] * m["atv"], True,
                    scaler="transactions / traffic, same format")
    if kpi == "csat":
        vals = [x["csat"] for x in pm]
        return pack(m["csat"], vals, (stats.mean(vals) - m["csat"]) * T * 0.0015, True, scale=1,
                    scaler="CSAT points, same format")
    if kpi == "attach":
        vals = [x["attach"] for x in pm]
        return pack(m["attach"], vals, (stats.mean(vals) - m["attach"]) * m["trans"] * 6.0, True,
                    scaler="baskets with add-on, same format")
    if kpi == "invacc":
        vals = [x["invacc"] for x in pm]
        return pack(m["invacc"], vals, (stats.mean(vals) - m["invacc"]) * T * 0.3, True,
                    scaler="inventory accuracy, same format")
    if kpi == "gapscan":
        vals = [x["gapscan"] for x in pm]
        return pack(m["gapscan"], vals, (stats.mean(vals) - m["gapscan"]) * T * 0.03, True,
                    scaler="gap scans completed, same format")
    if kpi == "cash":
        vals = [abs(x["cash"]) for x in pm]
        return pack(abs(m["cash"]), vals, abs(m["cash"]) - stats.mean(vals), False, scale=1, scaler="absolute till variance")
    return None

def _quartiles(vals):
    if len(vals) < 4: v = sorted(vals); return [v[0], v[0], v[-1], v[-1]] if v else [0, 0, 0, 0]
    q = stats.quantiles(vals, n=4)
    return [min(vals), q[0], q[1], q[2], max(vals)]

def confidence(z):
    return 1 - math.exp(-max(z, 0) / 1.5)

STORE_KPIS = ["labor", "overtime", "conversion", "csat", "attach", "invacc", "gapscan"]

def learned_multiplier(c):
    """Effectiveness learned from closed missions: KPI types whose missions deliver get boosted."""
    out = {}
    for r in db.rows(c, """SELECT m.kpi, AVG(CASE WHEN i.net>0 THEN 1.0 ELSE 0.0 END) sr, COUNT(*) n
                         FROM missions m JOIN (SELECT mission_id, SUM(net) net FROM impact GROUP BY mission_id) i
                         ON i.mission_id=m.id WHERE m.status IN ('live','done') GROUP BY m.kpi"""):
        out[r["kpi"]] = 0.85 + 0.3 * r["sr"] if r["n"] >= 3 else 1.0
    return out

def store_matches(store, target):
    if not target: return True
    tags = db.J(store.get("tags"), []) if isinstance(store.get("tags"), str) else store.get("tags", [])
    if target.get("stores") and store["id"] not in target["stores"]: return False
    if target.get("formats") and store["format"] not in target["formats"]: return False
    if target.get("districts") and store["district_id"] not in target["districts"]: return False
    if target.get("regions") and store.get("region_id") not in target["regions"]: return False
    if target.get("tags") and not set(target["tags"]) & set(tags): return False
    return True

def active_campaigns(c, week):
    return [dict(x, kpis=db.J(x["kpis"], []), categories=db.J(x["categories"], []), target=db.J(x["target"], {}), holdout=db.J(x.get("holdout"), []))
            for x in db.rows(c, "SELECT * FROM campaigns WHERE active=1 AND start_week<=? AND end_week>=?", (week, week))]

def store_rows(c):
    return {s["id"]: dict(s, region_id=db.one(c, "SELECT region_id FROM districts WHERE id=?", (s["district_id"],))["region_id"])
            for s in db.rows(c, "SELECT * FROM stores")}

def sibling_gain(wd, sid, cat, dept):
    """$ that sibling categories sell ABOVE what peers' share-of-total-sales predicts. Measured against store total (not the
    department) so one category's loss doesn't mechanically inflate its siblings' shares."""
    if not wd.total.get(sid): return 0.0
    gain = 0.0
    for sib in wd.children[dept]:
        if sib == cat: continue
        base = lambda s: wd.total.get(s, 0) - wd.sales[(s, cat)]      # total excluding the focal category
        peers = [s for s in wd.peers(sid, sib) if base(s) > 0]
        if len(peers) < 3 or base(sid) <= 0: continue
        mu = stats.mean(wd.sales[(s, sib)] / base(s) for s in peers)
        gain += max(0.0, wd.sales[(sid, sib)] - mu * base(sid))
    return gain

def dept_shortfall(wd, sid, dept):
    """$ the department is below where its peers' department share of total sales says it should be (positive = short)."""
    peers = [s for s in wd.peers(sid, dept) if wd.total.get(s)]
    if len(peers) < 3 or not wd.total.get(sid): return 0.0
    mu = stats.mean(wd.dept_sales[(s, dept)] / wd.total[s] for s in peers)
    return mu * wd.total[sid] - wd.dept_sales[(sid, dept)]

def compute_opportunities(c, week, window=None, persist=True):
    window = window or db.setting(c, "window_weeks", 1)
    wd = WeekData(c, week, window)
    learned = learned_multiplier(c)
    camps = active_campaigns(c, week)
    S = store_rows(c)
    out = []
    for sid in wd.active():
        cands = []
        for cat, p in wd.parent.items():
            if not p: continue
            g = metric_gap(wd, sid, "sales", cat)
            if g and g["gap"] > MIN_GAP and g["z"] > 0.8:
                # substitution test: if the whole department is NOT short by roughly this gap, shoppers bought sibling
                # categories instead – the money isn't lost, so the mission is deprioritised.
                subst = 1 if sibling_gain(wd, sid, cat, p) >= 0.6 * g["gap"] and wd.cat[cat]["name"] != "Hot Drinks Bar" else 0
                cands.append(("sales", cat, "opportunity", f"{wd.cat[cat]['name']} sales below peers", g, subst))
        for d in [k for k, v in wd.parent.items() if v is None]:
            g = metric_gap(wd, sid, "waste", d)
            if g and g["gap"] > MIN_GAP and g["z"] > 1.0:
                cands.append(("waste", d, "opportunity", f"{wd.cat[d]['name']} waste above peers", g, 0))
        for k in STORE_KPIS:
            g = metric_gap(wd, sid, k)
            if g and g["gap"] > MIN_GAP and g["z"] > 1.0:
                cands.append((k, None, "opportunity", {"labor": "Labor hours over budget", "overtime": "Excess overtime hours",
                    "conversion": "Conversion below peers", "csat": "Customer satisfaction below peers",
                    "attach": "Attachment rate below peers", "invacc": "Phantom inventory risk",
                    "gapscan": "Gap-scan compliance below standard"}[k], g, 0))
        for kpi, cat, kind, title, g, subst in cands:
            boost, camp = 1.0, None
            for cp in camps:
                if store_matches(S[sid], cp["target"]) and sid not in cp["holdout"] and (kpi in cp["kpis"] or (cat and (cat in cp["categories"] or wd.parent.get(cat) in cp["categories"]))):
                    boost, camp = max(boost, cp["boost"]), cp["id"]
            score = g["gap"] * confidence(g["z"]) * boost * learned.get(kpi, 1.0) * (0.35 if subst else 1.0)
            out.append(dict(week=week, store_id=sid, kpi=kpi, cat_id=cat, kind=kind, title=title, actual=g["actual"],
                            expected=g["expected"], gap_value=g["gap"], z=g["z"], score=score, peer_count=len(g["peers"]),
                            scaler=g["scaler"], substitution=subst,
                            detail=json.dumps({"campaign_id": camp, "boost": boost, "quart": g.get("quart"),
                                               "learned": learned.get(kpi, 1.0)})))
    out += anomaly_alerts(c, wd)
    out += rule_alerts(c, wd)
    if persist:
        c.execute("DELETE FROM opportunities WHERE week=?", (week,))
        for o in out:
            cols = ",".join(o.keys())
            c.execute(f"INSERT INTO opportunities({cols}) VALUES({','.join('?' * len(o))})", tuple(o.values()))
        c.commit()
    return out

def anomaly_alerts(c, wd):
    """Equipment / sudden-drop detection vs the store's own 8-week run rate."""
    out = []
    w = wd.week
    hist = defaultdict(list)
    for r in c.execute("SELECT store_id,cat_id,sales FROM fact_sales WHERE week BETWEEN ? AND ?", (w - 8, w - 1)):
        hist[(r[0], r[1])].append(r[2])
    for (sid, cat), vals in hist.items():
        if sid not in wd.m or len(vals) < 4 or not wd.parent.get(cat): continue
        mu = stats.mean(vals); now = wd.sales.get((sid, cat), 0)
        if mu > 300 and now < 0.25 * mu:
            out.append(dict(week=w, store_id=sid, kpi="equipment", cat_id=cat, kind="alert",
                            title=f"{wd.cat[cat]['name']}: sales stopped – possible equipment outage", actual=now,
                            expected=mu, gap_value=mu - now, z=5, score=(mu - now) * 1.5, peer_count=0,
                            scaler="own 8-week run-rate", substitution=0, detail=json.dumps({"priority": "Must"})))
    return out

RULE_METRICS = {"labor_ratio": ("labor", 100), "overtime_pct": ("overtime", 100), "conversion_pct": ("conversion", 100),
                "csat": ("csat", 1), "attach_pct": ("attach", 100), "cash_abs": ("cash", 1), "gapscan_pct": ("gapscan", 100),
                "invacc_pct": ("invacc", 100), "sales_vs_budget_pct": (None, 100)}

def store_metric(wd, sid, metric):
    m = wd.m.get(sid)
    if not m: return None
    if metric == "cash_abs": return abs(m["cash"])
    if metric == "sales_vs_budget_pct": return wd.total[sid] / m["bsales"] * 100 if m["bsales"] else None
    if metric.startswith("waste_pct:"):
        d = int(metric.split(":")[1]); ds = wd.dept_sales[(sid, d)]
        return wd.dept_waste[(sid, d)] / ds * 100 if ds else None
    k, sc = RULE_METRICS.get(metric, (None, None))
    return m[k] * sc if k else None

def cmp(v, op, t):
    return {"<": v < t, "<=": v <= t, ">": v > t, ">=": v >= t, "==": v == t}.get(op, False)

def rule_alerts(c, wd):
    """No-code mission builder rules (condition triggers)."""
    out = []
    S = store_rows(c)
    for r in db.rows(c, "SELECT * FROM mission_rules WHERE active=1 AND trigger_type='condition'"):
        tgt = db.J(r["target"], {})
        for sid in wd.active():
            if not store_matches(S[sid], tgt): continue
            v = store_metric(wd, sid, r["metric"])
            if v is None or not cmp(v, r["op"], r["threshold"]): continue
            kpi = RULE_METRICS.get(r["metric"], ("custom", 1))[0] or "custom"
            out.append(dict(week=wd.week, store_id=sid, kpi=kpi, cat_id=None, kind=r["kind"] or "alert",
                            title=r["title"].replace("{value}", f"{v:,.1f}"), actual=v, expected=r["threshold"],
                            gap_value=abs(v - r["threshold"]), z=3, score=1e6, peer_count=0,
                            scaler=f"rule: {r['metric']} {r['op']} {r['threshold']}", substitution=0,
                            detail=json.dumps({"rule_id": r["id"], "priority": r["priority"], "guidance": r["guidance"],
                                               "assignee_role": r["assignee_role"]})))
    return out

# ---------- prioritisation ----------
def in_blackout(c, store, date_iso):
    for b in db.rows(c, "SELECT * FROM blackouts"):
        if b["start_date"] <= date_iso <= b["end_date"] and store_matches(store, db.J(b["target"], {})): return b
    return None

def store_load_hours(c, sid):
    t = c.execute("SELECT COALESCE(SUM(est_minutes),0) FROM tasks WHERE store_id=? AND status='open'", (sid,)).fetchone()[0] / 60
    m = c.execute("SELECT COUNT(*) FROM missions WHERE store_id=? AND status IN ('incoming','prelaunch','proposed','live')", (sid,)).fetchone()[0]
    return round(t + 1.5 * m, 1)

def capacity_status(c):
    out = []
    for s in db.rows(c, "SELECT * FROM stores WHERE status='Open'"):
        load = store_load_hours(c, s["id"]); cap = s["capacity_hours"] * 0.5
        out.append(dict(store_id=s["id"], code=s["code"], name=s["name"], load=load, capacity=cap,
                        pct=round(load / cap * 100) if cap else 0, at_capacity=load >= cap))
    return out

def prioritise(c, week, inbox_size=None):
    inbox_size = inbox_size or db.setting(c, "inbox_size", 4)
    wstart = db.one(c, "SELECT start_date FROM weeks WHERE week=?", (week,))
    wdate = wstart["start_date"] if wstart else dt.date.today().isoformat()
    S = store_rows(c)
    managers = {u["store_id"]: u["id"] for u in db.rows(c, "SELECT * FROM users WHERE role='store_manager' AND active=1")}
    sent = 0; protected = []
    for sid, st in S.items():
        if st["status"] != "Open": continue
        if in_blackout(c, st, wdate): continue
        opps = db.rows(c, "SELECT * FROM opportunities WHERE week=? AND store_id=? ORDER BY score DESC", (week, sid))
        blocked = set()
        for m in db.rows(c, """SELECT kpi, cat_id FROM missions WHERE store_id=? AND (status IN ('incoming','prelaunch','proposed','live','snoozed')
                               OR (status='rejected' AND COALESCE(snooze_until,0)>=?))""", (sid, week)):
            blocked.add((m["kpi"], m["cat_id"]))
        load = store_load_hours(c, sid); cap = st["capacity_hours"] * 0.5
        n = inbox_size if load < cap else max(1, inbox_size // 2)
        existing = c.execute("SELECT COUNT(*) FROM missions WHERE store_id=? AND status='incoming' AND kind!='theme'", (sid,)).fetchone()[0]
        n = max(0, n - existing)
        musts = {cp["id"] for cp in active_campaigns(c, week) if cp.get("push") == "must"}
        opps.sort(key=lambda o: (0 if o["kind"] == "alert" else 1 if db.J(o["detail"], {}).get("campaign_id") in musts else 2, -o["score"]))
        if load >= cap: protected.append(sid)
        per_kpi = defaultdict(int); chosen = []
        for o in opps:
            key = (o["kpi"], o["cat_id"])
            if key in blocked: continue
            det = db.J(o["detail"], {})
            if len(chosen) >= n: break
            if o["kind"] == "alert":
                chosen.append((o, det.get("priority", "Must"))); blocked.add(key); continue
            if per_kpi[o["kpi"]] >= 2: continue
            if o["substitution"]: continue
            per_kpi[o["kpi"]] += 1; blocked.add(key)
            chosen.append((o, "Must" if det.get("campaign_id") in musts or not [x for x in chosen if x[0]["kind"] != "alert"] else "Should"))
        for o, pr in chosen:
            det = db.J(o["detail"], {})
            owner = managers.get(sid)
            if det.get("assignee_role") == "district_manager":
                d = db.one(c, "SELECT id FROM users WHERE role='district_manager' AND district_id=?", (st["district_id"],))
                owner = d["id"] if d else owner
            create_mission(c, dict(opp_id=o["id"], store_id=sid, owner_id=owner, kind=o["kind"], kpi=o["kpi"],
                                   cat_id=o["cat_id"], title=o["title"], status="incoming", baseline_gap=o["gap_value"],
                                   target_weekly=round(max(o["gap_value"], 0), 2), campaign_id=det.get("campaign_id"),
                                   source="engine" if o["kind"] != "alert" else ("rule" if det.get("rule_id") else "anomaly"),
                                   created_week=week, priority=pr, due_week=week, comment=det.get("guidance")))
            c.execute("UPDATE opportunities SET prioritized=1 WHERE id=?", (o["id"],)); sent += 1
    c.commit()
    return dict(sent=sent, protected=protected)

def now_iso():
    return dt.datetime.now().replace(microsecond=0).isoformat()

def create_mission(c, m):
    m.setdefault("created_at", now_iso())
    cols = ",".join(m.keys())
    cur = c.execute(f"INSERT INTO missions({cols}) VALUES({','.join('?' * len(m))})", tuple(m.values()))
    mid = cur.lastrowid
    log(c, "mission", mid, m.get("created_by"), "created", m.get("source", ""))
    if m.get("owner_id"):
        notify(c, m["owner_id"], f"New mission: {m['title']}", f"#/mission/{mid}")
    return mid

def log(c, entity, eid, uid, action, detail=""):
    c.execute("INSERT INTO activity(entity,entity_id,user_id,action,detail,ts) VALUES(?,?,?,?,?,?)",
              (entity, eid, uid, action, detail, now_iso()))

def notify(c, uid, text, link=""):
    c.execute("INSERT INTO notifications(user_id,text,link,ts) VALUES(?,?,?,?)", (uid, text, link, now_iso()))

# ---------- impact ----------
def mission_gap(wd, m):
    g = metric_gap(wd, m["store_id"], m["kpi"], m["cat_id"]) if m["kpi"] in ("sales", "waste", *STORE_KPIS, "cash") else None
    if g is None and m["kpi"] == "equipment":
        return None
    return g

def measure_impact(c, upto_week):
    """Weekly difference-in-differences for every launched mission; archives at end of duration."""
    ms = db.rows(c, "SELECT * FROM missions WHERE status IN ('live','done') AND start_week IS NOT NULL")
    cache = {}
    def W(w):
        if w not in cache: cache[w] = WeekData(c, w, 1)
        return cache[w]
    treated = defaultdict(set)
    for m in ms: treated[(m["kpi"], m["cat_id"])].add(m["store_id"])
    for m in ms:
        if m["kpi"] not in ("sales", "waste", "cash", *STORE_KPIS): continue
        base_w = m["start_week"] - 1
        if base_w < 1: continue
        b = metric_gap(W(base_w), m["store_id"], m["kpi"], m["cat_id"])
        if not b: continue
        if m.get("control_ids"):
            controls = db.J(m["control_ids"], [])          # comparison group fixed at accept
        else:
            controls = [s for s in b["peers"] if s not in treated[(m["kpi"], m["cat_id"])]][:12]
            c.execute("UPDATE missions SET control_ids=? WHERE id=?", (json.dumps(controls), m["id"]))
        ccum = defaultdict(float)
        cb = {s: (metric_gap(W(base_w), s, m["kpi"], m["cat_id"]) or {}).get("gap") for s in controls}
        last = min(upto_week, (m["end_week"] or upto_week) + 8)
        for w in range(m["start_week"], last + 1):
            if w not in [r["week"] for r in db.rows(c, "SELECT week FROM weeks WHERE week=?", (w,))]: break
            g = metric_gap(W(w), m["store_id"], m["kpi"], m["cat_id"])
            if not g: continue
            imp = b["gap"] - g["gap"]
            ci = []
            for s in controls:
                if cb.get(s) is None: continue
                v = cb[s] - (metric_gap(W(w), s, m["kpi"], m["cat_id"]) or {}).get("gap", cb[s]); ci.append(v)
                if w <= (m["end_week"] or w): ccum[s] += v
            cimp = stats.mean(ci) if ci else 0.0
            c.execute("INSERT OR REPLACE INTO impact VALUES(?,?,?,?,?,?)", (m["id"], w, g["gap"], imp, cimp, imp - cimp))
        c.execute("UPDATE missions SET impact_detail=? WHERE id=?", (json.dumps({"control_cum": [round(v, 2) for v in ccum.values()], "n_controls": len(controls)}), m["id"]))
        if m["status"] == "live" and m["end_week"] and upto_week > m["end_week"]:
            c.execute("UPDATE missions SET status='done' WHERE id=?", (m["id"],))
            log(c, "mission", m["id"], None, "done", "duration ended")
    c.commit()

def mission_impact_summary(c, mid):
    m = db.one(c, "SELECT * FROM missions WHERE id=?", (mid,))
    rows = db.rows(c, "SELECT * FROM impact WHERE mission_id=? ORDER BY week", (mid,))
    if not m or not rows: return dict(weeks=[], cumulative=0, latest=0, status="grey", erosion=0, low=0, high=0, weekly=0,
                                      weekly_low=0, weekly_high=0, confidence=None, weeks_measured=0, baseline=(m or {}).get("baseline_gap"),
                                      n_controls=len(db.J((m or {}).get("control_ids"), [])))
    end = m["end_week"] or 10**6
    during = [r for r in rows if r["week"] <= end]; after = [r for r in rows if r["week"] > end]
    cum = sum(r["net"] for r in during)
    latest = during[-1]["net"] if during else 0
    erosion = (latest - after[-1]["net"]) if after else 0
    lo, hi, conf = likely_range(cum, db.J(m.get("impact_detail"), {}).get("control_cum", []))
    nwk = max(len(during), 1)
    status = "green" if lo > 0 else ("red" if hi < 0 else "grey")
    return dict(weeks=rows, cumulative=round(cum, 2), latest=round(latest, 2), status=status, erosion=round(erosion, 2),
                baseline=m["baseline_gap"], low=round(lo, 2), high=round(hi, 2), weekly=round(cum / nwk, 2),
                weekly_low=round(lo / nwk, 2), weekly_high=round(hi / nwk, 2), confidence=conf, weeks_measured=len(during),
                n_controls=len(db.J(m.get("control_ids"), [])))

def likely_range(point, control_cums, level=0.90):
    """Placebo-based interval: spread of the comparison stores' own cumulative changes around their mean tells us how much a
    store moves with no mission. 90% range = point ± 1.645·sd·sqrt(1+1/n). Falls back to ±50% when there are <3 controls."""
    n = len(control_cums)
    if n < 3: return point - abs(point) * 0.5, point + abs(point) * 0.5, "Low"
    sd = stats.pstdev(control_cums) * (1 + 1 / n) ** 0.5
    half = 1.645 * sd
    lo, hi = point - half, point + half
    conf = "High" if (lo > 0 or hi < 0) and abs(point) > 2 * half else ("Medium" if lo > 0 or hi < 0 else "Low")
    return lo, hi, conf

def run_week(c, week):
    """Full weekly pipeline after a data load."""
    from . import tasks as T, ai
    db.set_setting(c, "current_week", week)
    c.execute("UPDATE missions SET status='incoming' WHERE status='snoozed' AND COALESCE(snooze_until,0)<=?", (week,))
    opps = compute_opportunities(c, week)
    measure_impact(c, week)
    T.run_condition_rules(c, week)
    T.run_schedule_rules(c, week)
    T.escalate(c)
    ai.extract_themes(c, week)
    pr = prioritise(c, week)
    c.commit()
    return dict(week=week, opportunities=len(opps), **pr)
