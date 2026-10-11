"""Synthetic multi-store retail dataset generator (fully fictional data)."""
import random, math, json, datetime as dt
from . import db

FORMATS = {"Superstore": dict(base=420000, atv=58, conv=0.52, prod=175, cap=60),
           "Standard": dict(base=210000, atv=41, conv=0.61, prod=160, cap=45),
           "Express": dict(base=85000, atv=17, conv=0.83, prod=140, cap=30)}
DEPTS = {
  "Grocery": ["Snacks", "Beverages", "Cereal & Breakfast", "Canned & Dry", "Coffee & Tea"],
  "Fresh": ["Produce", "Bakery", "Deli", "Meat & Seafood", "Hot Drinks Bar"],
  "Household": ["Cleaning", "Paper Goods", "Laundry", "Kitchenware"],
  "Health & Beauty": ["Personal Care", "OTC Health", "Cosmetics", "Vitamins"],
  "Pet": ["Dog Food", "Cat Food", "Pet Accessories"],
  "Seasonal": ["Outdoor & Garden", "Toys", "Electronics Accessories", "Party & Gifts"],
}
DEPT_MIX = {"Superstore": [.30, .26, .13, .11, .08, .12], "Standard": [.33, .27, .13, .11, .07, .09],
            "Express": [.42, .33, .09, .08, .04, .04]}
CITIES = ["Maple Grove", "Riverside", "Oak Hill", "Cedar Falls", "Lakeview", "Brookfield", "Fairview", "Westport",
  "Springdale", "Ashford", "Kingsbridge", "Millbrook", "Northgate", "Elmwood", "Harborview", "Pine Ridge", "Stonebridge",
  "Clearwater", "Highland Park", "Greenfield", "Summit", "Bayside", "Willow Creek", "Granite City", "Foxborough",
  "Hollis", "Redwood", "Silver Lake", "Thornbury", "Upton", "Vale", "Whitby", "Yarrow", "Zephyr Hills", "Amberly",
  "Belmont", "Carver", "Dunmore", "Easton", "Fulton", "Garrison", "Hampton", "Irvington", "Jasper", "Kendall",
  "Lancaster", "Monroe", "Newport", "Orchard Park", "Preston"]
FIRST = ["Alex", "Jordan", "Sam", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Avery", "Quinn", "Drew", "Reese",
  "Parker", "Rowan", "Skyler", "Emerson", "Hayden", "Kendall", "Logan", "Marley", "Noel", "Peyton", "Sage", "Toby"]
LAST = ["Nguyen", "Patel", "Garcia", "Okafor", "Kim", "Silva", "Novak", "Haddad", "Brennan", "Moreau", "Larsen",
  "Ito", "Rossi", "Mensah", "Kowalski", "Duarte", "Fischer", "Abara", "Lindqvist", "Reyes", "Castillo", "Doyle"]
N_WEEKS = 52
CURRENT_WEEK_START = dt.date(2026, 10, 5)  # Monday of week 52

def week_start(w):
    return (CURRENT_WEEK_START - dt.timedelta(days=7 * (N_WEEKS - w))).isoformat()

def seasonal(dept, w):
    s = 1 + 0.04 * math.sin(2 * math.pi * (w - 10) / 52)
    if dept == "Seasonal": s *= 1 + 0.35 * math.sin(2 * math.pi * (w - 1) / 52)
    if dept == "Fresh": s *= 1 + 0.06 * math.sin(2 * math.pi * (w - 5) / 52)
    if w in (8, 9): s *= 1.12  # a holiday spike hitting all stores
    return s

