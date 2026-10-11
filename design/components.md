# ColsTorso components spec

Mobile-first, designed for **store managers on the shop floor** first and scaled up for district, regional and HQ users. All values come from `tokens.css` (`--ct-*`). The reference CSS is in `mockups/ct-components.css`, and every component appears in `mockups/*.html`. Class names there are illustrative; **token names are the stable API.**

## Rules for every component

| Rule | Spec |
|---|---|
| Base text | 16 px (`--ct-type-body`) on mobile. Nothing the user must read or act on is under 14 px. 12 px is for metadata only. |
| Touch targets | ≥ 44 × 44 px (`--ct-size-touch-target`) on every store screen. Primary one-thumb actions (Accept, Done) are 56 px (`--ct-size-touch-target-lg`) and sit in the bottom third of the screen. At least 8 px between targets. |
| Colour | Never the only signal. Add a label and an icon, plus a sign or pattern where it helps (see brand.md §3). |
| Focus | Use `:focus-visible` with `--ct-focus-ring`. Never remove the outline without replacing it. Order follows reading order. |
| Motion | ≤ `--ct-motion-duration-base`. Must respect `prefers-reduced-motion` (tokens drop to 0 ms). Never use motion as the only signal of state. |
| Freshness | Every data-driven view shows **what data it uses and how old it is** (see the freshness strip under Nav shell). |
| Offline | Store actions (accept, snooze, tick a task, answer, photo) are **optimistic and queued**. Show "Saved on this device", sync in the background, and resolve conflicts on the server with last-writer-wins plus an activity log. Don't block the user with a spinner. |
| Common states | Each component below lists **Loading** (skeleton of the real layout, never a full-page spinner, shown after 300 ms), **Empty** (says why and what to do next), **Error** (what failed and a retry, keeping whatever is still usable) and **Stale** (shown when data passes its freshness threshold). |
| Freshness thresholds (defaults, set per feed) | Daily feeds (sales, waste): fresh ≤ 30 h, ageing ≤ 54 h, stale after. Weekly feeds (labor): fresh ≤ 8 days. The build can store these in `settings`. |
| Responsive | Mobile-first `min-width` breakpoints: 480, 768, **1024 (switch to side nav)**, 1280, 1440. Mockups use container queries on `.ct-app` so a frame can be any width. Media queries at the same values are fine in the build. |
| Roles | These match `users.role` in the build: `store_manager`, `associate`, `district_manager`, `regional_manager`, `central_analyst`, `hq_admin`, `dc_manager`. Navigation items vary by role (below). |

---

## 1. Nav shell

**Anatomy:** top bar (scope picker: store / district / region; date and week; notifications; avatar) → **freshness strip** → content → **bottom tab bar** below 1024 px, or **side nav** (248 px, `--ct-size-nav-side-width`; collapsible to 72 px) at 1024 px and up. An optional AI panel sits on the right at 1280 px and up (400 px, `--ct-size-ai-panel-width`).

**Tabs by role (5 at most on mobile, in the same order as the side nav):**
- Store manager / associate: Today · Missions · Tasks · Impact · Ask
- District / regional manager: Today · Stores · Visits · Review · Ask
- HQ / analyst: Overview · Campaigns · Feedback · Impact · Ask (Rules, Data and People live in the side nav and in "More" on mobile)

**Freshness strip:** one item per feed in use, each with an icon, the source and its age ("Sales & waste: through Sun 11 Oct", "Labor: 2 days old"), plus the last load time. A stale or missing feed is shown in `--ct-color-freshness-stale-fg` with `triangle-alert`, and the affected stores are named.

**Offline banner:** replaces the strip while offline, using `--ct-color-freshness-offline-bg/fg`, with `cloud-off` and a count of queued changes. It changes to "Synced" for 3 seconds when the connection comes back.

**States:** Loading shows the shell straight away with skeleton content. Error: "Can't reach ColsTorso. Showing what's saved on this device". Stale: the strip item turns amber, then red.

**Behaviour:** the tab bar is sticky with safe-area padding. The current tab has `aria-current="page"`, a 3 px top indicator and bold text, and its label is always visible. Badges show counts (99+). The tab bar hides when the on-screen keyboard is open.

**A11y:** `<nav aria-label="Main">`. A "Skip to content" link. The freshness strip is `role="status"` (polite). The scope picker is a real `<select>` or listbox.

