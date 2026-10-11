"""Builds the demo tenant: master data, 52 weeks of synthetic data, history of missions with real measured impact,
task templates/rules, surveys, visits, campaigns, comms, DC data. Run: python -m colstorso.seed"""
import json, random, os, sys, datetime as dt, hashlib
from . import db
from .generator import Gen, N_WEEKS, week_start
from .engine import WeekData, metric_gap, run_week, create_mission, now_iso, log
from .playbook import ACTIONS, DEFAULT_PERMISSIONS
from . import tasks as T, ai

KEY_FOR = {"sales": lambda m: (f"mult:{m['cat_id']}", 0.99), "waste": lambda m: (f"waste:{m['cat_id']}", 1.0),
           "labor": lambda m: ("labor_over", 0.0), "overtime": lambda m: ("ot", 0.0), "conversion": lambda m: ("conv", 0.0),
           "csat": lambda m: ("csat", 0.0), "attach": lambda m: ("attach", 0.0), "invacc": lambda m: ("invacc", 0.0),
           "gapscan": lambda m: ("gapscan", 0.0), "cash": lambda m: ("cash", 0.0)}
GOOD = {"sales": ["Fix availability & ordering", "Re-merchandise & fix facings", "Promotion & signage fix"],
        "waste": ["Ordering reduction", "Process / routine change"], "labor": ["Schedule rebalance"],
        "overtime": ["Schedule rebalance"], "attach": ["Coach the team"], "csat": ["Coach the team"],
        "conversion": ["Schedule rebalance"], "invacc": ["Process / routine change"], "gapscan": ["Process / routine change"]}
ACTION_TEXT = {"Fix availability & ordering": "Found {cat} under-ordered; raised order qty and fixed the auto-replen min.",
  "Re-merchandise & fix facings": "Restored {cat} facings to planogram and moved the bay out from behind the seasonal display.",
  "Promotion & signage fix": "Promo tickets for {cat} were missing; put them up and added an end-cap.",
  "Ordering reduction": "Cut orders on the 12 worst-waste lines by 15% and moved markdowns to 2pm.",
  "Process / routine change": "Named owner per shift and added a check at handover.",
  "Schedule rebalance": "Moved 20 hours from Tue/Wed mornings to Fri/Sat peak; published schedule 2 weeks ahead.",
  "Coach the team": "10-minute huddles each morning on the standard; checked mid-week.",
  "Repair / maintenance ticket": "Raised a maintenance ticket."}

def stamp_feeds(c, week, which=("Sales & waste", "Store ops & labor")):
    """Record when each feed last loaded. Daily feed (sales/waste) and weekly feed (labor/store ops)."""
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    thru = (dt.date.fromisoformat(week_start(week)) + dt.timedelta(days=6)).isoformat() if week <= N_WEEKS else None
    cad = {"Sales & waste": "daily", "Store ops & labor": "weekly"}
    for n in which:
        c.execute("INSERT OR REPLACE INTO feeds VALUES(?,?,?,?)", (n, cad.get(n, "daily"), now, thru or now[:10]))
    c.commit()

def success(mid, p=0.68):
    return int(hashlib.md5(str(mid).encode()).hexdigest(), 16) % 100 < p * 100

