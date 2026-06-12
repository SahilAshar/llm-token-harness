"""Task definitions and loader for search agent evaluation.

Each task is a single-turn decision: given a conversation history
(possibly including prior tool calls), the model picks the next
tool call. Multi-step chains share a scenario_id.

Tasks come in two mutually exclusive modes: single-call (``expected``
plus optional ``expected_alternatives``) and parallel
(``expected_parallel`` — a set of calls that must ALL be issued in
one batch).
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class ArgMatchType(StrEnum):
    EXACT = "exact"
    KEYWORDS = "keywords"


class ExpectedArg(BaseModel, frozen=True):
    name: str
    match_type: ArgMatchType
    value: Any


class ExpectedCall(BaseModel, frozen=True):
    tool: str
    args: list[ExpectedArg]
    # Adjudicated equally-correct variants of THIS spec (parallel-task
    # specs only): a call matching the primary or any alternative
    # satisfies the spec. Depth 1 — alternatives cannot nest.
    alternatives: list[ExpectedCall] = []


class Task(BaseModel, frozen=True):
    task_id: str
    scenario_id: str
    step: int
    description: str
    messages: list[dict[str, Any]]
    # Single-call mode: empty only when expected_parallel is set
    # (load_tasks enforces exactly one mode per task).
    expected_tool: str = ""
    expected_args: list[ExpectedArg] = []
    # Adjudicated equally-correct strategies; any full match scores 1.
    expected_alternatives: list[ExpectedCall] = []
    # Parallel mode: ALL specs must be matched by calls in one batch.
    expected_parallel: list[ExpectedCall] | None = None
    scoring_weights: dict[str, Any] = {}


def _parse_expected_args(raw: dict[str, Any]) -> list[ExpectedArg]:
    return [
        ExpectedArg(
            name=name,
            match_type=ArgMatchType(spec["type"]),
            value=spec["value"],
        )
        for name, spec in raw.items()
    ]


def _parse_expected_call(
    raw: dict[str, Any], task_id: str, *, allow_alternatives: bool = False
) -> ExpectedCall:
    alternatives_raw = raw.get("alternatives", [])
    if alternatives_raw and not allow_alternatives:
        raise ValueError(
            f"task {task_id}: per-spec 'alternatives' only applies to"
            " 'expected_parallel' specs and cannot nest"
        )
    return ExpectedCall(
        tool=raw["tool"],
        args=_parse_expected_args(raw.get("args", {})),
        alternatives=[_parse_expected_call(alt, task_id) for alt in alternatives_raw],
    )


def _parse_task(raw: dict[str, Any]) -> Task:
    task_id = raw["task_id"]
    has_expected = "expected" in raw
    has_parallel = "expected_parallel" in raw
    if has_expected == has_parallel:
        raise ValueError(
            f"task {task_id}: exactly one of 'expected' or"
            " 'expected_parallel' is required"
        )

    expected_tool = ""
    expected_args: list[ExpectedArg] = []
    expected_parallel: list[ExpectedCall] | None = None
    if has_expected:
        if "alternatives" in raw["expected"]:
            raise ValueError(
                f"task {task_id}: 'alternatives' inside 'expected' is not"
                " supported — use the task-level 'expected_alternatives'"
            )
        expected_tool = raw["expected"]["tool"]
        expected_args = _parse_expected_args(raw["expected"].get("args", {}))
    else:
        if raw.get("expected_alternatives"):
            raise ValueError(
                f"task {task_id}: 'expected_alternatives' only applies"
                " to single-call tasks, not 'expected_parallel'"
            )
        expected_parallel = [
            _parse_expected_call(spec, task_id, allow_alternatives=True)
            for spec in raw["expected_parallel"]
        ]
        if len(expected_parallel) < 2:
            raise ValueError(
                f"task {task_id}: 'expected_parallel' needs at least 2"
                " specs; use 'expected' for a single call"
            )

    return Task(
        task_id=task_id,
        scenario_id=raw["scenario_id"],
        step=raw["step"],
        description=raw["description"],
        messages=raw["messages"],
        expected_tool=expected_tool,
        expected_args=expected_args,
        expected_alternatives=[
            _parse_expected_call(alt, task_id)
            for alt in raw.get("expected_alternatives", [])
        ],
        expected_parallel=expected_parallel,
        scoring_weights=raw.get("scoring_weights", {}),
    )


def load_tasks(path: str | Path) -> list[Task]:
    with open(path) as f:
        data = json.load(f)

    return [_parse_task(raw) for raw in data["tasks"]]
