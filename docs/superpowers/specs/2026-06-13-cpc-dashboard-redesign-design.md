# CPC Dashboard Redesign — Design Spec

**Date:** 2026-06-13
**Status:** Proposed (awaiting review)
**Scope:** Restructure the published CPC benchmark dashboard (`viz/dashboard.html` + `viz/build_visualizer.py`) from a flat 12-chart scroll into a hierarchy-first "showpiece," and simplify the rendering + build code behind it. No eval-harness changes; no personal-site changes.

---

## 1. Problem

The dashboard at **cpc.sahilashar.com** has grown to **12 full-width charts stacked vertically with equal visual weight**. Two distinct problems wear one coat:

- **Editorial overload:** no hierarchy. The CPC money chart (north star) gets the same real estate as the Fable cost-frontier footnote. A first-time viewer doesn't know where to look; a returning analyst scrolls 12 screens to reach one panel.
- **Structural overload:** one **1,477-line `dashboard.html`** — ~1,000 lines of inline vanilla JS hand-building every SVG via `el()`/`card()` — plus a build step (`build_visualizer.py`) that does **fragile string-marker surgery** on that file to emit two variants (`visualizer.html` offline + inlined data; `pages-index.html` fetching `latest.json`).

## 2. Decision: optimize as a **showpiece, cut hard**

Primary audience is blog readers / peers / recruiters skimming the live site (the dashboard is the companion to the CPC-methodology blog post). Lead with one headline, demote secondary panels behind tabs/columns, prioritize clarity and polish. No underlying data is deleted — it relocates.

Research (two background agents, 2026-06-13) confirmed the direction: leading AI-benchmark dashboards (Artificial Analysis, LMArena, HELM, SWE-bench, Vellum) lead with **a KPI strip + one hero chart + a sortable table backbone**, with everything else behind tabs/drill-down. The fix is hierarchy, not fewer numbers.

## 3. Target information architecture

Landing view, top to bottom:

1. **Masthead + KPI strip** (already exists as `#statband`): best CPC · top accuracy · CPC spread · $0 local baseline. Keep as-is.
2. **Hero — Quality-vs-Cost scatter** (current Chart 1), full width. Y = accuracy, X = total cost (log). Highlight the cheap-and-accurate quadrant. The *only* chart that earns hero real estate.
3. **Supporting — compact Wilson-CI forest** (current Chart 11), reduced height. The single striking "no strict #1" uncertainty visual. Visually proves the rank ties in the table below.
4. **Backbone — one sortable model table** (new). The 30-second / 5-minute layer. Absorbs five current charts as columns (see §4).
5. **Tabs — the explorer** (collapsed by default):
   - **By task** → per-chain heatmap (6) + task difficulty (7) + parallel-invocation strips (4)
   - **Methodology** → before/after hardening spread (8) + Fable effort frontier (9)
   - **Over time** → history-over-time dated runs (10)

**Net:** 12 stacked cards → KPI strip + 1 hero + 1 forest + 1 table + 3 tabs. ~7 panels stop competing for the first screen; none are deleted.

### Chart → destination map

| # | Current chart | Destination |
|---|---|---|
| 1 | Quality-vs-Cost scatter | **Hero** (kept, enlarged) |
| 2 | Score ranking bars | Table column: Accuracy (inline bar + CI) |
| 3 | CPC ranking bars | Table column: CPC (inline bar) |
| 11 | Wilson-CI forest plot | **Supporting visual** (kept, compact) + drives table rank ties |
| 12 | Over-call rate | Table column |
| 5 | Distractor picks | Table column: distractor-pick rate (detail on row expand) |
| 6 | Per-chain heatmap | Tab: By task |
| 7 | Task difficulty | Tab: By task |
| 4 | Parallel strips | Tab: By task |
| 8 | Before/After hardening | Tab: Methodology |
| 9 | Fable effort frontier | Tab: Methodology |
| 10 | History over time | Tab: Over time |

## 4. The backbone table (crux)

One sortable HTML table, one row per config (12 rows). Columns:

