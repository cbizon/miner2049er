"""The checker: a separate session that tries to break each night's claims.

It runs after the night's agent finishes and before the morning debrief, in a
fresh Claude session that never saw the agent's reasoning. It reads the run
and queries the graph read-only, has no scorer access and no sealed labels,
and records one review per round under the reviews directory. The debrief
shows its verdicts; open challenges (doubtful or broken) are appended to the
next night's instruction so the agent has to answer them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from miner2049er.agent_runner import (
    _communicate_until_wall_deadline,
    _start_agent_process,
    _stop_process,
    build_agent_environment,
    build_claude_command,
    verify_container_isolation,
)
from miner2049er.run_artifacts import DEFAULT_EVALUATIONS_DIR, DEFAULT_RUNS_DIR, load_run
from miner2049er.schema_validation import validate_document
from miner2049er.settings import ROOT

DEFAULT_REVIEWS_DIR = Path(os.environ.get("MINER_REVIEWS_DIR", ROOT / "reviews"))
CHECKER_PROMPT = ROOT / "prompts" / "checker.md"
OPEN_VERDICTS = {"doubtful", "broken"}
NEO4J_VARIABLES = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")


def review_path(reviews_dir: Path, run_id: str, round_id: str) -> Path:
    return reviews_dir / run_id / f"{round_id}.json"


def load_reviews(reviews_dir: Path, run_id: str) -> list[dict[str, Any]]:
    run_reviews = reviews_dir / run_id
    if not run_reviews.is_dir():
        return []
    reviews = []
    for path in sorted(run_reviews.glob("round-*.json")):
        review = json.loads(path.read_text(encoding="utf-8"))
        validate_document(review, "review.schema.json")
        reviews.append(review)
    return reviews


def latest_verdicts(reviews: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each rule's most recent review entry; later rounds supersede earlier."""
    verdicts: dict[str, dict[str, Any]] = {}
    for review in sorted(reviews, key=lambda item: item["round_id"]):
        for entry in review["reviews"]:
            verdicts[entry["rule_id"]] = {**entry, "round_id": review["round_id"]}
    return verdicts


def open_challenges(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        entry
        for entry in latest_verdicts(reviews).values()
        if entry["verdict"] in OPEN_VERDICTS
    ]


def _final_summary(run: dict[str, Any], round_id: str) -> dict[str, Any] | None:
    summaries = [
        event
        for event in run["research_events"]
        if event["event_type"] == "final_summary" and event["round_id"] == round_id
    ]
    return summaries[-1] if summaries else None


def rules_to_review(
    run: dict[str, Any],
    round_id: str,
    challenged: set[str],
) -> list[dict[str, Any]]:
    """Rules recorded this round, plus earlier rules still under challenge."""
    return [
        rule
        for rule in run["rules"]
        if rule["round_id"] == round_id or rule["rule_id"] in challenged
    ]


def build_prompt(
    *,
    run: dict[str, Any],
    round_id: str,
    rules: list[dict[str, Any]],
    challenges: list[dict[str, Any]],
    evaluations_path: Path,
) -> str:
    feedback = {
        evaluation["rule_id"]: evaluation["metrics"]
        for evaluation in run["evaluations"]
        if evaluation["partition"] == "feedback"
    }
    challenge_by_rule = {entry["rule_id"]: entry for entry in challenges}
    rule_context = [
        {
            "rule_id": rule["rule_id"],
            "round_id": rule["round_id"],
            "name": rule["name"],
            "description": rule["plain_language_rule"],
            "hypothesis": rule["hypothesis"],
            "evidence_tier": rule.get("evidence_tier"),
            "status": rule["status"],
            "graded_by_scorer": feedback.get(rule["rule_id"]),
            "open_challenge": challenge_by_rule.get(rule["rule_id"], {}).get(
                "what_would_resolve"
            ),
        }
        for rule in rules
    ]
    summary = _final_summary(run, round_id)
    run_dir = run["run_dir"]
    return (
        CHECKER_PROMPT.read_text(encoding="utf-8")
        + "\n\n# This review\n\n"
        + f"- Run: `{run['manifest']['run_id']}`, round `{round_id}`.\n"
        + f"- Run folder (read-only): `{run_dir}`.\n"
        + f"- Scorer grades (read-only): `{evaluations_path}`.\n"
        + f"- The round's instruction: `{run_dir}/rounds/{round_id}/instructions.md`.\n"
        + "- Neo4j: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` are set.\n\n"
        + "The agent's own summary of the round:\n\n"
        + (summary["summary"] if summary else "(no final summary)")
        + "\n\nReview each of these rules. Rules with an `open_challenge` were "
        + "challenged in an earlier review; check whether the agent has since "
        + "answered it (research log, newer rules) and give a fresh verdict.\n\n"
        + "```json\n"
        + json.dumps(rule_context, indent=2)
        + "\n```\n"
    )


