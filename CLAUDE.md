# CLAUDE.md

## What this is

A search agent evaluation harness that tests how well different LLMs pick the right tool with the right arguments when acting as the brain of a search agent. Not a search agent itself — the exam, not the student.

**North star metric:** CPC (Cost Per Correct) = total run cost / tasks with correct retrieval strategy.

**Secondary north star — history over time:** results accumulate as dated snapshots so CPC/accuracy trends stay visible across dataset and model changes. The data layout preserves this (see "Visualization & publishing"); the dashboard's history *view* is future work. Do **not** churn the eval harness to chase this — just keep every run as a dated snapshot.

**Priority ordering:** Quality first, latency second, dollar cost third.

## Architecture

Single-turn eval: each task is one prompt → one expected tool call. Multi-step chains share a `scenario_id` and build real conversation history (not text summaries). The corpus is simulated — tool responses are hardcoded JSON. We're measuring the MODEL's search reasoning, isolated from retrieval infrastructure.

Current dataset: `data/tasks/search_agent_v1.json` — 25 tasks over a simulated contract repository: 3 chains (5, 4, and 4 steps) with non-adjacent state dependencies, 2 parallel-invocation tasks, 3 constraint-dense filter tasks, 1 relative-date filter task, and a 6-task easy baseline floor. The full pipeline (runner, CPC computation, CLI) is shipped; run it via `make eval`.

### Key modules

| Module | Purpose |
|---|---|
| `src/adapters/` | Provider adapters (OpenAI, Anthropic, Ollama) with unified `LLMAdapter` ABC |
| `src/adapters/base.py` | `Provider` enum, `ToolCall`, `LLMResponse` (Pydantic models) |
| `src/tools.py` | 4 search tool schemas + 5 distractor tool schemas in OpenAI function-calling format |
| `src/tasks.py` | `Task`, `ExpectedArg`, `ExpectedCall` models + JSON loader (validates single-call vs parallel mode) |
| `src/scorer.py` | All-or-nothing scoring: tool name + all args must match (primary, alternative, or all parallel specs) |
| `src/pricing.py` | Per-model token pricing, $0 for local/Ollama |
| `src/eval_runner.py` | Executes tasks against an adapter, computes CPC, writes results |
| `src/cli.py` | CLI entry point (`make eval`): runs an eval and prints a CPC summary |
| `data/tasks/` | Task JSON files |

### Legacy V1 files (excluded from lint)

These are from the original math/sentiment harness and are excluded in `pyproject.toml` ruff config: `src/adapter.py`, `src/runner.py`, `src/suites.py`, `src/trial.py`, `src/result_logger.py`, `utils/`, `main.py`.

### The 4 tools (QU → Strategy pipeline)

- `search(query, filters?, top_k=5)` — semantic search with inline metadata filtering
- `get_document(doc_id)` — fetch full doc by ID
- `list_documents(filters?)` — metadata-only exploration
- `query_decompose(query)` — break complex queries into sub-queries

### The 5 distractor tools

- 3 categorically wrong: `web_search(query)` (wrong corpus), `tag_document(doc_id, tags)` (wrong operation class), `create_alert(query, frequency?)` (wrong temporal mode)
- 2 semantic near-misses: `summarize_document(doc_id, focus?)` (shadows `get_document`; returns generated text, not source text) and `search_history(query?, filters?)` (shadows `search`; searches prior interactions, not the corpus)
- All are plausible schemas offered alongside the real tools (`ALL_TOOLS = SEARCH_TOOLS + DISTRACTOR_TOOLS`) but never the correct answer for any task
- Why: defends against saturation by testing tool *discrimination*, not just tool use (MCPAgentBench pattern)
- Distractor-pick rate is tracked from `actual_tools` in raw results as an unscored behavioral metric

### Scoring

