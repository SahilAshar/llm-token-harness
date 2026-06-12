"""Combine dashboard.html + insights + hardening md into one tabbed visualizer.

Output: viz/visualizer.html (single self-contained file).

Usage:
    python viz/build_visualizer.py [VIZ_DIR]

Defaults VIZ_DIR to this file's own directory.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

VIZ = Path(__file__).resolve().parent
INSIGHTS_MD = "insights-2026-06-12.md"
HARDENING_MD = "hardening-roadmap-2026-06-12.md"


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


# ---------- assemble ----------


def main() -> None:
    viz = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else VIZ

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
    font: inherit; font-size: 14px; font-weight: 600;
    padding: 14px 18px; cursor: pointer;
    border-bottom: 2px solid transparent; margin-bottom: -1px;
  }
  nav.tabs button:hover { color: var(--text); }
  nav.tabs button.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }
  .md-content {
    max-width: 1000px; margin: 0 auto; padding: 32px 40px 80px;
  }
  .md-content h2 { font-size: 24px; margin: 36px 0 12px; letter-spacing: -0.01em;
    padding-bottom: 6px; border-bottom: 1px solid var(--border); }
  .md-content h3 { font-size: 19px; margin: 28px 0 10px; color: var(--text); }
  .md-content h4 { font-size: 15px; margin: 20px 0 8px; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.04em; }
  .md-content p { margin: 10px 0; color: var(--text); }
  .md-content li { margin: 5px 0; }
  .md-content ul, .md-content ol { margin: 8px 0; padding-left: 24px; }
  .md-content code { background: var(--panel-2); border: 1px solid var(--border);
    border-radius: 4px; padding: 1px 5px; font-size: 12.5px;
    font-family: "SF Mono", ui-monospace, Menlo, monospace; color: #b9c4d4; }
  .md-content pre { background: #0a0e14; border: 1px solid var(--border);
    border-radius: 8px; padding: 14px 16px; overflow-x: auto; margin: 14px 0; }
  .md-content pre code { background: none; border: none; padding: 0;
    font-size: 12.5px; color: #c9d4e3; line-height: 1.5; }
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
        '<button class="tab-btn active" data-tab="dashboard">📊 Dashboard</button>'
        '<button class="tab-btn" data-tab="insights">🔍 Insights</button>'
        '<button class="tab-btn" data-tab="hardening">🛠 Hardening Roadmap</button>'
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

    out = viz / "visualizer.html"
    out.write_text(dash)
    print(f"wrote {out} ({len(dash)} bytes)")


if __name__ == "__main__":
    main()