class Gen:
    def __init__(self, c, seed=42):
        self.c, self.rng = c, random.Random(seed)

    def state(self, sid, key, default):
        r = self.c.execute("SELECT value FROM gen_state WHERE store_id=? AND key=?", (sid, key)).fetchone()
        return r[0] if r else default

    def set_state(self, sid, key, v):
        self.c.execute("INSERT OR REPLACE INTO gen_state VALUES(?,?,?)", (sid, key, v))

    def build_master(self, n_stores=50):
        c, R = self.c, self.rng
        for t in ["regions", "districts", "stores", "users", "categories", "space", "weeks", "gen_state", "dcs"]:
            c.execute(f"DELETE FROM {t}")
        regs = ["North", "South"]
        for i, r in enumerate(regs, 1): c.execute("INSERT INTO regions VALUES(?,?)", (i, r))
        dnames = ["Lakes", "Metro North", "Valley", "Coastal", "Metro South", "Hills"]
        for i, d in enumerate(dnames, 1): c.execute("INSERT INTO districts VALUES(?,?,?)", (i, d, 1 if i <= 3 else 2))
        fmts = (["Superstore"] * 12 + ["Standard"] * 25 + ["Express"] * 13)[:n_stores]
        R.shuffle(fmts)
        for i in range(1, n_stores + 1):
            f = fmts[i - 1]
            tags = []
            if R.random() < .25: tags.append("High Shrink Watch")
            if R.random() < .3: tags.append("Near Campus")
            if R.random() < .3: tags.append("Tourist Area")
            if f != "Express" and R.random() < .5: tags.append("Pharmacy")
            tags.append("Hot Drinks Bar")
            city = CITIES[(i - 1) % len(CITIES)]
            c.execute("INSERT INTO stores(id,code,name,district_id,format,sqft,status,tags,capacity_hours,city,lat,lon) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (i, f"S{i:03d}", f"{city} {f}", (i - 1) % 6 + 1, f,
                       {"Superstore": 90000, "Standard": 45000, "Express": 6000}[f] + R.randint(-4000, 4000), "Open",
                       json.dumps(tags), FORMATS[f]["cap"], city, 40 + R.random() * 3, -80 - R.random() * 4))
        cid = 1
        for d, subs in DEPTS.items():
            c.execute("INSERT INTO categories VALUES(?,?,?,1)", (cid, d, None)); pid = cid; cid += 1
            for s in subs:
                c.execute("INSERT INTO categories VALUES(?,?,?,1)", (cid, s, pid)); cid += 1
        cats = db.rows(c, "SELECT * FROM categories WHERE parent_id IS NOT NULL")
        for st in db.rows(c, "SELECT * FROM stores"):
            for d in db.rows(c, "SELECT * FROM categories WHERE parent_id IS NULL"):
                subs = [x for x in cats if x["parent_id"] == d["id"]]
                raw = [max(.05, R.gauss(1, .22)) for _ in subs]
                tot = sum(raw)
                for x, v in zip(subs, raw):
                    c.execute("INSERT INTO space VALUES(?,?,?)", (st["id"], x["id"], round(v / tot, 4)))
                self.set_state(st["id"], f"deptn:{d['id']}", R.gauss(1, .05))
            self.set_state(st["id"], "factor", R.gauss(1, .12))
        for w in range(1, N_WEEKS + 1): c.execute("INSERT INTO weeks VALUES(?,?)", (w, week_start(w)))
        for i, (n, city) in enumerate([("North DC", "Brookfield"), ("South DC", "Clearwater")], 1):
            c.execute("INSERT INTO dcs VALUES(?,?,?)", (i, n, city))
        # Users
        uid = 1
        def U(name, role, **kw):
            nonlocal uid
            c.execute("INSERT INTO users(id,name,email,role,store_id,district_id,region_id,dc_id,last_login) VALUES(?,?,?,?,?,?,?,?,?)",
                      (uid, name, name.lower().replace(" ", ".") + "@colstorso-demo.test", role, kw.get("store"),
                       kw.get("district"), kw.get("region"), kw.get("dc"), kw.get("last")))
            uid += 1; return uid - 1
        U("Dana Whitfield", "hq_admin", last="2026-10-10")
        U("Priya Raman", "central_analyst", last="2026-10-09")
        U("Marcus Cole", "regional_manager", region=1, last="2026-10-09")
        U("Elena Sato", "regional_manager", region=2, last="2026-10-08")
        for d in range(1, 7):
            U(f"{FIRST[d]} {LAST[d]}", "district_manager", district=d, region=1 if d <= 3 else 2,
              last=f"2026-10-{R.randint(5, 10):02d}")
        for st in db.rows(c, "SELECT * FROM stores ORDER BY id"):
            nm = f"{FIRST[(st['id'] * 7) % len(FIRST)]} {LAST[(st['id'] * 5) % len(LAST)]}"
            last = (CURRENT_WEEK_START + dt.timedelta(days=R.randint(-20, 5))).isoformat()
            U(nm, "store_manager", store=st["id"], district=st["district_id"], last=last)
        for sid in (1, 2, 3):
            for k in range(2):
                U(f"{FIRST[(sid + k * 3) % len(FIRST)]} {LAST[(sid * 3 + k) % len(LAST)]}", "associate", store=sid,
                  district=db.one(c, "SELECT district_id FROM stores WHERE id=?", (sid,))["district_id"], last="2026-10-09")
        U("Grace Holloway", "dc_manager", dc=1, last="2026-10-09")
        U("ColsTorso AI Agent", "ai_agent")
        c.commit()

    def plant_issues(self):
        """Plant realistic execution problems the engine should find."""
        c, R = self.c, self.rng
        cats = db.rows(c, "SELECT * FROM categories WHERE parent_id IS NOT NULL")
        planted = []
        for st in db.rows(c, "SELECT * FROM stores"):
            for x in R.sample(cats, 3):
                m = R.uniform(.62, .86); self.set_state(st["id"], f"mult:{x['id']}", m); planted.append((st["id"], x["id"], m))
            if R.random() < .3: self.set_state(st["id"], f"waste:{2}", R.uniform(1.5, 2.3))  # Fresh waste
            if R.random() < .25: self.set_state(st["id"], "labor_over", R.uniform(.06, .14))
            if R.random() < .25: self.set_state(st["id"], "ot", R.uniform(1.0, 2.5))
            if R.random() < .25: self.set_state(st["id"], "conv", -R.uniform(.03, .07))
            if R.random() < .25: self.set_state(st["id"], "csat", -R.uniform(4, 9))
            if R.random() < .3: self.set_state(st["id"], "attach", -R.uniform(.03, .06))
            if R.random() < .12: self.set_state(st["id"], "cash", R.choice([-1, 1]) * R.uniform(60, 140))
            if R.random() < .25: self.set_state(st["id"], "gapscan", -R.uniform(.08, .2))
            if R.random() < .2: self.set_state(st["id"], "invacc", -R.uniform(.04, .09))
        # Equipment outage: hot drinks machine silent in 2 stores in the latest week
        for sid in R.sample(range(1, 51), 2): self.set_state(sid, "outage_week", N_WEEKS)
        c.commit(); return planted

    def gen_week(self, w, effects=None):
        """effects: list of dict(store, key, start, target) – ramps a state toward target after start (mission success)."""
        c, R = self.c, self.rng
        cats = db.rows(c, "SELECT * FROM categories")
        depts = [x for x in cats if x["parent_id"] is None]
        dept_names = {d["id"]: d["name"] for d in depts}
        c.execute("INSERT OR IGNORE INTO weeks VALUES(?,?)", (w, week_start(w)))
        stores = db.rows(c, "SELECT * FROM stores WHERE status!='New'")
        for st in stores:
            sid, F = st["id"], FORMATS[st["format"]]
            if effects:
                for e in effects:
                    if e["store"] == sid and w >= e["start"]:
                        cur = self.state(sid, e["key"], 1.0 if e["key"].startswith(("mult", "waste")) else 0.0)
                        self.set_state(sid, e["key"], cur + (e["target"] - cur) * 0.45)
            base = F["base"] * self.state(sid, "factor", 1) * (1 + R.gauss(0, .025))
            space = {r["cat_id"]: r["share"] for r in db.rows(c, "SELECT * FROM space WHERE store_id=?", (sid,))}
            total = 0
            for di, d in enumerate(depts):
                dshare = DEPT_MIX[st["format"]][di] * self.state(sid, f"deptn:{d['id']}", 1)
                dsales = base * dshare * seasonal(d["name"], w)
                subs = [x for x in cats if x["parent_id"] == d["id"]]
                wts = [space.get(x["id"], .2) ** .85 for x in subs]; tw = sum(wts)
                wr_mult = self.state(sid, f"waste:{d['id']}", 1)
                for x, wt in zip(subs, wts):
                    m = self.state(sid, f"mult:{x['id']}", 1)
                    if x["name"] == "Hot Drinks Bar" and self.state(sid, "outage_week", 0) == w: m = 0.03
                    s = max(0, dsales * wt / tw * m * (1 + R.gauss(0, .035)))
                    wr = (.055 if d["name"] == "Fresh" else .006) * wr_mult * (1 + R.gauss(0, .1))
                    c.execute("INSERT OR REPLACE INTO fact_sales VALUES(?,?,?,?,?,?,?)",
                              (sid, w, x["id"], round(s, 2), round(s / R.uniform(3.5, 6.5), 1), round(s * wr, 2),
                               round(s / (1.03 + R.gauss(0, .02)), 2)))
                    total += s
            conv = min(.97, F["conv"] + self.state(sid, "conv", 0) + R.gauss(0, .01))
            trans = total / F["atv"]; traffic = trans / conv
            budget_h = total / F["prod"]
            hours = budget_h * (1 + self.state(sid, "labor_over", 0) + R.gauss(0, .015))
            ot = hours * .025 * (1 + self.state(sid, "ot", 0)) * (1 + R.gauss(0, .1))
            c.execute("INSERT OR REPLACE INTO fact_store VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                sid, w, round(traffic), round(trans), round(hours, 1), round(budget_h, 1), round(ot, 1),
                round(min(99, 83 + self.state(sid, "csat", 0) + R.gauss(0, 1.5)), 1),
                round(max(0, .19 + self.state(sid, "attach", 0) + R.gauss(0, .008)), 4),
                round(R.gauss(0, 14) + self.state(sid, "cash", 0), 2),
                round(min(1, max(0, .95 + self.state(sid, "gapscan", 0) + R.gauss(0, .015))), 4),
                round(min(1, .975 + self.state(sid, "invacc", 0) + R.gauss(0, .005)), 4),
                round(F["base"] * self.state(sid, "factor", 1) * 1.02, 0)))
        db.set_setting(c, "current_week", max(w, db.setting(c, "current_week", 0) or 0))
        c.commit()
