"""Render mockup PNGs with headless Chrome (Playwright). Usage: python render.py [filter...]"""
import sys, os
from playwright.sync_api import sync_playwright
HERE = os.path.dirname(os.path.abspath(__file__)); D = os.path.abspath(os.path.join(HERE, ".."))
M, OUT = f"{D}/mockups", f"{D}/png"
# (page, width, annotate, theme, out)
JOBS = [
 ("a-store-today", 390, 0, "", "a-store-today-390"), ("a-store-today", 1440, 0, "", "a-store-today-1440"),
 ("a-store-today", 390, 1, "", "a-store-today-390-annotated"), ("a-store-today", 390, 0, "dark", "a-store-today-390-dark"),
 ("b-mission-detail", 390, 0, "", "b-mission-detail-390"), ("b-mission-detail", 1440, 0, "", "b-mission-detail-1440"),
 ("b-mission-detail", 390, 1, "", "b-mission-detail-390-annotated"),
 ("c-regional-compare", 1440, 0, "", "c-regional-compare-1440"), ("c-regional-compare", 390, 0, "", "c-regional-compare-390"),
 ("c-regional-compare", 1440, 1, "", "c-regional-compare-1440-annotated"),
 ("d-hq-campaigns", 1440, 0, "", "d-hq-campaigns-1440"), ("d-hq-campaigns", 390, 0, "", "d-hq-campaigns-390"),
 ("d-hq-campaigns", 1440, 1, "", "d-hq-campaigns-1440-annotated"),
 ("e-impact", 1440, 0, "", "e-impact-1440"), ("e-impact", 390, 0, "", "e-impact-390"),
 ("e-impact", 1440, 1, "", "e-impact-1440-annotated"),
 ("f-tasks", 390, 0, "", "f-tasks-390"), ("f-tasks", 1440, 0, "", "f-tasks-1440"),
 ("f-tasks", 390, 1, "", "f-tasks-390-annotated"), ("f-tasks", 390, 0, "dark", "f-tasks-390-dark"),
]
only = sys.argv[1:]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    for page, w, ann, theme, out in JOBS:
        if only and not any(o in out for o in only): continue
        if not os.path.exists(f"{M}/{page}.html"): continue
        vw = w + 32 * 3 + 460 if ann else w
        mobile = (w < 500 and not ann)
        ctx = b.new_context(viewport={"width": vw, "height": 844 if w < 500 else 900}, device_scale_factor=2 if w < 500 else 1,
                            is_mobile=mobile, has_touch=mobile)
        pg = ctx.new_page()
        qs = f"?shot=1&frame={w}" + ("&annotate=1" if ann else "") + (f"&theme={theme}" if theme else "")
        pg.goto(f"file://{M}/{page}.html{qs}"); pg.wait_for_timeout(700)
        pg.evaluate("document.fonts.ready"); pg.wait_for_timeout(200)
        if ann: pg.evaluate("window.dispatchEvent(new Event('resize'))"); pg.wait_for_timeout(200)
        sw = pg.evaluate("document.documentElement.scrollWidth")
        over = pg.evaluate("""() => { const W = document.querySelector('.ct-app').getBoundingClientRect().right + 1; const r = [];
          document.querySelectorAll('.ct-app *').forEach(e => { const b = e.getBoundingClientRect(); if (b.width && b.right > W && getComputedStyle(e).position!=='fixed') r.push((e.className && e.className.baseVal===undefined ? e.className : e.tagName) + ':' + Math.round(b.right - W)); });
          return r.slice(0, 6); }""")
        small = pg.evaluate("""() => { const r=[]; document.querySelectorAll('.ct-app button, .ct-app a').forEach(e=>{const b=e.getBoundingClientRect(); if(b.width && (b.height<24||b.width<24)) r.push((e.textContent||e.getAttribute('aria-label')||'').trim().slice(0,20)+':'+Math.round(b.width)+'x'+Math.round(b.height));}); return r.slice(0,6);}""")
        pg.screenshot(path=f"{OUT}/{out}.png", full_page=True)
        print(f"{out}.png vw={vw} scrollW={sw} overflow={over} small={small}")
        ctx.close()
    b.close()
