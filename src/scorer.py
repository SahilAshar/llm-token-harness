"""Score model tool calls against expected answers.

All-or-nothing and batch-aware: every tool call in the batch is
evaluated, and the score is 1 if ANY call matches the expected
tool name AND all required args, 0 otherwise. The full list of
call names is recorded so parallel-call behavior can be analyzed
downstream.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src.adapters.base import ToolCall
from src.tasks import ArgMatchType, ExpectedArg, Task


class TaskResult(BaseModel, frozen=True):
    task_id: str
    score: int
    expected_tool: str
    actual_tool: str
    actual_tools: list[str]
    matched_args: list[str]
    failed_args: list[str]


def _match_exact(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict) and isinstance(actual, dict):
        exp = {str(k).lower(): v for k, v in expected.items()}
        act = {str(k).lower(): v for k, v in actual.items()}
        return exp.keys() == act.keys() and all(
            _match_exact(v, act[k]) for k, v in exp.items()
        )
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return False
        remaining = list(actual)
        for exp_item in expected:
            for i, act_item in enumerate(remaining):
                if _match_exact(exp_item, act_item):
                    del remaining[i]
                    break
            else:
                return False
        return True
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


def _split_args(task: Task, tc: ToolCall) -> tuple[list[str], list[str]]:
    matched: list[str] = []
    failed: list[str] = []
    for ea in task.expected_args:
        if _match_arg(ea, tc.arguments):
            matched.append(ea.name)
        else:
            failed.append(ea.name)
    return matched, failed


def score_task(task: Task, tool_calls: list[ToolCall]) -> TaskResult:
    """Score a batch of tool calls against the task's expectation.

    Any fully matching call in the batch (tool name + all expected
    args) scores 1. ``actual_tool`` is the call used for arg
    reporting: the fully matching call if one exists, otherwise the
    first call whose name matches the expected tool, otherwise the
    first call in the batch.
    """
    actual_tools = [tc.name for tc in tool_calls]

    if not tool_calls:
        return TaskResult(
            task_id=task.task_id,
            score=0,
            expected_tool=task.expected_tool,
            actual_tool="",
            actual_tools=actual_tools,
            matched_args=[],
            failed_args=[ea.name for ea in task.expected_args],
        )

    name_matches = [tc for tc in tool_calls if tc.name == task.expected_tool]
    for tc in name_matches:
        matched, failed = _split_args(task, tc)
        if not failed:
            return TaskResult(
                task_id=task.task_id,
                score=1,
                expected_tool=task.expected_tool,
                actual_tool=tc.name,
                actual_tools=actual_tools,
                matched_args=matched,
                failed_args=failed,
            )

    if name_matches:
        reporting = name_matches[0]
        matched, failed = _split_args(task, reporting)
    else:
        reporting = tool_calls[0]
        matched = []
        failed = [ea.name for ea in task.expected_args]

    return TaskResult(
        task_id=task.task_id,
        score=0,
        expected_tool=task.expected_tool,
        actual_tool=reporting.name,
        actual_tools=actual_tools,
        matched_args=matched,
        failed_args=failed,
    )
