"""Aggregate multi-rep benchmark runs into a per-config statistics table.

A multi-rep run executes the 25-task eval N times per config so two DISTINCT
quantities can be reported (do not conflate them):

  * per-rep score SPREAD (min..max across reps) — the run-to-run / sampling
    variance the single-run snapshot could not show; this is the headline signal.
  * a pooled Wilson 95% interval — within-trials sampling error treating the
    N*25 outcomes as pooled Bernoulli draws. This is NOT a run-to-run variance
    estimate; it is roughly constant per accuracy regardless of rep spread.

This script reads the per-rep raw result files
(``eval_*.json``, each ``{"summary": {...}, "records": [...]}``), groups them
by config ``(model_requested, effort)``, and emits:

    1. an aggregate JSON (``viz/data/reps_<tag>.json`` by default) with a
       per-config statistics block (medians, min/max, spread, pooled Wilson
       95% interval, CPC stats, latency), and
    2. a markdown table printed to stdout for the methodology blog.

Usage:
    python viz/aggregate_reps.py [REPS_DIR] [OUT_JSON]

Defaults:
    REPS_DIR -> results/reps_2026-06-13 (relative to repo root)
    OUT_JSON -> viz/data/reps_2026-06-13.json

The config set and rep count are discovered by globbing — nothing is
hardcoded, so configs still running (e.g. a late Ollama model) simply join
the table once their files land. Determinism: every value derives from the
source files; no wall-clock is read.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

from pydantic import BaseModel

REPO = Path(__file__).resolve().parents[1]
DEFAULT_REPS_DIR = REPO / "results" / "reps_2026-06-13"
DEFAULT_OUT = REPO / "viz" / "data" / "reps_2026-06-13.json"

N_TASKS_SCALE = 25  # tasks per eval; CI fractions are reported as a /25 score too.
Z = 1.96  # 95% two-sided normal quantile for the Wilson interval.


class WilsonInterval(BaseModel):
    """Wilson score interval on a pooled binomial proportion."""

    model_config = {"frozen": True}

    accuracy_pooled: float
    ci_low: float
    ci_high: float
    ci_low_score: float
    ci_high_score: float


class ConfigStats(BaseModel):
    """Per-config aggregate over all reps of one ``(model, effort)``."""

    model_config = {"frozen": True}

    label: str
    model: str
    provider: str
    effort: str | None
    n_reps: int

    scores: list[int]
    score_median: float
    score_mean: float
    score_min: int
    score_max: int
    score_spread: int

    accuracies: list[float]
    accuracy_pooled: float
    ci_low: float
    ci_high: float
    ci_low_score: float
    ci_high_score: float

    cpc_usds: list[float]
    cpc_median: float | None
    cpc_min: float | None
    cpc_max: float | None
    cost_per_rep_median: float
    total_cost_all_reps: float

    mean_latency_median: float


def wilson_interval(k: int, n: int, z: float = Z) -> WilsonInterval:
    """Wilson 95% score interval for ``k`` successes in ``n`` trials.

    For p̂ = k/n the interval is::

        (p̂ + z²/2n ± z·sqrt(p̂(1-p̂)/n + z²/4n²)) / (1 + z²/n)

    Returned as accuracy fractions plus the implied score range out of
    ``N_TASKS_SCALE`` (= ci × 25, rounded). ``n == 0`` yields a degenerate
    [0, 0] interval rather than dividing by zero.
    """
    if n == 0:
        return WilsonInterval(
            accuracy_pooled=0.0,
            ci_low=0.0,
            ci_high=0.0,
            ci_low_score=0.0,
            ci_high_score=0.0,
        )
    p_hat = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = p_hat + z2 / (2 * n)
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))
    low = (center - margin) / denom
    high = (center + margin) / denom
    return WilsonInterval(
        accuracy_pooled=round(p_hat, 6),
        ci_low=round(low, 6),
        ci_high=round(high, 6),
        ci_low_score=round(low * N_TASKS_SCALE, 2),
        ci_high_score=round(high * N_TASKS_SCALE, 2),
    )


Summary = dict[str, object]


def _as_str(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"expected str, got {type(value).__name__}")
    return value


def _as_float(value: object) -> float:
    if not isinstance(value, int | float):
        raise TypeError(f"expected number, got {type(value).__name__}")
    return float(value)


def config_key(summary: Summary) -> tuple[str, str | None]:
    """Group key for a rep file: ``(model_requested, effort)``."""
    effort = summary.get("effort")
    return (
        _as_str(summary["model_requested"]),
        None if effort is None else _as_str(effort),
    )


def load_summaries(reps_dir: Path) -> list[Summary]:
    """Load the ``summary`` block from every ``eval_*.json`` in ``reps_dir``."""
    summaries: list[Summary] = []
    for path in sorted(reps_dir.glob("eval_*.json")):
        with open(path) as fh:
            data = json.load(fh)
        summaries.append(data["summary"])
    return summaries


def group_by_config(
    summaries: list[Summary],
) -> dict[tuple[str, str | None], list[Summary]]:
    """Group rep summaries by ``(model_requested, effort)``, ordered by timestamp."""
    groups: dict[tuple[str, str | None], list[Summary]] = {}
    for s in summaries:
        groups.setdefault(config_key(s), []).append(s)
    for reps in groups.values():
        reps.sort(key=lambda s: _as_str(s.get("timestamp", "")))
    return groups


def _label(model: str, effort: str | None) -> str:
    return f"{model} ({effort})" if effort else model


def aggregate_config(key: tuple[str, str | None], reps: list[Summary]) -> ConfigStats:
    """Compute the aggregate statistics block for one config's reps."""
    model, effort = key
    scores = [int(_as_float(s["n_correct"])) for s in reps]
    n_tasks = [int(_as_float(s["n_tasks"])) for s in reps]
    accuracies = [round(_as_float(s["accuracy"]), 6) for s in reps]

    pooled_k = sum(scores)
    pooled_n = sum(n_tasks)
    wilson = wilson_interval(pooled_k, pooled_n)

    cpcs = [_as_float(s["cpc_usd"]) for s in reps if s.get("cpc_usd") is not None]
    costs = [_as_float(s["total_cost_usd"]) for s in reps]
    latencies = [_as_float(s["mean_latency_seconds"]) for s in reps]

    return ConfigStats(
        label=_label(model, effort),
        model=model,
        provider=_as_str(reps[0].get("provider", "?")),
        effort=effort,
        n_reps=len(reps),
        scores=scores,
        score_median=round(statistics.median(scores), 2),
        score_mean=round(statistics.fmean(scores), 4),
        score_min=min(scores),
        score_max=max(scores),
        score_spread=max(scores) - min(scores),
        accuracies=accuracies,
        accuracy_pooled=wilson.accuracy_pooled,
        ci_low=wilson.ci_low,
        ci_high=wilson.ci_high,
        ci_low_score=wilson.ci_low_score,
        ci_high_score=wilson.ci_high_score,
        cpc_usds=[round(c, 6) for c in cpcs],
        cpc_median=round(statistics.median(cpcs), 6) if cpcs else None,
        cpc_min=round(min(cpcs), 6) if cpcs else None,
        cpc_max=round(max(cpcs), 6) if cpcs else None,
        cost_per_rep_median=round(statistics.median(costs), 6),
        total_cost_all_reps=round(sum(costs), 6),
        mean_latency_median=round(statistics.median(latencies), 4),
    )


