# Benchmark visualizer

A static visualization of the 2026-06-12 hardened benchmark run (23 tasks ×
12 model configurations). The north-star metric is **CPC = total run cost /
tasks with correct retrieval strategy**.

## Files

| File | What it is |
|---|---|
| `visualizer.html` | The deliverable: a single self-contained tabbed page (Dashboard / Insights / Hardening Roadmap). Data is inlined, no CDN, opens under `file://`. |
| `dashboard.html` | The charts-only standalone version (Dashboard content only). |
| `data/bench_data_2026-06-12.json` | The committed data snapshot the pages render. |
| `insights-2026-06-12.md` | Prose backing the Insights tab. |
| `hardening-roadmap-2026-06-12.md` | Prose backing the Hardening Roadmap tab. |
| `export_bench_data.py` | Regenerates the data snapshot from the run files. |
| `build_visualizer.py` | Rebuilds `visualizer.html` from `dashboard.html` + the two md files. |

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

## Regenerating

The data snapshot is built from the per-model run files in the repo's
gitignored `results/` directory (`results/eval_*_20260612-*.json`). Those files
are **not** committed; only this published snapshot is. To regenerate from a
local checkout that has the run files, run both scripts from the repo root:

```bash
# 1. rebuild the data snapshot (reads results/, writes viz/data/...)
python viz/export_bench_data.py

# 2. rebuild the combined page (reads dashboard.html + the two md files)
python viz/build_visualizer.py
```

Both scripts default their paths relative to the repo (no absolute paths) and
accept positional overrides:

```bash
python viz/export_bench_data.py /path/to/repo /path/to/out.json
python viz/build_visualizer.py /path/to/viz
```

Note: `export_bench_data.py` only refreshes the JSON snapshot. The chart code
that renders that JSON lives inside `dashboard.html`; `build_visualizer.py`
folds `dashboard.html` plus the two markdown files into `visualizer.html`.
