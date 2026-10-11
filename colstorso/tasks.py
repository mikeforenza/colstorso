"""Intelligent Tasks: condition / event / schedule / CSV triggered work, targeting, escalation, surveys."""
import json, datetime as dt, csv, io
from . import db
from .engine import WeekData, store_metric, cmp, store_matches, store_rows, log, notify, now_iso, capacity_status

def today(c):
    return db.setting(c, "today", dt.date.today().isoformat())

def _due(c, days):
    return (dt.date.fromisoformat(today(c)) + dt.timedelta(days=days)).isoformat()

def assignee_for(c, store, role):
    if role == "district_manager":
        u = db.one(c, "SELECT id FROM users WHERE role='district_manager' AND district_id=? AND active=1", (store["district_id"],))
    elif role == "associate":
        u = db.one(c, "SELECT id FROM users WHERE role='associate' AND store_id=? AND active=1", (store["id"],)) or \
            db.one(c, "SELECT id FROM users WHERE role='store_manager' AND store_id=? AND active=1", (store["id"],))
    elif role == "ai_agent":
        u = db.one(c, "SELECT id FROM users WHERE role='ai_agent'")
    else:
        u = db.one(c, "SELECT id FROM users WHERE role='store_manager' AND store_id=? AND active=1", (store["id"],))
    return u["id"] if u else None

