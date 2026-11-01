"""Morning digest of a run's latest round, for the operator's daily review.

Reads only what the dashboard can read (run folder, aggregate evaluations,
agent controller state), never sealed labels. `--check` reports whether
anything needs the operator, for an unattended morning nudge.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from miner2049er.benchmark_config import DEFAULT_BENCHMARK_CONFIG, load_benchmark_config
from miner2049er.run_artifacts import DEFAULT_EVALUATIONS_DIR, DEFAULT_RUNS_DIR, load_run
from miner2049er.schema_validation import read_jsonl
from miner2049er.settings import ROOT

DEFAULT_AGENTS_DIR = ROOT / "agents"
DEFAULT_RULE_SET_EVALUATIONS_DIR = ROOT / "data" / "rule-set-evaluations"
LOW_BUDGET = 30
# Controller states that mean the night ended properly and awaits sealing.
FINISHED_STATES = {"awaiting_operator_seal", "round_complete"}


def _round_summary(events: list[dict[str, Any]], round_id: str) -> dict[str, Any] | None:
    summaries = [
        event
        for event in events
        if event["event_type"] == "final_summary" and event["round_id"] == round_id
    ]
    return summaries[-1] if summaries else None


def _feedback_used(run_id: str, evaluations: list[dict[str, Any]], rule_set_dir: Path) -> int:
    used = sum(evaluation["partition"] == "feedback" for evaluation in evaluations)
    rule_set_path = rule_set_dir / f"{run_id}.jsonl"
    if rule_set_path.is_file():
        used += sum(
            record["partition"] == "feedback"
            for record in read_jsonl(rule_set_path, "rule-set-evaluation.schema.json")
        )
    return used


def build_debrief(
    *,
    run_dir: Path,
    evaluations_dir: Path,
    rule_set_evaluations_dir: Path,
    agents_dir: Path,
    budget: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    run = load_run(run_dir, evaluations_dir)
    manifest = run["manifest"]
    run_id = manifest["run_id"]
    latest = run["rounds"][-1]
    round_id = latest["round_id"]
    deadline = datetime.fromisoformat(latest["deadline"])
    summary_event = _round_summary(run["research_events"], round_id)
    summary = summary_event["details"] if summary_event else None

    state_path = agents_dir / f"{run_id}-{round_id}" / "state.json"
    agent_state = (
        json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else None
    )
    feedback = {
        evaluation["rule_id"]: evaluation
        for evaluation in run["evaluations"]
        if evaluation["partition"] == "feedback"
    }
    new_rules = [
        {
            "rule_id": rule["rule_id"],
            "name": rule["name"],
            "rule": rule["plain_language_rule"],
            "evidence_tier": rule.get("evidence_tier", "untiered"),
            "status": rule["status"],
            "feedback_precision": feedback.get(rule["rule_id"], {})
            .get("metrics", {})
            .get("precision_lower_bound"),
            "feedback_recall": feedback.get(rule["rule_id"], {})
            .get("metrics", {})
            .get("recall"),
        }
        for rule in run["rules"]
        if rule["round_id"] == round_id
    ]
    used = _feedback_used(run_id, run["evaluations"], rule_set_evaluations_dir)

    attention: list[str] = []
    finished = summary is not None
    if now >= deadline and not finished:
        attention.append(f"{round_id} passed its deadline without a final summary")
    if agent_state and now >= deadline and agent_state.get("status") not in FINISHED_STATES:
        attention.append(f"{round_id} agent ended in state {agent_state.get('status')!r}")
    questions = (summary or {}).get("questions_for_operator", [])
    if questions:
        attention.append(f"the agent asked {len(questions)} question(s)")
    if budget - used <= LOW_BUDGET:
        attention.append(f"only {budget - used} of {budget} grading requests left")

    instruction_path = run_dir / "rounds" / round_id / "instructions.md"
    return {
        "run_id": run_id,
        "run_status": manifest["status"],
        "round_id": round_id,
        "round_count": manifest["round_count"],
        "deadline": latest["deadline"],
        "in_progress": now < deadline and not finished,
        "instruction": instruction_path.read_text(encoding="utf-8")
        if instruction_path.is_file()
        else None,
        "agent_state": None
        if agent_state is None
        else {
            key: agent_state.get(key)
            for key in ("status", "invocations", "completion_mode", "finalization_error")
        },
        "summary": None if summary_event is None else summary_event["summary"],
        "final_summary": summary,
        "questions": questions,
        "proposed_directions": (summary or {}).get("proposed_directions", []),
        "new_rules": new_rules,
        "rules_total": len(run["rules"]),
        "feedback_used": used,
        "feedback_budget": budget,
        "needs_attention": bool(attention),
        "attention": attention,
    }


def _percent(value: float | None) -> str:
    return "not graded" if value is None else f"{value * 100:.1f}%"


def render_markdown(debrief: dict[str, Any]) -> str:
    lines = [
        f"# {debrief['run_id']}: {debrief['round_id']}",
        "",
        f"- Run status: {debrief['run_status']}, {debrief['round_count']} round(s)",
        f"- Deadline: {debrief['deadline']}"
        + (" (still running)" if debrief["in_progress"] else ""),
        f"- Grading requests used: {debrief['feedback_used']} of {debrief['feedback_budget']}",
        f"- Rules this round: {len(debrief['new_rules'])} (run total {debrief['rules_total']})",
    ]
    if debrief["agent_state"]:
        state = debrief["agent_state"]
        lines.append(
            f"- Agent finished as: {state['status']}"
            + (f" ({state['completion_mode']})" if state.get("completion_mode") else "")
        )
    if debrief["attention"]:
        lines += ["", "## Needs you", *[f"- {item}" for item in debrief["attention"]]]
    if debrief["instruction"]:
        lines += ["", "## Last night's instruction", "", debrief["instruction"].strip()]
    final = debrief["final_summary"]
    if final:
        lines += ["", "## Agent's summary", "", debrief["summary"], "", final["pareto_summary"]]
        for title, key in (
            ("Families explored", "families_explored"),
            ("Failed families", "failed_families"),
            ("Graph gaps", "graph_gaps"),
        ):
            if final.get(key):
                lines += ["", f"**{title}**", *[f"- {item}" for item in final[key]]]
    if debrief["questions"]:
        lines += ["", "## Questions for you"]
        for number, item in enumerate(debrief["questions"], start=1):
            lines += [
                f"{number}. {item['question']}",
                f"   - Why it matters: {item['why_it_matters']}",
                f"   - If unanswered: {item['default_if_unanswered']}",
            ]
    if debrief["proposed_directions"]:
        lines += ["", "## Proposed next directions"]
        for number, item in enumerate(debrief["proposed_directions"], start=1):
            lines += [f"{number}. {item['direction']}", f"   - {item['rationale']}"]
    if debrief["new_rules"]:
        lines += [
            "",
            "## Rules this round",
            "",
            "| Rule | Tier | Precision | Recall | Status |",
            "| --- | --- | --- | --- | --- |",
        ]
        for rule in sorted(
            debrief["new_rules"],
            key=lambda item: -(item["feedback_precision"] or -1),
        ):
            lines.append(
                f"| {rule['name']} (`{rule['rule_id']}`) | {rule['evidence_tier']} | "
                f"{_percent(rule['feedback_precision'])} | "
                f"{_percent(rule['feedback_recall'])} | {rule['status']} |"
            )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a run's latest round")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--evaluations-dir", type=Path, default=DEFAULT_EVALUATIONS_DIR)
    parser.add_argument(
        "--rule-set-evaluations-dir",
        type=Path,
        default=DEFAULT_RULE_SET_EVALUATIONS_DIR,
    )
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--config", type=Path, default=DEFAULT_BENCHMARK_CONFIG)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print only whether the operator is needed, as JSON",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    debrief = build_debrief(
        run_dir=args.runs_dir / args.run_id,
        evaluations_dir=args.evaluations_dir,
        rule_set_evaluations_dir=args.rule_set_evaluations_dir,
        agents_dir=args.agents_dir,
        budget=load_benchmark_config(args.config).scoring.maximum_feedback_submissions_per_run,
    )
    if args.check:
        print(
            json.dumps(
                {
                    key: debrief[key]
                    for key in ("run_id", "round_id", "in_progress", "needs_attention", "attention")
                }
            )
        )
    else:
        print(render_markdown(debrief), end="")


if __name__ == "__main__":
    main()
