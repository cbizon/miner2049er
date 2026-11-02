from __future__ import annotations

import argparse
import fcntl
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from miner2049er.schema_validation import validate_document

RESEARCH_EVENT_SCHEMA_VERSION = "1.0"
RESEARCH_EVENT_TYPES = (
    "hypothesis",
    "query",
    "observation",
    "evaluation",
    "ablation",
    "materialization",
    "failure",
    "graph_limitation",
    "checkpoint",
    "final_summary",
)


def _load_details(args: argparse.Namespace) -> dict[str, Any]:
    if args.details_file:
        value = json.loads(args.details_file.read_text(encoding="utf-8"))
    else:
        value = json.loads(args.details_json)
    if not isinstance(value, dict):
        raise TypeError("Research event details must be a JSON object")
    return value


MAX_OPERATOR_QUESTIONS = 5

def append_research_event(
    *,
    run_dir: Path,
    event_type: str,
    summary: str,
    details: dict[str, Any],
    rule_id: str | None = None,
) -> dict[str, Any]:
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if manifest["status"] != "running" or not manifest["current_round_id"]:
        raise ValueError("Research events can be appended only to an active round")
    questions = details.get("questions_for_operator", []) if event_type == "final_summary" else []
    if len(questions) > MAX_OPERATOR_QUESTIONS:
        # Enforced at write time rather than in the schema, so logs written
        # before the cap still validate.
        raise ValueError(
            f"A final summary may ask at most {MAX_OPERATOR_QUESTIONS} questions; "
            f"this one asks {len(questions)}. Keep the ones that need human judgment."
        )

    path = run_dir / manifest["artifacts"]["research_log"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0)
        prior_sequence = 0
        prior_timestamp: datetime | None = None
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                prior = orjson.loads(line)
            except orjson.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid research event JSON at line {line_number}"
                ) from error
            validate_document(prior, "research-event.schema.json")
            if prior["run_id"] != manifest["run_id"]:
                raise ValueError(
                    f"Research event line {line_number} belongs to another run"
                )
            if prior["sequence"] != prior_sequence + 1:
                raise ValueError(
                    f"Research event sequence is invalid at line {line_number}"
                )
            timestamp = datetime.fromisoformat(prior["timestamp"])
            if prior_timestamp is not None and timestamp < prior_timestamp:
                raise ValueError(
                    f"Research event timestamp is out of order at line {line_number}"
                )
            prior_sequence = prior["sequence"]
            prior_timestamp = timestamp

        timestamp = datetime.now(UTC)
        if prior_timestamp is not None and timestamp < prior_timestamp:
            timestamp = prior_timestamp.astimezone(UTC)
        event = {
            "schema_version": RESEARCH_EVENT_SCHEMA_VERSION,
            "run_id": manifest["run_id"],
            "round_id": manifest["current_round_id"],
            "sequence": prior_sequence + 1,
            "timestamp": timestamp.isoformat(),
            "event_type": event_type,
            "rule_id": rule_id,
            "summary": summary,
            "details": details,
        }
        validate_document(event, "research-event.schema.json")
        stream.seek(0, 2)
        stream.write(orjson.dumps(event, option=orjson.OPT_SORT_KEYS) + b"\n")
        stream.flush()
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return event


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append one canonically ordered event to an active research log"
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--event-type",
        required=True,
        choices=RESEARCH_EVENT_TYPES,
    )
    parser.add_argument("--summary", required=True)
    parser.add_argument("--rule-id")
    details = parser.add_mutually_exclusive_group(required=True)
    details.add_argument("--details-json")
    details.add_argument("--details-file", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    event = append_research_event(
        run_dir=args.run_dir,
        event_type=args.event_type,
        summary=args.summary,
        details=_load_details(args),
        rule_id=args.rule_id,
    )
    print(json.dumps(event, indent=2))


if __name__ == "__main__":
    main()
