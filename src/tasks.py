"""Task definitions and loader for search agent evaluation.

Each task is a single-turn decision: given a conversation history
(possibly including prior tool calls), the model picks the next
tool call. Multi-step chains share a scenario_id.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class ArgMatchType(StrEnum):
    EXACT = "exact"
    KEYWORDS = "keywords"


@dataclass(frozen=True)
class ExpectedArg:
    name: str
    match_type: ArgMatchType
    value: Any


@dataclass(frozen=True)
class Task:
    task_id: str
    scenario_id: str
    step: int
    description: str
    messages: list[dict[str, Any]]
    expected_tool: str
    expected_args: list[ExpectedArg]
    scoring_weights: dict[str, Any] = field(default_factory=dict)


def _parse_expected_args(raw: dict[str, Any]) -> list[ExpectedArg]:
    args: list[ExpectedArg] = []
    for name, spec in raw.items():
        match_type = ArgMatchType(spec["type"])
        args.append(ExpectedArg(name=name, match_type=match_type, value=spec["value"]))
    return args


def load_tasks(path: str | Path) -> list[Task]:
    with open(path) as f:
        data = json.load(f)

    tasks: list[Task] = []
    for raw in data["tasks"]:
        expected = raw["expected"]
        tasks.append(
            Task(
                task_id=raw["task_id"],
                scenario_id=raw["scenario_id"],
                step=raw["step"],
                description=raw["description"],
                messages=raw["messages"],
                expected_tool=expected["tool"],
                expected_args=_parse_expected_args(expected.get("args", {})),
                scoring_weights=raw.get("scoring_weights", {}),
            )
        )
    return tasks
