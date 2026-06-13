from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from viz.aggregate_reps import (
    Z,
    aggregate,
    aggregate_config,
    config_key,
    group_by_config,
    wilson_interval,
)


def _summary(
    *,
    model: str,
    effort: str | None,
    n_correct: int,
    timestamp: str,
    n_tasks: int = 25,
    cpc_usd: float | None = 0.01,
    cost: float = 0.1,
    latency: float = 1.0,
    provider: str = "anthropic",
) -> dict:
    return {
        "model_requested": model,
        "provider": provider,
        "effort": effort,
        "n_tasks": n_tasks,
        "n_correct": n_correct,
        "accuracy": n_correct / n_tasks,
        "total_cost_usd": cost,
        "cpc_usd": cpc_usd,
        "mean_latency_seconds": latency,
        "timestamp": timestamp,
    }


class TestWilsonInterval:
    def test_hand_computed_75_of_100(self) -> None:
        # p̂ = 0.75, n = 100, z = 1.96 -> CI ≈ [0.656, 0.823].
        k, n, z = 75, 100, Z
        p_hat = k / n
        z2 = z * z
        denom = 1.0 + z2 / n
        center = p_hat + z2 / (2 * n)
        margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))
        expected_low = (center - margin) / denom
        expected_high = (center + margin) / denom

        wi = wilson_interval(k, n)
        assert wi.accuracy_pooled == pytest.approx(0.75)
        assert wi.ci_low == pytest.approx(expected_low, abs=1e-6)
        assert wi.ci_high == pytest.approx(expected_high, abs=1e-6)
        # Sanity against the spec's stated ballpark (exact high ≈ 0.8245).
        assert wi.ci_low == pytest.approx(0.6569, abs=1e-3)
        assert wi.ci_high == pytest.approx(0.8245, abs=1e-3)
        # Implied /25 score range = ci × 25.
        assert wi.ci_low_score == pytest.approx(expected_low * 25, abs=1e-2)
        assert wi.ci_high_score == pytest.approx(expected_high * 25, abs=1e-2)

    def test_zero_trials_is_degenerate(self) -> None:
        wi = wilson_interval(0, 0)
        assert wi.accuracy_pooled == 0.0
        assert wi.ci_low == 0.0
        assert wi.ci_high == 0.0

    def test_interval_brackets_point_estimate(self) -> None:
        wi = wilson_interval(15, 25)
        assert wi.ci_low < wi.accuracy_pooled < wi.ci_high


class TestScoreStats:
    def test_median_min_max_spread(self) -> None:
        reps = [
            _summary(model="m", effort=None, n_correct=20, timestamp="1"),
            _summary(model="m", effort=None, n_correct=18, timestamp="2"),
            _summary(model="m", effort=None, n_correct=22, timestamp="3"),
            _summary(model="m", effort=None, n_correct=21, timestamp="4"),
        ]
        cfg = aggregate_config(("m", None), reps)
        assert cfg.scores == [20, 18, 22, 21]
        assert cfg.score_median == pytest.approx(20.5)  # median of [18,20,21,22]
        assert cfg.score_mean == pytest.approx(20.25)
        assert cfg.score_min == 18
        assert cfg.score_max == 22
        assert cfg.score_spread == 4
        assert cfg.n_reps == 4

    def test_pooled_wilson_on_config(self) -> None:
        # 4 reps of k=15/25 -> pooled 60/100 = 0.6.
        reps = [
            _summary(model="m", effort=None, n_correct=15, timestamp=str(i))
            for i in range(4)
        ]
        cfg = aggregate_config(("m", None), reps)
        assert cfg.accuracy_pooled == pytest.approx(0.6)
        expected = wilson_interval(60, 100)
        assert cfg.ci_low == pytest.approx(expected.ci_low)
        assert cfg.ci_high == pytest.approx(expected.ci_high)

    def test_cpc_skips_none(self) -> None:
        reps = [
            _summary(model="g", effort=None, n_correct=10, timestamp="1", cpc_usd=None),
            _summary(model="g", effort=None, n_correct=10, timestamp="2", cpc_usd=0.0),
            _summary(model="g", effort=None, n_correct=10, timestamp="3", cpc_usd=0.0),
        ]
        cfg = aggregate_config(("g", None), reps)
        assert cfg.cpc_usds == [0.0, 0.0]
        assert cfg.cpc_median == pytest.approx(0.0)


class TestGrouping:
    def test_config_key_on_model_and_effort(self) -> None:
        assert config_key({"model_requested": "claude-opus-4-8", "effort": None}) == (
            "claude-opus-4-8",
            None,
        )
        assert config_key({"model_requested": "claude-fable-5", "effort": "high"}) == (
            "claude-fable-5",
            "high",
        )

    def test_same_model_different_effort_split(self) -> None:
        summaries = [
            _summary(model="f", effort="low", n_correct=10, timestamp="1"),
            _summary(model="f", effort="high", n_correct=12, timestamp="2"),
            _summary(model="f", effort="low", n_correct=11, timestamp="3"),
        ]
        groups = group_by_config(summaries)
        assert set(groups.keys()) == {("f", "low"), ("f", "high")}
        assert len(groups[("f", "low")]) == 2
        assert len(groups[("f", "high")]) == 1

    def test_groups_sorted_by_timestamp(self) -> None:
        summaries = [
            _summary(model="m", effort=None, n_correct=10, timestamp="20260612-3"),
            _summary(model="m", effort=None, n_correct=11, timestamp="20260612-1"),
            _summary(model="m", effort=None, n_correct=12, timestamp="20260612-2"),
        ]
        groups = group_by_config(summaries)
        ts = [s["timestamp"] for s in groups[("m", None)]]
        assert ts == ["20260612-1", "20260612-2", "20260612-3"]


class TestAggregateFromFiles:
    def test_globs_and_sorts_by_median(self, tmp_path: Path) -> None:
        files = {
            "eval_low_1.json": _summary(
                model="lowmodel", effort=None, n_correct=5, timestamp="1"
            ),
            "eval_low_2.json": _summary(
                model="lowmodel", effort=None, n_correct=6, timestamp="2"
            ),
            "eval_high_1.json": _summary(
                model="highmodel", effort=None, n_correct=24, timestamp="1"
            ),
            "eval_high_2.json": _summary(
                model="highmodel", effort=None, n_correct=23, timestamp="2"
            ),
        }
        for name, summary in files.items():
            (tmp_path / name).write_text(
                json.dumps({"summary": summary, "records": []})
            )
        # A non-matching file is ignored by the glob.
        (tmp_path / "notes.txt").write_text("ignore me")

        configs = aggregate(tmp_path)
        assert [c.model for c in configs] == ["highmodel", "lowmodel"]
        assert configs[0].n_reps == 2
        assert configs[0].score_median == pytest.approx(23.5)