## 2. Mission card

**Anatomy:** priority chip (Must / Should / Could + icon) · kind chip (Alert / Opportunity / HQ campaign / Storewalk) · rank ("1 of 3") → title (≤ 2 lines, plain words) → **"Why you're seeing this"** box (one sentence, with your number vs the expected number, the size of the peer group and the timeframe) → three facts: **If fixed** (+$ / wk), **Effort** (~min), **Confidence** (High / Medium / Low with a 3-bar glyph) → actions: **Accept** (primary, 56 px), **Snooze** (secondary, 56 px), **⋯** (Not for my store, Reassign, Ask AI). A 6 px left edge in the priority colour.

**Data mapping:** `missions.title`, `priority`, `kind`; why comes from `opportunities.actual / expected / peer_count`; If fixed is `gap_value`; Confidence comes from `z` / `score` (the build sets thresholds); a campaign comes from `campaign_id`.

**Behaviour:**
- **Accept is one tap.** It accepts with the suggested action plan (it doesn't open a form), shows a toast with **Undo** for 6 s, and moves the card to "Working on it". Editing the plan is optional, later.
- **Snooze is one tap** for 3 days (the default). Long-press or ⋯ gives 1 week or a custom date. The toast has Undo.
- **Not for my store** opens a bottom sheet with a single tap on a reason (Stock not delivered · Fixture missing · Already fixed · Not enough hours · Other). The reason feeds the themes and HQ feedback. Never ask for free text before the reason.
- **Daily budget:** Today shows at most 3 missions (a setting per role). The rest go into a collapsed "N more can wait" row. HQ "Must-do" campaign missions may displace a store mission but never go over the cap.
- Tapping the title opens Mission detail.

**States:** Loading: a skeleton with the same height as a real card. Empty (none today): "Nothing urgent today. Your store is in line with similar stores", with links to In progress and Best practices. Error: the card is replaced by "Couldn't load missions. Retry", and cached cards stay visible. **Stale:** if a feed behind the mission is stale, show an amber note in the why box ("Based on sales through Thu, newer data delayed"), and give the Accept button a confirm hint rather than disabling it.

**A11y:** each card is an `<article>` whose heading is the title. The buttons' accessible names include the mission ("Accept: Bakery waste…"). The confidence glyph is `aria-hidden` and the word is shown. Undo is reachable by keyboard and stays for 6 s (and won't time out while focused).

## 3. Mission detail (accept and plan)

**Anatomy:** back, title and context → payoff row (Expected payoff · Your time · Confidence · Measured over) → **Why you're seeing this** (labelled comparison bars: your store / similar median / best quarter; an 8-week trend vs peer median; the peer definition in a sentence; "How we compare" link) → **What's likely causing it?** (cause checkboxes ranked by how often they were the cause in similar stores, plus "Something else…") → **What worked elsewhere** (top matching best practice with its measured $ impact; "Use this plan") → **Your action plan** (action, pre-filled owner and start date, auto-created tasks, measurement statement) → **sticky action bar:** Snooze (1 part) | **Accept & start** (2 parts, on the right).

**Data mapping:** `missions.root_causes`, `action_type`, `action`, `duration`, `target_weekly`; `best_practices` (same `kpi`/`cat_id`, sorted by `impact_value`); `mission_tasks`; `approval` / `approver_id` (show "Your district manager will review" when approval is required).

**Behaviour:** everything is pre-filled, so the plan is valid on arrival. The measurement window and comparison group are **fixed at accept** and shown. Accepting offline queues the change. Approval flow: Accepted → "Waiting for DM" chip, and the DM can comment, which turns into a notification.

**States:** Loading: payoff skeletons, then charts. Empty best practice: "No proven fix yet. Yours could be the first" (and it can be shared later). Error on a chart: show the numbers as text. Stale: an amber line under the payoff row.

**A11y:** charts have `role="img"` and a full-sentence `aria-label` or `<desc>`. Each cause is a checkbox with its label. The sticky bar doesn't cover focused inputs (scroll padding equal to its height).

## 4. Action plan (component inside Mission detail; also used for visit-agreed actions)

**Anatomy:** numbered steps: 1 What will you do (dropdown of templates plus free text) · 2 Who and when (person picker, date) · 3 Tasks we'll create (checklist rows with owner and day) · measurement note (`shield-check`).

