"""End-to-end core loop through the HTTP API: ingest -> missions -> accept/plan -> tasks -> impact, plus guards."""
import io, csv, json
from conftest import H
from colstorso import db, engine as E

def sm(client):
    return next(u for u in client.get("/api/users").json() if u["role"] == "store_manager")

def test_health(client):
    assert client.get("/api/health").json()["ok"]

def test_one_tap_accept_snooze_not_for_us(client):
    u = sm(client)
    inbox = client.get("/api/missions?status=incoming", headers=H(u["id"])).json()
    inbox = [m for m in inbox if m["kind"] != "theme"]
    assert 1 <= len(inbox) <= 3 and all(m["label"] == "Suggested" for m in inbox)
    assert {"effort_min", "confidence"} <= set(inbox[0])
    plan = client.get(f"/api/missions/{inbox[0]['id']}/plan", headers=H(u["id"])).json()
    assert plan["action_type"] and plan["tasks"] and plan["source"]
    r = client.post(f"/api/missions/{inbox[0]['id']}/quick", json={"action": "accept"}, headers=H(u["id"])).json()
    assert r["status"] == "live" and r["label"] == "In progress" and r["action_type"] == plan["action_type"]
    assert json.loads(r["control_ids"]) and r["accepted_at"]
    assert client.get(f"/api/missions/{inbox[0]['id']}", headers=H(u["id"])).json()["tasks"]
    if len(inbox) > 1:
        r = client.post(f"/api/missions/{inbox[1]['id']}/quick", json={"action": "snooze"}, headers=H(u["id"])).json()
        assert r["status"] == "snoozed"
    if len(inbox) > 2:
        r = client.post(f"/api/missions/{inbox[2]['id']}/quick", json={"action": "not_for_us", "reason": "Stock not delivered"}, headers=H(u["id"])).json()
        assert r["label"] == "Not for us"
        pb = client.get("/api/pushback", headers=H(1)).json()
        assert any(x["key"] == "Stock not delivered" for x in pb["by_reason"])

def test_csv_ingest_recomputes_missions(client, c):
    w = db.setting(c, "current_week")
    stores = db.rows(c, "SELECT code FROM stores WHERE status='Open'")
    cats = db.rows(c, "SELECT name FROM categories WHERE parent_id IS NOT NULL")
    last = {(r["store_id"], r["cat_id"]): r["sales"] for r in db.rows(c, "SELECT * FROM fact_sales WHERE week=?", (w,))}
    ids = {s["code"]: s["id"] for s in db.rows(c, "SELECT id, code FROM stores")}
    cid = {x["name"]: x["id"] for x in db.rows(c, "SELECT id, name FROM categories")}
    nxt = db.one(c, "SELECT date(start_date, '+7 day') d FROM weeks WHERE week=?", (w,))["d"]
    buf = io.StringIO(); wr = csv.writer(buf); wr.writerow(["Store", "Sub Category", "Net Sales", "Date"])
    for s in stores:
        for k in cats:
            v = last.get((ids[s["code"]], cid[k["name"]]), 100)
            wr.writerow([s["code"], k["name"], round(v * (0.5 if s["code"] == "S002" and k["name"] == "Snacks" else 1.0), 2), nxt])
    p = client.post("/api/data/preview", files={"file": ("wk.csv", buf.getvalue(), "text/csv")}, data={"target": "sales"}, headers=H(1)).json()
    assert p["suggested"]["store_code"] == "Store" and p["suggested"]["sales"] == "Net Sales"
    mapping = {"store_code": "Store", "category": "Sub Category", "sales": "Net Sales", "date": "Date"}
    r = client.post("/api/data/ingest", json={"token": p["token"], "target": "sales", "mapping": mapping, "filename": "wk.csv"}, headers=H(1)).json()
    assert r["ok"] and r["loaded"] == len(stores) * len(cats) and r["recompute"]["week"] == w + 1
    o = db.rows(db.get(), "SELECT * FROM opportunities WHERE week=? AND store_id=? AND cat_id=?", (w + 1, ids["S002"], cid["Snacks"]))
    assert o, "halved Snacks sales in S002 should be detected"

def test_must_do_campaign_limit(client):
    mx = client.get("/api/meta", headers=H(1)).json()["settings"]["max_must_per_quarter"]
    codes = []
    for i in range(mx + 1):
        codes.append(client.post("/api/campaigns", json={"name": f"Must {i}", "push": "must", "kpis": ["labor"]}, headers=H(1)).status_code)
    assert 400 in codes

def test_ai_answers_cite_sources(client):
    u = sm(client)
    r = client.post("/api/ai/ask", json={"q": "What should I focus on this week?"}, headers=H(u["id"])).json()
    assert r["answer"] and r["sources"]
    m = client.get("/api/missions?status=live", headers=H(u["id"])).json()[0]
    assert client.get(f"/api/ai/explain/{m['id']}", headers=H(u["id"])).json()["sources"]

def test_freshness_states(client):
    f = client.get("/api/freshness", headers=H(1)).json()
    assert {x["cadence"] for x in f} == {"daily", "weekly"} and all(x["state"] == "fresh" for x in f)
    c = db.get(); c.execute("UPDATE feeds SET loaded_at=datetime('now','-40 hours') || '+00:00' WHERE cadence='daily'"); c.commit()
    assert next(x for x in client.get("/api/freshness", headers=H(1)).json() if x["cadence"] == "daily")["state"] == "aging"
    c.execute("UPDATE feeds SET loaded_at=datetime('now','-9 days') || '+00:00' WHERE cadence='weekly'"); c.commit()
    assert next(x for x in client.get("/api/freshness", headers=H(1)).json() if x["cadence"] == "weekly")["state"] == "stale"

def test_scope_is_enforced(client):
    u = sm(client)
    other = db.one(db.get(), "SELECT id FROM missions WHERE store_id!=? LIMIT 1", (u["store_id"],))
    assert client.get(f"/api/missions/{other['id']}", headers=H(u["id"])).status_code in (403, 404)
    assert client.get("/api/home").status_code == 401

def test_rate_limit(monkeypatch, client):
    from colstorso import config, main
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MIN", 5); main._hits.clear()
    codes = [client.get("/api/meta", headers=H(1)).status_code for _ in range(8)]
    main._hits.clear()
    assert 429 in codes
