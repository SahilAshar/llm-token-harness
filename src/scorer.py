"""Score model tool calls against expected answers.

All-or-nothing: score is 1 if tool name matches AND all required
args match, 0 otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.adapters.base import ToolCall
from src.tasks import ArgMatchType, ExpectedArg, Task


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    score: int
    expected_tool: str
    actual_tool: str
    matched_args: list[str]
    failed_args: list[str]


def _match_exact(expected: Any, actual: Any) -> bool:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return expected == actual
    return str(expected).lower() == str(actual).lower()


def _match_keywords(keywords: list[str], actual: Any) -> bool:
    actual_lower = str(actual).lower()
    return all(kw.lower() in actual_lower for kw in keywords)


def _match_arg(expected: ExpectedArg, actual_args: dict[str, Any]) -> bool:
    if expected.name not in actual_args:
        return False
    actual_val = actual_args[expected.name]
    if expected.match_type == ArgMatchType.EXACT:
        return _match_exact(expected.value, actual_val)
    if expected.match_type == ArgMatchType.KEYWORDS:
        return _match_keywords(expected.value, actual_val)
    return False


def score_task(task: Task, tool_calls: list[ToolCall]) -> TaskResult:
    if not tool_calls:
        return TaskResult(
            task_id=task.task_id,
            score=0,
            expected_tool=task.expected_tool,
            actual_tool="",
            matched_args=[],
            failed_args=[ea.name for ea in task.expected_args],
        )

    tc = tool_calls[0]

    if tc.name != task.expected_tool:
        return TaskResult(
            task_id=task.task_id,
            score=0,
            expected_tool=task.expected_tool,
            actual_tool=tc.name,
            matched_args=[],
            failed_args=[ea.name for ea in task.expected_args],
        )

    matched: list[str] = []
    failed: list[str] = []
    for ea in task.expected_args:
        if _match_arg(ea, tc.arguments):
            matched.append(ea.name)
        else:
            failed.append(ea.name)

    return TaskResult(
        task_id=task.task_id,
        score=1 if not failed else 0,
        expected_tool=task.expected_tool,
        actual_tool=tc.name,
        matched_args=matched,
        failed_args=failed,
    )
