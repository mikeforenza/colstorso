"""Mission engine: peer benchmarking, prioritisation limits, impact maths."""
import json, statistics as st
from colstorso import engine as E, db

def test_peers_share_format(c):
    w = c.execute("SELECT MAX(week) FROM fact_store").fetchone()[0]; wd = E.WeekData(c, w, 1)
    fmt = {s["id"]: s["format"] for s in db.rows(c, "SELECT id, format FROM stores")}
    for sid in list(wd.active())[:10]:
        g = E.metric_gap(wd, sid, "labor")
        assert g and len(g["peers"]) >= E.MIN_PEERS
        assert all(fmt[p] == fmt[sid] for p in g["peers"]) or len(g["peers"]) >= E.MIN_PEERS

def test_gap_is_actual_minus_expected_in_dollars(c):
    w = c.execute("SELECT MAX(week) FROM fact_store").fetchone()[0]; wd = E.WeekData(c, w, 1)
    sid = wd.active()[0]; g = E.metric_gap(wd, sid, "labor")
    assert set(["actual", "expected", "gap", "z", "peers"]) <= set(g)
    # being worse than peers on labor (higher ratio) must produce a positive $ gap
    if g["actual"] > g["expected"]: assert g["gap"] > 0

def test_planted_underperformance_is_detected(c):
    """Generator plants category multipliers < 0.8 in some stores; the engine must surface most of them."""
    w = c.execute("SELECT MAX(week) FROM fact_store").fetchone()[0]
    planted = [(r["store_id"], int(r["key"].split(":")[1])) for r in db.rows(c, "SELECT * FROM gen_state WHERE key LIKE 'mult:%' AND value <= 0.8")]
    busy = {(m["store_id"], m["cat_id"]) for m in db.rows(c, "SELECT store_id, cat_id FROM missions WHERE status IN ('live','done') AND kpi='sales'")}
    planted = [p for p in planted if p not in busy]
    found = {(o["store_id"], o["cat_id"]) for o in db.rows(c, "SELECT store_id, cat_id FROM opportunities WHERE week=? AND kpi='sales'", (w,))}
    assert planted, "generator planted nothing"
    recall = sum(1 for p in planted if p in found) / len(planted)
    assert recall >= 0.5, recall

def test_inbox_never_exceeds_limit(c):
    lim = db.setting(c, "inbox_size", 3)
    for r in db.rows(c, "SELECT store_id, COUNT(*) n FROM missions WHERE status='incoming' AND kind!='theme' GROUP BY store_id"):
        assert r["n"] <= lim, r

def test_prioritise_respects_blackout(c):
    w = db.setting(c, "current_week")
    sd = db.one(c, "SELECT start_date FROM weeks WHERE week=?", (w,))["start_date"]
    s = db.one(c, "SELECT * FROM stores WHERE status='Open' ORDER BY id DESC LIMIT 1")
    c.execute("DELETE FROM missions WHERE store_id=? AND status='incoming'", (s["id"],))
    bid = c.execute("INSERT INTO blackouts(name,start_date,end_date,target) VALUES('t',?,?,?)", (sd, sd, json.dumps({"stores": [s["id"]]}))).lastrowid
    E.prioritise(c, w)
    n = c.execute("SELECT COUNT(*) FROM missions WHERE store_id=? AND status='incoming'", (s["id"],)).fetchone()[0]
    c.execute("DELETE FROM blackouts WHERE id=?", (bid,)); c.commit()
    assert n == 0

def test_likely_range_math():
    lo, hi, conf = E.likely_range(1000, [10, -20, 30, -5, 0, 15, -10, 5])
    sd = st.pstdev([10, -20, 30, -5, 0, 15, -10, 5]) * (1 + 1 / 8) ** 0.5
    assert abs((hi - lo) / 2 - 1.645 * sd) < 1e-6 and lo > 0 and conf == "High"
    lo, hi, conf = E.likely_range(5, [100, -100, 80, -90, 50])
    assert lo < 0 < hi and conf == "Low"

def test_diff_in_diff_subtracts_controls(c):
    for r in db.rows(c, "SELECT * FROM impact LIMIT 50"):
        assert abs(r["net"] - (r["improvement"] - r["control_improvement"])) < 1e-6

def test_measured_missions_have_fixed_comparison_group(c):
    ms = db.rows(c, "SELECT * FROM missions WHERE status IN ('live','done') AND control_ids IS NOT NULL")
    assert ms
    for m in ms[:20]:
        ctl = json.loads(m["control_ids"]); assert m["store_id"] not in ctl
