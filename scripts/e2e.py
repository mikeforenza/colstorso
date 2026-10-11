"""Headless browser walk-through: every page for every role, fails on JS errors / error toasts; saves screenshots."""
import sys, json, re
from playwright.sync_api import sync_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8100"
SHOTS = "screenshots"
ROUTES = {
  11: ["home", "missions", "tasks", "walks", "business", "kpi/labor", "pnl", "team", "bp", "comms", "dc", "ask", "notifications", "coaching"],
  5: ["home", "team", "visits", "missions", "impact", "pushback", "business", "tasks/analytics"],
  3: ["home", "team", "impact"],
  1: ["onboarding", "home", "campaigns", "impact", "pushback", "architect/data", "architect/missions", "architect/tasks", "architect/surveys", "architect/stores", "architect/users", "architect/settings", "architect/integrations", "tasks/send", "kpi/total_sales/rank", "kpi/waste/opps", "pnl/biggest"],
}
errors = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    for dark in (False,):
        pg = b.new_page(viewport={"width": 1440, "height": 1000}, color_scheme="dark" if dark else "light")
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on("console", lambda m: m.type == "error" and errors.append(f"console: {m.text}"))
        pg.goto(BASE + "/#/login"); pg.wait_for_selector(".persona")
        users = {u["role"]: u for u in pg.evaluate("fetch('/api/users').then(r=>r.json())")}
        for uid, routes in ROUTES.items():
            pg.evaluate(f"login({uid})"); pg.wait_for_timeout(800)
            for r in routes:
                pg.goto(f"{BASE}/#/{r}"); pg.wait_for_timeout(900)
                pg.wait_for_load_state("networkidle")
                t = pg.inner_text("#content") if pg.query_selector("#content") else ""
                if "Couldn't load" in t: errors.append(f"user {uid} {r}: {t[:200]}")
                bad = pg.query_selector_all(".toast.err")
                for e in bad: errors.append(f"user {uid} {r}: toast {e.inner_text()}")
                name = f"{SHOTS}/u{uid}-{r.replace('/', '-')}.png"
                pg.set_viewport_size({"width": 1440, "height": min(2400, pg.evaluate("document.documentElement.scrollHeight"))}); pg.screenshot(path=name); pg.set_viewport_size({"width": 1440, "height": 1000})
        # mission detail for store manager + one live mission
        pg.evaluate("login(11)"); pg.wait_for_timeout(800)
        mids = pg.evaluate("api('/api/missions?status=incoming,live,done').then(r=>r.map(m=>[m.id,m.status]))")
        for st in ("incoming", "live", "done"):
            m = next((x for x in mids if x[1] == st), None)
            if m:
                pg.goto(f"{BASE}/#/mission/{m[0]}"); pg.wait_for_timeout(1800)
                pg.screenshot(path=f"{SHOTS}/u11-mission-{st}.png", full_page=False)
        # interactions: one-tap accept / snooze / not for my store from Today
        pg.goto(BASE + "/#/home"); pg.wait_for_timeout(1200)
        n0 = len(pg.query_selector_all("article.mission"))
        btn = pg.query_selector("article.mission button.btn-primary")
        if btn: btn.click(); pg.wait_for_timeout(1500)
        btn = pg.query_selector("article.mission button.btn-secondary")
        if btn: btn.click(); pg.wait_for_timeout(1500)
        more = pg.query_selector("article.mission button[aria-label=More]")
        if more:
            more.click(); pg.wait_for_timeout(500); pg.click("text=Not for my store >> nth=-1"); pg.wait_for_timeout(1500)
        print("cards before/after one-tap actions:", n0, len(pg.query_selector_all("article.mission")))
        pg.screenshot(path=f"{SHOTS}/u11-home-after-actions.png", full_page=False)
        # dark mode
        pg.emulate_media(color_scheme="dark"); pg.evaluate("localStorage.removeItem('ct_theme'); applyTheme()")
        pg.goto(BASE + "/#/home"); pg.wait_for_timeout(1200); print("theme follows device:", pg.evaluate("document.documentElement.dataset.theme"))
        pg.screenshot(path=f"{SHOTS}/u11-home-dark.png", full_page=False)
        pg.evaluate("toggleTheme()"); print("after toggle:", pg.evaluate("document.documentElement.dataset.theme")); pg.evaluate("localStorage.removeItem('ct_theme')")
        pg.evaluate("openHelp('how do I upload a csv')"); pg.wait_for_timeout(1500)
        pg.screenshot(path=f"{SHOTS}/u11-help-panel.png"); pg.evaluate("document.querySelectorAll('.drawer').forEach(d=>d.remove())")
        mob = b.new_page(viewport={"width": 390, "height": 844}, color_scheme="light")
        mob.goto(BASE + "/#/login"); mob.wait_for_selector(".persona"); mob.evaluate("login(12)"); mob.wait_for_timeout(1500)
        mob.screenshot(path=f"{SHOTS}/mobile-store-today.png", full_page=False)
        b.close()
print(json.dumps(errors, indent=1)); print("ERRORS:", len(errors))
