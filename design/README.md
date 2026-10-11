# ColsTorso design kit

Everything here is original. Mockups use **fictional example data** ("Harbor & Pine Market"). The build code in `/workspace/colstorso/` was read for naming and data shape (`colstorso/db.py`, `generator.py`) and was **not modified**.

| Path | What it is |
|---|---|
| `brand.md` | Idea, logo use, colour roles with measured contrast, type scale, iconography (Lucide), voice, data visualisation |
| `logo.svg`, `logo-reversed.svg`, `logo-mono.svg`, `logo-mark.svg`, `logo-mark-reversed.svg`, `wordmark.svg` | Logo files (the wordmark is outlined, so no font is needed) |
| `tokens.css` | **Design tokens, a stable API** (`--ct-` prefix). Light by default, `[data-theme="dark"]`, reduced motion. Self-hosted `@font-face` |
| `TOKENS.md` | Full table of all 250 tokens (light and dark values) plus the rules for using them |
| `contrast-report.md` | Measured WCAG contrast for 59 semantic pairs × 2 themes (all pass) |
| `components.md` | Component spec: nav shell, mission card, mission detail, action plan, task list, impact chart, store leaderboard, visit checklist, HQ campaign builder, AI panel |
| `research.md` | Quorso research with sources, how strong the evidence is, and the decision → pain-point map |
| `mockups/*.html` | 6 self-contained annotated screens (use `../tokens.css`). Add `?annotate=1` to the URL or use the "Toggle annotations" button. Add `?theme=dark` for dark mode |
| `mockups/ct-components.css` | Reference component CSS, built only on tokens |
| `mockups/_src/` | Mockup sources (the build step inlines the icon sprite) |
| `png/` | Rendered PNGs: clean, annotated and dark |
| `fonts/` | Manrope and Inter variable WOFF2 + OFL licences |
| `icons/ct-icons.svg`, `icons/LUCIDE-LICENSE.txt` | Lucide sprite used by the mockups (ISC) |
| `scripts/` | `contrast.py` (measure), `tokens_md.py` (regenerate TOKENS.md), `make_logo.py`, `build_mockups.py`, `render.py` (Playwright and Chrome), `slice.py` |

Rebuild: `python3 scripts/build_mockups.py && python scripts/render.py` (needs Playwright, with `/workspace/.venv-pw` on this box) and `python3 scripts/contrast.py && python3 scripts/tokens_md.py`. `build_mockups.py` reads Lucide icons from `/tmp/luc/package/icons` (from `npm pack lucide-static`). If that folder is gone, run that again or use `icons/ct-icons.svg`.

Screens: (a) Store manager Today · (b) Mission detail + accept/plan · (c) Regional store comparison + visit · (d) HQ campaigns + builder · (e) Impact results · (f) Tasks (offline).
