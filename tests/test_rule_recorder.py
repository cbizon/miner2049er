from __future__ import annotations

import json
from pathlib import Path

import pytest

from miner2049er.benchmark_config import load_benchmark_config
from miner2049er.feedback_submitter import FeedbackSubmissionError
from miner2049er.rule_recorder import build_rule, record_rule
from miner2049er.run_artifacts import initialize_run, load_run


def _candidate(
    *,
    rule_id: str = "candidate-rule",
    derived_features: list[dict] | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "rule_id": rule_id,
        "family_id": "candidate-family",
        "parent_rule_id": None,
        "name": "Candidate causal rule",
        "status": "candidate",
        "plain_language_rule": (
            "A chemical is connected to a disease through a causal graph edge."
        ),
        "hypothesis": "A causal chemical-disease edge may predict treatment.",
        "variant_parameters": {},
        "graph_pattern": {
            "nodes": [
                {
                    "id": "chemical",
                    "role": "candidate treatment",
                    "categories": ["biolink:ChemicalEntity"],
                    "explanation": "The predicted treatment.",
                },
                {
                    "id": "disease",
                    "role": "candidate disease",
                    "categories": ["biolink:Disease"],
                    "explanation": "The predicted disease.",
                },
            ],
            "edges": [
                {
                    "id": "evidence",
                    "subject": "chemical",
                    "object": "disease",
                    "predicates": ["biolink:causes"],
                    "direction": "forward",
                    "explanation": "The chemical has causal evidence for the disease.",
                }
            ],
            "constraints": [],
        },
        "derived_features": derived_features or [],
        "mechanism": {
            "score": "low",
            "rationale": "This candidate exercises deterministic rule recording.",
        },
        "execution": {
            "cypher_template": (
                "MATCH (subject)-[e:{{relationship_types:evidence}}]->(object) "
                "WHERE e.predicate IN {{predicates:evidence}} "
                "RETURN subject.id AS subject_id, object.id AS object_id, "
                "1 AS support_count"
            ),
            "trapi": {
                "expressibility": "full",
                "query": {
                    "message": {
                        "query_graph": {
                            "nodes": {
                                "chemical": {
                                    "categories": ["biolink:ChemicalEntity"]
                                },
                                "disease": {"categories": ["biolink:Disease"]},
                            },
                            "edges": {
                                "evidence": {
                                    "subject": "chemical",
                                    "object": "disease",
                                    "predicates": ["biolink:causes"],
                                }
                            },
                        }
                    }
                },
                "limitations": "",
            },
        },
        "limitations": ["This fixture is not a biological claim."],
    }


def _run(tmp_path: Path) -> tuple[Path, Path]:
    evaluations_dir = tmp_path / "evaluations"
    run_dir = initialize_run(
        runs_dir=tmp_path / "runs",
        evaluations_dir=evaluations_dir,
        authorization_dir=tmp_path / "sealed" / "authorized-runs",
        run_id="test-run",
        config=load_benchmark_config(),
        prompt_path=Path("prompts/treats-rule-mining.md"),
        deadline="2026-08-21T07:00:00-04:00",
    )
    return run_dir, evaluations_dir


def test_record_rule_builds_expansions_and_appends_sorted_predictions(
    tmp_path: Path,
) -> None:
    run_dir, evaluations_dir = _run(tmp_path)

    result = record_rule(
        run_dir=run_dir,
        candidate=_candidate(),
        evaluations_dir=evaluations_dir,
        query_records=lambda cypher: [
            {
                "subject_id": "CHEBI:2",
                "object_id": "MONDO:2",
                "support_count": 1,
            },
            {
                "subject_id": "CHEBI:1",
                "object_id": "MONDO:1",
                "support_count": 1,
            },
            {
                "subject_id": "CHEBI:1",
                "object_id": "MONDO:1",
                "support_count": 1,
            },
        ],
    )

    loaded = load_run(run_dir, evaluations_dir)
    rule = loaded["rules"][0]
    predictions = [
        json.loads(line)
        for line in (run_dir / "predictions.jsonl").read_text().splitlines()
    ]
    assert result["prediction_count"] == 2
    assert result["duplicate_rows_collapsed"] == 1
    assert result["feedback"]["status"] == "not_requested"
    assert rule["graph_pattern"]["edges"][0]["predicate_expansion"][
        "expanded_predicates"
    ] == ["biolink:causes"]
    assert "{{predicates:" not in rule["execution"]["cypher"]
    assert "{{relationship_types:" not in rule["execution"]["cypher"]
    assert rule["uses_treatment_edges"] is False
    assert [prediction["subject_id"] for prediction in predictions] == [
        "CHEBI:1",
        "CHEBI:2",
    ]


