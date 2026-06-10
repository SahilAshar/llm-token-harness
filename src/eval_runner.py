"""Eval runner: execute tasks against an adapter and compute CPC.

CPC (Cost Per Correct) = total run cost / number of tasks with a
correct tool selection. CPC is None when nothing was correct.

Cost attribution keys off the model name reported in the API
*response* (``LLMResponse.model``), not the requested model: some
models (e.g. claude-fable-5) silently reroute a small share of
requests to a different model (claude-opus-4-8) billed at that
model's prices.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.adapters.base import LLMAdapter
from src.pricing import get_pricing
from src.scorer import TaskResult, score_task
from src.tasks import Task
from src.tools import ALL_TOOLS

DEFAULT_MAX_OUTPUT_TOKENS = 1024


class TaskRunRecord(BaseModel, frozen=True):
    result: TaskResult
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    latency_seconds: float
    response_model: str
    cost_usd: float


class RunSummary(BaseModel, frozen=True):
    model_requested: str
    provider: str
    n_tasks: int
    n_correct: int
    accuracy: float
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    cpc_usd: float | None
    mean_latency_seconds: float


def run_task(
    adapter: LLMAdapter,
    model: str,
    task: Task,
    *,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    effort: str | None = None,
) -> TaskRunRecord:
    extra: dict[str, Any] = {}
    if effort is not None:
        extra["effort"] = effort

    start = time.perf_counter()
    response = adapter.complete(
        model=model,
        messages=task.messages,
        max_output_tokens=max_output_tokens,
        tools=ALL_TOOLS,
        **extra,
    )
    latency = time.perf_counter() - start

    result = score_task(task, response.tool_calls)
    response_model = response.model or model
    cost = get_pricing(response_model, adapter.provider).cost_usd(
        response.input_tokens, response.output_tokens
    )
    return TaskRunRecord(
        result=result,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        reasoning_tokens=response.reasoning_tokens,
        latency_seconds=latency,
        response_model=response_model,
        cost_usd=cost,
    )


def summarize(model: str, provider: str, records: list[TaskRunRecord]) -> RunSummary:
    n_tasks = len(records)
    n_correct = sum(r.result.score for r in records)
    total_cost = sum(r.cost_usd for r in records)
    return RunSummary(
        model_requested=model,
        provider=provider,
        n_tasks=n_tasks,
        n_correct=n_correct,
        accuracy=n_correct / n_tasks if n_tasks else 0.0,
        total_input_tokens=sum(r.input_tokens for r in records),
        total_output_tokens=sum(r.output_tokens for r in records),
        total_cost_usd=total_cost,
        cpc_usd=total_cost / n_correct if n_correct else None,
        mean_latency_seconds=(
            sum(r.latency_seconds for r in records) / n_tasks if n_tasks else 0.0
        ),
    )


def run_eval(
    adapter: LLMAdapter,
    model: str,
    tasks: list[Task],
    *,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    effort: str | None = None,
) -> tuple[list[TaskRunRecord], RunSummary]:
    records = [
        run_task(
            adapter,
            model,
            task,
            max_output_tokens=max_output_tokens,
            effort=effort,
        )
        for task in tasks
    ]
    return records, summarize(model, str(adapter.provider), records)


def write_results(
    records: list[TaskRunRecord],
    summary: RunSummary,
    output_dir: str | Path,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    model_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", summary.model_requested)
    path = out / f"eval_{model_slug}_{timestamp}.json"
    payload = {
        "summary": summary.model_dump(),
        "records": [r.model_dump() for r in records],
    }
    path.write_text(json.dumps(payload, indent=2))
    return path
