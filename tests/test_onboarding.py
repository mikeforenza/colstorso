"""Self-serve onboarding: blank workspace -> sample CSVs through the mapping wizard -> first missions."""
import os, time
from conftest import H

def _up(client, name, target, uid=1):
    from colstorso import onboarding as OB
    p = client.post("/api/data/preview", files={"file": (f"{name}.csv", OB.sample(name), "text/csv")}, data={"target": target}, headers=H(uid)).json()
    r = client.post("/api/data/ingest", json={"token": p["token"], "target": target, "mapping": p["suggested"], "filename": f"{name}.csv"}, headers=H(uid)).json()
    assert r["ok"], r; return p, r

def test_zz_onboarding_to_first_missions(client):
    t0 = time.time()
    assert client.post("/api/onboarding/blank", json={"company": "Test Co"}, headers=H(1)).json()["ok"]
    st = client.get("/api/onboarding/status", headers=H(1)).json(); assert st["blank"] and st["stores"] == 0
    p, r = _up(client, "stores", "stores"); assert p["suggested"]["code"] == "Store Code" and r["loaded"] == 16
    assert client.post("/api/onboarding/stores_done", headers=H(1)).json()["open_stores"] == 16
    p, r = _up(client, "sales", "sales"); assert set(["store_code", "category", "sales", "date"]) <= set(p["suggested"])
    p, r = _up(client, "store", "store"); assert "traffic" in p["suggested"] and "labor_hours" in p["suggested"]
    out = client.post("/api/onboarding/run", headers=H(1)).json()
    assert out["missions"] > 0 and out["engine_ms"] < 10000
    from colstorso import db
    c = db.get()
    found = {(r["code"], r["title"]) for r in db.rows(c, "SELECT s.code, m.title FROM missions m JOIN stores s ON s.id=m.store_id")}
    assert any(code == "N002" and "Coffee" in t for code, t in found), found
    sm = db.one(c, "SELECT id FROM users WHERE role='store_manager' LIMIT 1")["id"]
    assert client.get("/api/home", headers=H(sm)).status_code == 200
    assert client.get("/api/meta", headers=H(1)).status_code == 200
    assert time.time() - t0 < 60

def test_help_search_and_ask(client):
    a = client.get("/api/help?q=upload csv", headers=H(1)).json()["articles"]
    assert a and a[0]["id"] in ("csv-mapping", "getting-started")
    r = client.post("/api/help/ask", json={"q": "how is impact measured?"}, headers=H(1)).json()
    assert r["articles"][0]["id"] == "impact" and r["sources"]
