"""CLI entry point: run an eval and print a CPC summary.

Usage:
    python -m src.cli --model claude-haiku-4-5 --provider anthropic \
        --tasks data/tasks/search_agent_v1.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from src.adapters import get_adapter
from src.adapters.base import Provider
from src.eval_runner import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    RunSummary,
    run_eval,
    write_results,
)
from src.tasks import load_tasks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm-token-harness",
        description="Run search-agent tool-selection tasks and compute CPC.",
    )
    parser.add_argument("--model", required=True, help="Model ID to request.")
    parser.add_argument(
        "--provider",
        required=True,
        choices=[p.value for p in Provider],
        help="Provider adapter to use.",
    )
    parser.add_argument(
        "--tasks",
        required=True,
        type=Path,
        help="Path to a task JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results"),
        help="Directory for the per-run results JSON (default: results/).",
    )
    parser.add_argument(
        "--effort",
        default=None,
        help=(
            "Optional effort level passed through to the adapter"
            " (Anthropic adaptive-thinking effort, e.g. low/medium/high)."
        ),
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=DEFAULT_MAX_OUTPUT_TOKENS,
        help="Max output tokens per task.",
    )
    return parser


def format_summary(summary: RunSummary) -> str:
    cpc = f"${summary.cpc_usd:.6f}" if summary.cpc_usd is not None else "n/a"
    rows = [
        ("model (requested)", summary.model_requested),
        ("provider", summary.provider),
        ("tasks", str(summary.n_tasks)),
        ("correct", str(summary.n_correct)),
        ("accuracy", f"{summary.accuracy:.1%}"),
        ("input tokens", str(summary.total_input_tokens)),
        ("output tokens", str(summary.total_output_tokens)),
        ("total cost", f"${summary.total_cost_usd:.6f}"),
        ("CPC", cpc),
        ("mean latency", f"{summary.mean_latency_seconds:.2f}s"),
    ]
    width = max(len(label) for label, _ in rows)
    return "\n".join(f"{label.ljust(width)}  {value}" for label, value in rows)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    adapter = get_adapter(args.provider)
    tasks = load_tasks(args.tasks)
    records, summary = run_eval(
        adapter,
        args.model,
        tasks,
        max_output_tokens=args.max_output_tokens,
        effort=args.effort,
    )
    path = write_results(records, summary, args.output_dir)
    print(format_summary(summary))
    print(f"\nresults written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
