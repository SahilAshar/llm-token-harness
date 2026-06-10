"""Validity checks for the committed v1 task dataset (no network)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from src.tasks import Task, load_tasks
from src.tools import get_tool_names

DATASET_PATH = Path("data/tasks/search_agent_v1.json")

EXPECTED_DISTRIBUTION = {
    "search": 6,
    "get_document": 4,
    "list_documents": 3,
    "query_decompose": 2,
}


@pytest.fixture(scope="module")
def tasks() -> list[Task]:
    return load_tasks(DATASET_PATH)


def test_loads_15_tasks(tasks: list[Task]) -> None:
    assert len(tasks) == 15


def test_expected_tools_exist(tasks: list[Task]) -> None:
    tool_names = get_tool_names()
    for task in tasks:
        assert task.expected_tool in tool_names, task.task_id


def test_tool_distribution(tasks: list[Task]) -> None:
    distribution = Counter(t.expected_tool for t in tasks)
    assert distribution == EXPECTED_DISTRIBUTION


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