def build(path=None, quiet=False):
    if path: db.DB_PATH = path
    p = db.DB_PATH
    old = getattr(db._local, "conn", None)
    if old is not None:
        try: old.close()
        except Exception: pass
        db._local.conn = None
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(p + ext): os.remove(p + ext)
    db.GEN[0] += 1
    c = db.get()
    R = random.Random(7)
    g = Gen(c, seed=11)
    g.build_master(); planted = g.plant_issues()
    db.set_setting(c, "today", (dt.date.fromisoformat(week_start(N_WEEKS)) + dt.timedelta(days=3)).isoformat())
    db.set_setting(c, "inbox_size", 3); db.set_setting(c, "max_must_per_quarter", 3); db.set_setting(c, "require_approval", False)
    stamp_feeds(c, N_WEEKS)
    db.set_setting(c, "_unused", 0); db.set_setting(c, "window_weeks", 1); db.set_setting(c, "currency", "USD")
    db.set_setting(c, "mission_duration", 4); db.set_setting(c, "permissions", DEFAULT_PERMISSIONS)
    db.set_setting(c, "brand", {"name": "ColsTorso"})
    # history: choose ~40 planted sales issues + some store-KPI issues to have been worked by managers
    cats = {x["id"]: x for x in db.rows(c, "SELECT * FROM categories")}
    hist = []
    for sid, cat, m in R.sample(planted, 42):
        hist.append(dict(store_id=sid, kpi="sales", cat_id=cat, start=R.randint(40, 51)))
    for sid in range(1, 51):
        for k, key in [("labor", "labor_over"), ("waste", "waste:2"), ("attach", "attach"), ("overtime", "ot")]:
            v = g.state(sid, key, 0 if k != "waste" else 1)
            if (k == "waste" and v > 1.2) or (k != "waste" and abs(v) > 0.01):
                if R.random() < 0.4: hist.append(dict(store_id=sid, kpi=k, cat_id=2 if k == "waste" else None, start=R.randint(42, 51)))
    effects = []
    for i, h in enumerate(hist):
        h["sid_key"] = i + 1000
        h["ok"] = success(h["sid_key"])
        if h["ok"]:
            key, tgt = KEY_FOR[h["kpi"]](h)
            effects.append(dict(store=h["store_id"], key=key, start=h["start"], target=tgt))
    for w in range(1, N_WEEKS + 1):
        g.gen_week(w, effects)
    db.set_setting(c, "current_week", N_WEEKS)
    seed_config(c)
    # insert historical missions with baselines computed from the data
    sm = {u["store_id"]: u for u in db.rows(c, "SELECT * FROM users WHERE role='store_manager'")}
    cache = {}
    for h in hist:
        w0 = h["start"] - 1
        if w0 not in cache: cache[w0] = WeekData(c, w0)
        gp = metric_gap(cache[w0], h["store_id"], h["kpi"], h["cat_id"])
        if not gp: continue
        at = R.choice(GOOD.get(h["kpi"], ["Coach the team"])) if h["ok"] else R.choice(list(ACTIONS))
        catn = cats[h["cat_id"]]["name"] if h["cat_id"] else ""
        title = {"sales": f"{catn} sales below peers", "waste": f"{catn} waste above peers", "labor": "Labor hours over budget",
                 "attach": "Attachment rate below peers", "overtime": "Excess overtime hours"}[h["kpi"]]
        owner = sm[h["store_id"]]["id"]
        mid = create_mission(c, dict(store_id=h["store_id"], owner_id=owner, kind="opportunity", kpi=h["kpi"], cat_id=h["cat_id"],
            title=title, status="live", root_causes=json.dumps([R.choice(["Product out of stock / low on-hand", "Shelf gaps or poor facings",
            "Planogram not followed", "Over-ordering vs demand", "Schedule built above model"])]), action_type=at,
            action=ACTION_TEXT.get(at, "Action logged").format(cat=catn or "the area"), target_weekly=round(gp["gap"], 2),
            baseline_gap=round(gp["gap"], 2), start_week=h["start"], end_week=h["start"] + 3, source="engine", created_by=owner,
            created_week=h["start"], approval="approved", priority="Must", due_week=h["start"]))
        c.execute("INSERT INTO mission_tasks(mission_id,title,assignee_id,due,done) VALUES(?,?,?,?,1)",
                  (mid, "Walk the bay and log findings", owner, week_start(h["start"])))
    c.commit()
    # rejected missions with reasons (feed themes)
    reasons = ["Short staffed all week, two call outs", "Delivery late again from the DC, truck short shipped",
               "Freezer broken, waiting on repair", "Out of stock at DC, nothing we can do", "Price labels wrong from head office"]
    for sid in range(1, 26):
        if R.random() < .5:
            create_mission(c, dict(store_id=sid, owner_id=sm[sid]["id"], kind="opportunity", kpi="sales",
                cat_id=R.choice([k for k, v in cats.items() if v["parent_id"]]), title="Category sales below peers", status="rejected",
                reason=R.choice(reasons), snooze_until=N_WEEKS + 2, created_week=N_WEEKS - 1, source="engine", baseline_gap=300))
    seed_activity(c, R)
    res = run_week(c, N_WEEKS)
    seed_after(c, R)
    ai.run_agent(c)
    c.commit()
    if not quiet: print("seeded", res)
    return c

