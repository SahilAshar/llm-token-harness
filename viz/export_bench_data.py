"""Export the 2026-06-12 benchmark into one canonical JSON.

All viz/insight/hardening views read this single export so their
numbers can never drift from each other.

Usage:
    python viz/export_bench_data.py [REPO_ROOT] [OUT_PATH]

Defaults:
    REPO_ROOT -> the repo root (this file's parent's parent)
    OUT_PATH  -> viz/data/bench_data_<date>.json

Reads the gitignored ``results/eval_*_20260612-*.json`` run files under
REPO_ROOT and writes the committed data snapshot.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

DATE = "2026-06-12"
REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "viz" / "data" / f"bench_data_{DATE}.json"

DISTRACTORS = {
    "web_search",
    "tag_document",
    "create_alert",
    "summarize_document",
    "search_history",
}
PARALLEL_TASK = "halverson_dispute_02"
CHAINS = {"halverson_dispute": 5, "easton_amendment": 4, "vendor_autorenew": 4}
ALT_TASKS = {"easton_amendment_02", "vendor_autorenew_01", "halverson_dispute_05"}
FLOOR_TASKS = {
    "corvid_fetch_01",
    "stonebridge_term_01",
    "nda_inventory_01",
    "q1_2025_inventory_01",
    "nonsolicit_search_01",
    "termination_topk_01",
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
    pattern = str(repo / "results" / "eval_*_20260612-*.json")
    files = sorted(glob.glob(pattern), key=os.path.getmtime)
    runs, fable_i = [], 0
    efforts = ["low", "medium", "high"]
    for f in files:
        with open(f) as fh:
            data = json.load(fh)
        s = data["summary"]
        model = s["model_requested"]
        effort = None
        label = model
        if model == "claude-fable-5":
            effort = efforts[fable_i]
            label = f"Fable 5 ({effort})"
            fable_i += 1
        runs.append(
            {
                "label": label,
                "model": model,
                "effort": effort,
                "summary": s,
                "records": data["records"],
            }
        )
    return runs


def main() -> None:
    repo = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else OUT

    runs = load_runs(repo)
    if not runs:
        raise SystemExit(
            f"no run files matched {repo / 'results'}/eval_*_20260612-*.json"
        )

    configs = []
    per_config_task = {}
    for r in runs:
        s = r["summary"]
        rt = sum(x["reasoning_tokens"] for x in r["records"])
        configs.append(
            {
                "label": r["label"],
                "model": r["model"],
                "provider": PROVIDER.get(r["model"], "?"),
                "effort": r["effort"],
                "score": s["n_correct"],
                "n_tasks": s["n_tasks"],
                "accuracy": round(s["accuracy"], 4),
                "total_cost_usd": round(s["total_cost_usd"], 6),
                "cpc_usd": (
                    round(s["cpc_usd"], 6) if s["cpc_usd"] is not None else None
                ),
                "input_tokens": s["total_input_tokens"],
                "output_tokens": s["total_output_tokens"],
                "reasoning_tokens": rt,
                "mean_latency_s": round(s["mean_latency_seconds"], 2),
            }
        )
        per_config_task[r["label"]] = {
            x["result"]["task_id"]: x["result"]["score"] for x in r["records"]
        }

    # Parallel task
    parallel = []
    for r in runs:
        rec = next(
            (x for x in r["records"] if x["result"]["task_id"] == PARALLEL_TASK), None
        )
        res = rec["result"] if rec else None
        parallel.append(
            {
                "label": r["label"],
                "pass": bool(res and res["score"] == 1),
                "matched": res.get("parallel_matched") if res else None,
                "expected": res.get("parallel_expected") if res else None,
                "calls": res["actual_tools"] if res else [],
                "failed_specs": res.get("parallel_failed_specs") if res else None,
            }
        )

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
            "is_parallel": tid == PARALLEL_TASK,
            "is_alt": tid in ALT_TASKS,
            "is_floor": tid in FLOOR_TASKS,
            "is_chain": scenario_of(tid) in CHAINS,
        }
        for tid in order
    ]

    export = {
        "meta": {
            "date": DATE,
            "dataset": "data/tasks/search_agent_v1.json",
            "n_tasks": runs[0]["summary"]["n_tasks"],
            "n_configs": n_cfg,
            "north_star": (
                "CPC = total run cost / tasks with correct retrieval strategy"
            ),
            "note": "Hardened 23-task run. NOT comparable to June-10 15-task grid.",
            "distractor_tools": sorted(DISTRACTORS),
            "chains": CHAINS,
        },
        "configs": configs,
        "parallel_task": {"task_id": PARALLEL_TASK, "per_config": parallel},
        "distractor_picks": distractors,
        "chains_per_config": chains,
        "task_difficulty": difficulty,
        "per_config_task_scores": per_config_task,
        "prior_run_june10": PRIOR,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        json.dump(export, fh, indent=2)
    print(f"wrote {out}")
    print(
        f"configs={len(configs)} tasks={export['meta']['n_tasks']} "
        f"distractor_configs={len(distractors)}"
    )


if __name__ == "__main__":
    main()
