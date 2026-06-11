"""Task definitions and loader for search agent evaluation.

Each task is a single-turn decision: given a conversation history
(possibly including prior tool calls), the model picks the next
tool call. Multi-step chains share a scenario_id.
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


class Task(BaseModel, frozen=True):
    task_id: str
    scenario_id: str
    step: int
    description: str
    messages: list[dict[str, Any]]
    expected_tool: str
    expected_args: list[ExpectedArg]
    # Adjudicated equally-correct strategies; any full match scores 1.
    expected_alternatives: list[ExpectedCall] = []
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


def _parse_expected_call(raw: dict[str, Any]) -> ExpectedCall:
    return ExpectedCall(
        tool=raw["tool"],
        args=_parse_expected_args(raw.get("args", {})),
    )


def load_tasks(path: str | Path) -> list[Task]:
    with open(path) as f:
        data = json.load(f)

    return [
        Task(
            task_id=raw["task_id"],
            scenario_id=raw["scenario_id"],
            step=raw["step"],
            description=raw["description"],
            messages=raw["messages"],
            expected_tool=raw["expected"]["tool"],
            expected_args=_parse_expected_args(raw["expected"].get("args", {})),
            expected_alternatives=[
                _parse_expected_call(alt)
                for alt in raw.get("expected_alternatives", [])
            ],
            scoring_weights=raw.get("scoring_weights", {}),
        )
        for raw in data["tasks"]
    ]