**Behaviour:** choosing a template fills the tasks in. Each task row can be removed or reassigned with one tap. Plans can be edited until the end of the first week. After that, edits are logged in `activity` so measurement stays honest.

**States:** Empty template list: free-text action plus "Add task". Error saving: the inline message keeps the input and retries automatically when back online.

**A11y:** steps are an ordered list. Pickers are native inputs on mobile. Errors are linked with `aria-describedby`.

## 5. Task list

**Anatomy:** filter (Today · This week · Done, with counts) → groups by due time ("Due by 11 AM", with the total minutes) → task row: 44 px checkbox · title · meta (source: mission / HQ campaign / routine / rule; owner; ~minutes; due) · sync chip ("Saved" with `cloud-off` while queued) · chevron → **task runner** (full screen on mobile, side panel on desktop): question blocks with large Yes/No (56 px), quick-pick answers, Photo / Voice note / barcode scan, link to the parent mission and what happens next, sticky **Skip | Done, next task**.

**Data mapping:** `tasks` (`title`, `due`, `status`, `questions`, `answers`, `est_minutes`, `source`, `attachments`, `escalated`), `task_templates`, `task_rules` (`escalate_after_days`).

**Behaviour:** ticking a box completes the task straight away when it has no required questions. Otherwise it opens the runner. "Done, next task" moves through the group. Overdue tasks get an amber "Overdue 2 days" chip, and escalation follows `escalate_after_days`. **Photo or other evidence** can be made required for compliance tasks, to stop tick-box completion. Answers and photos are queued offline, and photos upload in the background with retry.

**States:** Loading: 3 skeleton rows. Empty: "All done for today 🎉" (emoji is decorative, `aria-hidden`), with a link to This week. Error: rows stay usable from the cache. Stale: not applicable (tasks are first-party). A sync conflict shows "Updated by Sam at 9:14. Keep yours / Use Sam's".

**A11y:** the checkbox's accessible name includes the task title. Group headings are real headings. The runner manages focus (first question on open, back to the row on close).

## 6. Impact chart

**Anatomy:** result chip (Worked / No clear change / Got worse / Too early) → headline numbers: **+$/wk with a likely range**, total over the window (after removing the seasonal lift), confidence in words → chart: your store (solid `--ct-color-impact-store-line`), comparison group (dashed `--ct-color-impact-control-line`), likely-range band (`--ct-color-impact-band`), a marked start line and a shaded "after" area, end-of-line labels → plain-words explainer → "Can I trust this number?" checklist (fair comparison, pre-period match, data gaps and how they were handled) → actions: Share as best practice · Thank the team · Start a follow-up.

**Data mapping:** `impact` (`week`, `gap`, `improvement`, `control_improvement`, `net`). Net = improvement − control improvement. The range comes from the analytics (the build defines the method; show "Too early" until ≥ 2 weeks after the start).

**States:** Loading: a chart skeleton with the axes. Empty (not enough weeks): "Too early to tell. Check back Mon 19 Oct". Error: the table of values stays visible. **Stale/partial:** weeks with missing data are drawn as a gap (no interpolation) and listed in the trust checklist.

