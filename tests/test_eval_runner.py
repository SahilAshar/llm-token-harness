"""Tests for the eval runner using a stub adapter (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.adapters.base import LLMAdapter, LLMResponse, Provider, ToolCall
from src.eval_runner import run_eval, write_results
from src.pricing import PRICING
from src.tasks import ArgMatchType, ExpectedArg, Task
from src.tools import ALL_TOOLS


class StubAdapter(LLMAdapter):
    """Returns canned LLMResponse objects in order, recording each call."""

    provider = Provider.ANTHROPIC

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_output_tokens: int,
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "max_output_tokens": max_output_tokens,
                "tools": tools,
                "kwargs": kwargs,
            }
        )
        return self._responses.pop(0)


def _make_task(task_id: str = "t1") -> Task:
    return Task(
        task_id=task_id,
        scenario_id="s1",
        step=1,
        description="Fetch a known document.",
        messages=[{"role": "user", "content": "Get doc_3"}],
        expected_tool="get_document",
        expected_args=[
            ExpectedArg(name="doc_id", match_type=ArgMatchType.EXACT, value="doc_3")
        ],
    )


def _make_response(
    *,
    model: str = "claude-fable-5",
    tool_calls: list[ToolCall] | None = None,
    input_tokens: int = 1000,
    output_tokens: int = 200,
) -> LLMResponse:
    return LLMResponse(
        text="",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        model=model,
        tool_calls=tool_calls or [],
    )


CORRECT_CALL = ToolCall(name="get_document", arguments={"doc_id": "doc_3"})
WRONG_CALL = ToolCall(name="search", arguments={"query": "doc_3"})


class TestRunEval:
    def test_scoring_flow(self) -> None:
        adapter = StubAdapter(
            [
                _make_response(tool_calls=[CORRECT_CALL]),
                _make_response(tool_calls=[WRONG_CALL]),
            ]
        )
        tasks = [_make_task("t1"), _make_task("t2")]
        records, summary = run_eval(adapter, "claude-fable-5", tasks)

        assert summary.n_tasks == 2
        assert summary.n_correct == 1
        assert summary.accuracy == 0.5
        assert summary.total_input_tokens == 2000
        assert summary.total_output_tokens == 400
        assert summary.model_requested == "claude-fable-5"
        assert summary.provider == "anthropic"
        assert [r.result.score for r in records] == [1, 0]
        assert all(r.latency_seconds >= 0 for r in records)
        # Runner must pass all 5 tool schemas to the adapter.
        assert adapter.calls[0]["tools"] == ALL_TOOLS

    def test_cost_attribution_uses_response_model(self) -> None:
        # claude-fable-5 request silently rerouted to claude-opus-4-8:
        # cost must be billed at Opus prices, keyed off response.model.
        adapter = StubAdapter(
            [
                _make_response(
                    model="claude-opus-4-8",
                    tool_calls=[CORRECT_CALL],
                    input_tokens=1_000_000,
                    output_tokens=100_000,
                )
            ]
        )
        records, summary = run_eval(adapter, "claude-fable-5", [_make_task()])

        opus = PRICING["claude-opus-4-8"]
        fable = PRICING["claude-fable-5"]
        expected = opus.cost_usd(1_000_000, 100_000)
        assert records[0].response_model == "claude-opus-4-8"
        assert records[0].cost_usd == expected
        assert records[0].cost_usd != fable.cost_usd(1_000_000, 100_000)
        assert summary.total_cost_usd == expected
        assert summary.cpc_usd == expected  # one task, one correct

    def test_cpc_none_when_zero_correct(self) -> None:
        adapter = StubAdapter([_make_response(tool_calls=[WRONG_CALL])])
        _, summary = run_eval(adapter, "claude-fable-5", [_make_task()])

        assert summary.n_correct == 0
        assert summary.accuracy == 0.0
        assert summary.cpc_usd is None

    def test_effort_passed_through(self) -> None:
        adapter = StubAdapter([_make_response(tool_calls=[CORRECT_CALL])])
        run_eval(adapter, "claude-fable-5", [_make_task()], effort="medium")
        assert adapter.calls[0]["kwargs"] == {"effort": "medium"}

    def test_effort_omitted_by_default(self) -> None:
        adapter = StubAdapter([_make_response(tool_calls=[CORRECT_CALL])])
        run_eval(adapter, "claude-fable-5", [_make_task()])
        assert adapter.calls[0]["kwargs"] == {}


class TestWriteResults:
    def test_results_json_written(self, tmp_path: Path) -> None:
        adapter = StubAdapter([_make_response(tool_calls=[CORRECT_CALL])])
        records, summary = run_eval(adapter, "claude-fable-5", [_make_task()])

        path = write_results(records, summary, tmp_path / "results")

        assert path.exists()
        assert path.parent == tmp_path / "results"
        payload = json.loads(path.read_text())
        assert payload["summary"]["model_requested"] == "claude-fable-5"
        assert payload["summary"]["n_correct"] == 1
        assert len(payload["records"]) == 1
        assert payload["records"][0]["result"]["task_id"] == "t1"