| Column | Source | Render |
|---|---|---|
| **Rank** | accuracy + Wilson CI from `reps_*.json` | LMArena-style: rank = 1 + (# configs whose CI is *fully above* this one's). Overlapping CIs share a rank — never implies false precision. Configs without reps (Fable ×3, API suspended) get a point-estimate rank flagged with a `*` + footnote. |
| **Model** | `label`, `provider` | Provider color dot; medal accent on top rank(s). |
| **Accuracy** | `score`/`N`, `ci_low_score`/`ci_high_score` | `score/N` + inline horizontal bar + `+x/−y` CI suffix (from reps; omitted with `*` where absent). |
| **CPC** | `cpc_usd` | `$value` + inline bar. Cheapest-first emphasis. |
| **Cost** | `total_cost_usd` | `$value`. |
| **Over-call** | `over_call_rate` | `pct%`. |
| **Distractor** | `distractor_picks` | pick-rate `pct%`; row-expand reveals which tasks/tools. |
| **Latency** | `mean_latency_s` | `Ns`. |

- **Sortable** by any column (click header). **Default sort: Rank** (accuracy, CI-tied). CPC story carried by hero + KPI + CPC column.
- Inline bars are CSS-width-driven `<div>`s (Vellum pattern) — the table doubles as a bar chart, which is what lets it absorb charts 2/3/12.
- Theming inherits the existing lab-instrument palette + CSS variables (light-first + dark toggle). No new colors.

## 5. Engineering: refactor, don't re-platform

**Charting:** keep hand-rolled SVG; **no charting library.** With the cut, only ~3 charts remain visible (scatter, forest, plus tab charts), and a library (Observable Plot was the research pick) would add a D3 dependency and re-theming work for little gain, while weakening the strict brand-palette control we already have. Instead:

- Extract the ~1,000 inline JS lines into a separate `viz/dashboard.js` organized as **small composable functions**: `scatter()`, `forest()`, `table()`, `heatmap()`, `difficultyChart()`, `parallelStrips()`, `historyChart()`, plus shared helpers (`el()`, `card()`, `axis()`, `scale()`, `legend()`, `tabs()`). Each function: takes data + a mount node, owns one panel, testable in isolation.
- `dashboard.html` becomes structure + `<script src="dashboard.js">` — not a 1,477-line monolith.

**Build simplification (kills the marker surgery):**

- Data moves to generated `data.js` files: `window.__DATA__ = {…}`, `window.__BENCH_HISTORY__ = […]`, `window.__BENCH_REPS__ = {…}`.
- The page logic is uniform: **use `window.__DATA__` if present, else `fetch('./data/latest.json')`** (same fallback for history/reps). `<script src>` works under `file://` (unlike `fetch`, which CORS-blocks local files) — this is why offline gets the script tags and Pages does not.
- `build_visualizer.py` shrinks to two well-defined jobs:
  - **offline** (`visualizer.html`): write `data.js`/`history.js`/`reps.js` next to the HTML and include their `<script src>` tags. Opens under `file://`.
  - **`--pages`** (`pages-index.html`): omit those script tags → page fetches `./data/latest.json` (+ runs/reps) at runtime → live site shows newest data without an HTML rebuild.
- The build difference becomes "include vs omit a few `<script src>` lines," not surgical string replacement inside large inlined blobs.
- `deploy_pages.sh` unchanged in spirit: still assembles `_site/` with `index.html` + `data/*.json`.

## 6. Non-goals / out of scope

- No eval-harness changes (runner, scorer, tasks, pricing). This is presentation only.
- No personal-site (`sahilashar.com`) changes — it only links out.
- History snapshots preserved: `runs/<date>.json` + `latest.json` + `runs.json` + `reps_*.json` layout untouched (secondary north star — keep every run as a dated snapshot).
- No data churn: numbers come from existing export; this redesign reads the same `latest.json` / `reps_*.json`.
- Reps filename is still dated/hardcoded (`reps_2026-06-13.json`); bumping it on the next rerun stays a manual one-liner (pre-existing, not addressed here).

## 7. Risks & validation

- **`file://` regression:** the whole point of inlining is `file://` support. Validate `visualizer.html` opens and renders offline with `data.js` script-src (no fetch).
- **Pages live-data path:** validate `pages-index.html` fetches `latest.json`/`runs.json`/`reps_*.json` (200s) and renders without the inlined blobs.
- **Render gate:** reuse the existing jsdom render gate + geometry gate (`/tmp/jsdom-gate`) — assert all panels mount, table has 12 rows + sortable headers, forest has 9 CI whiskers, both light/dark themes, 0 jsdom errors.
- **Table-absorbs-charts honesty:** confirm CI columns + overlap-tied ranks reproduce the forest plot's ordering (no contradiction between the two surfaces).
- **Screenshot caveat (known):** headless-Chrome `captureScreenshot` deadlocks on the wide forest SVG on this machine; rely on render+geometry gates + live deploy verification, as in the prior chart work.

## 8. Open questions

None blocking. Default table sort (Rank vs CPC) and exact tab grouping are low-stakes and can be tuned during implementation.
