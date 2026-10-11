"""In-app help centre + support assistant. Articles are plain data; search is keyword/TF scoring (no external calls)."""
import re, math
from collections import Counter

ARTICLES = [
 ("getting-started", "Get to your first missions in 10 minutes", "Onboarding",
  "Open Get started (HQ admin). 1) Name your workspace. 2) Upload a stores CSV with code, name, format (and optional district, tags). "
  "3) Upload weekly category sales: store code, category, sales and a week number or date. At least 2 weeks, 4+ stores per format. "
  "4) Optionally upload store KPIs (traffic, transactions, labor hours, labor budget, CSAT). 5) Press Find my first missions. "
  "Download the sample files on each step if you want to try it with example data first.", "#/onboarding"),
 ("csv-mapping", "Uploading CSV files and mapping columns", "Data",
  "Go to Architect > Data & uploads, choose what the file contains, pick the file and press Preview & map columns. ColsTorso guesses "
  "the mapping from your column names (for example Net Sales -> sales, Store -> store_code). Fix any guesses, then Load & recompute. "
  "Every row is validated; unknown stores are skipped and listed under Data quality issues. New categories are created automatically.", "#/architect/data"),
 ("missions", "What a mission is and why I'm seeing it", "Missions",
  "A mission is one specific opportunity for one store, found by comparing the store with similar stores (same format, similar space). "
  "Each card says why you're seeing it, what it is worth per week if fixed, the effort and how confident we are. At most 3 are suggested "
  "per store at a time so the list stays doable.", "#/missions"),
 ("accept", "Accept, snooze or 'not for my store'", "Missions",
  "Accept starts the mission with a pre-filled plan (the action that worked best elsewhere) and a task for you. Snooze hides it for a week. "
  "Not for my store asks for a reason; HQ sees every reason under Store feedback and on the Campaigns page.", "#/home"),
 ("impact", "How impact is measured", "Impact",
  "When you accept, ColsTorso fixes a comparison group of up to 12 similar stores not doing the same mission. Each week it counts how much your "
  "gap closed minus how much theirs moved on its own (difference-in-differences). The likely range is a 90% range based on how much the "
  "comparison stores move with no mission. Worked = the whole range is above zero.", "#/impact"),
 ("freshness", "Data age and freshness labels", "Data",
  "The strip under the top bar shows each feed's age. Daily feeds are fresh under 30 hours, ageing from 30 to 54 hours and stale after that. "
  "Weekly labor and store KPIs are stale after 8 days. Stale data does not stop missions but you should treat new suggestions with care.", "#/home"),
 ("campaigns", "HQ campaigns and Must-do limits", "HQ",
  "Campaigns point stores at a KPI or category for some weeks. Gentle and Standard boost matching missions; Must-do skips the queue. "
  "Only 3 Must-do campaigns can be active per quarter (change it under Architect > Settings). A few matching stores are held back as a "
  "comparison group so seasonal lift isn't counted as campaign impact.", "#/campaigns"),
 ("tasks", "Tasks, store walks and checklists", "Tasks",
  "Tasks come from mission plans, schedules, data conditions, events and CSV schedules. Store walks and audits are surveys whose questions can "
  "depend on earlier answers, store tags and live performance. A 'No' can create a follow-up task automatically.", "#/tasks"),
 ("roles", "Roles and switching users", "Admin",
  "Store managers see their store; district and regional managers see their stores and can compare them; HQ sees everything and steers "
  "campaigns. Use Switch user (bottom of the menu) to try each role in the demo. Permissions are edited in Architect > People & permissions.", "#/architect/users"),
 ("reset", "Resetting the demo", "Admin",
  "Reset demo data (in the freshness strip) rebuilds the synthetic 50-store tenant. Nothing in the demo is real data.", "#/home"),
 ("ai", "Ask ColsTorso (AI assistant)", "AI",
  "Ask questions about your stores in plain words, e.g. 'What should I focus on this week?' or 'Why is labor over budget?'. Every answer lists "
  "the data it used. It works offline with built-in rules; an LLM can be switched on with COLSTORSO_LLM_URL and answers are cached.", "#/ask"),
 ("costs", "Running costs", "Admin",
  "ColsTorso runs as one small container with SQLite. The mission engine runs once per data load (batch), not per page view. LLM use is off by "
  "default; when on, answers are cached and capped per process.", "#/architect/integrations"),
]
TOK = re.compile(r"[a-z0-9']+")
STOP = set("a an the to of and or in on for is it i my me do how what why where can with at be this that are from".split())
def toks(s): return [t for t in TOK.findall(s.lower()) if t not in STOP]
_DOCS = [(a, Counter(toks(a[1] + " " + a[1] + " " + a[2] + " " + a[3]))) for a in ARTICLES]
_DF = Counter(t for _, tf in _DOCS for t in tf)

def search(q, k=3):
    qt = toks(q); N = len(_DOCS); out = []
    for a, tf in _DOCS:
        s = sum((1 + math.log(tf[t])) * math.log(1 + N / _DF[t]) for t in qt if tf[t])
        if s > 0: out.append((s, a))
    return [dict(id=a[0], title=a[1], section=a[2], body=a[3], link=a[4], score=round(s, 2)) for s, a in sorted(out, key=lambda x: -x[0])[:k]]

HOWTO = re.compile(r"\b(how (do|can|to)|where (do|is|can)|what is a|help|upload|import|csv|reset|onboard|get started|set ?up|switch user|permission|campaign limit|likely range|fresh|stale)\b", re.I)
def is_howto(q): return bool(HOWTO.search(q))

def answer(q):
    hits = search(q)
    if not hits: return dict(answer="I couldn't find a help article for that. Try words like upload, mission, impact, campaign or tasks.", articles=[], sources=["Help centre"])
    top = hits[0]
    return dict(answer=f"**{top['title']}**\n\n{top['body']}", articles=hits, sources=[f"Help: {h['title']}" for h in hits[:2]])
