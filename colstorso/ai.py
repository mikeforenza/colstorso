"""AI layer ("company brain"): explanations, Q&A, theme extraction, AI mission triggers, AI agent.

Everything here works offline with deterministic templates/rules. If COLSTORSO_LLM_URL (an OpenAI-compatible
/v1/chat/completions endpoint) and COLSTORSO_LLM_KEY are set, `llm()` rewrites the templated answer in natural
language, grounded on the same facts. No data leaves the box unless you configure that.
"""
import os, re, json, statistics as stats
from collections import defaultdict, Counter
from . import db
from .playbook import KPIS, ROOT_CAUSES, GUIDANCE, ACTIONS, SURVEY_CONCEPTS
from .engine import WeekData, metric_gap, mission_impact_summary, create_mission, log, notify, now_iso

LLM_STATS = {"calls": 0, "cache_hits": 0, "fallbacks": 0}

def llm(system, facts, fallback):
    """Optional LLM polish. Off unless COLSTORSO_LLM_URL is set. Answers are cached by a hash of (prompt, facts, draft) so the
    same question over the same data never costs twice; any error or timeout falls back to the rule-based draft."""
    url, key = os.environ.get("COLSTORSO_LLM_URL"), os.environ.get("COLSTORSO_LLM_KEY")
    if not url: return fallback
    import hashlib, time
    k = hashlib.sha256(json.dumps([system, facts, fallback], sort_keys=True, default=str).encode()).hexdigest()
    ttl = float(os.environ.get("COLSTORSO_LLM_CACHE_HOURS", "168")) * 3600
    c = db.get()
    hit = db.one(c, "SELECT v, ts FROM llm_cache WHERE k=?", (k,))
    if hit and time.time() - hit["ts"] < ttl:
        LLM_STATS["cache_hits"] += 1; return hit["v"]
    if LLM_STATS["calls"] >= int(os.environ.get("COLSTORSO_LLM_MAX_CALLS_PER_PROCESS", "500")):
        LLM_STATS["fallbacks"] += 1; return fallback        # hard budget guard
    try:
        LLM_STATS["calls"] += 1
        out = _llm_call(url, key, system, facts, fallback)
        c.execute("INSERT OR REPLACE INTO llm_cache VALUES(?,?,?)", (k, out, time.time()))
        return out
    except Exception:
        LLM_STATS["fallbacks"] += 1; return fallback

def _llm_call(url, key, system, facts, fallback):
    if True:
        import urllib.request
        body = json.dumps({"model": os.environ.get("COLSTORSO_LLM_MODEL", "default"), "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": f"Facts: {json.dumps(facts, default=str)}\nDraft: {fallback}"}]}).encode()
        req = urllib.request.Request(url, body, {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=int(os.environ.get("COLSTORSO_LLM_TIMEOUT", "12"))) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]

def money(v): return f"${v:,.0f}"

def similar_wins(c, kpi, cat_id, exclude_store=None, limit=3):
    q = """SELECT m.*, s.code, s.name store_name, SUM(i.net) cum FROM missions m JOIN impact i ON i.mission_id=m.id
           JOIN stores s ON s.id=m.store_id WHERE m.kpi=? AND (m.cat_id IS ? OR m.cat_id=?) AND m.store_id != ?
           AND i.week<=COALESCE(m.end_week, 999) GROUP BY m.id HAVING cum>0 ORDER BY cum DESC LIMIT ?"""
    return db.rows(c, q, (kpi, cat_id, cat_id, exclude_store or -1, limit))

def action_stats(c, kpi):
    rows = db.rows(c, """SELECT m.action_type a, COUNT(*) n, AVG(x.cum) avg FROM missions m JOIN
        (SELECT mission_id, SUM(net) cum FROM impact GROUP BY mission_id) x ON x.mission_id=m.id
        WHERE m.kpi=? AND m.action_type IS NOT NULL GROUP BY m.action_type ORDER BY avg DESC""", (kpi,))
    return rows

