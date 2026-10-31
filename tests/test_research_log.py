import json
from pathlib import Path

import pytest

from miner2049er.research_log import append_research_event


def _checkpoint_details() -> dict:
    return {
        "progress": ["Recorded the current search state."],
        "active_hypotheses": ["pathway convergence"],
        "completed_hypotheses": [],
        "next_actions": ["Profile pathway degree distributions."],
        "resource_summary": None,
    }


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "research-log.jsonl").touch()
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "test-run",
                "status": "running",
                "current_round_id": "round-0001",
                "artifacts": {"research_log": "research-log.jsonl"},
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def test_append_research_event_owns_sequence_timestamp_and_round(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    first = append_research_event(
        run_dir=run_dir,
        event_type="evaluation",
        summary="Recorded delayed scorer output.",
        details={
            "method": "Aggregate feedback scoring.",
            "metrics": {"precision_lower_bound": 0.5},
            "interpretation": "The candidate warrants refinement.",
            "decision": "refine",
            "next_action": "Test the degree ablation.",
            "scored_at": "2020-01-01T00:00:00+00:00",
        },
    )
    second = append_research_event(
        run_dir=run_dir,
        event_type="checkpoint",
        summary="Checkpointed the active search.",
        details=_checkpoint_details(),
    )

    assert [first["sequence"], second["sequence"]] == [1, 2]
    assert first["round_id"] == second["round_id"] == "round-0001"
    assert first["schema_version"] == second["schema_version"] == "1.0"
    assert first["timestamp"] <= second["timestamp"]
    assert first["timestamp"] != first["details"]["scored_at"]


def test_append_research_event_rejects_inactive_run(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    manifest_path = run_dir / "run.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(status="round_complete", current_round_id=None)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="active round"):
        append_research_event(
            run_dir=run_dir,
            event_type="checkpoint",
            summary="Should not append.",
            details=_checkpoint_details(),
        )


def test_append_research_event_requires_event_specific_details(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    with pytest.raises(ValueError, match="research-event.schema.json"):
        append_research_event(
            run_dir=run_dir,
            event_type="query",
            summary="Missing the structured query fields.",
            details={"query_text": "MATCH (n) RETURN count(n)"},
        )
