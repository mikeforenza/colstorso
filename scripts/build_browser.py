"""Build dist/browser/: a static site that runs the real ColsTorso app (same Python engine + SQLite) in WebAssembly.
Deploy the folder to any static host (GitHub Pages, Netlify, Cloudflare Pages) or open it with any static file server."""
import os, re, shutil, subprocess, gzip, zipfile, sys, glob, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "dist", "browser")
PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/"
shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
# 1. fresh demo snapshot (synthetic data only)
tmpdb = os.path.join(OUT, "_seed.db")
subprocess.run([sys.executable, "-m", "colstorso.seed"], cwd=ROOT, check=True, env=dict(os.environ, COLSTORSO_DB=tmpdb), stdout=subprocess.DEVNULL)
import sqlite3
c = sqlite3.connect(tmpdb); c.execute("PRAGMA wal_checkpoint(TRUNCATE)"); c.execute("PRAGMA journal_mode=DELETE"); c.execute("VACUUM"); c.close()
with open(tmpdb, "rb") as f, gzip.open(os.path.join(OUT, "demo.db.gz"), "wb", 9) as g: g.write(f.read())
for e in ("", "-wal", "-shm"):
    if os.path.exists(tmpdb + e): os.remove(tmpdb + e)
# 2. the app's Python package + browser shim, zipped
with zipfile.ZipFile(os.path.join(OUT, "app.zip"), "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(glob.glob(os.path.join(ROOT, "colstorso", "*.py"))): z.write(f, "colstorso/" + os.path.basename(f))
    z.write(os.path.join(ROOT, "browser", "ct_browser.py"), "ct_browser.py")
# python-multipart wheel (Apache-2.0), vendored so uploads work without PyPI
whl = os.path.join(OUT, "python_multipart-0.0.32-py3-none-any.whl")
idx = urllib.request.urlopen("https://pypi.org/pypi/python-multipart/0.0.32/json").read().decode()
url = re.search(r'"url":\s*"([^"]+python_multipart-0\.0\.32-py3-none-any\.whl)"', idx).group(1)
urllib.request.urlretrieve(url, whl)
# 3. front end with relative URLs (works under a sub-path like /colstorso/)
shutil.copytree(os.path.join(ROOT, "static"), os.path.join(OUT, "static"))
os.makedirs(os.path.join(OUT, "design"))
for f in ["tokens.css", "logo.svg", "logo-reversed.svg", "logo-mono.svg", "logo-mark.svg", "logo-mark-reversed.svg", "wordmark.svg"]:
    shutil.copy(os.path.join(ROOT, "design", f), os.path.join(OUT, "design", f))
shutil.copytree(os.path.join(ROOT, "design", "fonts"), os.path.join(OUT, "design", "fonts"))
shutil.copytree(os.path.join(ROOT, "design", "icons"), os.path.join(OUT, "design", "icons"))
for p in glob.glob(os.path.join(OUT, "static", "*.*")):
    if p.endswith((".js", ".css", ".html")):
        s = open(p).read()
        s = re.sub(r"(['\"`(])/(static|design)/", r"\1\2/", s)
        open(p, "w").write(s)
html = open(os.path.join(OUT, "static", "index.html")).read()
html = re.sub(r'(href|src)="/(static|design)/', r'\1="\2/', html)
html = html.replace('<script src="static/charts.js"></script>',
    f'<script>window.CT_PYODIDE="{PYODIDE}";</script><script src="{PYODIDE}pyodide.js"></script><script src="static/browser-boot.js"></script>\n<script src="static/charts.js"></script>')
open(os.path.join(OUT, "index.html"), "w").write(html)
os.remove(os.path.join(OUT, "static", "index.html"))
shutil.copy(os.path.join(ROOT, "browser", "browser-boot.js"), os.path.join(OUT, "static", "browser-boot.js"))
open(os.path.join(OUT, ".nojekyll"), "w").close()
open(os.path.join(OUT, "404.html"), "w").write(open(os.path.join(OUT, "index.html")).read())
tot = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(OUT) for f in fs)
print("built", OUT, f"{tot/1e6:.1f} MB")
