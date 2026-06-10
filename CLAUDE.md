# CLAUDE.md

## What this is

A search agent evaluation harness that tests how well different LLMs pick the right tool with the right arguments when acting as the brain of a search agent. Not a search agent itself — the exam, not the student.

**North star metric:** CPC (Cost Per Correct) = total run cost / tasks with correct retrieval strategy.

**Priority ordering:** Quality first, latency second, dollar cost third.

## Architecture

Single-turn eval: each task is one prompt → one expected tool call. Multi-step chains share a `scenario_id` and build real conversation history (not text summaries). The corpus is simulated — tool responses are hardcoded JSON. We're measuring the MODEL's search reasoning, isolated from retrieval infrastructure.

### Key modules

| Module | Purpose |
|---|---|
| `src/adapters/` | Provider adapters (OpenAI, Anthropic, Ollama) with unified `LLMAdapter` ABC |
| `src/adapters/base.py` | `Provider` enum, `ToolCall`, `LLMResponse` (Pydantic models) |
| `src/tools.py` | 4 search tool schemas + 3 distractor tool schemas in OpenAI function-calling format |
| `src/tasks.py` | `Task`, `ExpectedArg` models + JSON loader |
| `src/scorer.py` | All-or-nothing scoring: tool name + all args must match |
| `src/pricing.py` | Per-model token pricing, $0 for local/Ollama |
| `data/tasks/` | Task JSON files |

### Legacy V1 files (excluded from lint)

These are from the original math/sentiment harness and are excluded in `pyproject.toml` ruff config: `src/adapter.py`, `src/runner.py`, `src/suites.py`, `src/trial.py`, `src/result_logger.py`, `utils/`, `main.py`.

### The 4 tools (QU → Strategy pipeline)

- `search(query, filters?, top_k=5)` — semantic search with inline metadata filtering
- `get_document(doc_id)` — fetch full doc by ID
- `list_documents(filters?)` — metadata-only exploration
- `query_decompose(query)` — break complex queries into sub-queries

### The 3 distractor tools

- `web_search(query)`, `tag_document(doc_id, tags)`, `create_alert(query, frequency?)` — plausible schemas offered to models alongside the real tools (`ALL_TOOLS = SEARCH_TOOLS + DISTRACTOR_TOOLS`) but never the correct answer for any task
- Why: defends against saturation by testing tool *discrimination*, not just tool use (MCPAgentBench pattern)
- Distractor-pick rate is tracked from `actual_tools` in raw results as an unscored behavioral metric

### Scoring

- **All-or-nothing:** score is 1 if tool name matches AND all required args match, 0 otherwise
- **Batch-aware:** every tool call in the model's batch is evaluated; ANY fully matching call scores 1. `TaskResult.actual_tools` records all call names in order, so parallel-call propensity and decompose invocation rate fall out of the raw results
- **Two arg match types:** `exact` (doc_id, top_k, filters — case-insensitive, type-coerced, dict key-order and list order insensitive) and `keywords` (query — all keywords must appear in model's value)
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
6. **Conversation history for multi-step state** — real message history, not text summaries.
7. **tool_choice: "auto"** — models must decide WHETHER to use tools.
8. **Quality → Latency → Dollar cost** — priority ordering for metrics.
9. **Gemma 4 thinking not disabled** — reasoning token cost is real data for CPC.

## What's next

- Visualization (quality vs cost scatter plot)
