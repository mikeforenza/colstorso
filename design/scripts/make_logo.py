"""Builds ColsTorso logo SVGs. Wordmark glyphs are outlined from Manrope ExtraBold (SIL OFL)."""
import os
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "..")
f = instantiateVariableFont(TTFont("/tmp/fnt/Manrope.ttf"), {"wght": 800})
gs, cmap, hmtx = f.getGlyphSet(), f.getBestCmap(), f["hmtx"]
upm = f["head"].unitsPerEm
def word(text, size, x0, base, track=-0.02):
    s = size / upm; x = x0; paths = []
    for ch in text:
        g = cmap[ord(ch)]; pen = SVGPathPen(gs)
        gs[g].draw(TransformPen(pen, (s, 0, 0, -s, x, base)))
        paths.append(pen.getCommands()); x += hmtx[g][0] * s + track * size
    return " ".join(paths), x
INK, COBALT, MARI, WHITE = "#0F1340", "#3443D1", "#F5BA0A", "#FFFFFF"
def mark(x, y, sq, bars, dot):
    # 48-unit grid: rounded square, three rising columns; the tallest is marigold with an up-slanted top = 'the one thing to act on today'
    return (f'<g transform="translate({x} {y})">'
            f'<rect width="48" height="48" rx="12" fill="{sq}"/>'
            f'<rect x="10" y="25" width="7" height="13" rx="2.5" fill="{bars}"/>'
            f'<rect x="20.5" y="19" width="7" height="19" rx="2.5" fill="{bars}"/>'
            f'<path d="M31 18.6 Q31 16.6 32.9 16 L36.1 15 Q38 14.4 38 16.4 V35.5 Q38 38 35.5 38 H33.5 Q31 38 31 35.5 Z" fill="{dot}"/>'
            "</g>")
def svg(w, h, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="t">'
            f'<title id="t">{title}</title>{body}</svg>\n')
def lockup(sq, bars, dot, text, cols_col=None):
    d, end = word("colstorso", 34, 60, 36)
    return svg(round(end + 2), 48, mark(0, 0, sq, bars, dot) + f'<path d="{d}" fill="{text}"/>', "ColsTorso")
open(f"{OUT}/logo.svg", "w").write(lockup(COBALT, WHITE, MARI, INK))
open(f"{OUT}/logo-reversed.svg", "w").write(lockup("#4A5CE8", WHITE, MARI, WHITE))
open(f"{OUT}/logo-mono.svg", "w").write(lockup(INK, WHITE, WHITE, INK))
open(f"{OUT}/logo-mark.svg", "w").write(svg(48, 48, mark(0, 0, COBALT, WHITE, MARI), "ColsTorso"))
open(f"{OUT}/logo-mark-reversed.svg", "w").write(svg(48, 48, mark(0, 0, "#4A5CE8", WHITE, MARI), "ColsTorso"))
d, end = word("colstorso", 34, 0, 36)
open(f"{OUT}/wordmark.svg", "w").write(svg(round(end + 2), 48, f'<path d="{d}" fill="{INK}"/>', "ColsTorso"))
print("ok", end)
