"""Combine dashboard.html + insights + hardening md into one tabbed visualizer.

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

import html
import json
import re
import sys
from pathlib import Path

VIZ = Path(__file__).resolve().parent
INSIGHTS_MD = "insights-2026-06-12.md"
HARDENING_MD = "hardening-roadmap-2026-06-12.md"

# History-over-time (Chart 10) reads a single global contract:
#   window.__BENCH_HISTORY__ = newest-first slim run array.
# The offline build INLINES it (build_history_blob); the Pages build BLANKS it
# and fetches data/runs.json + each run file at runtime (HISTORY_LOADER_JS),
# falling back to [] on any failure so history is non-fatal to the page.
HISTORY_BLOB_ID = "history-blob"
RUNS_MANIFEST = "data/runs.json"

# Only the keys Chart 10 reads, to keep the inlined offline payload slim.
_HISTORY_CONFIG_KEYS = ("label", "provider", "accuracy", "cpc_usd", "score", "n_tasks")


# ---------- minimal markdown -> HTML ----------


def _inline(text: str) -> str:
    # protect code spans
    spans: list[str] = []

    def stash(m: re.Match[str]) -> str:
        spans.append(html.escape(m.group(1)))
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<em>\1</em>", text)

    def restore(m: re.Match[str]) -> str:
        return f"<code>{spans[int(m.group(1))]}</code>"

    return re.sub(r"\x00(\d+)\x00", restore, text)


def md_to_html(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    list_stack: list[str] = []  # 'ul'/'ol' with indents

    def close_lists(to: int = 0) -> None:
        while len(list_stack) > to:
            out.append(f"</{list_stack.pop()}>")

    while i < n:
        line = lines[i]

        # fenced code
        m = re.match(r"^```(\w*)", line)
        if m:
            close_lists()
            lang = m.group(1)
            i += 1
            buf: list[str] = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            cls = f' class="lang-{lang}"' if lang else ""
            out.append(
                f"<pre><code{cls}>" + html.escape("\n".join(buf)) + "</code></pre>"
            )
            continue

        # table
        if (
            line.lstrip().startswith("|")
            and i + 1 < n
            and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1])
        ):
            close_lists()
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows: list[list[str]] = []
            while i < n and lines[i].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append('<table class="md-table"><thead><tr>')
            out.extend(f"<th>{_inline(c)}</th>" for c in header)
            out.append("</tr></thead><tbody>")
            for r in rows:
                out.append(
                    "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
                )
            out.append("</tbody></table>")
            continue

        # heading
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            close_lists()
            lvl = min(len(m.group(1)) + 1, 6)  # offset: # -> h2
            out.append(f"<h{lvl}>{_inline(m.group(2).strip())}</h{lvl}>")
            i += 1
            continue

        # hr
        if re.match(r"^\s*([-*_])\1\1+\s*$", line):
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        # blockquote
        if line.lstrip().startswith(">"):
            close_lists()
            buf2: list[str] = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf2.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f"<blockquote>{_inline(' '.join(buf2))}</blockquote>")
            continue

        # list item
        m = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", line)
        if m:
            indent = len(m.group(1))
            kind = "ol" if m.group(2)[0].isdigit() else "ul"
            depth = 1 if indent >= 2 else 0
            target = depth + 1
            while len(list_stack) > target:
                out.append(f"</{list_stack.pop()}>")
            if len(list_stack) < target:
                list_stack.append(kind)
                out.append(f"<{kind}>")
            elif list_stack and list_stack[-1] != kind:
                out.append(f"</{list_stack.pop()}>")
                list_stack.append(kind)
                out.append(f"<{kind}>")
            out.append(f"<li>{_inline(m.group(3))}</li>")
            i += 1
            continue

        # blank
        if not line.strip():
            close_lists()
            i += 1
            continue

        # paragraph (gather until blank / block)
        close_lists()
        buf3 = [line]
        i += 1
        while (
            i < n
            and lines[i].strip()
            and not re.match(r"^(#{1,6}\s|```|\s*[-*+]\s|\s*\d+\.\s|>|\|)", lines[i])
        ):
            buf3.append(lines[i])
            i += 1
        out.append(f"<p>{_inline(' '.join(buf3))}</p>")

    close_lists()
    return "\n".join(out)


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
      // History is a non-fatal second stage: load it (or fall back to []),
      // then render. A history failure must NOT block the single-run dashboard.
      var histP = (typeof window.__loadBenchHistory === 'function')
        ? window.__loadBenchHistory() : Promise.resolve([]);
      return histP.catch(function () { return []; }).then(function (history) {
        window.__BENCH_HISTORY__ = history || [];
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
        raise RuntimeError("expected history-blob bootstrap not found in dashboard.html")
    out = out.replace(history_bootstrap, pages_history_bootstrap, 1)

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
    # HISTORY_LOADER_JS must precede PAGES_LOADER_JS so window.__loadBenchHistory
    # is defined when the latest.json loader invokes it before rendering.
    wrapped_close = (
        "})();\n};\n</script>\n" + HISTORY_LOADER_JS + "\n" + PAGES_LOADER_JS
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
    insights = md_to_html((viz / INSIGHTS_MD).read_text())
    hardening = md_to_html((viz / HARDENING_MD).read_text())

    extra_css = """
  /* ---- tabs + markdown (combined visualizer) ---- */
  nav.tabs {
    position: sticky; top: 0; z-index: 20;
    display: flex; gap: 4px;
    padding: 0 40px; background: var(--panel);
    border-bottom: 1px solid var(--border);
  }
  nav.tabs button {
    background: none; border: none; color: var(--muted);
    font-family: var(--font-mono); font-size: 12px; font-weight: 500;
    letter-spacing: 0.10em; text-transform: uppercase;
    padding: 13px 18px; cursor: pointer;
    border-bottom: 2px solid transparent; margin-bottom: -1px;
  }
  nav.tabs button:hover { color: var(--text); }
  nav.tabs button.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }
  .md-content {
    max-width: 1000px; margin: 0 auto; padding: 32px 40px 80px;
  }
  .md-content h2 { font-family: var(--font-display); font-weight: 600;
    font-size: 22px; margin: 38px 0 12px; letter-spacing: 0.005em;
    padding-bottom: 8px; border-bottom: 1px solid var(--border); }
  .md-content h3 { font-family: var(--font-display); font-weight: 600;
    font-size: 17px; margin: 28px 0 10px; color: var(--text); letter-spacing: 0.005em; }
  .md-content h4 { font-family: var(--font-mono); font-size: 12px; margin: 20px 0 8px;
    color: var(--accent); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.10em; }
  .md-content p { margin: 10px 0; color: var(--text); }
  .md-content li { margin: 5px 0; }
  .md-content ul, .md-content ol { margin: 8px 0; padding-left: 24px; }
  .md-content code { background: var(--panel-2); border: 1px solid var(--border);
    border-radius: 4px; padding: 1px 5px; font-size: 12px;
    font-family: var(--font-mono); color: var(--code-fg); }
  .md-content pre { background: var(--code-bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 14px 16px; overflow-x: auto; margin: 14px 0; }
  .md-content pre code { background: none; border: none; padding: 0;
    font-size: 12.5px; color: var(--code-fg); line-height: 1.5; }
  .md-content blockquote { border-left: 3px solid var(--accent);
    margin: 14px 0; padding: 4px 16px; color: var(--muted); background: var(--panel); }
  .md-content hr { border: none; border-top: 1px solid var(--border); margin: 28px 0; }
  .md-content a { color: var(--accent); text-decoration: none; }
  .md-content a:hover { text-decoration: underline; }
  table.md-table { border-collapse: collapse; width: 100%; margin: 16px 0;
    font-size: 13px; }
  table.md-table th, table.md-table td {
    border: 1px solid var(--border); padding: 7px 11px; text-align: left;
    vertical-align: top; }
  table.md-table th { background: var(--panel-2); font-weight: 600; }
  table.md-table tr:nth-child(even) td { background: rgba(255,255,255,0.015); }
"""

    tab_nav = (
        '<nav class="tabs">'
        '<button class="tab-btn active" data-tab="dashboard">Dashboard</button>'
        '<button class="tab-btn" data-tab="insights">Insights</button>'
        '<button class="tab-btn" data-tab="hardening">Hardening Roadmap</button>'
        "</nav>"
    )

    insights_panel = (
        '<section id="tab-insights" class="tab-panel">'
        f'<div class="md-content">{insights}</div></section>'
    )
    hardening_panel = (
        '<section id="tab-hardening" class="tab-panel">'
        f'<div class="md-content">{hardening}</div></section>'
    )

    tab_js = """
<script>
(function () {
  var btns = document.querySelectorAll('.tab-btn');
  var panels = {
    dashboard: 'tab-dashboard', insights: 'tab-insights', hardening: 'tab-hardening'
  };
  btns.forEach(function (b) {
    b.addEventListener('click', function () {
      btns.forEach(function (x) { x.classList.remove('active'); });
      b.classList.add('active');
      Object.values(panels).forEach(function (id) {
        document.getElementById(id).classList.remove('active');
      });
      document.getElementById(panels[b.dataset.tab]).classList.add('active');
      window.scrollTo(0, 0);
    });
  });
})();
</script>
"""

    # inject
    dash = dash.replace("</style>", extra_css + "\n</style>", 1)
    dash = dash.replace("</header>", "</header>\n" + tab_nav, 1)
    dash = dash.replace(
        '<main id="main"></main>',
        '<section id="tab-dashboard" class="tab-panel active">'
        '<main id="main"></main></section>\n' + insights_panel + "\n" + hardening_panel,
        1,
    )
    dash = dash.replace("</body>", tab_js + "\n</body>", 1)

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
        out = viz / "visualizer.html"
        out.write_text(dash)
        print(f"wrote {out} ({len(dash)} bytes)")


if __name__ == "__main__":
    main()
