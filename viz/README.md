# Benchmark visualizer

A static visualization of the 2026-06-12 hardened benchmark run (23 tasks ×
12 model configurations). The north-star metric is **CPC = total run cost /
tasks with correct retrieval strategy**.

## Files

| File | What it is |
|---|---|
| `visualizer.html` | Offline deliverable: a single self-contained tabbed page (Dashboard / Insights / Hardening Roadmap). Data inlined, no CDN, opens under `file://`. |
| `pages-index.html` | Live-data variant: identical layout, but fetches `./data/latest.json` at runtime. Served as `index.html` on Cloudflare Pages. Built by `build_visualizer.py --pages`. |
| `dashboard.html` | The charts-only standalone version (Dashboard content only). |
| `data/latest.json` | Canonical **latest** snapshot the live site fetches. Mirrors the newest dated run. |
| `data/runs/<date>.json` | Dated history snapshots — one immutable file per benchmark run. |
| `data/runs.json` | Manifest of every run (newest first); the future history view reads this to populate a run picker. |
| `insights-2026-06-12.md` | Prose backing the Insights tab. |
| `hardening-roadmap-2026-06-12.md` | Prose backing the Hardening Roadmap tab. |
| `export_bench_data.py` | Regenerates the data snapshots (`runs/<date>.json` + `latest.json` + `runs.json`) from the run files. |
| `build_visualizer.py` | Rebuilds `visualizer.html` (default) or `pages-index.html` (`--pages`). |
| `deploy_pages.sh` | Builds the site dir and deploys it to Cloudflare Pages (Path A, manual). |

## Viewing

Open `viz/visualizer.html` directly in a browser. It is fully self-contained:
the benchmark data is inlined in a `<script id="data-blob">` block and there
are no `fetch()` calls or CDN dependencies.

The three tabs:

- **Dashboard** — the headline charts: CPC and accuracy per config, the
  cost/quality scatter, chain pass rates, distractor-pick behavior, and
  per-task difficulty.
- **Insights** — narrative findings from the run.
- **Hardening Roadmap** — where the dataset is saturated and what to harden next.

## Data layout (history over time)

Runs accumulate as history (a project north star — see `CLAUDE.md`). Every
export writes three things under `data/`:

- `runs/<date>.json` — the immutable snapshot for that run.
- `latest.json` — a copy of the newest run; this is the only file the live site
  fetches. **To refresh the live site, re-export and redeploy** (no HTML rebuild
  needed — `pages-index.html` always fetches `latest.json`).
- `runs.json` — a manifest (newest first) that a future history view will read
  to offer a run picker. The chart UI does not consume it yet.

## Regenerating

The data snapshots are built from the per-model run files in the repo's
gitignored `results/` directory (`results/eval_*_20260612-*.json`). Those files
are **not** committed; only the published snapshots are. To regenerate from a
local checkout that has the run files, run both scripts from the repo root:

```bash
# 1. rebuild the data snapshots (reads results/, writes runs/<date>.json,
#    latest.json, and upserts runs.json)
python viz/export_bench_data.py

# 2. rebuild the offline page (reads dashboard.html + the two md files)
python viz/build_visualizer.py

# 2b. (publishing) rebuild the live-data page instead -> viz/pages-index.html
python viz/build_visualizer.py --pages
```

Both scripts default their paths relative to the repo (no absolute paths) and
accept positional overrides:

```bash
python viz/export_bench_data.py /path/to/repo /path/to/data_dir
python viz/build_visualizer.py /path/to/viz
```

Note: `export_bench_data.py` only refreshes the JSON snapshots. The chart code
that renders them lives inside `dashboard.html`; `build_visualizer.py` folds
`dashboard.html` plus the two markdown files into `visualizer.html` (offline) or
`pages-index.html` (live-data).

## Publishing (Cloudflare Pages — Path A, manual)

The live dashboard is served at **cpc.sahilashar.com** (Cloudflare Pages). It is
a **direct upload**, not a git-connected auto-deploy: there is no cron and no
GitHub secret. To publish on demand:

```bash
# scoped token: Account > Pages: Edit, Zone (sahilashar.com) > DNS: Edit + Zone: Read
CLOUDFLARE_API_TOKEN=... viz/deploy_pages.sh            # production
CLOUDFLARE_API_TOKEN=... viz/deploy_pages.sh --branch preview-x   # preview URL
```

`deploy_pages.sh` rebuilds `pages-index.html`, assembles a clean `viz/_site/`
(`index.html` + `data/`), and runs `wrangler pages deploy`. Scheduled / CI
publishing with a run-health gate (Path B) is deliberately **not** built yet.
