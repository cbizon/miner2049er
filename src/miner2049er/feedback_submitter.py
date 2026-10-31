from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx

from miner2049er.biolink_semantics import validate_rule_biolink_semantics
from miner2049er.schema_validation import read_jsonl, validate_document


class FeedbackSubmissionError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(
            f"Feedback scorer returned HTTP {status_code}: {detail[:1000]}"
        )
        self.status_code = status_code
        self.detail = detail


def build_feedback_payload(run_dir: Path, rule_id: str) -> dict[str, Any]:
    manifest_path = run_dir / "run.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_document(manifest, "run.schema.json")
    if manifest["status"] != "running" or not manifest["current_round_id"]:
        raise ValueError("Feedback can be submitted only for an active run")
    run_id = manifest["run_id"]
    round_id = manifest["current_round_id"]

    rules = [
        rule
        for rule in read_jsonl(
            run_dir / manifest["artifacts"]["rules"],
            "rule.schema.json",
        )
        if rule["rule_id"] == rule_id
    ]
    if len(rules) != 1:
        raise ValueError(f"Rule is not uniquely recorded in the run: {rule_id}")
    rule = rules[0]
    validate_rule_biolink_semantics(
        rule,
        manifest["biolink_version"],
        manifest["target_predicates"],
    )
    if rule["run_id"] != run_id or rule["round_id"] != round_id:
        raise ValueError("Feedback can be submitted only for a rule from the active round")

    predictions = [
        {
            "subject_id": prediction["subject_id"],
            "object_id": prediction["object_id"],
        }
        for prediction in read_jsonl(
            run_dir / manifest["artifacts"]["predictions"],
            "prediction.schema.json",
        )
        if prediction["rule_id"] == rule_id
        and prediction["run_id"] == run_id
        and prediction["round_id"] == round_id
    ]
    if not predictions:
        raise ValueError(f"Rule has no recorded predictions: {rule_id}")
    return {
        "run_id": run_id,
        "round_id": round_id,
        "rule_id": rule_id,
        "predictions": predictions,
    }


def submit_feedback(
    *,
    run_dir: Path,
    rule_id: str,
    scorer_url: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    payload = build_feedback_payload(run_dir, rule_id)
    response = httpx.post(
        f"{scorer_url.rstrip('/')}/score/feedback",
        json=payload,
        timeout=timeout_seconds,
    )
    if not response.is_success:
        try:
            detail = response.json().get("detail", response.text)
        except (AttributeError, TypeError, ValueError):
            detail = response.text
        raise FeedbackSubmissionError(response.status_code, str(detail))
    return response.json()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit one active-round rule to the aggregate feedback scorer"
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--rule", required=True)
    parser.add_argument(
        "--scorer-url",
        default=os.environ.get("SCORER_URL", "http://127.0.0.1:6430"),
    )
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = submit_feedback(
        run_dir=args.run_dir,
        rule_id=args.rule,
        scorer_url=args.scorer_url,
        timeout_seconds=args.timeout_seconds,
    )
    document = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document, encoding="utf-8")
    print(document, end="")


if __name__ == "__main__":
    main()