def seed_config(c):
    tpls = [
      ("Product recall", "Product recall: remove affected lines", "Remove all affected lot codes from shelf and backroom. **Do not** sell.\n\n1. Check shelf\n2. Check backroom\n3. Record quantity removed",
       [{"id": "q1", "type": "number", "text": "Units removed", "required": True}, {"id": "q2", "type": "photo", "text": "Photo of quarantined stock"}], 20, "store_manager"),
      ("New manager onboarding", "Welcome: complete week-1 onboarding", "Welcome to the team! Work through the checklist below with your district manager.",
       [{"id": "q1", "type": "yesno", "text": "Met your district manager?", "required": True},
        {"id": "q2", "type": "yesno", "text": "Completed safety walk?", "required": True,
         "followup": {"equals": "No", "task_title": "Book safety walk with DM", "role": "district_manager"}}], 60, "store_manager"),
      ("Waste reduction protocol", "High waste: run the waste-reduction protocol", "Fresh waste is above the trigger. Review the 10 highest-waste lines, cut orders, and move markdowns earlier.",
       [{"id": "q1", "type": "single", "text": "Main cause", "options": ["Over-ordering", "Late markdowns", "Rotation", "Equipment"], "required": True},
        {"id": "q2", "type": "text", "text": "What did you change?"}], 30, "store_manager"),
      ("Severe weather prep", "Severe weather: prepare the store", "A weather warning is active for your area. Stock up on water, batteries; secure trolleys and outdoor displays.",
       [{"id": "q1", "type": "yesno", "text": "Outdoor displays secured?", "required": True}], 20, "store_manager"),
      ("Weekly safety check", "Weekly safety & fire-exit check", "Check all fire exits are clear and extinguishers are tagged.",
       [{"id": "q1", "type": "yesno", "text": "All exits clear?", "required": True, "followup": {"equals": "No", "task_title": "Clear blocked fire exit today"}},
        {"id": "q2", "type": "yesno", "text": "Extinguishers in date?"}], 15, "associate"),
      ("Labor overage review", "Labor over budget: review next week's schedule", "Worked hours are above budget. Rebalance next week's schedule before it is published.",
       [{"id": "q1", "type": "number", "text": "Hours removed from next week", "required": True}], 30, "store_manager"),
      ("Data pull (agent)", "Pull KPI summary for coaching call", "Prepare a short KPI summary for the coaching call.", [], 5, "ai_agent"),
      ("Promo setup", "Set up the seasonal promotion end-caps", "Build the two seasonal end-caps per the guide. Attach a photo when done.",
       [{"id": "q1", "type": "photo", "text": "Photo of end-cap", "required": True}], 45, "store_manager"),
    ]
    for n, t, b, q, est, role in tpls:
        c.execute("INSERT INTO task_templates(name,title,body_md,questions,est_minutes,assignee_role) VALUES(?,?,?,?,?,?)", (n, t, b, json.dumps(q), est, role))
    rules = [
      ("Recall events", "event", {"event": "product_recall", "urgent": True}, 1, {}, 1, 1),
      ("New manager joins", "event", {"event": "new_manager"}, 2, {}, 7, 3),
      ("Fresh waste trigger", "condition", {"metric": "waste_pct:7", "op": ">", "threshold": 8.5}, 3, {}, 3, 2),
      ("Weather warnings", "event", {"event": "weather_warning", "urgent": True}, 4, {}, 1, 1),
      ("Weekly safety check", "schedule", {"every_weeks": 1, "offset": 0}, 5, {}, 4, 2),
      ("Labor over budget", "condition", {"metric": "labor_ratio", "op": ">", "threshold": 108}, 6, {}, 4, 2),
      ("Seasonal end-caps (large stores)", "schedule", {"every_weeks": 4, "offset": 0}, 8, {"formats": ["Superstore", "Standard"]}, 5, 2),
    ]
    fresh = db.one(c, "SELECT id FROM categories WHERE name='Fresh'")["id"]
    for n, tt, cfg, tid, tgt, due, esc in rules:
        if "waste_pct" in cfg.get("metric", ""): cfg["metric"] = f"waste_pct:{fresh}"
        c.execute("INSERT INTO task_rules(name,trigger_type,config,template_id,target,due_days,escalate_after_days) VALUES(?,?,?,?,?,?,?)",
                  (n, tt, json.dumps(cfg), tid, json.dumps(tgt), due, esc))
    mr = [("Cash variance over $75", "cash_abs", ">", 75, "Till variance of ${value} last week – double-count tills", "Count every till twice for 3 days and review the change-fund log.", "Must"),
          ("Gap scans under 85%", "gapscan_pct", "<", 85, "Gap scans only {value}% completed", "Assign a named scanner on every shift.", "Must"),
          ("Inventory accuracy under 92%", "invacc_pct", "<", 92, "Inventory accuracy {value}% – run today's count list", "Count the lines most likely to have drifted (see count list).", "Should")]
    for n, met, op, th, title, gd, pr in mr:
        c.execute("INSERT INTO mission_rules(name,metric,op,threshold,kind,title,guidance,priority) VALUES(?,?,?,?,?,?,?,?)", (n, met, op, th, "alert", title, gd, pr))
    walk = [
      {"id": "w1", "type": "yesno", "text": "Entrance clean and welcoming?", "required": True, "followup": {"equals": "No", "task_title": "Fix entrance standard"}},
      {"id": "w2", "type": "yesno", "text": "Fresh department fully stocked?", "required": True},
      {"id": "w3", "type": "single", "text": "Main reason for gaps", "options": ["Late delivery", "Short staffed", "Ordering", "No gaps"], "show_if": {"q": "w2", "equals": "No"}},
      {"id": "w4", "type": "yesno", "text": "Waste markdowns done by 2pm?", "perf_condition": {"metric": f"waste_pct:{fresh}", "op": ">", "threshold": 6.5}},
      {"id": "w5", "type": "yesno", "text": "Pharmacy counter staffed?", "store_attr": {"tags": ["Pharmacy"]}},
      {"id": "w6", "type": "yesno", "text": "Hot drinks machine working?", "store_attr": {"tags": ["Hot Drinks Bar"]}, "followup": {"equals": "No", "task_title": "Raise maintenance ticket for hot drinks machine"}},
      {"id": "w7", "type": "number", "text": "Tills open at peak", "required": True},
      {"id": "w8", "type": "text", "text": "Biggest issue in the store today?"},
      {"id": "w9", "type": "photo", "text": "Photo of the main promo end-cap", "image": "/static/img/endcap-standard.svg"},
    ]
    c.execute("INSERT INTO surveys(name,kind,questions,trigger,target) VALUES(?,?,?,?,?)", ("Weekly store walk", "storewalk", json.dumps(walk), json.dumps({"type": "schedule", "every_weeks": 1}), "{}"))
    audit = [{"id": "a1", "type": "yesno", "text": "Fire exits clear?", "required": True}, {"id": "a2", "type": "yesno", "text": "Fridge temps logged twice daily?", "required": True},
             {"id": "a3", "type": "yesno", "text": "Allergen labels correct in Deli?"}, {"id": "a4", "type": "multi", "text": "Areas needing attention", "options": ["Backroom", "Fresh", "Tills", "Car park"]},
             {"id": "a5", "type": "date", "text": "Date of last pest-control visit"}]
    c.execute("INSERT INTO surveys(name,kind,questions,trigger,target) VALUES(?,?,?,?,?)", ("Quarterly compliance audit", "audit", json.dumps(audit), json.dumps({"type": "schedule", "every_weeks": 13}), "{}"))
    chk = [{"id": "k1", "type": "yesno", "text": "Opening checks done?"}, {"id": "k2", "type": "yesno", "text": "Tills floated?"}, {"id": "k3", "type": "yesno", "text": "Hot food at temperature?"}]
    c.execute("INSERT INTO surveys(name,kind,questions,trigger,target) VALUES(?,?,?,?,?)", ("Opening checklist", "checklist", json.dumps(chk), json.dumps({"type": "schedule", "every_weeks": 1}), "{}"))
    c.execute("INSERT INTO campaigns(name,kpis,categories,boost,start_week,end_week,target,active,created_by,message,push,holdout) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
              ("Fresh Q4 waste push", json.dumps(["waste"]), json.dumps([fresh]), 3.0, N_WEEKS - 1, N_WEEKS + 6, "{}", 1, 1,
               "Q4 priority: cut Fresh waste. Waste missions skip the queue in every inbox.", "must", json.dumps([5, 17, 29, 41])))
    snacks = db.one(c, "SELECT id FROM categories WHERE name='Snacks'")
    c.execute("INSERT INTO campaigns(name,kpis,categories,boost,start_week,end_week,target,active,created_by,message,push,holdout) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
              ("Fall snack range", json.dumps([]), json.dumps([snacks["id"]] if snacks else []), 1.6, N_WEEKS - 2, N_WEEKS + 4,
               json.dumps({"formats": ["Standard", "Superstore"]}), 1, 1, "Snacks should sell to their space this fall.", "standard", json.dumps([8, 22])))
    c.execute("INSERT INTO blackouts(name,start_date,end_date,target) VALUES(?,?,?,?)", ("Thanksgiving trading peak", "2026-11-23", "2026-11-29", "{}"))
    anns = [("Q4 focus: Fresh waste", "This quarter we are prioritising Fresh waste. You'll see waste missions boosted in your inbox.", {}, "high", 1),
            ("New handheld scanners for Superstores", "Superstores receive new scanners next week. Training video in the task.", {"formats": ["Superstore"]}, "normal", 0),
            ("Pharmacy hours change", "Pharmacy counters close at 8pm from Monday.", {"tags": ["Pharmacy"]}, "normal", 1)]
    for t, b, tg, pr, ack in anns:
        c.execute("INSERT INTO announcements(title,body,target,author_id,ts,priority,require_ack) VALUES(?,?,?,?,?,?,?)", (t, b, json.dumps(tg), 1, now_iso(), pr, ack))
    c.commit()