**A11y:** SVG with `<title>` + `<desc>` giving the conclusion in a sentence. A "View as table" toggle. Lines differ in style as well as colour. The range is never shown by colour alone (it's also in the text).

## 7. Store leaderboard (district / regional)

**Anatomy:** scope filters (district, period) → 4 KPI tiles (accept rate, measured impact, plans to review, overdue tasks) → **pattern banner** (a theme across stores with a hand-off action) → leaderboard: "Rank by" segmented control (**Improvement** (default, fair) · Impact $ · Vs plan) → table (≥ 1024 px) or cards (below): rank, store and manager (with last visit), improvement %, $/wk, accepted (x of y), overdue, status chip (Top / OK / Data gap / Visit) → selection opens the **store panel** (focus areas, visit checklist, Message / Start visit).

**Behaviour:** clicking a row selects it (`aria-selected`) and opens the panel without leaving the page. Sorting by column header is supported, with `aria-sort`. "Recognise" sends kudos (`missions.kudos`). Stores with missing data get a "Data gap" chip and are **not** ranked down for it.

**States:** Loading: skeleton rows. Empty (filter returns none): "No stores match. Clear filters". Error: "Couldn't load comparison", keeping the last good snapshot with its date. Stale: the freshness strip names the stores affected.

**A11y:** a real `<table>` with `<th scope>`. Numbers are right-aligned and tabular. The rank has text (not just a medal colour). The mobile cards repeat the column labels.

## 8. Visit checklist (district / regional manager)

**Anatomy:** store header (manager, tenure) → **What to focus on during the visit** (2 issues + 1 "doing well", data-generated) → checklist: rows with 44 px checkboxes, optional photo / voice per row → "Agree actions" (each one becomes a mission via Action plan) → coaching note (voice or text) → Message / **Start visit** → while a visit is running: timer, offline-capable, Finish → summary is sent to the store manager.

**Data mapping:** `visits` (`status` planned / in_progress / done; `coaching`, `agreed_actions`), `surveys` (kind `storewalk`), `survey_responses`.

**States:** Loading: skeleton. Empty focus: "No issues flagged. Use this visit to recognise the team." Error saving: queue it. Offline is fully supported (the visit often happens in a back room).

**A11y:** the checklist is a list of checkboxes with labels. Voice notes have a text transcript (editable). The timer is not announced continuously.

## 9. HQ campaign builder

**Anatomy:** 4 steps with numbered labels (Goal & KPI → Stores → Message & tasks → Review & launch), autosaved drafts → **Stores:** rule tokens that read like sentences (Format is…, Has…, Except…), live match count with a list → **Push strength** segmented control (Gentle / Standard / Must-do) with an explanation → **Mission budget check** (added missions per store per week; which stores hit their cap; what gets moved back; "Start them a week later") → **How we'll measure it** (a random comparison group held back, shown at launch) → **Live store preview** (the exact mission card with the per-store "why") → Back / Next.

**Data mapping:** `campaigns` (`kpis`, `categories`, `boost`, `start_week`, `end_week`, `target`, `message`), `blackouts`, `mission_rules`.

**Behaviour:** launch is blocked only by hard errors (no stores, no KPI). Budget and control warnings advise but don't block. Must-do needs a reason and is limited to N per quarter (a setting). After launch: running campaigns show progress, accept rate and measured impact, and rejection reasons flow into **Store feedback**.

**States:** Loading the store count: an inline spinner on the count only. Empty (0 stores match): an inline error naming the rule that excluded the most stores. Error: the draft is kept, with a retry.

**A11y:** the stepper is an `<ol>` with `aria-current="step"`. Rule tokens are buttons with "Remove rule: Has Bakery". The preview is marked as a preview (`aria-label`), not live UI.

## 10. AI panel ("Ask ColsTorso")

**Anatomy:** header with the `sparkles` icon → conversation (user message right, AI left) → **source chips under every answer** (data feeds, weeks, best-practice IDs, mission IDs) → suggested prompts → input with voice. On mobile it's the Ask tab (full screen). On desktop it's the right rail or a slide-over panel (`--ct-z-overlay`).

**Behaviour:**
- Answers are scoped to what the user's role and store can see. The AI never shows other stores' data beyond the peer aggregates the user already has.
- **The AI proposes and the user confirms.** Actions (create a plan, draft a message, add tasks) appear as buttons ("Yes, add it") and run only on tap, with Undo. The `ai_agent` user is recorded as the proposer in `activity`.
- It states data limits ("Labor data is 2 days old").
- Open with context: from a mission, it starts with that mission ("Ask about this mission").

**States:** Loading: a typing indicator plus streamed text. Empty: 3 suggested prompts for the role. Error: "I couldn't answer that. Try rephrasing or check the data in Missions." Offline: the input is disabled with "Ask needs a connection. Your missions and tasks still work offline."

**A11y:** the message list is `role="log"` with polite live updates (once a message completes, not per token). Source chips are links. The voice button has `aria-label` and shows its recording state as text.

---

## Other shared pieces (in the mockups)

- **Toast:** `--ct-color-surface-inverse`, sits above the tab bar, 6 s, one action (Undo), `role="status"`.
- **Segmented control:** `role="group"` + `aria-pressed`, 40 px+ inside a 48 px+ container, for 2–4 options.
- **Chip:** `--ct-radius-sm`, label + icon. Status chips use `-fg` on `-bg`. Priority chips also have a border.
- **KPI tile:** label · value (`--ct-type-metric`) · change in words with an arrow.
- **Skeleton:** `--ct-color-surface-sunken` to `--ct-color-border-subtle`, matching the real layout. The shimmer is turned off under reduced motion.