- **All-or-nothing:** score is 1 if tool name matches AND all required args match, 0 otherwise
- **Batch-aware:** every tool call in the model's batch is evaluated; ANY fully matching call scores 1. `TaskResult.actual_tools` records all call names in order, so parallel-call propensity and decompose invocation rate fall out of the raw results
- **Two arg match types:** `exact` (doc_id, top_k, filters — case-insensitive, type-coerced, dict key-order and list order insensitive) and `keywords` (query — all keywords must appear in model's value)
- **Adjudicated alternatives:** tasks may carry an optional `expected_alternatives` list of equally-correct strategies; a full match against the primary expected spec OR any alternative scores 1. No partial credit across alternatives; failure reporting stays anchored to the primary spec
- **Parallel mode:** a task has exactly one of `expected` (single call, optional alternatives) or `expected_parallel` (2+ specs that must ALL be matched by calls in one batch — any-call-per-spec, all-specs-required). `TaskResult.parallel_matched`/`parallel_expected`/`parallel_failed_specs` record per-spec results; the score stays all-or-nothing
- **Per-spec parallel alternatives:** each `expected_parallel` spec may carry an `alternatives` list (adjudicated equally-correct variants of that one spec, e.g. counterparty scoped via a metadata filter with a topical query instead of a counterparty token in the query string). A call matching the spec's primary or any alternative satisfies it; alternatives cannot nest. Added after the June-12 rerun showed correct filter-scoped fan-outs scoring 0 on both parallel tasks
- `tool_choice: "auto"` — models must decide WHETHER to use tools

## Code conventions

### Strong typing

- **Pydantic v2** `BaseModel` with `frozen=True` for all data models. No raw dataclasses.
- **mypy strict** across all new code. Legacy files are excluded.
- **StrEnum** for closed sets (Provider, ArgMatchType).
- Always use keyword arguments when constructing Pydantic models.

### Dependencies and tooling

- **uv** for dependency management. `.in` files are source of truth, `.txt` files are compiled locks.
- **Makefile** targets: `install`, `lint`, `test`, `clean`.
- **ruff** for linting (`E`, `F`, `I`, `UP` rules) and formatting (88 char line length).
- **pytest** with `@pytest.mark.live` for tests that hit real APIs or local services.

### Style

- Explicit imports, no star imports.
- `from __future__ import annotations` in every file.
- Canonical tool format is OpenAI function-calling (`{type: "function", function: {name, description, parameters}}`). Anthropic adapter converts internally.
- Filters are flat key-value with `start_date`/`end_date` for date ranges.

## CI

GitHub Actions runs on push to main and PRs:
- `ruff check` + `ruff format --check`
- `mypy` on all new `src/` modules
- `pytest -m "not live"` — all unit tests, excluding live API/Ollama tests

## Running locally

```bash
uv venv && uv pip install -r requirements-dev.txt
make lint    # ruff + mypy
make test    # pytest (all tests, including live if APIs available)

# Ollama must be running for local model tests
ollama list  # should show gemma4:12b
```

## Design decisions

Key decisions and their rationale (don't relitigate — read first):

1. **Search agent domain** — not generic tool-calling. Evaluates retrieval strategy, not retrieval results.
2. **Single-turn tasks** — each task is one prompt → one tool call. Multi-step chains share a scenario_id.
3. **4 realistic tools** — trimmed from 9, then from 5. Mirrors real search APIs (LangChain, LlamaIndex, Azure AI Search). Cut: summarize, query_expand, entity_extract, passage_retrieve, metadata_filter (absorbed into search filters). `compare` was also removed after dataset red-teaming: comparison is in-context generation work after retrieval, not a retrieval operation, and no real search API exposes it standalone.
4. **All-or-nothing scoring** — binary 1/0. Partial credit backlogged for V2.
5. **Keyword-contains for free-text args** — no NLP deps. We control both sides (task authoring + expected args).
6. **Conversation history for multi-step state** — real message history, not text summaries. Chain histories always follow the primary expected path; `expected_alternatives` affect scoring only, so a step whose alternative was the "actual" answer still sees primary-path history at the next step.
7. **tool_choice: "auto"** — models must decide WHETHER to use tools.
8. **Quality → Latency → Dollar cost** — priority ordering for metrics.
9. **Gemma 4 thinking not disabled** — reasoning token cost is real data for CPC.
10. **`expected_alternatives` for adjudicated ties** — when dataset red-teaming shows two retrieval strategies are equally sound, the task lists both rather than penalizing one. Alternatives are added only after adjudication, never to paper over a vague task.
11. **Four hardening axes (shipped)** — the first benchmark run showed 10/15 tasks passed by everyone; single-turn selection from small tool sets is saturated industry-wide. Hardened along: (1) longer chains with non-adjacent state dependency, (2) constraint-dense filters, (3) semantic near-miss distractors, (4) parallel invocation scoring (`expected_parallel`). Easy tasks are kept as a baseline floor; the hard tasks are where CPC means something.

## Visualization & publishing

The benchmark dashboard is published at **cpc.sahilashar.com** (Cloudflare Pages). Harness code + data live entirely in this repo; the personal site only links out (never touched on a results refresh).

- **Data layout** (`viz/data/`): `runs/<date>.json` (immutable per-run history) + `latest.json` (the only file the live site fetches) + `runs.json` (manifest, newest-first, for the future history view). `export_bench_data.py` writes all three on every export; `latest.json` always mirrors the newest run.
- **Two page builds** (`build_visualizer.py`): default → `visualizer.html` (data inlined, opens under `file://`); `--pages` → `pages-index.html` (fetches `./data/latest.json`, served as `index.html`).
- **Publishing is Path A (manual / on-demand):** `viz/deploy_pages.sh` assembles a clean site dir and runs `wrangler pages deploy` — a direct upload with a scoped `CLOUDFLARE_API_TOKEN`, no cron and no GitHub secret. Flow: local run → PR → Cloudflare preview → merge → deploy.
- **Path B (later, not built):** scheduled cloud runs + a "publish only if the run is healthy" gate, plus the dashboard history-over-time view. Caveat: gemma can't run in CI (no local Ollama), so cloud runs are API-models-only.

## What's next

- CPC-methodology blog post (canonical data: `viz/data/runs/2026-06-12-r2.json` + `viz/insights-2026-06-12-r2.md`)
- Dashboard history-over-time view (trend charts reading `runs.json`)
- Resolve the `vendor_renewal_decompose_01` keep-strict vs loosen adjudication with the rerun data in hand
- V2 backlog: anchor-dependent relative-date tasks (Axis E follow-up), `expected_no_call` mode (Axis D redesign), partial credit
- Path B: scheduled runs + run-health publish gate