def explain_mission(c, mid):
    m = db.one(c, "SELECT * FROM missions WHERE id=?", (mid,))
    if not m: return {"text": "Mission not found."}
    s = db.one(c, "SELECT * FROM stores WHERE id=?", (m["store_id"],))
    week = m["start_week"] or m["created_week"] or db.setting(c, "current_week")
    wd = WeekData(c, min(week, db.setting(c, "current_week")), 1)
    k = KPIS.get(m["kpi"], KPIS["custom"])
    g = metric_gap(wd, m["store_id"], m["kpi"], m["cat_id"]) if m["kpi"] not in ("equipment", "custom", "dc_quality") else None
    parts, facts = [], {"mission": m["title"], "store": s["name"]}
    if g and m["kpi"] == "sales":
        p = wd.parent[m["cat_id"]]
        parts.append(f"**What we found.** At {s['name']}, {wd.cat[m['cat_id']]['name']} makes up {g['share']*100:.1f}% of "
                     f"{wd.cat[p]['name']} sales. The {len(g['peers'])} most comparable {s['format']} stores (similar shelf space) "
                     f"average {g['peer_share']*100:.1f}%.")
        parts.append(f"**Why it's fair.** We scale every peer to *your* {wd.cat[p]['name']} sales, so footfall, weather or a "
                     f"holiday that moves the whole department cancels out. If you sold at the peer rate you would take about "
                     f"{money(g['expected'])} a week instead of {money(g['actual'])} — a gap of **{money(g['gap'])}/week**.")
    elif g:
        unit = k["unit"]
        parts.append(f"**What we found.** {k['label']} at {s['name']} is {g['actual']:,.1f}{unit if unit!='$' else ''} vs a "
                     f"same-format peer average of {g['expected']:,.1f}{unit if unit!='$' else ''} ({len(g['peers'])} stores).")
        parts.append(f"**What it's worth.** Closing the gap is worth about **{money(max(g['gap'],0))}/week** ({k['scaler']}).")
    else:
        parts.append(f"**What we found.** {m['title']}. {m.get('comment') or ''}")
    if g: parts.append(f"**How unusual.** You are {g['z']:.1f} standard deviations from peers, so this is "
                       f"{'very likely a fixable execution issue' if g['z']>2 else 'probably worth a look'}.")
    rc = ROOT_CAUSES.get(m["kpi"], [])[:4]
    if rc: parts.append("**Check first:** " + "; ".join(rc) + ".")
    parts.append("**Guidance:** " + GUIDANCE.get(m["kpi"], ""))
    wins = similar_wins(c, m["kpi"], m["cat_id"], m["store_id"])
    if wins:
        w = wins[0]
        parts.append(f"**What worked elsewhere.** {w['store_name']} chose *{w['action_type']}* — \"{(w['action'] or '')[:120]}\" — "
                     f"and gained {money(w['cum'])} vs control stores.")
    st = action_stats(c, m["kpi"])
    if st: parts.append("**Best actions for this KPI so far:** " + ", ".join(f"{r['a']} (avg {money(r['avg'])}, n={r['n']})" for r in st[:3]) + ".")
    if m["status"] in ("live", "done"):
        imp = mission_impact_summary(c, mid)
        parts.append(f"**Progress.** Net impact vs control stores so far: {money(imp['cumulative'])} "
                     f"(latest week {money(imp['latest'])}).")
    text = "\n\n".join(parts)
    facts.update({"gap": g and g["gap"], "z": g and g["z"]})
    return {"text": llm("Explain this retail store mission to a busy store manager in plain words.", facts, text),
            "llm": bool(os.environ.get("COLSTORSO_LLM_URL")), "root_causes": ROOT_CAUSES.get(m["kpi"], []),
            "actions": list(ACTIONS.keys()), "suggested_action": (st[0]["a"] if st else None),
            "sources": [f"{k['label']} · week {wd.week} data", f"{len(g['peers'])} peer stores ({g['scaler']})" if g else "Mission record",
                        *(["Best-practice library"] if wins else []), *(["Mission impact (diff-in-diff)"] if st else [])]}

def briefing(c, user, scope_store_ids):
    week = db.setting(c, "current_week")
    inbox = db.rows(c, f"SELECT * FROM missions WHERE status='incoming' AND store_id IN ({','.join(map(str, scope_store_ids)) or 0})")
    live = db.rows(c, f"SELECT * FROM missions WHERE status='live' AND store_id IN ({','.join(map(str, scope_store_ids)) or 0})")
    tot = sum(max(0, m["baseline_gap"] or 0) for m in inbox if m["kind"] == "opportunity")
    ups = [m for m in live if mission_impact_summary(c, m["id"])["status"] == "green"]
    first = user["name"].split()[0]
    txt = (f"Good morning {first}. Week {week}: {len(inbox)} new missions are waiting "
           f"(worth about {money(tot)}/week if closed), and {len(ups)} of {len(live)} live missions are improving.")
    alerts = [m for m in inbox if m["kind"] == "alert"]
    if alerts: txt += f" Start with the alert: {alerts[0]['title']}."
    elif inbox:
        top = max(inbox, key=lambda m: m["baseline_gap"] or 0); txt += f" Biggest one: {top['title']}."
    return txt