def record_review(review_file: Path, reviews_dir: Path) -> Path:
    review = json.loads(review_file.read_text(encoding="utf-8"))
    validate_document(review, "review.schema.json")
    expected = {
        "run_id": os.environ.get("MINER_CHECKER_RUN"),
        "round_id": os.environ.get("MINER_CHECKER_ROUND"),
    }
    for field, value in expected.items():
        if value and review[field] != value:
            raise ValueError(f"Review {field} is {review[field]!r}; this check is for {value!r}")
    allowed = os.environ.get("MINER_CHECKER_RULES")
    if allowed:
        unknown = {entry["rule_id"] for entry in review["reviews"]} - set(allowed.split(","))
        if unknown:
            raise ValueError(f"Review covers rules it wasn't asked to: {sorted(unknown)}")
    path = review_path(reviews_dir, review["run_id"], review["round_id"])
    if path.exists():
        raise FileExistsError(f"A review for this round already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".json.partial")
    partial.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    partial.replace(path)
    return path


def render_challenges(challenges: list[dict[str, Any]]) -> str:
    """Instruction text listing open challenges the agent must answer tonight."""
    if not challenges:
        return ""
    lines = [
        "",
        "## Checker challenges to answer tonight",
        "",
        (
            "An independent checker reviewed earlier rules and found problems. For "
            "each, either produce the evidence that resolves it, narrow the claim, "
            "or withdraw the rule, and say which in your final summary. Don't "
            "headline a challenged rule until the challenge is answered."
        ),
    ]
    for entry in sorted(challenges, key=lambda item: item["rule_id"]):
        findings = "; ".join(attack["finding"] for attack in entry["attacks"])
        lines += [
            "",
            f"- `{entry['rule_id']}` ({entry['verdict']}): {entry['plain_claim']}",
            f"  - Found: {findings}",
            f"  - To resolve: {entry['what_would_resolve']}",
        ]
    return "\n".join(lines) + "\n"


def run_checker(args: argparse.Namespace) -> int:
    verify_container_isolation(args.sealed_root)
    run_dir = args.runs_dir / args.run_id
    run = load_run(run_dir, args.evaluations_dir)
    round_id = run["rounds"][-1]["round_id"]
    if _final_summary(run, round_id) is None:
        raise RuntimeError(
            f"{round_id} has no final summary yet; the night hasn't finished"
        )
    destination = review_path(args.reviews_dir, args.run_id, round_id)
    if destination.exists():
        print(f"Already reviewed: {destination}")
        return 0

    challenges = open_challenges(load_reviews(args.reviews_dir, args.run_id))
    rules = (
        run["rules"]
        if args.all_rules
        else rules_to_review(run, round_id, {entry["rule_id"] for entry in challenges})
    )
    if not rules:
        raise RuntimeError(f"No rules to review in {round_id}")
    prompt = build_prompt(
        run=run,
        round_id=round_id,
        rules=rules,
        challenges=challenges,
        evaluations_path=args.evaluations_dir / f"{args.run_id}.jsonl",
    )

    runtime_dir = args.runtime_dir / f"{args.run_id}-{round_id}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    missing = [name for name in NEO4J_VARIABLES if not os.environ.get(name)]
    if missing:
        raise ValueError(f"Checker is missing {', '.join(missing)}")
    environment = build_agent_environment(
        runtime_dir=runtime_dir,
        # Graph access only: no scorer, so the checker spends no grading requests.
        service_environment={name: os.environ[name] for name in NEO4J_VARIABLES},
        api_key_env="UNUSED",
        agent_runtime="claude",
        isolation="container",
        evaluations_dir=args.evaluations_dir,
    )
    environment.update(
        {
            "MINER_REVIEWS_DIR": str(args.reviews_dir),
            "MINER_CHECKER_RUN": args.run_id,
            "MINER_CHECKER_ROUND": round_id,
            "MINER_CHECKER_RULES": ",".join(rule["rule_id"] for rule in rules),
        }
    )
    command = build_claude_command(
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        isolation="container",
    )
    deadline = datetime.now(UTC) + timedelta(minutes=args.minutes)
    events_path = runtime_dir / "checker.jsonl"
    stderr_path = runtime_dir / "checker.stderr.log"
    with events_path.open("w", encoding="utf-8") as events, stderr_path.open(
        "w", encoding="utf-8"
    ) as errors:
        process = _start_agent_process(
            command=command,
            agent_runtime="claude",
            environment=environment,
            events=events,
            errors=errors,
            isolation="container",
        )
        if not _communicate_until_wall_deadline(process, prompt, deadline, 15):
            _stop_process(process, 30)
    if not destination.exists():
        raise RuntimeError(
            f"The checker recorded no review for {round_id} "
            f"(exit {process.returncode}); see {events_path}"
        )
    print(f"Recorded {destination}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Independent review of a round's claims")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Review the latest finished round")
    run.add_argument("--run-id", required=True)
    run.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    run.add_argument("--evaluations-dir", type=Path, default=DEFAULT_EVALUATIONS_DIR)
    run.add_argument("--reviews-dir", type=Path, default=DEFAULT_REVIEWS_DIR)
    run.add_argument("--runtime-dir", type=Path, default=ROOT / ".run" / "checker")
    run.add_argument("--sealed-root", type=Path, default=Path("/sealed"))
    run.add_argument("--model", required=True)
    run.add_argument("--reasoning-effort", default="high")
    run.add_argument("--minutes", type=int, default=45)
    run.add_argument(
        "--all-rules",
        action="store_true",
        help="Review every rule in the run (a first review of an existing run)",
    )

    record = commands.add_parser("record", help="Validate and save a review")
    record.add_argument("--review-file", type=Path, required=True)
    record.add_argument("--reviews-dir", type=Path, default=DEFAULT_REVIEWS_DIR)

    challenges = commands.add_parser(
        "challenges", help="Print open challenges as instruction text"
    )
    challenges.add_argument("--run-id", required=True)
    challenges.add_argument("--reviews-dir", type=Path, default=DEFAULT_REVIEWS_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "run":
        raise SystemExit(run_checker(args))
    if args.command == "record":
        print(f"Recorded {record_review(args.review_file, args.reviews_dir)}")
        return
    sys.stdout.write(render_challenges(open_challenges(load_reviews(args.reviews_dir, args.run_id))))


if __name__ == "__main__":
    main()
