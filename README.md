# LLM Token Harness — Search Agent Eval

A search-agent **evaluation harness** that measures how well different LLMs pick the
right tool with the right arguments when acting as the brain of a search agent. It is
**the exam, not the student**: the corpus is simulated and tool responses are hardcoded
JSON, so what's being measured is the *model's* retrieval reasoning, isolated from real
retrieval infrastructure.

> **North-star metric — CPC (Cost Per Correct)** = total agent-run cost ÷ tasks where the
> retrieval strategy was correct. The publishable output is a quality-vs-cost scatter,
> one dot per model; the efficient frontier is the story.

Results are published at **[cpc.sahilashar.com](https://cpc.sahilashar.com)**.

## How it works

Each task is a single turn: a conversation history (system prompt + user query + any prior
tool calls, as real message history) → **one expected tool call**. Multi-step workflows are
modelled as chains of single-turn tasks sharing a `scenario_id`, with non-adjacent state
dependencies. The model sees all tool schemas with `tool_choice: "auto"` and must decide
*whether* and *which* to call.

- **4 search tools:** `search(query, filters?, top_k=5)`, `get_document(doc_id)`,
  `list_documents(filters?)`, `query_decompose(query)`.
- **5 distractor tools** offered alongside them but never the correct answer — 3 categorically
  wrong (`web_search`, `tag_document`, `create_alert`) and 2 semantic near-misses
  (`summarize_document`, `search_history`) — to test tool *discrimination*, not just tool use.
- **Scoring is all-or-nothing:** 1 if the tool name and all required args match, else 0.
  Args match by `exact` (structured: doc_id, top_k, filters — order/case-insensitive) or
  `keywords` (free text: all keywords must appear). Parallel tasks require every expected
  call to be matched by the model's batch. Tasks may carry adjudicated `expected_alternatives`.

Current dataset: `data/tasks/search_agent_v1.json` — 25 tasks over a simulated contract
repository (3 chains, 2 parallel-invocation tasks, constraint-dense filters, a relative-date
filter, and a 6-task easy baseline floor).

## Quickstart

```bash
uv venv && uv pip install -r requirements-dev.txt
make lint    # ruff + mypy
make test    # pytest (add live tests when API keys / Ollama are available)

# Run an eval (CPC summary prints to stdout; per-run JSON lands in results/)
make eval MODEL=claude-haiku-4-5 PROVIDER=anthropic TASKS=data/tasks/search_agent_v1.json
# optional reasoning-effort sweep: append EFFORT=medium
```

Providers: OpenAI, Anthropic, Ollama (local, $0 API cost — e.g. `gemma4:12b`). Cost is keyed
off the model reported in each API **response**, so silent provider fallbacks are billed
correctly.

## Layout

| Path | Purpose |
|---|---|
| `src/adapters/` | Provider adapters (OpenAI, Anthropic, Ollama) behind a unified `LLMAdapter` |
| `src/tools.py` | The 4 search tools + 5 distractor schemas (OpenAI function-calling format) |
| `src/tasks.py` | `Task` models + JSON loader (validates single-call vs. parallel mode) |
| `src/scorer.py` | All-or-nothing scoring (exact/keywords, parallel, alternatives) |
| `src/pricing.py` | Per-model token pricing ($0 for local/Ollama) |
| `src/eval_runner.py` | Executes tasks, computes CPC, writes per-run results |
| `src/cli.py` | `make eval` entry point + CPC summary |
| `data/tasks/` | Task datasets |
| `viz/` | Dashboard build (`build_visualizer.py`), data export, and publish path |

See [`CLAUDE.md`](CLAUDE.md) for the full architecture, scoring rules, and design decisions.

## Visualization

`viz/export_bench_data.py` writes immutable per-run snapshots (`viz/data/runs/<date>.json`),
a `latest.json` the live site fetches, and a `runs.json` manifest. `make visualizer` rebuilds
the offline dashboard (`viz/visualizer.html`, data inlined, opens under `file://`);
`viz/deploy_pages.sh` builds and deploys the Cloudflare Pages variant. Generated HTML is not
checked in — only the `dashboard.html` source is.