def ask(c, user, q, scope_store_ids):
    from . import help as HELP
    if HELP.is_howto(q):
        h = HELP.answer(q); return {"answer": h["answer"], "rows": [], "sources": h["sources"], "articles": h["articles"]}
    """Rule-based question answering over the platform's data (LLM plugs in via llm())."""
    ql = q.lower(); week = db.setting(c, "current_week")
    ids = ",".join(map(str, scope_store_ids)) or "0"
    S = {s["id"]: s for s in db.rows(c, f"SELECT * FROM stores WHERE id IN ({ids})")}
    kpi = next((k for k in KPIS if k in ql or KPIS[k]["label"].lower().split()[0] in ql), None)
    if "shrink" in ql or "waste" in ql: kpi = "waste"
    if "overtime" in ql: kpi = "overtime"
    if "labor" in ql or "labour" in ql: kpi = kpi or "labor"
    ans, rows, sources = "", [], []
    if any(w in ql for w in ["focus", "should i", "priorit", "first"]):
        rows = db.rows(c, f"""SELECT m.*, s.code FROM missions m JOIN stores s ON s.id=m.store_id WHERE m.status='incoming' AND m.store_id IN ({ids})
                         ORDER BY CASE m.priority WHEN 'Must' THEN 0 WHEN 'Should' THEN 1 ELSE 2 END, m.baseline_gap DESC LIMIT 3""")
        ans = ("Focus on these, in order:\n" + "\n".join(f"{i+1}. {r['code']} {r['title']} ({r['priority']}, about {money(max(r['baseline_gap'] or 0, 0))}/wk)"
               for i, r in enumerate(rows))) if rows else "Your inbox is clear. Check live missions and open tasks."
        sources = ["Mission inbox · week %d" % week]
    elif "why" in ql and kpi in ("labor", "overtime", "conversion", "csat", "attach", "invacc", "gapscan", "waste"):
        wd = WeekData(c, week, 1); out = []
        for sid in list(S)[:50]:
            g = metric_gap(wd, sid, kpi, 2 if kpi == "waste" else None)
            if g and g["gap"] > 0: out.append((g["gap"], S[sid]["code"], g))
        out.sort(reverse=True)
        if out:
            gap, code, g = out[0]
            ans = (f"{KPIS[kpi]['label']}: {len(out)} of your {len(S)} store(s) are worse than peers. Largest: {code} at {g['actual']:,.1f} vs "
                   f"peers {g['expected']:,.1f} (worth {money(gap)}/wk). Most common causes: " + "; ".join(ROOT_CAUSES.get(kpi, [])[:3]) + ". "
                   + GUIDANCE.get(kpi, ""))
        else:
            ans = f"{KPIS[kpi]['label']} is in line with peers across your stores this week."
        sources = [f"{KPIS[kpi]['label']} · peer benchmark · week {week}"]
    elif ("worked" in ql or "what works" in ql or "best practice" in ql):
        q3 = "SELECT * FROM best_practices" + (" WHERE kpi=?" if kpi else "") + " ORDER BY impact_value DESC LIMIT 5"
        rows = db.rows(c, q3, (kpi,) if kpi else ())
        ans = ("Top shared practices" + (f" for {KPIS[kpi]['label']}" if kpi else "") + ":\n" + "\n".join(f"- {b['title']}: \"{(b['body'] or '')[:90]}\" ({money(b['impact_value'] or 0)} measured)" for b in rows)) if rows else "No shared practices for that yet."
        st = action_stats(c, kpi) if kpi else []
        if st: ans += "\nAcross all missions, the best average result came from: " + ", ".join(f"{r['a']} ({money(r['avg'])}, n={r['n']})" for r in st[:3]) + "."
        sources = ["Best-practice library", "Mission impact (diff-in-diff)"]
    elif any(w in ql for w in ["worst", "which stores", "bottom", "lowest", "biggest"]):
        q2 = f"SELECT o.*, s.code, s.name FROM opportunities o JOIN stores s ON s.id=o.store_id WHERE week=? AND store_id IN ({ids})"
        args = [week]
        if kpi: q2 += " AND kpi=?"; args.append(kpi)
        rows = db.rows(c, q2 + " ORDER BY gap_value DESC LIMIT 5", args)
        ans = "Biggest gaps" + (f" for {KPIS[kpi]['label']}" if kpi else "") + " this week: " + \
              "; ".join(f"{r['code']} {r['title']} ({money(r['gap_value'])}/wk)" for r in rows) if rows else "No open gaps found."
    elif "impact" in ql or "roi" in ql or "worth" in ql:
        r = db.one(c, f"""SELECT COUNT(DISTINCT m.id) n, COALESCE(SUM(i.net),0) v FROM missions m JOIN impact i ON i.mission_id=m.id
                 WHERE m.store_id IN ({ids}) AND i.week<=COALESCE(m.end_week,999)""")
        ans = f"{r['n']} launched missions have delivered {money(r['v'])} of net impact vs control stores."
    elif "mission" in ql and ("my" in ql or "live" in ql or "how" in ql):
        rows = db.rows(c, f"SELECT * FROM missions WHERE status='live' AND store_id IN ({ids}) LIMIT 8")
        ans = "Live missions: " + "; ".join(f"{m['title']} → {money(mission_impact_summary(c, m['id'])['cumulative'])}" for m in rows) if rows else "No live missions."
    elif "theme" in ql or "survey" in ql or "walk" in ql:
        rows = db.rows(c, "SELECT * FROM themes ORDER BY week DESC, count DESC LIMIT 5")
        ans = "Recurring themes from store walks and comments: " + "; ".join(f"{t['label']} ({t['count']} stores, {t['scope']})" for t in rows) if rows else "No themes yet."
    elif "task" in ql or "overdue" in ql:
        rows = db.rows(c, f"SELECT t.*, s.code FROM tasks t JOIN stores s ON s.id=t.store_id WHERE t.status='open' AND t.store_id IN ({ids}) ORDER BY t.due LIMIT 8")
        ans = f"{len(rows)} open tasks (soonest first): " + "; ".join(f"{t['code']} {t['title']} due {t['due']}" for t in rows)
    else:
        ans = ("I can answer questions like: 'which stores have the worst waste?', 'how are my live missions doing?', "
               "'what is our impact so far?', 'what themes are coming from store walks?', 'what tasks are overdue?', "
               "'what works for attachment rate?'. ")
        ans += briefing(c, user, scope_store_ids)
    return {"answer": llm("You are an operations assistant. Answer from the facts only.", {"q": q, "rows": rows[:5]}, ans),
            "rows": rows[:10], "sources": sources or [f"Live data · week {week}"]}

