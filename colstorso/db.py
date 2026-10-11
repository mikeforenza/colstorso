"""SQLite schema + helpers for ColsTorso (original, from-scratch store-ops platform)."""
import sqlite3, json, os, threading

DB_PATH = os.environ.get("COLSTORSO_DB", os.path.join(os.path.dirname(__file__), "..", "data", "colstorso.db"))
_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS llm_cache(k TEXT PRIMARY KEY, v TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS feeds(name TEXT PRIMARY KEY, cadence TEXT, loaded_at TEXT, data_through TEXT);
CREATE TABLE IF NOT EXISTS regions(id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS districts(id INTEGER PRIMARY KEY, name TEXT, region_id INT);
CREATE TABLE IF NOT EXISTS stores(id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, district_id INT, format TEXT,
  sqft INT, status TEXT DEFAULT 'Open', tags TEXT DEFAULT '[]', capacity_hours REAL DEFAULT 40, city TEXT, lat REAL, lon REAL);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT, role TEXT, store_id INT, district_id INT,
  region_id INT, dc_id INT, last_login TEXT, active INT DEFAULT 1, profile TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY, name TEXT, parent_id INT, first_seen_week INT);
CREATE TABLE IF NOT EXISTS space(store_id INT, cat_id INT, share REAL, PRIMARY KEY(store_id, cat_id));
CREATE TABLE IF NOT EXISTS weeks(week INT PRIMARY KEY, start_date TEXT);
CREATE TABLE IF NOT EXISTS fact_sales(store_id INT, week INT, cat_id INT, sales REAL, units REAL, waste REAL,
  ly_sales REAL, PRIMARY KEY(store_id, week, cat_id));
CREATE TABLE IF NOT EXISTS fact_store(store_id INT, week INT, traffic REAL, transactions REAL, labor_hours REAL,
  labor_budget REAL, overtime_hours REAL, csat REAL, attach_rate REAL, cash_over_short REAL, gap_scan_pct REAL,
  inv_accuracy REAL, budget_sales REAL, PRIMARY KEY(store_id, week));
CREATE TABLE IF NOT EXISTS gen_state(store_id INT, key TEXT, value REAL, PRIMARY KEY(store_id, key));
CREATE TABLE IF NOT EXISTS opportunities(id INTEGER PRIMARY KEY, week INT, store_id INT, kpi TEXT, cat_id INT,
  kind TEXT, title TEXT, actual REAL, expected REAL, gap_value REAL, z REAL, score REAL, peer_count INT, scaler TEXT,
  detail TEXT DEFAULT '{}', substitution INT DEFAULT 0, prioritized INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_opp ON opportunities(week, store_id);
CREATE TABLE IF NOT EXISTS missions(id INTEGER PRIMARY KEY, opp_id INT, store_id INT, owner_id INT, kind TEXT,
  kpi TEXT, cat_id INT, title TEXT, status TEXT, reason TEXT, snooze_until INT, root_causes TEXT DEFAULT '[]',
  action_type TEXT, action TEXT, target_weekly REAL, baseline_gap REAL, start_week INT, end_week INT, duration INT DEFAULT 4,
  approval TEXT DEFAULT 'none', approver_id INT, campaign_id INT, source TEXT, created_by INT, created_week INT,
  created_at TEXT, priority TEXT DEFAULT 'Should', due_week INT, comment TEXT, ai_context TEXT, kudos INT DEFAULT 0,
  control_ids TEXT, accepted_at TEXT, impact_detail TEXT);
CREATE INDEX IF NOT EXISTS ix_mis ON missions(store_id, status);
CREATE TABLE IF NOT EXISTS mission_tasks(id INTEGER PRIMARY KEY, mission_id INT, title TEXT, assignee_id INT, due TEXT, done INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS impact(mission_id INT, week INT, gap REAL, improvement REAL, control_improvement REAL,
  net REAL, PRIMARY KEY(mission_id, week));
CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY, entity TEXT, entity_id INT, user_id INT, text TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY, entity TEXT, entity_id INT, user_id INT, action TEXT, detail TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS best_practices(id INTEGER PRIMARY KEY, mission_id INT, user_id INT, store_id INT, title TEXT,
  body TEXT, kpi TEXT, cat_id INT, action_type TEXT, impact_value REAL, likes INT DEFAULT 0, ts TEXT);
CREATE TABLE IF NOT EXISTS bp_adopt(bp_id INT, store_id INT, user_id INT, mission_id INT, ts TEXT);
CREATE TABLE IF NOT EXISTS task_templates(id INTEGER PRIMARY KEY, name TEXT, title TEXT, body_md TEXT, questions TEXT DEFAULT '[]',
  est_minutes INT DEFAULT 15, assignee_role TEXT DEFAULT 'store_manager', attachments TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS task_rules(id INTEGER PRIMARY KEY, name TEXT, trigger_type TEXT, config TEXT, template_id INT,
  target TEXT DEFAULT '{}', due_days INT DEFAULT 3, escalate_after_days INT DEFAULT 2, active INT DEFAULT 1, last_run TEXT);
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, rule_id INT, template_id INT, store_id INT, assignee_role TEXT,
  assignee_id INT, title TEXT, body_md TEXT, questions TEXT, due TEXT, status TEXT DEFAULT 'open', created TEXT,
  completed TEXT, answers TEXT DEFAULT '{}', escalated INT DEFAULT 0, est_minutes INT DEFAULT 15, context TEXT DEFAULT '{}',
  source TEXT, attachments TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS surveys(id INTEGER PRIMARY KEY, name TEXT, kind TEXT DEFAULT 'storewalk', questions TEXT,
  trigger TEXT DEFAULT '{}', target TEXT DEFAULT '{}', active INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS survey_responses(id INTEGER PRIMARY KEY, survey_id INT, store_id INT, user_id INT, ts TEXT,
  week INT, answers TEXT, visit_id INT, score REAL);
CREATE TABLE IF NOT EXISTS visits(id INTEGER PRIMARY KEY, dm_id INT, store_id INT, date TEXT, status TEXT DEFAULT 'planned',
  notes TEXT, coaching TEXT DEFAULT '[]', agreed_actions TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS campaigns(id INTEGER PRIMARY KEY, name TEXT, kpis TEXT, categories TEXT DEFAULT '[]', boost REAL,
  start_week INT, end_week INT, target TEXT DEFAULT '{}', active INT DEFAULT 1, created_by INT, message TEXT,
  push TEXT DEFAULT 'standard', holdout TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS blackouts(id INTEGER PRIMARY KEY, name TEXT, start_date TEXT, end_date TEXT, target TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY, title TEXT, body TEXT, target TEXT DEFAULT '{}', author_id INT,
  ts TEXT, priority TEXT DEFAULT 'normal', require_ack INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS announcement_reads(ann_id INT, user_id INT, ts TEXT, PRIMARY KEY(ann_id, user_id));
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, user_id INT, text TEXT, link TEXT, read INT DEFAULT 0, ts TEXT);
CREATE TABLE IF NOT EXISTS mission_rules(id INTEGER PRIMARY KEY, name TEXT, metric TEXT, op TEXT, threshold REAL,
  kind TEXT DEFAULT 'alert', title TEXT, guidance TEXT, target TEXT DEFAULT '{}', assignee_role TEXT DEFAULT 'store_manager',
  priority TEXT DEFAULT 'Must', followup_rule_id INT, active INT DEFAULT 1, trigger_type TEXT DEFAULT 'condition');
CREATE TABLE IF NOT EXISTS data_issues(id INTEGER PRIMARY KEY, ts TEXT, upload_id INT, severity TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS uploads(id INTEGER PRIMARY KEY, ts TEXT, filename TEXT, target TEXT, rows INT, mapping TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS dcs(id INTEGER PRIMARY KEY, name TEXT, city TEXT);
CREATE TABLE IF NOT EXISTS pallets(id TEXT PRIMARY KEY, dc_id INT, store_id INT, week INT, picker TEXT, picker_tenure_m INT,
  loader TEXT, shift TEXT);
CREATE TABLE IF NOT EXISTS load_flags(id INTEGER PRIMARY KEY, pallet_id TEXT, store_id INT, user_id INT, issue_type TEXT,
  note TEXT, photo TEXT, ts TEXT, status TEXT DEFAULT 'open', resolution TEXT, mission_id INT);
CREATE TABLE IF NOT EXISTS themes(id INTEGER PRIMARY KEY, week INT, scope TEXT, scope_id INT, label TEXT, keywords TEXT,
  stores TEXT, count INT, source TEXT, mission_id INT);
CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, name TEXT, path TEXT, mime TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS logins(user_id INT, ts TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, type TEXT, payload TEXT, ts TEXT, result TEXT);
"""

MIGRATIONS = [("missions", "control_ids", "TEXT"), ("missions", "accepted_at", "TEXT"), ("missions", "impact_detail", "TEXT"),
              ("campaigns", "push", "TEXT DEFAULT 'standard'"), ("campaigns", "holdout", "TEXT DEFAULT '[]'")]

def connect(path=None):
    p = path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    c = sqlite3.connect(p, check_same_thread=False, timeout=30, isolation_level=None)  # autocommit: no request can leave a lock open
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA synchronous=NORMAL")
    c.executescript(SCHEMA)
    for t, col, typ in MIGRATIONS:
        try: c.execute(f"ALTER TABLE {t} ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError: pass
    return c

GEN = [0]   # bumped when the database file is rebuilt (demo reset) so every thread reconnects

def get():
    c = getattr(_local, "conn", None)
    if c is None or getattr(_local, "path", None) != DB_PATH or getattr(_local, "gen", -1) != GEN[0]:
        if c is not None:
            try: c.close()
            except Exception: pass
        c = connect(DB_PATH); _local.conn = c; _local.path = DB_PATH; _local.gen = GEN[0]
    return c

def rows(c, sql, args=()):
    return [dict(r) for r in c.execute(sql, args).fetchall()]

def one(c, sql, args=()):
    r = c.execute(sql, args).fetchone()
    return dict(r) if r else None

def setting(c, key, default=None):
    r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if not r: return default
    try: return json.loads(r[0])
    except Exception: return r[0]

def set_setting(c, key, value):
    c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value))); c.commit()

def J(s, default=None):
    if s is None: return default
    try: return json.loads(s)
    except Exception: return default