def test_record_rule_keeps_low_volume_rule_without_submitting_feedback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, evaluations_dir = _run(tmp_path)

    def unexpected_submit(**kwargs):
        raise AssertionError(kwargs)

    monkeypatch.setattr(
        "miner2049er.rule_recorder.submit_feedback",
        unexpected_submit,
    )
    result = record_rule(
        run_dir=run_dir,
        candidate=_candidate(),
        evaluations_dir=evaluations_dir,
        query_records=lambda cypher: [
            {"subject_id": "CHEBI:1", "object_id": "MONDO:1"}
        ],
        submit=True,
    )

    assert result["status"] == "recorded"
    assert result["prediction_count"] == 1
    assert result["feedback"]["status"] == "skipped"
    assert "configured feedback minimum of 5" in result["feedback"]["reason"]
    assert len(load_run(run_dir, evaluations_dir)["rules"]) == 1


def test_record_rule_treats_scorer_eligible_minimum_as_a_skip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, evaluations_dir = _run(tmp_path)

    def ineligible_submit(**kwargs):
        raise FeedbackSubmissionError(
            400,
            "At least 5 partition-eligible unique predictions are required "
            "after excluding visible labels",
        )

    monkeypatch.setattr(
        "miner2049er.rule_recorder.submit_feedback",
        ineligible_submit,
    )
    result = record_rule(
        run_dir=run_dir,
        candidate=_candidate(),
        evaluations_dir=evaluations_dir,
        query_records=lambda cypher: [
            {
                "subject_id": f"CHEBI:{index}",
                "object_id": f"MONDO:{index}",
            }
            for index in range(5)
        ],
        submit=True,
    )

    assert result["status"] == "recorded"
    assert result["feedback"]["status"] == "skipped"
    assert "partition-eligible" in result["feedback"]["reason"]


def test_record_rule_records_zero_result_candidate(tmp_path: Path) -> None:
    run_dir, evaluations_dir = _run(tmp_path)

    result = record_rule(
        run_dir=run_dir,
        candidate=_candidate(),
        evaluations_dir=evaluations_dir,
        query_records=lambda cypher: [],
    )

    assert result["prediction_count"] == 0
    assert len(load_run(run_dir, evaluations_dir)["rules"]) == 1
    assert (run_dir / "predictions.jsonl").read_text() == ""


def test_conflicting_duplicate_predictions_append_nothing(tmp_path: Path) -> None:
    run_dir, evaluations_dir = _run(tmp_path)

    with pytest.raises(ValueError, match="conflicting duplicate"):
        record_rule(
            run_dir=run_dir,
            candidate=_candidate(),
            evaluations_dir=evaluations_dir,
            query_records=lambda cypher: [
                {
                    "subject_id": "CHEBI:1",
                    "object_id": "MONDO:1",
                    "support_count": 1,
                },
                {
                    "subject_id": "CHEBI:1",
                    "object_id": "MONDO:1",
                    "support_count": 2,
                },
            ],
        )

    assert (run_dir / "rules.jsonl").read_text() == ""
    assert (run_dir / "predictions.jsonl").read_text() == ""


def test_post_append_validation_failure_rolls_back_both_ledgers(
    tmp_path: Path,
) -> None:
    run_dir, evaluations_dir = _run(tmp_path)
    candidate = _candidate(
        derived_features=[
            {
                "name": "Missing feature",
                "definition": "A feature that was not recorded.",
                "inputs": ["test input"],
                "construction": "Read a missing Neo4j node property.",
                "formula": None,
                "interpretation": "This should fail run-level validation.",
                "neo4j_artifact_id": "missing-artifact",
            }
        ]
    )

    with pytest.raises(ValueError, match="unknown Neo4j artifact"):
        record_rule(
            run_dir=run_dir,
            candidate=candidate,
            evaluations_dir=evaluations_dir,
            query_records=lambda cypher: [
                {"subject_id": "CHEBI:1", "object_id": "MONDO:1"}
            ],
        )

    assert (run_dir / "rules.jsonl").read_text() == ""
    assert (run_dir / "predictions.jsonl").read_text() == ""


def test_rule_candidate_requires_predicate_placeholder(tmp_path: Path) -> None:
    run_dir, _ = _run(tmp_path)
    manifest = json.loads((run_dir / "run.json").read_text())
    candidate = _candidate()
    candidate["execution"]["cypher_template"] = (
        "MATCH (subject)-[e:CAUSES]->(object) "
        "RETURN subject.id AS subject_id, object.id AS object_id"
    )

    with pytest.raises(ValueError, match="token for every graph edge"):
        build_rule(candidate, manifest)
