"""Score model tool calls against expected answers.

All-or-nothing and batch-aware: every tool call in the batch is
evaluated, and the score is 1 if ANY call matches the expected
tool name AND all required args, 0 otherwise. Tasks may carry
``expected_alternatives`` — adjudicated equally-correct strategies;
a full match against the primary expectation OR any alternative
scores 1, with no partial credit across alternatives. The full
list of call names is recorded so parallel-call behavior can be
analyzed downstream.

Parallel tasks (``expected_parallel``) invert the quantifier: EVERY
spec must be matched by its own DISTINCT call in the batch (injective
matching, all-specs-required) — one combined call whose args happen to
satisfy two specs is not parallel invocation and does not score.
Per-spec match results are recorded in
``parallel_matched``/``parallel_expected``/``parallel_failed_specs``
so partial parallel behavior ("issued 1 of 2 expected calls") falls
out of the raw results even though the score stays all-or-nothing.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src.adapters.base import ToolCall
from src.tasks import ArgMatchType, ExpectedArg, ExpectedCall, Task


class TaskResult(BaseModel, frozen=True):
    task_id: str
    score: int
    expected_tool: str
    actual_tool: str
    actual_tools: list[str]
    # Arguments of the reporting call, recorded for failure analysis.
    actual_args: dict[str, Any] | None
    matched_args: list[str]
    failed_args: list[str]
    # Parallel-task fields (None for single-call tasks). Spec labels
    # are "{index}:{tool}" since parallel specs can share a tool name.
    parallel_expected: int | None = None
    parallel_matched: int | None = None
    parallel_failed_specs: list[str] | None = None


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


def _split_args(
    expected_args: list[ExpectedArg], tc: ToolCall
) -> tuple[list[str], list[str]]:
    matched: list[str] = []
    failed: list[str] = []
    for ea in expected_args:
        if _match_arg(ea, tc.arguments):
            matched.append(ea.name)
        else:
            failed.append(ea.name)
    return matched, failed


def _score_parallel(
    task: Task, specs: list[ExpectedCall], tool_calls: list[ToolCall]
) -> TaskResult:
    # One call's args can satisfy several specs at once (e.g. a single
    # combined search containing every spec's keywords), but a model
    # that issued fewer calls than specs did not parallelize. Each call
    # may therefore satisfy at most one spec: maximum bipartite
    # matching of specs to distinct calls, via augmenting paths.
    compatible = [
        [
            j
            for j, tc in enumerate(tool_calls)
            if tc.name == spec.tool and not _split_args(spec.args, tc)[1]
        ]
        for spec in specs
    ]
    call_owner: dict[int, int] = {}

    def _assign(spec_idx: int, visited: set[int]) -> bool:
        for call_idx in compatible[spec_idx]:
            if call_idx in visited:
                continue
            visited.add(call_idx)
            if call_idx not in call_owner or _assign(call_owner[call_idx], visited):
                call_owner[call_idx] = spec_idx
                return True
        return False

    failed_specs = [
        f"{i}:{spec.tool}" for i, spec in enumerate(specs) if not _assign(i, set())
    ]
    matched_count = len(specs) - len(failed_specs)
    return TaskResult(
        task_id=task.task_id,
        score=1 if not failed_specs else 0,
        expected_tool=" + ".join(spec.tool for spec in specs),
        # Display only — parallel analysis reads actual_tools/parallel_*.
        actual_tool=tool_calls[0].name if tool_calls else "",
        actual_tools=[tc.name for tc in tool_calls],
        actual_args=None,
        matched_args=[],
        failed_args=[],
        parallel_expected=len(specs),
        parallel_matched=matched_count,
        parallel_failed_specs=failed_specs,
    )


def score_task(task: Task, tool_calls: list[ToolCall]) -> TaskResult:
    """Score a batch of tool calls against the task's expectation.

    Single-call tasks: any call in the batch that fully matches the
    primary expectation or any entry in ``expected_alternatives``
    (tool name + all expected args) scores 1. ``actual_tool`` is the
    call used for arg reporting: the fully matching call if one
    exists, otherwise the first call whose name matches the primary
    expected tool, otherwise the first call in the batch. On failure,
    arg reporting is always against the primary expectation.

    Parallel tasks (``expected_parallel`` set): scores 1 only if every
    spec is fully matched by its own distinct call in the batch (a
    single call never satisfies more than one spec). Per-spec
    results land in the ``parallel_*`` fields; ``expected_tool`` is
    the joined spec tool names and the per-arg report fields stay
    empty.
    """
    if task.expected_parallel is not None:
        return _score_parallel(task, task.expected_parallel, tool_calls)

    actual_tools = [tc.name for tc in tool_calls]

    if not tool_calls:
        return TaskResult(
            task_id=task.task_id,
            score=0,
            expected_tool=task.expected_tool,
            actual_tool="",
            actual_tools=actual_tools,
            actual_args=None,
            matched_args=[],
            failed_args=[ea.name for ea in task.expected_args],
        )

    specs = [
        ExpectedCall(tool=task.expected_tool, args=task.expected_args),
        *task.expected_alternatives,
    ]
    for spec in specs:
        for tc in tool_calls:
            if tc.name != spec.tool:
                continue
            matched, failed = _split_args(spec.args, tc)
            if not failed:
                return TaskResult(
                    task_id=task.task_id,
                    score=1,
                    expected_tool=task.expected_tool,
                    actual_tool=tc.name,
                    actual_tools=actual_tools,
                    actual_args=tc.arguments,
                    matched_args=matched,
                    failed_args=failed,
                )

    name_matches = [tc for tc in tool_calls if tc.name == task.expected_tool]
    if name_matches:
        reporting = name_matches[0]
        matched, failed = _split_args(task.expected_args, reporting)
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
        actual_args=reporting.arguments,
        matched_args=matched,
        failed_args=failed,
    )
