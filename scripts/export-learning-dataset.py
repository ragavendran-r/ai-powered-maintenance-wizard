#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.data import repository  # noqa: E402
from app.data.database import initialize_database  # noqa: E402
from app.services.learning import TRAINING_WORTHY_SCORE, refresh_learning_examples  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export approved, LLM-judge-qualified maintenance examples as JSONL for local PEFT tuning."
    )
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument("--min-judge-score", type=float, default=TRAINING_WORTHY_SCORE)
    parser.add_argument("--include-unapproved", action="store_true")
    parser.add_argument("--skip-refresh", action="store_true")
    args = parser.parse_args()

    initialize_database(seed=True)
    if not args.skip_refresh:
        refresh_learning_examples()

    examples = repository.list_learning_examples(
        approved_only=None if args.include_unapproved else True,
        min_judge_score=args.min_judge_score,
        limit=10000,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(_jsonl_record(example), separators=(",", ":")) + "\n")

    print(
        f"Exported {len(examples)} example(s) with judge score >= {args.min_judge_score} to {output}"
    )
    return 0


def _jsonl_record(example: dict) -> dict:
    return {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a role-safe steel-plant maintenance assistant. Ground answers in "
                    "approved maintenance history, work-order outcomes, feedback, documents, and evidence."
                ),
            },
            {
                "role": "user",
                "content": f"{example['instruction']}\n\n{example['input_text']}",
            },
            {"role": "assistant", "content": example["expected_output"]},
        ],
        "metadata": {
            "example_id": example["id"],
            "source_type": example["source_type"],
            "source_id": example["source_id"],
            "equipment_id": example.get("equipment_id"),
            "work_order_id": example.get("work_order_id"),
            "judge_score": example.get("judge_score"),
            "judge_label": example.get("judge_label"),
            **(example.get("metadata") or {}),
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
