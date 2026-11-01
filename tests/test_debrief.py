from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from miner2049er.benchmark_config import load_benchmark_config
from miner2049er.debrief import build_debrief, render_markdown
from miner2049er.research_log import append_research_event
from miner2049er.run_artifacts import initialize_run
from miner2049er.settings import ROOT

SUMMARY = {
    "families_explored": ["shared-target transfer"],
    "surviving_rule_ids": [],
    "failed_families": ["pathway overlap"],
    "pareto_summary": "Nothing beat the direct-evidence baseline yet.",
    "graph_gaps": [],
    "next_round_priorities": ["direction qualifiers"],
    "questions_for_operator": [
        {
            "question": "Should rules that use clinical-trial edges count as discovery?",
            "why_it_matters": "They dominate precision but restate known evidence.",
            "default_if_unanswered": "Report them only on the treats-included surface.",
        }
    ],
    "proposed_directions": [
        {
            "direction": "Add gain or loss of function direction to target rules.",
            "rationale": "Unsigned target rules mix agonists and antagonists.",
        }
    ],
}


def _run(tmp_path: Path, deadline: datetime) -> Path:
    return initialize_run(
        runs_dir=tmp_path / "runs",
        evaluations_dir=tmp_path / "evaluations",
        authorization_dir=tmp_path / "sealed" / "authorized-runs",
        run_id="nightly",
        config=load_benchmark_config(),
        prompt_path=ROOT / "prompts" / "treats-rule-mining.md",
        deadline=deadline.isoformat(),
        instruction="Strip down the over-fancy rules.",
    )


def _debrief(tmp_path: Path, run_dir: Path, now: datetime) -> dict:
    return build_debrief(
        run_dir=run_dir,
        evaluations_dir=tmp_path / "evaluations",
        rule_set_evaluations_dir=tmp_path / "rule-set-evaluations",
        agents_dir=tmp_path / "agents",
        budget=200,
        now=now,
    )


def test_debrief_surfaces_questions_and_instruction(tmp_path: Path):
    deadline = datetime.now(UTC) + timedelta(hours=1)
    run_dir = _run(tmp_path, deadline)
    append_research_event(
        run_dir=run_dir,
        event_type="final_summary",
        summary="First night done.",
        details=SUMMARY,
    )
    state_dir = tmp_path / "agents" / "nightly-round-0001"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(
        json.dumps({"status": "awaiting_operator_seal", "invocations": 1})
    )

    debrief = _debrief(tmp_path, run_dir, deadline + timedelta(minutes=5))
    text = render_markdown(debrief)

    assert debrief["needs_attention"]
    assert debrief["attention"] == ["the agent asked 1 question(s)"]
    assert debrief["feedback_used"] == 0
    assert "Strip down the over-fancy rules." in text
    assert "Should rules that use clinical-trial edges count as discovery?" in text
    assert "Add gain or loss of function direction" in text


def test_debrief_flags_a_night_without_a_final_summary(tmp_path: Path):
    deadline = datetime.now(UTC) + timedelta(hours=1)
    run_dir = _run(tmp_path, deadline)

    during = _debrief(tmp_path, run_dir, deadline - timedelta(minutes=5))
    after = _debrief(tmp_path, run_dir, deadline + timedelta(minutes=5))

    assert during["in_progress"] and not during["needs_attention"]
    assert after["attention"] == ["round-0001 passed its deadline without a final summary"]