def create_task(c, store, tpl, rule=None, title=None, context=None, source="manual", due_days=None, body_extra=""):
    if isinstance(tpl, int): tpl = db.one(c, "SELECT * FROM task_templates WHERE id=?", (tpl,))
    role = tpl["assignee_role"]
    dup = db.one(c, "SELECT id FROM tasks WHERE store_id=? AND template_id=? AND status='open' AND COALESCE(rule_id,0)=?",
                 (store["id"], tpl["id"], rule["id"] if rule else 0))
    if dup and source != "manual": return dup["id"]
    aid = assignee_for(c, store, role)
    body = tpl["body_md"] + (("\n\n" + body_extra) if body_extra else "")
    cur = c.execute("""INSERT INTO tasks(rule_id,template_id,store_id,assignee_role,assignee_id,title,body_md,questions,due,status,
        created,est_minutes,context,source,attachments) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (rule["id"] if rule else None, tpl["id"], store["id"], role, aid, title or tpl["title"], body, tpl["questions"],
         _due(c, due_days if due_days is not None else (rule["due_days"] if rule else 3)), "open", now_iso(),
         tpl["est_minutes"], json.dumps(context or {}), source, tpl.get("attachments") or "[]"))
    tid = cur.lastrowid
    log(c, "task", tid, None, "created", source)
    if aid: notify(c, aid, f"New task: {title or tpl['title']}", f"#/task/{tid}")
    return tid

def target_stores(c, target, throttle=True):
    S = store_rows(c)
    caps = {x["store_id"]: x for x in capacity_status(c)} if throttle else {}
    out, skipped = [], []
    for s in S.values():
        if s["status"] != "Open" or not store_matches(s, target): continue
        if throttle and caps.get(s["id"], {}).get("at_capacity") and not target.get("ignore_capacity"):
            skipped.append(s["id"]); continue
        out.append(s)
    return out, skipped

def run_condition_rules(c, week):
    wd = WeekData(c, week, 1); n = 0
    for r in db.rows(c, "SELECT * FROM task_rules WHERE active=1 AND trigger_type='condition'"):
        cfg = db.J(r["config"], {})
        stores, _ = target_stores(c, db.J(r["target"], {}))
        for s in stores:
            v = store_metric(wd, s["id"], cfg.get("metric", ""))
            if v is not None and cmp(v, cfg.get("op", ">"), float(cfg.get("threshold", 0))):
                create_task(c, s, r["template_id"], r, context={"metric": cfg["metric"], "value": round(v, 2)},
                            source="condition", body_extra=f"_Triggered because **{cfg['metric']} = {v:,.2f}** ({cfg['op']} {cfg['threshold']})._")
                n += 1
        c.execute("UPDATE task_rules SET last_run=? WHERE id=?", (now_iso(), r["id"]))
    c.commit(); return n

def run_schedule_rules(c, week, force=False):
    n = 0
    for r in db.rows(c, "SELECT * FROM task_rules WHERE active=1 AND trigger_type='schedule'"):
        cfg = db.J(r["config"], {})
        every = int(cfg.get("every_weeks", 1))
        if not force and week % every != int(cfg.get("offset", 0)) % every: continue
        stores, _ = target_stores(c, db.J(r["target"], {}))
        for s in stores: create_task(c, s, r["template_id"], r, source="schedule"); n += 1
        c.execute("UPDATE task_rules SET last_run=? WHERE id=?", (now_iso(), r["id"]))
    c.commit(); return n

def fire_event(c, etype, payload):
    """Event hub: external systems post events (new manager, recall, weather...)."""
    n = 0; created = []
    tgt = dict(payload.get("target") or {})
    if payload.get("store_codes"):
        tgt["stores"] = [x["id"] for x in db.rows(c, f"SELECT id FROM stores WHERE code IN ({','.join('?'*len(payload['store_codes']))})", payload["store_codes"])]
    for r in db.rows(c, "SELECT * FROM task_rules WHERE active=1 AND trigger_type='event'"):
        cfg = db.J(r["config"], {})
        if cfg.get("event") != etype: continue
        t = dict(db.J(r["target"], {})); t.update(tgt); t["ignore_capacity"] = cfg.get("urgent", True)
        stores, _ = target_stores(c, t)
        for s in stores:
            created.append(create_task(c, s, r["template_id"], r, context=payload, source=f"event:{etype}",
                                       body_extra=payload.get("message", ""))); n += 1
    c.execute("INSERT INTO events(type,payload,ts,result) VALUES(?,?,?,?)", (etype, json.dumps(payload), now_iso(), f"{n} tasks"))
    c.commit(); return dict(created=n, task_ids=created)

def csv_schedule(c, text, template_id):
    """CSV with store_code[,due_date][,note] -> store-specific tasks."""
    rd = csv.DictReader(io.StringIO(text)); n = 0; errors = []
    tpl = db.one(c, "SELECT * FROM task_templates WHERE id=?", (template_id,))
    for i, row in enumerate(rd, 2):
        code = (row.get("store_code") or row.get("store") or "").strip()
        s = db.one(c, "SELECT * FROM stores WHERE code=?", (code,))
        if not s: errors.append(f"line {i}: unknown store '{code}'"); continue
        tid = create_task(c, s, tpl, source="csv", body_extra=row.get("note", ""))
        if row.get("due_date"): c.execute("UPDATE tasks SET due=? WHERE id=?", (row["due_date"], tid))
        n += 1
    c.commit(); return dict(created=n, errors=errors)

def escalate(c):
    """Overdue tasks escalate to the district manager automatically."""
    t = today(c); n = 0
    for k in db.rows(c, """SELECT t.*, r.escalate_after_days ead FROM tasks t LEFT JOIN task_rules r ON r.id=t.rule_id
                           WHERE t.status='open' AND t.escalated=0"""):
        ead = k["ead"] if k["ead"] is not None else 2
        if k["due"] and (dt.date.fromisoformat(t) - dt.date.fromisoformat(k["due"])).days >= ead:
            s = db.one(c, "SELECT * FROM stores WHERE id=?", (k["store_id"],))
            dm = assignee_for(c, s, "district_manager")
            c.execute("UPDATE tasks SET escalated=1 WHERE id=?", (k["id"],))
            if dm: notify(c, dm, f"Escalation: '{k['title']}' overdue at {s['code']}", f"#/task/{k['id']}")
            log(c, "task", k["id"], None, "escalated", f"to DM {dm}"); n += 1
    c.commit(); return n

def priority_bucket(c, task):
    """Must = due this week, Should = due later but in window, Could = no due / far out."""
    if not task.get("due"): return "Could"
    d = (dt.date.fromisoformat(task["due"]) - dt.date.fromisoformat(today(c))).days
    return "Must" if d <= 7 else ("Should" if d <= 21 else "Could")

def visible_questions(questions, answers, store, perf=None):
    out = []
    tags = db.J(store.get("tags"), []) if isinstance(store.get("tags"), str) else store.get("tags", [])
    for q in questions:
        si = q.get("show_if")
        if si and str(answers.get(si.get("q"), "")) != str(si.get("equals")): continue
        sa = q.get("store_attr")
        if sa:
            if sa.get("tags") and not set(sa["tags"]) & set(tags): continue
            if sa.get("formats") and store["format"] not in sa["formats"]: continue
        pc = q.get("perf_condition")
        if pc and perf is not None:
            v = perf.get(pc["metric"])
            if v is None or not cmp(v, pc["op"], float(pc["threshold"])): continue
        out.append(q)
    return out

def complete_task(c, tid, uid, answers):
    k = db.one(c, "SELECT * FROM tasks WHERE id=?", (tid,))
    qs = db.J(k["questions"], [])
    s = db.one(c, "SELECT * FROM stores WHERE id=?", (k["store_id"],))
    missing = [q["text"] for q in visible_questions(qs, answers, s) if q.get("required") and answers.get(q["id"]) in (None, "", [])]
    if missing: return dict(ok=False, missing=missing)
    c.execute("UPDATE tasks SET status='done', completed=?, answers=? WHERE id=?", (now_iso(), json.dumps(answers), tid))
    log(c, "task", tid, uid, "completed", "")
    followups = apply_followups(c, qs, answers, s, f"task {tid}")
    c.commit(); return dict(ok=True, followups=followups)

def apply_followups(c, qs, answers, store, origin):
    made = []
    for q in qs:
        f = q.get("followup")
        if not f: continue
        a = answers.get(q["id"])
        hit = (str(a) == str(f.get("equals"))) if "equals" in f else False
        if "lt" in f:
            try: hit = float(a) < float(f["lt"])
            except Exception: pass
        if hit:
            tpl = {"id": 0, "title": f.get("task_title", "Follow-up"), "body_md": f"Follow-up from {origin}: _{q['text']}_ → **{a}**",
                   "questions": "[]", "est_minutes": 20, "assignee_role": f.get("role", "store_manager"), "attachments": "[]"}
            made.append(create_task(c, store, tpl, source="followup", due_days=2))
    return made

def survey_perf(c, store_id, week):
    wd = WeekData(c, week, 1)
    out = {k: store_metric(wd, store_id, k) for k in ["labor_ratio", "overtime_pct", "conversion_pct", "csat", "attach_pct",
                                                    "cash_abs", "gapscan_pct", "invacc_pct", "sales_vs_budget_pct"]}
    for d in [x for x, p in wd.parent.items() if p is None]: out[f"waste_pct:{d}"] = store_metric(wd, store_id, f"waste_pct:{d}")
    return out

def submit_survey(c, sid, store_id, uid, answers, visit_id=None):
    sv = db.one(c, "SELECT * FROM surveys WHERE id=?", (sid,))
    store = db.one(c, "SELECT * FROM stores WHERE id=?", (store_id,))
    week = db.setting(c, "current_week")
    qs = visible_questions(db.J(sv["questions"], []), answers, store, survey_perf(c, store_id, week))
    yn = [q for q in qs if q["type"] == "yesno"]
    score = round(sum(1 for q in yn if answers.get(q["id"]) == "Yes") / len(yn) * 100, 1) if yn else None
    cur = c.execute("INSERT INTO survey_responses(survey_id,store_id,user_id,ts,week,answers,visit_id,score) VALUES(?,?,?,?,?,?,?,?)",
                    (sid, store_id, uid, now_iso(), week, json.dumps(answers), visit_id, score))
    fu = apply_followups(c, qs, answers, store, sv["name"])
    c.commit(); return dict(id=cur.lastrowid, score=score, followups=fu)
