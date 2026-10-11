"""Self-serve onboarding: blank workspace -> stores CSV -> weekly sales CSV -> (optional) store KPIs -> first missions.
Also generates small, realistic sample CSVs so anyone can try the wizard end to end in a few minutes."""
import csv, io, os, random, datetime as dt, json, time
from . import db

def wipe(path=None):
    p = path or db.DB_PATH
    old = getattr(db._local, "conn", None)
    if old is not None:
        try: old.close()
        except Exception: pass
        db._local.conn = None
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(p + ext): os.remove(p + ext)
    db.GEN[0] += 1
    return db.get()

def blank(company="My retail company", admin_name="HQ admin"):
    c = wipe()
    for k, v in dict(inbox_size=3, max_must_per_quarter=3, require_approval=False, window_weeks=1, currency="USD",
                     mission_duration=4, current_week=0, today=dt.date.today().isoformat(), tenant_kind="blank",
                     company=company, onboarding_started=time.time()).items():
        db.set_setting(c, k, v)
    c.execute("INSERT INTO regions(id,name) VALUES(1,'Region 1')")
    c.execute("INSERT INTO districts(id,name,region_id) VALUES(1,'District 1',1)")
    c.execute("INSERT INTO users(id,name,email,role) VALUES(1,?,?,'hq_admin')", (admin_name, "admin@colstorso-demo.test"))
    return 1

def finish_stores(c):
    """Open every newly uploaded store and create a demo login for each store manager and district manager."""
    c.execute("UPDATE stores SET status='Open' WHERE status='New'")
    made = 0
    for s in db.rows(c, "SELECT * FROM stores"):
        if not db.one(c, "SELECT 1 FROM users WHERE role='store_manager' AND store_id=?", (s["id"],)):
            c.execute("INSERT INTO users(name,email,role,store_id) VALUES(?,?,?,?)", (f"{s['code']} manager", f"{s['code'].lower()}@colstorso-demo.test", "store_manager", s["id"])); made += 1
    for d in db.rows(c, "SELECT * FROM districts"):
        if not db.one(c, "SELECT 1 FROM users WHERE role='district_manager' AND district_id=?", (d["id"],)):
            c.execute("INSERT INTO users(name,email,role,district_id) VALUES(?,?,?,?)", (f"{d['name']} manager", f"dm{d['id']}@colstorso-demo.test", "district_manager", d["id"])); made += 1
    return made

def status(c):
    st = c.execute("SELECT COUNT(*) FROM stores").fetchone()[0]
    opn = c.execute("SELECT COUNT(*) FROM stores WHERE status='Open'").fetchone()[0]
    sw = c.execute("SELECT COUNT(DISTINCT week) FROM fact_sales").fetchone()[0]
    kw = c.execute("SELECT COUNT(DISTINCT week) FROM fact_store").fetchone()[0]
    ms = c.execute("SELECT COUNT(*) FROM missions WHERE kind!='theme'").fetchone()[0]
    t0 = db.setting(c, "onboarding_started")
    return dict(blank=db.setting(c, "tenant_kind") == "blank", company=db.setting(c, "company"), stores=st, open_stores=opn,
                sales_weeks=sw, kpi_weeks=kw, missions=ms, elapsed_min=round((time.time() - t0) / 60, 1) if t0 else None,
                ready=opn >= 4 and sw >= 2)

# ---------- sample files ----------
CATS = {"Grocery": ["Snacks", "Beverages", "Coffee & Tea", "Cereal"], "Fresh": ["Bakery", "Produce", "Dairy"]}
def _stores():
    R = random.Random(3); out = []
    for i in range(1, 17):
        fmt = "Standard" if i <= 10 else "Express"
        out.append(dict(code=f"N{i:03d}", name=f"Sample store {i}", format=fmt, district="North" if i % 2 else "South",
                        tags="has_bakery" if i % 3 else "", base=(9000 if fmt == "Standard" else 4000) * R.uniform(0.85, 1.15)))
    return out

def sample(name):
    S = _stores(); R = random.Random(9); buf = io.StringIO(); w = csv.writer(buf)
    mon = dt.date.today() - dt.timedelta(days=dt.date.today().weekday())
    weeks = [mon - dt.timedelta(days=7 * k) for k in range(8, 0, -1)]
    planted = {("N002", "Coffee & Tea"): 0.55, ("N005", "Bakery"): 0.6, ("N012", "Snacks"): 0.6, ("N007", "Produce"): 0.7}
    if name == "stores":
        w.writerow(["Store Code", "Store Name", "Format", "District", "Tags"])
        for s in S: w.writerow([s["code"], s["name"], s["format"], s["district"], s["tags"]])
    elif name == "sales":
        w.writerow(["Week Start", "Store", "Department", "Sub Category", "Net Sales", "Waste"])
        share = {"Snacks": .3, "Beverages": .3, "Coffee & Tea": .2, "Cereal": .2, "Bakery": .35, "Produce": .4, "Dairy": .25}
        for d in weeks:
            for s in S:
                for dep, cats in CATS.items():
                    for cat in cats:
                        v = s["base"] * share[cat] * (0.6 if dep == "Fresh" else 1) * R.gauss(1, 0.05) * planted.get((s["code"], cat), 1)
                        waste = v * (0.09 if (s["code"] == "N009" and dep == "Fresh") else 0.035 if dep == "Fresh" else 0.005) * R.gauss(1, .1)
                        w.writerow([d.isoformat(), s["code"], dep, cat, round(v, 2), round(waste, 2)])
    elif name == "store":
        w.writerow(["Week Start", "Store", "Footfall", "Transactions", "Hours Worked", "Budget Hours", "Overtime", "CSAT"])
        for d in weeks:
            for s in S:
                tr = s["base"] / 2.2 * R.gauss(1, .04); conv = 0.62 * (0.85 if s["code"] == "N004" else 1) * R.gauss(1, .02)
                bh = s["base"] / 45; hw = bh * (1.12 if s["code"] == "N010" else 1.0) * R.gauss(1, .02)
                w.writerow([d.isoformat(), s["code"], round(tr), round(tr * conv), round(hw, 1), round(bh, 1), round(hw * 0.03, 1), round(R.gauss(82, 2), 1)])
    else:
        raise KeyError(name)
    return buf.getvalue()
