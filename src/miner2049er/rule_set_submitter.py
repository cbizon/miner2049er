from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx

from miner2049er.schema_validation import read_jsonl, validate_document
from miner2049er.settings import ROOT

DEFAULT_RULE_SET_ROOT = ROOT / "results" / "rule-sets"


class RuleSetSubmissionError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(
            f"Rule-set scorer returned HTTP {status_code}: {detail[:1000]}"
        )
        self.status_code = status_code
        self.detail = detail


def build_rule_set_payload(
    *,
    run_dir: Path,
    rule_set_root: Path,
    rule_set_id: str,
) -> dict[str, Any]:
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    validate_document(manifest, "run.schema.json")
    rule_sets_path = rule_set_root / manifest["run_id"] / "rule-sets.jsonl"
    matches = [
        rule_set
        for rule_set in read_jsonl(rule_sets_path, "rule-set.schema.json")
        if rule_set["rule_set_id"] == rule_set_id
    ]
    if len(matches) != 1:
        raise ValueError(f"Rule set is not uniquely recorded: {rule_set_id}")
    rule_set = matches[0]
    return {
        "run_id": manifest["run_id"],
        "through_round_id": rule_set["through_round_id"],
        "rule_set_id": rule_set_id,
        "member_rule_ids": [member["rule_id"] for member in rule_set["members"]],
    }


def submit_rule_set(
    *,
    run_dir: Path,
    rule_set_root: Path,
    rule_set_id: str,
    partition: str,
    scorer_url: str,
    timeout_seconds: float,
    final_token: str | None = None,
) -> dict[str, Any]:
    if partition not in {"feedback", "final"}:
        raise ValueError(f"Unsupported partition: {partition}")
    payload = build_rule_set_payload(
        run_dir=run_dir,
        rule_set_root=rule_set_root,
        rule_set_id=rule_set_id,
    )
    headers = {}
    if partition == "final":
        if not final_token:
            raise PermissionError("Final rule-set scoring requires a final token")
        headers["X-Final-Token"] = final_token
    response = httpx.post(
        f"{scorer_url.rstrip('/')}/score/rule-set/{partition}",
        json=payload,
        headers=headers,
        timeout=timeout_seconds,
    )
    if not response.is_success:
        try:
            detail = response.json().get("detail", response.text)
        except (AttributeError, TypeError, ValueError):
            detail = response.text
        raise RuleSetSubmissionError(response.status_code, str(detail))
    return response.json()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit a recorded rule portfolio to the aggregate scorer"
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--rule-set", required=True)
    parser.add_argument(
        "--rule-set-root",
        type=Path,
        default=DEFAULT_RULE_SET_ROOT,
    )
    parser.add_argument(
        "--partition",
        choices=("feedback", "final"),
        default="feedback",
    )
    parser.add_argument(
        "--scorer-url",
        default=os.environ.get("SCORER_URL", "http://127.0.0.1:6430"),
    )
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument(
        "--final-token",
        default=os.environ.get("SCORER_FINAL_TOKEN"),
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = submit_rule_set(
        run_dir=args.run_dir,
        rule_set_root=args.rule_set_root,
        rule_set_id=args.rule_set,
        partition=args.partition,
        scorer_url=args.scorer_url,
        timeout_seconds=args.timeout_seconds,
        final_token=args.final_token,
    )
    document = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document, encoding="utf-8")
    print(document, end="")


if __name__ == "__main__":
    main()
