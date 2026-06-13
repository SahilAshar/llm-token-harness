"""Export a benchmark run into the canonical viz data layout.

All viz/insight/hardening views read this single export so their
numbers can never drift from each other.

Runs accumulate as history over time. Each invocation writes three things
under ``viz/data/`` (history is a north star — see CLAUDE.md):

    runs/<date>.json   the dated snapshot for this run (immutable history)
    latest.json        a copy of the most recent run; the live site fetches
                       this (``pages-index.html`` does ``fetch('./data/latest.json')``)
    runs.json          a manifest listing every dated run, newest first, so a
                       future history view can populate a run picker

Usage:
    python viz/export_bench_data.py [REPO_ROOT] [DATA_DIR]

Defaults:
    REPO_ROOT -> the repo root (this file's parent's parent)
    DATA_DIR  -> viz/data

Reads the gitignored run files listed in ``RUN`` under REPO_ROOT and
writes the committed data snapshots. Parallel-task records are
RE-SCORED from their recorded ``actual_calls`` under the current
``src.scorer`` (the run executed before per-spec alternatives, PR #25,
merged); single-call scoring is unchanged by #25, so recorded scores
stand. Config totals, accuracy, and CPC are recomputed from the
re-scored records.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.adapters.base import ToolCall  # noqa: E402
from src.scorer import score_task  # noqa: E402
from src.tasks import load_tasks  # noqa: E402

DATE_TAG = "2026-06-12-r2"
DATASET = "data/tasks/search_agent_v1.json"
DATA_DIR = REPO / "viz" / "data"

# The 12-config run of 2026-06-12 afternoon (25-task dataset, post-#22).
# Explicit filenames: the morning run shares the date prefix, and the
# three Fable efforts are distinguishable only by launch order.
RUN: list[tuple[str, str | None, str]] = [
    ("gpt-4o-mini", None, "eval_gpt-4o-mini_20260612-153853.json"),
    ("claude-haiku-4-5", None, "eval_claude-haiku-4-5_20260612-153901.json"),
    ("gpt-5.4-nano", None, "eval_gpt-5.4-nano_20260612-153920.json"),
    ("gpt-5.4-mini", None, "eval_gpt-5.4-mini_20260612-153946.json"),
    ("gpt-5.5", None, "eval_gpt-5.5_20260612-154056.json"),
    ("gemma4:12b", None, "eval_gemma4-12b_20260612-154624.json"),
    ("claude-sonnet-4-6", None, "eval_claude-sonnet-4-6_20260612-155453.json"),
    ("claude-opus-4-6", None, "eval_claude-opus-4-6_20260612-155630.json"),
    ("claude-opus-4-8", None, "eval_claude-opus-4-8_20260612-155731.json"),
    ("claude-fable-5", "low", "eval_claude-fable-5_20260612-155932.json"),
    ("claude-fable-5", "medium", "eval_claude-fable-5_20260612-160150.json"),
    ("claude-fable-5", "high", "eval_claude-fable-5_20260612-160424.json"),
]

DISTRACTORS = {
    "web_search",
    "tag_document",
    "create_alert",
    "summarize_document",
    "search_history",
}
CHAINS = {"halverson_dispute": 5, "easton_amendment": 4, "vendor_autorenew": 4}
ALT_TASKS = {"easton_amendment_02", "vendor_autorenew_01", "halverson_dispute_05"}
# h2_2024_relative_01 (Axis E) saturated 12/12 on this run and is
# reclassified as floor per the PR #22 watch item.
# stonebridge_term_01 reclassified OUT of floor: passes only 7/12 and draws
# summarize_document near-miss picks — a genuine discriminator, not a floor task.
# okafor_leases_01 stays OUT of floor: a real constraint-dense task that merely
# saturated 12/12 this run (already visible via task_difficulty n_pass).
FLOOR_TASKS = {
    "corvid_fetch_01",
    "nda_inventory_01",
    "q1_2025_inventory_01",
    "nonsolicit_search_01",
    "termination_topk_01",
    "h2_2024_relative_01",
}
PROVIDER = {
    "gpt-4o-mini": "openai",
    "gpt-5.4-nano": "openai",
    "gpt-5.4-mini": "openai",
    "gpt-5.5": "openai",
    "claude-haiku-4-5": "anthropic",
    "claude-sonnet-4-6": "anthropic",
    "claude-opus-4-6": "anthropic",
    "claude-opus-4-8": "anthropic",
    "claude-fable-5": "anthropic",
    "gemma4:12b": "ollama",
}

# June-10 (15-task) grid, for before/after.
PRIOR = [
    {"label": "Sonnet 4.6", "score": 14, "n": 15, "cpc": 0.0073},
    {"label": "Opus 4.6", "score": 13, "n": 15, "cpc": 0.0139},
    {"label": "GPT-4o-mini", "score": 12, "n": 15, "cpc": 0.00018},
    {"label": "GPT-5.4 nano", "score": 12, "n": 15, "cpc": 0.00031},
    {"label": "Gemma 4 12B", "score": 11, "n": 15, "cpc": 0.0},
    {"label": "Haiku 4.5", "score": 11, "n": 15, "cpc": 0.0032},
    {"label": "Fable 5 (low=med=high)", "score": 10, "n": 15, "cpc": 0.037},
    {"label": "GPT-5.5", "score": 10, "n": 15, "cpc": 0.0106},
    {"label": "GPT-5.4 mini", "score": 10, "n": 15, "cpc": 0.0013},
    {"label": "Opus 4.8", "score": 10, "n": 15, "cpc": 0.0192},
]


def scenario_of(task_id: str) -> str:
    return task_id.rsplit("_", 1)[0]


def load_runs(repo: Path) -> list[dict]:
    tasks = {t.task_id: t for t in load_tasks(repo / DATASET)}
    parallel_ids = {tid for tid, t in tasks.items() if t.expected_parallel}

    runs = []
    for model, effort, fname in RUN:
        path = repo / "results" / fname
        with open(path) as fh:
            data = json.load(fh)
        records = []
        rescored = []
        for rec in data["records"]:
            res = rec["result"]
            tid = res["task_id"]
            if tid in parallel_ids and res.get("actual_calls") is not None:
                calls = [
                    ToolCall(name=c["name"], arguments=c["arguments"])
                    for c in res["actual_calls"]
                ]
                new = score_task(tasks[tid], calls)
                if new.score != res["score"]:
                    rescored.append(tid)
                rec = {**rec, "result": new.model_dump()}
            records.append(rec)
        label = f"Fable 5 ({effort})" if effort else model
        runs.append(
            {
                "label": label,
                "model": model,
                "effort": effort,
                "summary": data["summary"],
                "records": records,
                "rescored_tasks": rescored,
            }
        )
    return runs


def write_outputs(export: dict, data_dir: Path) -> list[Path]:
    """Write the dated snapshot, refresh latest.json, and upsert the manifest.

    Returns the paths written, newest snapshot first. The manifest is an
    upsert keyed by date, so re-exporting an existing run replaces its entry
    rather than duplicating it; runs are listed newest-first and ``latest``
    points at the max date.
    """
    meta = export["meta"]
    date = meta["date"]
    runs_dir = data_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    dated = runs_dir / f"{date}.json"
    latest = data_dir / "latest.json"
    blob = json.dumps(export, indent=2) + "\n"
    dated.write_text(blob)

    manifest_path = data_dir / "runs.json"
    by_date: dict[str, dict] = {}
    if manifest_path.exists():
        prior = json.loads(manifest_path.read_text())
        for entry in prior.get("runs", []):
            by_date[entry["date"]] = entry
    by_date[date] = {
        "date": date,
        "path": f"runs/{date}.json",
        "dataset": meta["dataset"],
        "n_tasks": meta["n_tasks"],
        "n_configs": meta["n_configs"],
        "note": meta.get("note", ""),
    }
    runs = sorted(by_date.values(), key=lambda e: e["date"], reverse=True)
    manifest = {"latest": runs[0]["date"], "runs": runs}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    # latest.json mirrors the newest dated snapshot the manifest knows about.
    newest = runs[0]["date"]
    newest_blob = blob if newest == date else (runs_dir / f"{newest}.json").read_text()
    latest.write_text(newest_blob)

    return [dated, latest, manifest_path]


def main() -> None:
    repo = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO
    data_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else DATA_DIR

    runs = load_runs(repo)
    tasks = load_tasks(repo / DATASET)
    parallel_ids = [t.task_id for t in tasks if t.expected_parallel]
    # Expected call count per task: parallel tasks expect one call per spec,
    # all others a single call. Used for the over-call behavioral metric.
    parallel_spec_count = {
        t.task_id: len(t.expected_parallel) for t in tasks if t.expected_parallel
    }

    configs = []
    per_config_task = {}
    for r in runs:
        s = r["summary"]
        n_correct = sum(x["result"]["score"] for x in r["records"])
        cost = s["total_cost_usd"]
        rt = sum(x["reasoning_tokens"] for x in r["records"])
        # Over-call: a correct record (score == 1) that emitted more tool calls
        # than necessary. Behavioral metric only — never touches score/CPC.
        over_call_count = 0
        for x in r["records"]:
            res = x["result"]
            if res["score"] != 1:
                continue
            expected_calls = parallel_spec_count.get(res["task_id"], 1)
            if len(res["actual_tools"]) > expected_calls:
                over_call_count += 1
        configs.append(
            {
                "label": r["label"],
                "model": r["model"],
                "provider": PROVIDER.get(r["model"], "?"),
                "effort": r["effort"],
                "score": n_correct,
                "score_at_runtime": s["n_correct"],
                "rescored_tasks": r["rescored_tasks"],
                "n_tasks": s["n_tasks"],
                "accuracy": round(n_correct / s["n_tasks"], 4),
                "total_cost_usd": round(cost, 6),
                "cpc_usd": round(cost / n_correct, 6) if n_correct else None,
                "input_tokens": s["total_input_tokens"],
                "output_tokens": s["total_output_tokens"],
                "reasoning_tokens": rt,
                "over_call_count": over_call_count,
                "over_call_rate": round(over_call_count / s["n_tasks"], 4),
                "mean_latency_s": round(s["mean_latency_seconds"], 2),
            }
        )
        per_config_task[r["label"]] = {
            x["result"]["task_id"]: x["result"]["score"] for x in r["records"]
        }

    # Parallel tasks (one block per task, all configs each)
    parallel_tasks = []
    for tid in parallel_ids:
        per_config = []
        for r in runs:
            rec = next((x for x in r["records"] if x["result"]["task_id"] == tid), None)
            res = rec["result"] if rec else None
            per_config.append(
                {
                    "label": r["label"],
                    "pass": bool(res and res["score"] == 1),
                    "rescued_by_pr25": tid in r["rescored_tasks"],
                    "matched": res.get("parallel_matched") if res else None,
                    "expected": res.get("parallel_expected") if res else None,
                    "calls": res["actual_tools"] if res else [],
                    "failed_specs": res.get("parallel_failed_specs") if res else None,
                }
            )
        parallel_tasks.append({"task_id": tid, "per_config": per_config})

    # Distractor picks
    distractors = []
    for r in runs:
        picks = {}
        for rec in r["records"]:
            for t in rec["result"]["actual_tools"]:
                if t in DISTRACTORS:
                    key = (rec["result"]["task_id"], t)
                    picks[key] = picks.get(key, 0) + 1
        if picks:
            distractors.append(
                {
                    "label": r["label"],
                    "picks": [
                        {"task": k[0], "tool": k[1], "count": v}
                        for k, v in picks.items()
                    ],
                }
            )

    # Chains
    chains = []
    for r in runs:
        row = {"label": r["label"], "chains": {}}
        for sc, n in CHAINS.items():
            fails = [
                rec["result"]["task_id"]
                for rec in r["records"]
                if scenario_of(rec["result"]["task_id"]) == sc
                and rec["result"]["score"] == 0
            ]
            row["chains"][sc] = {"correct": n - len(fails), "total": n, "failed": fails}
        chains.append(row)

    # Task difficulty
    task_pass, order = {}, []
    for r in runs:
        for rec in r["records"]:
            tid = rec["result"]["task_id"]
            if tid not in task_pass:
                task_pass[tid] = 0
                order.append(tid)
            task_pass[tid] += rec["result"]["score"]
    n_cfg = len(runs)
    difficulty = [
        {
            "task_id": tid,
            "scenario": scenario_of(tid),
            "n_pass": task_pass[tid],
            "n_configs": n_cfg,
            "is_parallel": tid in parallel_ids,
            "is_alt": tid in ALT_TASKS,
            "is_floor": tid in FLOOR_TASKS,
            "is_chain": scenario_of(tid) in CHAINS,
        }
        for tid in order
    ]

    export = {
        "meta": {
            "date": DATE_TAG,
            "dataset": DATASET,
            "n_tasks": runs[0]["summary"]["n_tasks"],
            "n_configs": n_cfg,
            "north_star": (
                "CPC = total run cost / tasks with correct retrieval strategy"
            ),
            "note": (
                "Hardened 25-task run (post-#22). Parallel tasks re-scored"
                " under per-spec alternatives (#25). NOT score-comparable"
                " task-for-task to the June-10 or June-12-morning grids."
            ),
            "reasoning_tokens_note": (
                "Per-config reasoning_tokens is NOT cross-provider comparable:"
                " Anthropic folds thinking into output_tokens (reads 0), OpenAI"
                " reports real reasoning tokens, and Ollama/gemma's value is a"
                " whitespace word-count, not tokens. Chart it within-provider"
                " only; never across providers."
            ),
            "distractor_tools": sorted(DISTRACTORS),
            "chains": CHAINS,
        },
        "configs": configs,
        "parallel_tasks": parallel_tasks,
        "distractor_picks": distractors,
        "chains_per_config": chains,
        "task_difficulty": difficulty,
        "per_config_task_scores": per_config_task,
        "prior_run_june10": PRIOR,
    }

    written = write_outputs(export, data_dir)
    for path in written:
        print(f"wrote {path}")
    print(
        f"configs={len(configs)} tasks={export['meta']['n_tasks']} "
        f"distractor_configs={len(distractors)}"
    )


if __name__ == "__main__":
    main()
