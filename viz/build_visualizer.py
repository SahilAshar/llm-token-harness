"""Build the published CPC dashboard from dashboard.html into one of two modes.

Two output modes:

* default (offline) -> viz/visualizer.html: data is INLINED in a data-blob
  script tag, so the file works over file:// with zero network access.
* --pages (live data) -> viz/pages-index.html: identical layout, but the
  inlined data blob is dropped and the page fetches ./data/latest.json at
  runtime. Intended to be served over HTTP(S) (e.g. GitHub Pages). Degrades
  gracefully to a visible error banner if the fetch fails.

Usage:
    python viz/build_visualizer.py [--pages] [VIZ_DIR]

Defaults VIZ_DIR to this file's own directory.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

VIZ = Path(__file__).resolve().parent

# History-over-time (Chart 10) reads a single global contract:
#   window.__BENCH_HISTORY__ = newest-first slim run array.
# The offline build INLINES it (build_history_blob); the Pages build BLANKS it
# and fetches data/runs.json + each run file at runtime (HISTORY_LOADER_JS),
# falling back to [] on any failure so history is non-fatal to the page.
HISTORY_BLOB_ID = "history-blob"
RUNS_MANIFEST = "data/runs.json"

# Multi-rep CI study (Chart 11): a single dated aggregate produced by
# aggregate_reps.py. Offline build INLINES it; Pages build BLANKS it and fetches
# the file at runtime (REPS_LOADER_JS), falling back to null so Chart 11 degrades
# cleanly. Dated filename mirrors the runs/<date>.json convention; bump on rerun.
REPS_BLOB_ID = "reps-blob"
REPS_JSON = "data/reps_2026-06-13.json"

# Only the keys Chart 10 reads, to keep the inlined offline payload slim.
_HISTORY_CONFIG_KEYS = ("label", "provider", "accuracy", "cpc_usd", "score", "n_tasks")


# ---------- live-data (Pages) transform ----------

DATA_URL = "./data/latest.json"

# Replaces the inlined data-blob parse. The render code is wrapped in a function
# and only invoked after fetch() resolves; on failure we show a visible banner
# instead of a blank page.
PAGES_LOADER_JS = """
<script>
"use strict";
// Live-data loader for GitHub Pages: fetch the canonical latest snapshot,
// then run the (deferred) dashboard renderer. No CDNs; same-origin JSON only.
(function () {
  function banner(html) {
    var main = document.getElementById('main');
    var el = document.createElement('div');
    el.setAttribute('role', 'alert');
    el.style.cssText =
      'margin:32px 40px;padding:18px 22px;border:1px solid #f85149;' +
      'border-radius:10px;background:rgba(248,81,73,0.08);color:#f0b6b2;' +
      'font-size:14px;line-height:1.5;';
    el.innerHTML = html;
    if (main) { main.appendChild(el); } else { document.body.appendChild(el); }
  }
  // Genuine network / JSON load failure: the data never arrived.
  function showFetchError(msg) {
    banner(
      '<strong>Could not load benchmark data.</strong><br>' +
      'Tried to fetch <code>%URL%</code>. ' +
      'This page needs to be served over HTTP(S) (e.g. GitHub Pages) so the ' +
      'same-origin data file is reachable.<br><span style="opacity:0.8">' +
      msg + '</span>');
  }
  // Data arrived fine but a renderer threw: do NOT blame the fetch.
  function showRenderError(msg) {
    banner(
      '<strong>Benchmark data loaded, but a panel failed to render.</strong><br>' +
      'The data fetch succeeded — this is a rendering error, not a load ' +
      'failure. See the browser console for details.<br>' +
      '<span style="opacity:0.8">' + msg + '</span>');
  }
  fetch('%URL%', { cache: 'no-cache' })
    .then(function (r) {
      if (!r.ok) { throw new Error('HTTP ' + r.status + ' ' + r.statusText); }
      return r.json();
    })
    .then(function (data) {
      window.__BENCH_DATA__ = data;
      if (typeof window.__renderDashboard !== 'function') {
        showRenderError('Renderer not found.');
        return;
      }
      // History + multi-rep are non-fatal second-stage loads (fall back to
      // []/null), then render. Neither must block the single-run dashboard.
      var histP = (typeof window.__loadBenchHistory === 'function')
        ? window.__loadBenchHistory() : Promise.resolve([]);
      var repsP = (typeof window.__loadBenchReps === 'function')
        ? window.__loadBenchReps() : Promise.resolve(null);
      return Promise.all([
        histP.catch(function () { return []; }),
        repsP.catch(function () { return null; })
      ]).then(function (res) {
        window.__BENCH_HISTORY__ = res[0] || [];
        window.__BENCH_REPS__ = res[1] || null;
        // Keep render exceptions out of the fetch .catch so they are reported
        // honestly instead of masquerading as a data-load failure.
        try {
          window.__renderDashboard();
        } catch (err) {
          if (window.console && console.error) { console.error(err); }
          showRenderError(String(err));
        }
      });
    })
    .catch(function (err) { showFetchError(String(err)); });
})();
</script>
""".replace("%URL%", DATA_URL)


# ---------- history-over-time (Chart 10) ----------


def _slim_run(date: str, note: str, run: dict) -> dict:
    """Reduce a full run JSON to only the keys Chart 10 renders."""
    return {
        "date": date,
        "note": note,
        "n_tasks": run.get("meta", {}).get("n_tasks"),
        "configs": [
            {k: cfg.get(k) for k in _HISTORY_CONFIG_KEYS}
            for cfg in run.get("configs", [])
        ],
        "per_config_task_scores": run.get("per_config_task_scores", {}),
    }


def build_history(viz: Path) -> list[dict]:
    """Read runs.json + each run file into a newest-first slim history array.

    Newest-first order mirrors the manifest. Missing/broken run files are
    skipped (history is best-effort); a missing manifest yields []. The note
    is sourced from the manifest entry (authoritative caveat text).
    """
    manifest_path = viz / RUNS_MANIFEST
    if not manifest_path.exists():
        return []
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        return []
    history: list[dict] = []
    for entry in manifest.get("runs", []):
        rel = entry.get("path")
        if not rel:
            continue
        run_path = (manifest_path.parent / rel).resolve()
        try:
            run = json.loads(run_path.read_text())
        except (OSError, ValueError):
            continue
        history.append(
            _slim_run(
                date=entry.get("date", run.get("meta", {}).get("date", "")),
                note=entry.get("note", run.get("meta", {}).get("note", "")),
                run=run,
            )
        )
    return history


def inline_history(full_html: str, history: list[dict]) -> str:
    """Replace the placeholder history-blob with the real slim run payload.

    Mirrors the data-blob pattern: dashboard.html ships an empty `[]` blob;
    the offline build inlines real runs so the file works under file://.
    """
    payload = json.dumps(history, separators=(",", ":"))
    # Guard against a literal `</script>` inside any note string closing the tag.
    payload = payload.replace("</", "<\\/")
    new_html, n = re.subn(
        rf'(<script id="{HISTORY_BLOB_ID}" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + payload + m.group(2),
        full_html,
        count=1,
        flags=re.DOTALL,
    )
    if n != 1:
        raise RuntimeError("history-blob placeholder not found in dashboard.html")
    return new_html


# ---------- multi-rep CI study (Chart 11) ----------


def load_reps(viz: Path) -> dict | None:
    """Read the dated multi-rep aggregate, or None if absent/malformed."""
    path = viz / REPS_JSON
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) and obj.get("configs") else None


def inline_reps(full_html: str, reps: dict | None) -> str:
    """Replace the placeholder reps-blob with the real aggregate (or `{}`).

    Mirrors the history-blob pattern: dashboard.html ships an empty `{}` blob;
    the offline build inlines the real aggregate so Chart 11 works under file://.
    """
    payload = json.dumps(reps or {}, separators=(",", ":")).replace("</", "<\\/")
    new_html, n = re.subn(
        rf'(<script id="{REPS_BLOB_ID}" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + payload + m.group(2),
        full_html,
        count=1,
        flags=re.DOTALL,
    )
    if n != 1:
        raise RuntimeError("reps-blob placeholder not found in dashboard.html")
    return new_html


# Pages build: the multi-rep aggregate is fetched as a non-fatal stage. On ANY
# failure __BENCH_REPS__ falls back to null and Chart 11 shows its own degraded
# message — never the red banner.
REPS_LOADER_JS = """
<script>
"use strict";
// Live-data multi-rep loader: fetch the dated reps aggregate and expose it as
// window.__BENCH_REPS__. Non-fatal: any failure resolves to null.
window.__loadBenchReps = function () {
  return fetch('%REPS_URL%', { cache: 'no-cache' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (o) { return (o && o.configs) ? o : null; })
    .catch(function () { return null; });
};
</script>
""".replace("%REPS_URL%", "./" + REPS_JSON)


# Pages build: history is fetched as a non-fatal second stage. On ANY failure
# (missing manifest, bad run file, offline) __BENCH_HISTORY__ falls back to []
# and Chart 10 shows its own clean degraded message — never the red banner.
HISTORY_LOADER_JS = """
<script>
"use strict";
// Live-data history loader: fetch runs.json then each run file, slim to the
// Chart-10 contract, and expose newest-first as window.__BENCH_HISTORY__.
// Non-fatal: any failure resolves to [] so the rest of the dashboard renders.
window.__loadBenchHistory = function () {
  var KEYS = ['label', 'provider', 'accuracy', 'cpc_usd', 'score', 'n_tasks'];
  function slimCfg(c) {
    var o = {};
    for (var i = 0; i < KEYS.length; i++) { o[KEYS[i]] = c ? c[KEYS[i]] : undefined; }
    return o;
  }
  return fetch('./data/runs.json', { cache: 'no-cache' })
    .then(function (r) { if (!r.ok) { throw new Error('runs.json ' + r.status); } return r.json(); })
    .then(function (manifest) {
      var runs = (manifest && manifest.runs) || [];
      return Promise.all(runs.map(function (entry) {
        return fetch('./data/' + entry.path, { cache: 'no-cache' })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (run) {
            if (!run) { return null; }
            return {
              date: entry.date || (run.meta && run.meta.date) || '',
              note: entry.note || (run.meta && run.meta.note) || '',
              n_tasks: run.meta && run.meta.n_tasks,
              configs: (run.configs || []).map(slimCfg),
              per_config_task_scores: run.per_config_task_scores || {}
            };
          })
          .catch(function () { return null; });
      }));
    })
    .then(function (list) { return (list || []).filter(Boolean); })
    .catch(function () { return []; });
};
</script>
"""


def to_pages_variant(full_html: str) -> str:
    """Turn the inlined visualizer HTML into a fetch-based live-data variant."""
    out = full_html

    # History: blank the inlined blob and swap the JSON.parse bootstrap for a
    # placeholder the live loader will populate before __renderDashboard runs.
    out = re.sub(
        rf'(<script id="{HISTORY_BLOB_ID}" type="application/json">).*?(</script>)',
        r"\1[]\2",
        out,
        count=1,
        flags=re.DOTALL,
    )
    history_bootstrap = (
        "  window.__BENCH_HISTORY__ = JSON.parse("
        f"document.getElementById('{HISTORY_BLOB_ID}').textContent || '[]');"
    )
    pages_history_bootstrap = "  window.__BENCH_HISTORY__ = [];"
    if history_bootstrap not in out:
        raise RuntimeError(
            "expected history-blob bootstrap not found in dashboard.html"
        )
    out = out.replace(history_bootstrap, pages_history_bootstrap, 1)

    # Multi-rep: same treatment — blank the inlined blob and swap the bootstrap
    # for a placeholder the live loader populates before render.
    out = re.sub(
        rf'(<script id="{REPS_BLOB_ID}" type="application/json">).*?(</script>)',
        r"\1{}\2",
        out,
        count=1,
        flags=re.DOTALL,
    )
    reps_bootstrap = (
        "  window.__BENCH_REPS__ = (function () { try { var o = JSON.parse("
        f"document.getElementById('{REPS_BLOB_ID}').textContent || '{{}}'); "
        "return (o && o.configs) ? o : null; } catch (e) { return null; } })();"
    )
    pages_reps_bootstrap = "  window.__BENCH_REPS__ = null;"
    if reps_bootstrap not in out:
        raise RuntimeError("expected reps-blob bootstrap not found in dashboard.html")
    out = out.replace(reps_bootstrap, pages_reps_bootstrap, 1)

    # 1. Drop the stale inlined data so nothing ships baked into the page.
    out = re.sub(
        r'(<script id="data-blob" type="application/json">).*?(</script>)',
        r"\1{}\2",
        out,
        count=1,
        flags=re.DOTALL,
    )

    # 2. Source DATA from the fetched payload instead of the data-blob.
    parse_line = (
        "const DATA = JSON.parse(document.getElementById('data-blob').textContent);"
    )
    pages_data_line = "const DATA = window.__BENCH_DATA__;"
    if parse_line not in out:
        raise RuntimeError("expected data-blob parse line not found in dashboard.html")
    out = out.replace(parse_line, pages_data_line, 1)

    # 3. Defer the renderer: wrap the render script body in a function that the
    #    loader calls once data has arrived. The render block is the <script>
    #    immediately following the data-blob; it begins with `"use strict";`.
    open_marker = '<script>\n"use strict";\n' + pages_data_line
    wrapped_open = '<script>\n"use strict";\nwindow.__renderDashboard = function () {\n'
    if open_marker not in out:
        raise RuntimeError("could not locate render script opening to wrap")
    out = out.replace(open_marker, wrapped_open + pages_data_line, 1)

    # Close the wrapper at the end of that same script block. The render block
    # ends with `})();\n\n</script>` (the final IIFE then the closing tag).
    close_marker = "})();\n\n</script>"
    # HISTORY_LOADER_JS + REPS_LOADER_JS must precede PAGES_LOADER_JS so both
    # window.__loadBenchHistory and window.__loadBenchReps are defined when the
    # latest.json loader invokes them before rendering.
    wrapped_close = (
        "})();\n};\n</script>\n"
        + HISTORY_LOADER_JS
        + "\n"
        + REPS_LOADER_JS
        + "\n"
        + PAGES_LOADER_JS
    )
    if close_marker not in out:
        raise RuntimeError("could not locate render script closing to wrap")
    out = out.replace(close_marker, wrapped_close, 1)

    return out


# ---------- assemble ----------


def main() -> None:
    args = [a for a in sys.argv[1:]]
    pages = "--pages" in args
    args = [a for a in args if a != "--pages"]
    viz = Path(args[0]).resolve() if args else VIZ

    dash = (viz / "dashboard.html").read_text()

    # The published site is the dashboard only — the Insights and Hardening
    # Roadmap markdown tabs were removed (2026-06-13). dashboard.html ships its
    # own <main id="main"> and full <style>, so no tab shell is injected here.

    if pages:
        # Pages build: history is fetched at runtime; the blob stays empty and
        # to_pages_variant swaps the bootstrap to a loader-populated placeholder.
        pages_html = to_pages_variant(dash)
        out = viz / "pages-index.html"
        out.write_text(pages_html)
        print(f"wrote {out} ({len(pages_html)} bytes) [live-data / Pages]")
    else:
        # Offline build: inline the real dated runs so Chart 10 works under file://.
        history = build_history(viz)
        dash = inline_history(dash, history)
        print(f"  inlined {len(history)} dated run(s) for history-over-time")
        reps = load_reps(viz)
        dash = inline_reps(dash, reps)
        print(
            "  inlined multi-rep aggregate: "
            + (f"{len(reps['configs'])} configs" if reps else "none")
        )
        out = viz / "visualizer.html"
        out.write_text(dash)
        print(f"wrote {out} ({len(dash)} bytes)")


if __name__ == "__main__":
    main()
