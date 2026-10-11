"""Browser e2e of the self-serve wizard on a throwaway server: blank workspace -> 3 sample CSVs -> first missions. Times it."""
import sys, time, urllib.request, os
from playwright.sync_api import sync_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8200"
tmp = "/tmp/ct-ob"; os.makedirs(tmp, exist_ok=True)
for n in ("stores", "sales", "store"):
    open(f"{tmp}/{n}.csv", "wb").write(urllib.request.urlopen(f"{BASE}/api/onboarding/sample/{n}.csv").read())
errs = []; t0 = time.time()
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1440, "height": 1700})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/#/login"); pg.wait_for_selector(".persona"); pg.evaluate("login(1)"); pg.wait_for_timeout(800)
    pg.goto(BASE + "/#/onboarding"); pg.wait_for_timeout(1000)
    pg.fill("#obc", "Harbor Test Co"); pg.click("button:has-text('Start a blank workspace')"); pg.click(".modal button.btn-primary"); pg.wait_for_timeout(2500)
    for t, n in (("stores", "stores"), ("sales", "sales"), ("store", "store")):
        pg.set_input_files(f"#obf-{t}", f"{tmp}/{n}.csv"); pg.click(f"#obf-{t} + button"); pg.wait_for_selector(f"#obm-{t} button.btn-primary")
        pg.click(f"#obm-{t} button.btn-primary"); pg.wait_for_timeout(2500)
    pg.screenshot(path="screenshots/onboarding-loaded.png")
    pg.click("button:has-text('Find my first missions')"); pg.wait_for_selector("#obr .notice", timeout=20000)
    print(pg.inner_text("#obr"))
    pg.screenshot(path="screenshots/onboarding-done.png")
    pg.click("#obr button.btn-secondary"); pg.wait_for_timeout(2000)
    pg.screenshot(path="screenshots/onboarding-store-today.png")
    print("cards on store Today:", len(pg.query_selector_all("article.mission")))
    b.close()
print("errors:", errs, "wall time s:", round(time.time() - t0, 1))