def seed_activity(c, R):
    """Store-walk responses with free text (themes), visits, best practices, pallets & load flags."""
    week = N_WEEKS
    texts = {1: ["Short staffed again, two call outs on Saturday", "Delivery late, truck short shipped dairy", "Short staffed on the late shift"],
             4: ["Freezer broken in aisle 9, repair booked", "Hot drinks machine broken since Tuesday", "Fridge leak by the deli, machine down"]}
    dm = {u["district_id"]: u["id"] for u in db.rows(c, "SELECT * FROM users WHERE role='district_manager'")}
    for s in db.rows(c, "SELECT * FROM stores"):
        for wk in (week - 2, week - 1):
            pool = texts.get(s["district_id"], ["All good", "Busy weekend, store looked great", "Minor shelf gaps in snacks"])
            ans = {"w1": R.choice(["Yes", "Yes", "No"]), "w2": R.choice(["Yes", "No"]), "w3": R.choice(["Late delivery", "Short staffed", "Ordering"]),
                   "w7": R.randint(2, 8), "w8": R.choice(pool)}
            yn = [ans["w1"], ans["w2"]]
            c.execute("INSERT INTO survey_responses(survey_id,store_id,user_id,ts,week,answers,score) VALUES(?,?,?,?,?,?,?)",
                      (1, s["id"], dm[s["district_id"]], week_start(wk) + "T10:00:00", wk, json.dumps(ans), round(yn.count("Yes") / 2 * 100, 1)))
    for d, uid in dm.items():
        for k, s in enumerate(db.rows(c, "SELECT * FROM stores WHERE district_id=? LIMIT 3", (d,))):
            c.execute("INSERT INTO visits(dm_id,store_id,date,status,notes,coaching,agreed_actions) VALUES(?,?,?,?,?,?,?)",
                      (uid, s["id"], week_start(week - 1 + k) , "done" if k == 0 else "planned",
                       "Good energy; backroom needs work." if k == 0 else "", json.dumps(["Praise the fresh team"] if k == 0 else []),
                       json.dumps(["Tidy backroom by Friday"] if k == 0 else [])))
    names = ["Ana", "Ben", "Chen", "Dev", "Eli", "Fay"]
    for i in range(1, 121):
        sid = R.randint(1, 50); dc = 1 if db.one(c, "SELECT district_id FROM stores WHERE id=?", (sid,))["district_id"] <= 3 else 2
        c.execute("INSERT INTO pallets VALUES(?,?,?,?,?,?,?,?)", (f"PL{10000+i}", dc, sid, week, R.choice(names) + " (picker)",
                  R.randint(1, 36), R.choice(names) + " (loader)", R.choice(["Day", "Night"])))
    c.commit()

