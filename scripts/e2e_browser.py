"""E2E against the static WebAssembly build (no backend): core loop, uploads, onboarding, AI, persistence across reload."""
import sys, time, json
from playwright.sync_api import sync_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8300/browser/"
errs = []; t0 = time.time()
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1440, "height": 1100}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append("pageerror " + str(e)))
    pg.on("console", lambda m: m.type == "error" and errs.append("console " + m.text[:200]))
    pg.goto(BASE + "#/login"); pg.wait_for_selector(".persona", timeout=120000)
    print("boot to login s:", round(time.time() - t0, 1))
    sm = pg.evaluate("api('/api/users').then(u=>u.find(x=>x.role==='store_manager').id)")
    pg.evaluate(f"login({sm})"); pg.wait_for_selector("article.mission", timeout=30000)
    pg.screenshot(path="screenshots/browser-build-today.png")
    n0 = len(pg.query_selector_all("article.mission"))
    pg.click("article.mission button.btn-primary"); pg.wait_for_timeout(2500)
    mid = pg.evaluate("api('/api/missions?status=live').then(r=>r[0].id)")
    pg.goto(BASE + f"#/mission/{mid}"); pg.wait_for_timeout(2500); pg.screenshot(path="screenshots/browser-build-mission.png")
    pg.goto(BASE + "#/home"); pg.wait_for_timeout(1500)
    more = pg.query_selector("article.mission button[aria-label=More]")
    if more: more.click(); pg.wait_for_timeout(400); pg.click(".modal button.btn-primary"); pg.wait_for_timeout(2000)
    print("cards", n0, "->", len(pg.query_selector_all("article.mission")))
    r = pg.evaluate("post('/api/ai/ask',{q:'Why is labor over budget?'})"); print("ai sources:", r.get("sources"))
    h = pg.evaluate("post('/api/help/ask',{q:'how do I upload a csv'})"); print("help:", h["articles"][0]["title"])
    pg.reload(); pg.wait_for_selector("#app .shell, .persona", timeout=120000); pg.wait_for_timeout(1500)
    live = pg.evaluate(f"api('/api/missions/{mid}').then(m=>m.status)"); print("after reload mission status (persisted):", live)
    pg.evaluate("login(1)"); pg.wait_for_timeout(2000)
    for r_ in ["impact", "pushback", "campaigns", "architect/data", "tasks", "business", "ask"]:
        pg.goto(BASE + "#/" + r_); pg.wait_for_timeout(2500)
        if "Couldn't load" in pg.inner_text("#content"): errs.append("page " + r_)
        if r_ in ("impact", "campaigns", "pushback"): pg.screenshot(path=f"screenshots/browser-build-{r_}.png")
    # onboarding with sample files through the real wizard
    import urllib.request, os
    os.makedirs("/tmp/ct-ob", exist_ok=True)
    for n in ("stores", "sales", "store"):
        txt = pg.evaluate(f"fetch('/api/onboarding/sample/{n}.csv').then(r=>r.text())"); open(f"/tmp/ct-ob/{n}.csv", "w").write(txt)
    pg.goto(BASE + "#/onboarding"); pg.wait_for_selector("#obc")
    pg.fill("#obc", "Browser Test Co"); pg.click("button:has-text('Start a blank workspace')"); pg.click(".modal button.btn-primary"); pg.wait_for_timeout(3000)
    for t in ("stores", "sales", "store"):
        pg.set_input_files(f"#obf-{t}", f"/tmp/ct-ob/{t}.csv"); pg.click(f"#obf-{t} + button"); pg.wait_for_selector(f"#obm-{t} button.btn-primary")
        pg.click(f"#obm-{t} button.btn-primary"); pg.wait_for_timeout(4000)
    pg.click("button:has-text('Find my first missions')"); pg.wait_for_selector("#obr .notice", timeout=30000)
    print("onboarding:", pg.inner_text("#obr").split("\n")[0])
    pg.screenshot(path="screenshots/browser-build-onboarding.png")
    # reset back to demo
    pg.evaluate("post('/api/admin/reset')"); print("reset ok")
    b.close()
print("errors:", json.dumps(errs, indent=1), "total s:", round(time.time() - t0, 1))
