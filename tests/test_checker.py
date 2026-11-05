from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from miner2049er.checker import (
    build_prompt,
    load_reviews,
    open_challenges,
    record_review,
    render_challenges,
    rules_to_review,
)
from miner2049er.debrief import build_debrief, render_markdown
from tests.test_debrief import SUMMARY, _run

FINDING = "Most of its correct predictions come from ten heavily studied diseases."


def _review(round_id: str, rule_id: str, verdict: str) -> dict:
    entry = {
        "rule_id": rule_id,
        "plain_claim": "Predict a drug for a disease when similar diseases share its treatments.",
        "verdict": verdict,
        "attacks": [
            {
                "check": "concentration",
                "what_was_done": "Split the rule's training hits by disease degree.",
                "finding": FINDING,
            }
        ],
    }
    if verdict != "holds":
        entry["what_would_resolve"] = "Report precision separately for low-degree diseases."
    return {
        "schema_version": "1.0",
        "run_id": "nightly",
        "round_id": round_id,
        "reviewed_at": "2026-11-04T11:00:00+00:00",
        "reviewer_model": "claude-opus-5-5",
        "summary": "One transfer rule leans heavily on well-studied diseases.",
        "reviews": [entry],
    }


def _record(tmp_path: Path, review: dict, monkeypatch=None) -> Path:
    path = tmp_path / f"{review['round_id']}-{review['reviews'][0]['rule_id']}.json"
    path.write_text(json.dumps(review))
    return record_review(path, tmp_path / "reviews")


def test_record_review_validates_and_refuses_overwrite(tmp_path: Path):
    saved = _record(tmp_path, _review("round-0001", "rule-a", "doubtful"))
    assert saved == tmp_path / "reviews" / "nightly" / "round-0001.json"
    with pytest.raises(FileExistsError):
        _record(tmp_path, _review("round-0001", "rule-a", "holds"))
    bad = _review("round-0002", "rule-a", "broken")
    del bad["reviews"][0]["what_would_resolve"]
    with pytest.raises(ValueError):
        _record(tmp_path, bad)


def test_record_review_rejects_wrong_round_and_unasked_rules(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MINER_CHECKER_RUN", "nightly")
    monkeypatch.setenv("MINER_CHECKER_ROUND", "round-0002")
    monkeypatch.setenv("MINER_CHECKER_RULES", "rule-a")
    with pytest.raises(ValueError, match="round_id"):
        _record(tmp_path, _review("round-0001", "rule-a", "holds"))
    with pytest.raises(ValueError, match="wasn't asked"):
        _record(tmp_path, _review("round-0002", "rule-z", "holds"))


def test_later_reviews_supersede_and_open_challenges_render(tmp_path: Path):
    _record(tmp_path, _review("round-0001", "rule-a", "doubtful"))
    reviews = load_reviews(tmp_path / "reviews", "nightly")
    challenges = open_challenges(reviews)
    assert [entry["rule_id"] for entry in challenges] == ["rule-a"]
    text = render_challenges(challenges)
    assert "Checker challenges to answer tonight" in text
    assert FINDING in text and "low-degree diseases" in text

    _record(tmp_path, _review("round-0002", "rule-a", "holds"))
    reviews = load_reviews(tmp_path / "reviews", "nightly")
    assert open_challenges(reviews) == []
    assert render_challenges([]) == ""


def test_challenged_rules_are_reviewed_again_and_listed_in_prompt():
    run = {
        "run_dir": Path("/work/runs/nightly"),
        "manifest": {"run_id": "nightly"},
        "research_events": [],
        "evaluations": [],
        "rules": [
            {"rule_id": "old", "round_id": "round-0001", "name": "Old", "plain_language_rule": "x" * 20,
             "hypothesis": "h" * 10, "status": "candidate"},
            {"rule_id": "new", "round_id": "round-0002", "name": "New", "plain_language_rule": "y" * 20,
             "hypothesis": "h" * 10, "status": "candidate"},
            {"rule_id": "quiet", "round_id": "round-0001", "name": "Quiet", "plain_language_rule": "z" * 20,
             "hypothesis": "h" * 10, "status": "candidate"},
        ],
    }
    rules = rules_to_review(run, "round-0002", {"old"})
    assert [rule["rule_id"] for rule in rules] == ["old", "new"]
    prompt = build_prompt(
        run=run,
        round_id="round-0002",
        rules=rules,
        challenges=[{"rule_id": "old", "what_would_resolve": "Split by degree."}],
        evaluations_path=Path("/work/evaluations/nightly.jsonl"),
    )
    assert "Split by degree." in prompt and '"rule_id": "quiet"' not in prompt


def test_debrief_shows_checker_verdicts(tmp_path: Path):
    from miner2049er.research_log import append_research_event

    deadline = datetime.now(UTC) + timedelta(hours=1)
    run_dir = _run(tmp_path, deadline)
    append_research_event(
        run_dir=run_dir, event_type="final_summary", summary="Night done.", details=SUMMARY
    )
    _record(tmp_path, _review("round-0001", "rule-a", "broken"))

    debrief = build_debrief(
        run_dir=run_dir,
        evaluations_dir=tmp_path / "evaluations",
        rule_set_evaluations_dir=tmp_path / "rule-set-evaluations",
        agents_dir=tmp_path / "agents",
        budget=200,
        reviews_dir=tmp_path / "reviews",
        now=deadline + timedelta(minutes=5),
    )
    text = render_markdown(debrief)

    assert "the checker found 1 broken and 0 doubtful claim(s)" in debrief["attention"]
    assert "## The checker's review" in text and FINDING in text
