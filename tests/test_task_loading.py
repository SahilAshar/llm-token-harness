"""Loader validation for the two task modes (single-call vs parallel)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.tasks import load_tasks

_BASE: dict[str, Any] = {
    "task_id": "t_01",
    "scenario_id": "t",
    "step": 1,
    "description": "test",
    "messages": [{"role": "user", "content": "test"}],
}

_EXPECTED = {
    "tool": "search",
    "args": {"query": {"type": "keywords", "value": ["nda"]}},
}

_PARALLEL = [
    {"tool": "search", "args": {"query": {"type": "keywords", "value": ["a"]}}},
    {"tool": "search", "args": {"query": {"type": "keywords", "value": ["b"]}}},
]


def _write_dataset(tmp_path: Path, **fields: Any) -> Path:
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps({"tasks": [{**_BASE, **fields}]}))
    return path


def test_single_call_task_loads(tmp_path: Path) -> None:
    task = load_tasks(_write_dataset(tmp_path, expected=_EXPECTED))[0]
    assert task.expected_tool == "search"
    assert [a.name for a in task.expected_args] == ["query"]
    assert task.expected_parallel is None


def test_parallel_task_loads(tmp_path: Path) -> None:
    task = load_tasks(_write_dataset(tmp_path, expected_parallel=_PARALLEL))[0]
    assert task.expected_parallel is not None
    assert [spec.tool for spec in task.expected_parallel] == ["search", "search"]
    assert task.expected_tool == ""
    assert task.expected_args == []


def test_both_modes_rejected(tmp_path: Path) -> None:
    path = _write_dataset(tmp_path, expected=_EXPECTED, expected_parallel=_PARALLEL)
    with pytest.raises(ValueError, match="exactly one of"):
        load_tasks(path)


def test_neither_mode_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly one of"):
        load_tasks(_write_dataset(tmp_path))


def test_parallel_with_alternatives_rejected(tmp_path: Path) -> None:
    path = _write_dataset(
        tmp_path,
        expected_parallel=_PARALLEL,
        expected_alternatives=[_EXPECTED],
    )
    with pytest.raises(ValueError, match="expected_alternatives"):
        load_tasks(path)


def test_parallel_needs_two_specs(tmp_path: Path) -> None:
    path = _write_dataset(tmp_path, expected_parallel=_PARALLEL[:1])
    with pytest.raises(ValueError, match="at least 2"):
        load_tasks(path)


def test_parallel_spec_alternatives_load(tmp_path: Path) -> None:
    specs = [
        {
            **_PARALLEL[0],
            "alternatives": [
                {
                    "tool": "search",
                    "args": {
                        "query": {"type": "keywords", "value": [["x", "y"]]},
                        "filters": {"type": "exact", "value": {"counterparty": "A"}},
                    },
                }
            ],
        },
        _PARALLEL[1],
    ]
    task = load_tasks(_write_dataset(tmp_path, expected_parallel=specs))[0]
    assert task.expected_parallel is not None
    alts = task.expected_parallel[0].alternatives
    assert len(alts) == 1
    assert alts[0].tool == "search"
    assert {a.name for a in alts[0].args} == {"query", "filters"}
    assert task.expected_parallel[1].alternatives == []


def test_nested_spec_alternatives_rejected(tmp_path: Path) -> None:
    specs = [
        {
            **_PARALLEL[0],
            "alternatives": [{**_PARALLEL[1], "alternatives": [_PARALLEL[1]]}],
        },
        _PARALLEL[1],
    ]
    path = _write_dataset(tmp_path, expected_parallel=specs)
    with pytest.raises(ValueError, match="cannot nest"):
        load_tasks(path)


def test_alternatives_on_expected_alternatives_rejected(tmp_path: Path) -> None:
    path = _write_dataset(
        tmp_path,
        expected=_EXPECTED,
        expected_alternatives=[{**_EXPECTED, "alternatives": [_EXPECTED]}],
    )
    with pytest.raises(ValueError, match="alternatives"):
        load_tasks(path)