def extract_themes(c, week, lookback=4):
    """Theme extraction over free text (store-walk answers, rejection reasons, comments, load flags).
    Concept dictionary + n-gram fallback; a theme seen in >=3 stores of a district becomes a Theme mission
    for the district manager (an 'AI mission trigger')."""
    texts = []
    for r in db.rows(c, "SELECT store_id, answers, week FROM survey_responses WHERE week>=?", (week - lookback,)):
        for v in db.J(r["answers"], {}).values():
            if isinstance(v, str) and len(v) > 8: texts.append((r["store_id"], v, "store walk"))
    for r in db.rows(c, "SELECT store_id, reason FROM missions WHERE status='rejected' AND reason IS NOT NULL AND created_week>=?", (week - lookback,)):
        texts.append((r["store_id"], r["reason"], "mission rejection"))
    for r in db.rows(c, "SELECT entity_id, text FROM comments WHERE entity='visit'"):
        v = db.one(c, "SELECT store_id FROM visits WHERE id=?", (r["entity_id"],))
        if v: texts.append((v["store_id"], r["text"], "visit notes"))
    for r in db.rows(c, "SELECT store_id, note FROM load_flags"):
        if r["note"]: texts.append((r["store_id"], r["note"], "load flags"))
    S = {s["id"]: s for s in db.rows(c, "SELECT * FROM stores")}
    by = defaultdict(lambda: defaultdict(set)); src = defaultdict(set); kw = defaultdict(Counter)
    for sid, t, so in texts:
        tl = t.lower()
        for concept, words in SURVEY_CONCEPTS.items():
            hits = [w for w in words if re.search(r"\b" + re.escape(w) + r"\b", tl)]
            if hits:
                d = S[sid]["district_id"]; by[d][concept].add(sid); src[(d, concept)].add(so); kw[(d, concept)].update(hits)
    c.execute("DELETE FROM themes WHERE week=?", (week,))
    made = 0
    for d, concepts in by.items():
        dn = db.one(c, "SELECT name FROM districts WHERE id=?", (d,))["name"]
        for concept, stores in concepts.items():
            if len(stores) < 3: continue
            label = f"{concept} reported across {dn} district"
            cur = c.execute("INSERT INTO themes(week,scope,scope_id,label,keywords,stores,count,source) VALUES(?,?,?,?,?,?,?,?)",
                            (week, f"District {dn}", d, label, json.dumps([k for k, _ in kw[(d, concept)].most_common(5)]),
                             json.dumps(sorted(stores)), len(stores), ", ".join(sorted(src[(d, concept)]))))
            dm = db.one(c, "SELECT id FROM users WHERE role='district_manager' AND district_id=?", (d,))
            exists = db.one(c, "SELECT id FROM missions WHERE kind='theme' AND title=? AND status IN ('incoming','prelaunch','proposed','live')", (label,))
            if dm and not exists:
                anchor = sorted(stores)[0]
                mid = create_mission(c, dict(store_id=anchor, owner_id=dm["id"], kind="theme", kpi="custom", title=label,
                    status="incoming", source="ai_theme", created_week=week, priority="Should", due_week=week + 1,
                    baseline_gap=0, target_weekly=0,
                    comment=f"AI found this theme in {len(stores)} stores ({', '.join(S[x]['code'] for x in sorted(stores))}) from {', '.join(sorted(src[(d, concept)]))}. Keywords: {', '.join(k for k,_ in kw[(d, concept)].most_common(5))}.",
                    ai_context=json.dumps({"stores": sorted(stores), "concept": concept})))
                c.execute("UPDATE themes SET mission_id=? WHERE id=?", (mid, cur.lastrowid)); made += 1
    c.commit(); return made