def seed_after(c, R):
    """After the pipeline: best practices from real successful missions, some accepted/pre-launch states, comments."""
    allw = db.rows(c, """SELECT m.*, s.name sname, x.cum FROM missions m JOIN stores s ON s.id=m.store_id JOIN
        (SELECT mission_id, SUM(net) cum FROM impact GROUP BY mission_id) x ON x.mission_id=m.id WHERE x.cum>0 ORDER BY x.cum DESC""")
    per = {}; wins = []
    for w in allw:
        if per.get(w["kpi"], 0) < (6 if w["kpi"] == "sales" else 2): wins.append(w); per[w["kpi"]] = per.get(w["kpi"], 0) + 1
    for w in wins:
        c.execute("INSERT INTO best_practices(mission_id,user_id,store_id,title,body,kpi,cat_id,action_type,impact_value,likes,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (w["id"], w["owner_id"], w["store_id"], f"{w['action_type']}: {w['title'].replace(' below peers','').replace(' above peers','')}",
                   w["action"], w["kpi"], w["cat_id"], w["action_type"], round(w["cum"], 2), R.randint(0, 14), now_iso()))
        c.execute("UPDATE missions SET kudos=kudos+? WHERE id=?", (R.randint(1, 5), w["id"]))
    # a proposal awaiting DM approval, and a draft in pre-launch, for store 1
    inc = db.rows(c, "SELECT * FROM missions WHERE store_id=1 AND status='incoming' AND kind='opportunity' ORDER BY baseline_gap DESC")
    if len(inc) >= 3:
        c.execute("UPDATE missions SET status='prelaunch', root_causes=? WHERE id=?", (json.dumps(["Shelf gaps or poor facings"]), inc[2]["id"]))
    for s in (2, 3):
        x = db.one(c, "SELECT * FROM missions WHERE store_id=? AND status='incoming' AND kind='opportunity' ORDER BY baseline_gap DESC", (s,))
        if x:
            c.execute("UPDATE missions SET status='proposed', approval='pending', action_type=?, action=?, root_causes=? WHERE id=?",
                      ("Re-merchandise & fix facings", "Rebuild the bay to planogram and add a second facing on top sellers.",
                       json.dumps(["Planogram not followed"]), x["id"]))
    dm1 = db.one(c, "SELECT id FROM users WHERE role='district_manager' AND district_id=1")["id"]
    lv = db.one(c, "SELECT id FROM missions WHERE store_id=1 AND status='live'")
    if lv:
        c.execute("INSERT INTO comments(entity,entity_id,user_id,text,ts) VALUES('mission',?,?,?,?)", (lv["id"], dm1, "Nice work – check the backroom stock too.", now_iso()))
    ag = db.one(c, "SELECT * FROM task_templates WHERE assignee_role='ai_agent'")
    T.create_task(c, db.one(c, "SELECT * FROM stores WHERE id=1"), ag, source="manual")
    c.commit()

def next_week(c):
    """Simulate the next weekly data drop: live missions with good actions recover in the data; then re-run the pipeline."""
    w = db.setting(c, "current_week") + 1
    g = Gen(c, seed=1000 + w)
    effects = []
    for m in db.rows(c, "SELECT * FROM missions WHERE status='live' AND kpi IN ('sales','waste','labor','overtime','conversion','csat','attach','invacc','gapscan','cash')"):
        if success(m["id"], 0.6 if m["action_type"] in GOOD.get(m["kpi"], []) else 0.3):
            key, tgt = KEY_FOR[m["kpi"]](m); effects.append(dict(store=m["store_id"], key=key, start=m["start_week"], target=tgt))
    for s in db.rows(c, "SELECT store_id FROM gen_state WHERE key='outage_week'"):
        g.set_state(s["store_id"], "outage_week", 0)
    g.gen_week(w, effects)
    t = dt.date.fromisoformat(db.setting(c, "today")) + dt.timedelta(days=7)
    db.set_setting(c, "today", t.isoformat())
    stamp_feeds(c, w)
    res = run_week(c, w)
    ai.run_agent(c)
    return res

if __name__ == "__main__":
    build()
