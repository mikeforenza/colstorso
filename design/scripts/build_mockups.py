"""Build mockups: inline a Lucide (ISC) symbol sprite into each mockups/_src/*.html -> mockups/*.html.
Also writes icons/ct-icons.svg (the sprite) for the build agent to reuse."""
import os, re, glob
HERE = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(HERE, "..")
LUC = "/tmp/luc/package/icons"
srcs = sorted(glob.glob(f"{D}/mockups/_src/*.html"))
names = set()
for s in srcs: names |= set(re.findall(r'href="#i-([a-z0-9-]+)"', open(s).read()))
sym = []
for n in sorted(names):
    t = open(f"{LUC}/{n}.svg").read()
    inner = re.search(r"<svg[^>]*>(.*)</svg>", t, re.S).group(1).strip()
    sym.append(f'<symbol id="i-{n}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{inner}</symbol>')
sprite = '<svg xmlns="http://www.w3.org/2000/svg" style="display:none" aria-hidden="true">' + "".join(sym) + "</svg>"
open(f"{D}/icons/ct-icons.svg", "w").write("<!-- Lucide icons (ISC license) used by ColsTorso mockups -->\n" + sprite + "\n")
for s in srcs:
    h = open(s).read().replace("<!--ICONS-->", sprite)
    open(f"{D}/mockups/" + os.path.basename(s), "w").write(h)
print("built", len(srcs), "pages,", len(names), "icons")