def run_agent(c):
    """The AI agent works tasks assigned to it (data look-ups), and reports back — humans + agents in one queue."""
    agent = db.one(c, "SELECT id FROM users WHERE role='ai_agent'")
    if not agent: return 0
    n = 0
    week = db.setting(c, "current_week")
    for t in db.rows(c, "SELECT * FROM tasks WHERE assignee_id=? AND status='open'", (agent["id"],)):
        wd = WeekData(c, week, 1)
        s = db.one(c, "SELECT * FROM stores WHERE id=?", (t["store_id"],))
        lines = []
        for k in ["labor", "overtime", "csat", "conversion", "invacc"]:
            g = metric_gap(wd, s["id"], k)
            if g: lines.append(f"{KPIS[k]['label']}: {g['actual']:.1f} vs peers {g['expected']:.1f}")
        rep = f"Agent summary for {s['code']}: " + "; ".join(lines)
        c.execute("UPDATE tasks SET status='done', completed=?, answers=? WHERE id=?", (now_iso(), json.dumps({"agent_report": rep}), t["id"]))
        c.execute("INSERT INTO comments(entity,entity_id,user_id,text,ts) VALUES('task',?,?,?,?)", (t["id"], agent["id"], rep, now_iso()))
        log(c, "task", t["id"], agent["id"], "completed by AI agent", ""); n += 1
    c.commit(); return n

def org_context(c):
    """The 'context & memory' layer: org graph + KPI catalogue + learned effectiveness, exportable for agents (MCP)."""
    return {"regions": db.rows(c, "SELECT * FROM regions"), "districts": db.rows(c, "SELECT * FROM districts"),
            "store_count": db.one(c, "SELECT COUNT(*) n FROM stores")["n"], "kpis": KPIS,
            "learned_actions": {k: action_stats(c, k) for k in KPIS},
            "guardrails": db.setting(c, "guardrails", ["Never assign more than inbox_size missions per store",
                                                        "No missions during blackout periods",
                                                        "Protect stores at capacity"])}
