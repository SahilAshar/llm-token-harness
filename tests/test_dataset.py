"""Validity checks for the committed v1 task dataset (no network)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from src.tasks import Task, load_tasks
from src.tools import get_search_tool_names, get_tool_names

DATASET_PATH = Path("data/tasks/search_agent_v1.json")

# Distribution over single-call tasks; the parallel task is counted
# separately in test_parallel_tasks.
EXPECTED_DISTRIBUTION = {
    "search": 9,
    "get_document": 6,
    "list_documents": 5,
    "query_decompose": 2,
}

EXPECTED_CHAIN_LENGTHS = {
    "halverson_dispute": 5,
    "easton_amendment": 4,
    "vendor_autorenew": 4,
}


@pytest.fixture(scope="module")
def tasks() -> list[Task]:
    return load_tasks(DATASET_PATH)


def test_loads_24_tasks(tasks: list[Task]) -> None:
    assert len(tasks) == 24


def test_expected_tools_are_real_tools(tasks: list[Task]) -> None:
    search_tool_names = get_search_tool_names()
    distractor_names = set(get_tool_names()) - set(search_tool_names)
    assert distractor_names, "harness should offer distractor tools"
    for task in tasks:
        if task.expected_parallel is not None:
            expected = [spec.tool for spec in task.expected_parallel]
        else:
            expected = [task.expected_tool]
        for name in expected:
            assert name in search_tool_names, task.task_id
            assert name not in distractor_names, task.task_id


def test_tool_distribution(tasks: list[Task]) -> None:
    distribution = Counter(
        t.expected_tool for t in tasks if t.expected_parallel is None
    )
    assert distribution == EXPECTED_DISTRIBUTION


def test_parallel_tasks(tasks: list[Task]) -> None:
    parallel = {
        t.task_id: t.expected_parallel for t in tasks if t.expected_parallel is not None
    }
    assert set(parallel) == {
        "halverson_dispute_02",
        "tri_counterparty_parallel_01",
    }
    assert [spec.tool for spec in parallel["halverson_dispute_02"]] == [
        "search",
        "search",
    ]
    assert [spec.tool for spec in parallel["tri_counterparty_parallel_01"]] == [
        "search",
        "search",
        "search",
    ]


def test_chain_lengths(tasks: list[Task]) -> None:
    chains = Counter(t.scenario_id for t in tasks)
    multi_step = {s: n for s, n in chains.items() if n > 1}
    assert multi_step == EXPECTED_CHAIN_LENGTHS
    for scenario, length in EXPECTED_CHAIN_LENGTHS.items():
        steps = sorted(t.step for t in tasks if t.scenario_id == scenario)
        assert steps == list(range(1, length + 1)), scenario


def test_expected_alternatives_adjudicated_tasks(tasks: list[Task]) -> None:
    with_alternatives = {t.task_id for t in tasks if t.expected_alternatives}
    assert with_alternatives == {
        "easton_amendment_02",
        "vendor_autorenew_01",
        "halverson_dispute_05",
    }
    search_tool_names = get_search_tool_names()
    for task in tasks:
        for alt in task.expected_alternatives:
            assert alt.tool in search_tool_names, task.task_id
            assert alt.args, task.task_id


def test_shared_system_prompt(tasks: list[Task]) -> None:
    prompts = set()
    for task in tasks:
        first = task.messages[0]
        assert first["role"] == "system", task.task_id
        prompts.add(first["content"])
    assert len(prompts) == 1


def test_multi_step_tasks_have_real_history(tasks: list[Task]) -> None:
    multi_step = [t for t in tasks if t.step > 1]
    assert multi_step, "dataset should contain multi-step chain tasks"
    for task in multi_step:
        found = False
        for i, msg in enumerate(task.messages):
            if msg["role"] == "assistant" and msg.get("tool_calls"):
                assert i + 1 < len(task.messages), task.task_id
                assert task.messages[i + 1]["role"] == "tool", task.task_id
                found = True
        assert found, f"{task.task_id} has no assistant tool_calls in history"


def test_tool_message_contents_are_json(tasks: list[Task]) -> None:
    for task in tasks:
        for msg in task.messages:
            if msg["role"] == "tool":
                json.loads(msg["content"])
