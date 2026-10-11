# ColsTorso brand

**Version 1.0 · 11 Oct 2026.** Original identity for ColsTorso, an open-source retail operations platform. It is deliberately different from Quorso (near-black, space and "Mission Control" theme) and from AE Global (Evergreen #18332F / Sand #D1B98D, GT Super + Work Sans). No colours, assets, fonts or copy were taken from either.

## 1. Idea

**"The one thing to act on today."** Retail data is a wall of numbers. ColsTorso picks the few that matter and makes them doable. The brand is calm, practical and confident, like a good store manager, not a control room.

- **Columns** ("Cols"): three rising columns are stores, signals and results stacked into progress.
- **Core** ("Torso"): the strong centre that holds the operation together. The product is the operating core, not another dashboard.
- **The marigold column:** the tallest column, cut at an upward angle, is the one priority. Marigold is used sparingly, only to mark what matters most.

## 2. Logo

| File | Use |
|---|---|
| `logo.svg` | Primary lockup (mark + wordmark) on light backgrounds |
| `logo-reversed.svg` | Lockup on dark or cobalt backgrounds (white wordmark) |
| `logo-mono.svg` | One-ink use (fax, embossing, single-colour print) |
| `logo-mark.svg` | App icon, favicon, compact top bar, avatar placeholder |
| `logo-mark-reversed.svg` | Mark on dark backgrounds |
| `wordmark.svg` | Wordmark only, for places where the mark already appears |
| `png/brand-logo-sheet.png` | Preview of all versions |

- The wordmark is lowercase **colstorso**, drawn as outlines from Manrope ExtraBold (SIL OFL), so it renders the same everywhere with no font dependency. In running text, write the name as **ColsTorso**.
- **Clear space:** at least half the mark's height on every side.
- **Minimum size:** mark 24 px (favicon 16 px is allowed using the mark only); lockup 96 px wide.
- **Don't:** recolour the columns, use marigold for the wordmark, add gradients or shadows, rotate it, put it on photos without a solid panel, or use space or rocket imagery with it.

## 3. Colour

All values are in `tokens.css`. **Measured contrast** for every semantic pair, in both themes, is in [`contrast-report.md`](contrast-report.md): 59 pairs × 2 themes, all pass (text ≥ 4.5:1, UI ≥ 3:1). Re-run `python3 scripts/contrast.py` after any change.

| Role | Primitive | Hex | Notes |
|---|---|---|---|
| Brand / primary action | Cobalt 600 | `#3443D1` | White text on it: **7.32:1** |
| Brand ink (logo text) | Cobalt 950 | `#0F1340` | |
| Accent (highlight only) | Marigold 400 | `#F5BA0A` | Never text on white. Dark text on it: **10.78:1** |
| Neutrals | Slate 0–950 | `#FFFFFF` → `#0E1016` | Cool greys. Muted text (Slate 500 `#616A7F`) is **4.88:1** even on the sunken surface |
| Success / positive impact | Green 700 on Green 50 | `#126632` / `#E8F7EE` | **6.38:1** |
| Warning / ageing data | Amber 700 on Amber 50 | `#8A4A00` / `#FFF4E0` | **6.30:1** |
| Danger / negative impact | Red 700 on Red 50 | `#9C1C21` / `#FDECEC` | **7.07:1** |
| Info | Sky 700 on Sky 50 | `#08587E` / `#E6F4FB` | **6.91:1** |
| Priority "Must" | Flame 700 on Flame 50 | `#9A3408` / `#FFEFE6` | **6.53:1**. Kept separate from danger red so "urgent" doesn't read as "error" |
| Priority "Should" | Cobalt 700 on Cobalt 50 | | **8.59:1** |
| Priority "Could" | Slate 600 on Slate 50 | | |

**Colour is never the only signal (WCAG 1.4.1).** Priority always has a label and an icon (flame / arrow-up / minus). Impact always has a sign (+/−), an arrow and words ("Worked", "No clear change", "Got worse"). Freshness always has an icon and text. Charts label their lines directly and vary the line style (solid vs dashed).

Dark theme (`[data-theme="dark"]`) is fully specified and measured too. It's useful for back-of-house screens and night shifts.

## 4. Type

Open-source fonts (SIL OFL), self-hosted in `fonts/` as variable WOFF2, with system fallbacks:

- **Manrope** (display: headings, big numbers, wordmark). Fallback: `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Arial`.
- **Inter** (UI and body). Same fallback stack. Use `font-variant-numeric: tabular-nums` for any column of numbers.
- Mono: system only (`ui-monospace, SFMono-Regular, Menlo, Consolas`), for IDs and codes.

| Token | Size / line height | Weight | Use |
|---|---|---|---|
| `--ct-type-display` | 48 / 1.15 | 800 Manrope | Marketing, empty-state heroes |
| `--ct-type-h1` | 30 / 1.15 | 800 Manrope | Page title (24 px on mobile) |
| `--ct-type-h2` | 24 / 1.3 | 700 Manrope | Section title |
| `--ct-type-h3` | 20 / 1.3 | 700 Manrope | Card title |
| `--ct-type-h4` | 18 / 1.3 | 600 Inter | Mission title, list headers |
| `--ct-type-body-lg` | 18 / 1.5 | 400 Inter | Reading on desktop |
| `--ct-type-body` | **16** / 1.5 | 400 Inter | **Base. Minimum for store-floor content** |
| `--ct-type-body-sm` | 14 / 1.5 | 400 Inter | Secondary detail, tables |
| `--ct-type-label` | 14 / 1.3 | 600 Inter | Buttons (16 px in touch UI), chips, field labels |
| `--ct-type-caption` | 12 / 1.3 | 500 Inter | Metadata only, never the only place key info appears |
| `--ct-type-metric` | 36 / 1.15 | 800 Manrope | KPI values |
| `--ct-type-metric-sm` | 24 / 1.15 | 700 Manrope | Inline numbers |

Rules: rem-based so OS text size is respected. Layouts must survive 200% zoom. No text in all caps except captions (with letter spacing). Keep lines under 68ch.

## 5. Iconography

**Use [Lucide](https://lucide.dev) (ISC licence, open source)**, with the same 24 px grid and 2 px stroke everywhere. The mockups inline a sprite of the icons used (`icons/ct-icons.svg`, generated by `scripts/build_mockups.py` from `lucide-static`). The build can use `lucide-static` or `lucide` from npm. Licence: `icons/LUCIDE-LICENSE.txt`.

Usage rules:
1. **Sizes:** 16 (inline with 14 px text), 20 (default), 24 (tab bar, primary actions), 32 (empty states). Keep the 2 px stroke and don't mix in filled icon styles.
2. **Icons support labels, they don't replace them.** Nav items, buttons and chips show text. Icon-only buttons are allowed only for universal actions (back, search, notifications, more) and must have an `aria-label` and a 44 × 44 px hit area.
3. **Decorative icons** get `aria-hidden="true"`. Meaningful icons sit next to visible text that carries the meaning.
4. **Colour:** icons inherit `currentColor`. Use semantic text tokens, never a bare hex value.
5. **Fixed meanings (don't reuse these icons for other things):**

| Meaning | Lucide icon |
|---|---|
| Priority Must / Should / Could | `flame` / `arrow-up` / `minus` |
| Mission kinds: alert / opportunity / HQ campaign / storewalk | `triangle-alert` / `chart-column` / `megaphone` / `clipboard-check` |
| Accept / Snooze / Not for us | `check` / `alarm-clock` / `ellipsis` (menu) |
| Impact up / down / no change | `trending-up` / `trending-down` / `minus` |
| Worked (result) | `badge-check` |
| Data fresh / ageing / stale or missing | `circle-check` / `clock` / `triangle-alert` (+ `database` for a missing feed) |
| Offline / saved on device | `cloud-off` |
| Best practice / pattern across stores | `lightbulb` |
| AI assistant | `sparkles` (only for AI) |
| Fair comparison / measurement | `shield-check` |
| Visit | `map-pin` |

## 6. Voice

- **Plain words, numbers first.** Say "Bakery waste is double the rate of similar stores", not "Fresh shrink KPI variance detected".
- **Always say why and what it's worth:** the reason, the comparison group, the payoff, the time it takes.
- **No blame.** If data is missing or a cause is outside the store's control, say so ("You won't be blamed for the sales drop").
- **Admit when it's unclear:** "No clear change yet", "Too early", a likely range.
- **Naming** (avoid Quorso's terms "Mission Control", "Pre-launch", "Live", "Archive"): navigation is *Today · Missions · Tasks · Impact · Ask*. Mission lifecycle: **Suggested → Accepted (planning) → In progress → Done** (result: *Worked / No clear change / Got worse*), plus **Snoozed** and **Not for us** (with a reason). These are **display labels only**. Keep the build's existing `missions.status` values and map them in the UI: `incoming` → Suggested · `proposed` / `prelaunch` → Accepted (planning; "Waiting for review" when approval is needed) · `live` → In progress · `done` / `archived` → Done · `rejected` → Not for us · `snooze_until` set → Snoozed. No data change is needed.

## 7. Data visualisation

- Your store is a solid cobalt line (`--ct-color-impact-store-line`). The comparison group is a dashed slate line (`-control-line`). The likely range is a tinted band (`-band`).
- Label lines directly at their ends and give every chart a text alternative (`<title>`/`<desc>` or `aria-label`).
- Bars come with their value labels. Series order follows `--ct-color-chart-1..6`.
- Show a likely range for impact numbers, not a single misleadingly precise figure.