def aggregate(reps_dir: Path) -> list[ConfigStats]:
    """Aggregate every config found under ``reps_dir``, sorted by median score."""
    groups = group_by_config(load_summaries(reps_dir))
    configs = [aggregate_config(key, reps) for key, reps in groups.items()]
    configs.sort(key=lambda c: c.score_median, reverse=True)
    return configs


def build_export(reps_dir: Path, configs: list[ConfigStats]) -> dict[str, object]:
    """Assemble the aggregate JSON payload (deterministic; no wall-clock)."""
    return {
        "meta": {
            "generated_from": str(reps_dir),
            "reps_dir": reps_dir.name,
            "n_configs": len(configs),
            "n_tasks": N_TASKS_SCALE,
            "note": (
                "Multi-rep aggregate: per config, N repetitions of the 25-task"
                " eval. Wilson 95% interval is computed on POOLED accuracy"
                " (Σ n_correct / Σ n_tasks across reps). Configs sorted by"
                " median score descending. Config set + rep count discovered by"
                " globbing eval_*.json — not hardcoded."
            ),
        },
        "configs": [c.model_dump() for c in configs],
    }


def _fmt_cpc(cpc: float | None) -> str:
    return "n/a" if cpc is None else f"${cpc:.6f}"


def markdown_table(configs: list[ConfigStats]) -> str:
    """Render the blog markdown table for the aggregated configs."""
    header = (
        "| Config | reps | median score (/25) | score range (min–max) "
        "| Wilson 95% CI (/25) | median CPC |"
    )
    sep = "|---|---|---|---|---|---|"
    rows = [header, sep]
    for c in configs:
        score_med = f"{c.score_median:g}"
        score_range = f"{c.score_min}–{c.score_max}"
        ci = f"{c.ci_low_score:g}–{c.ci_high_score:g}"
        rows.append(
            f"| {c.label} | {c.n_reps} | {score_med} | {score_range} "
            f"| {ci} | {_fmt_cpc(c.cpc_median)} |"
        )
    return "\n".join(rows)


def main() -> None:
    reps_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_REPS_DIR
    out_path = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else DEFAULT_OUT

    configs = aggregate(reps_dir)
    export = build_export(reps_dir, configs)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(export, indent=2) + "\n")

    print(markdown_table(configs))
    print()
    print(f"wrote {out_path} ({len(configs)} configs)")


if __name__ == "__main__":
    main()
