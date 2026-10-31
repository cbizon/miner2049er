import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from miner2049er.benchmark_config import load_benchmark_config
from miner2049er.biolink_semantics import (
    BIOLINK_VERSION,
    FULL_EXPANSION,
    predicate_expansion_record,
)
from miner2049er.run_artifacts import (
    close_run,
    finish_round,
    initialize_run,
    load_run,
    load_run_authorization,
    record_agent_execution,
    start_round,
    validate_run_directory,
)
from miner2049er.scorer import LabelStore, append_evaluation, score_predictions
from tests.benchmark_examples import neo4j_artifact


def _event(
    run_id: str,
    round_id: str,
    sequence: int,
    summary: str,
    event_type: str = "checkpoint",
) -> dict:
    if event_type != "final_summary":
        raise ValueError("This test helper only constructs final summary events")
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "round_id": round_id,
        "sequence": sequence,
        "timestamp": datetime.now(UTC).isoformat(),
        "event_type": event_type,
        "rule_id": None,
        "summary": summary,
        "details": {
            "families_explored": [],
            "surviving_rule_ids": [],
            "failed_families": [],
            "pareto_summary": "No scored rules were available in this test.",
            "graph_gaps": [],
            "next_round_priorities": [],
        },
    }


def _append_event(run_dir: Path, event: dict) -> None:
    with (run_dir / "research-log.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event) + "\n")


def _rule(
    run_id: str,
    round_id: str,
    rule_id: str,
    neo4j_artifact_id: str | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "round_id": round_id,
        "rule_id": rule_id,
        "family_id": "test-family",
        "parent_rule_id": None,
        "name": "Test treatment rule",
        "status": "retained",
        "plain_language_rule": (
            "A candidate chemical is connected to a disease through test evidence."
        ),
        "hypothesis": "The test graph pattern predicts treatment relationships.",
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
                    "role": "target disease",
                    "categories": ["biolink:Disease"],
                    "explanation": "The predicted disease.",
                },
            ],
            "edges": [
                {
                    "id": "evidence",
                    "subject": "chemical",
                    "object": "disease",
                    "predicates": ["biolink:related_to"],
                    "predicate_expansion": predicate_expansion_record(
                        ["biolink:related_to"]
                    ),
                    "direction": "forward",
                    "explanation": "The test evidence relationship.",
                }
            ],
            "constraints": [],
        },
        "derived_features": (
            [
                {
                    "name": "Disease-associated gene count",
                    "definition": "Number of distinct associated genes for the disease.",
                    "inputs": ["gene-disease association relationships"],
                    "construction": "Materialized as a Disease node property.",
                    "formula": "count(DISTINCT gene.id)",
                    "interpretation": "Lower values indicate a focused gene neighborhood.",
                    "neo4j_artifact_id": neo4j_artifact_id,
                }
            ]
            if neo4j_artifact_id
            else []
        ),
        "mechanism": {
            "score": "low",
            "rationale": "This fixture tests lifecycle behavior rather than biology.",
        },
        "uses_treatment_edges": True,
        "execution": {
            "cypher": (
                "MATCH (subject)-[]->(object) "
                "RETURN subject.id AS subject_id, object.id AS object_id"
            ),
            "predicate_expansion": {
                "semantics": FULL_EXPANSION,
                "biolink_version": BIOLINK_VERSION,
                "implementation": (
                    "The query applies the complete descendant predicate set "
                    "recorded for the graph edge."
                ),
            },
            "trapi": {
                "expressibility": "full",
                "query": {},
                "limitations": "",
            },
        },
        "limitations": ["This is a test fixture."],
    }


def test_run_can_continue_across_rounds_and_close(tmp_path: Path):
    evaluations_dir = tmp_path / "evaluations"
    authorization_dir = tmp_path / "sealed" / "authorized-runs"
    config = load_benchmark_config()
    run_dir = initialize_run(
        runs_dir=tmp_path / "runs",
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        run_id="test-run",
        config=config,
        prompt_path=Path("prompts/treats-rule-mining.md"),
        deadline="2026-08-19T07:00:00-04:00",
        instruction="Establish the first set of mechanism families.",
    )
    _append_event(
        run_dir,
        _event(
            "test-run",
            "round-0001",
            1,
            "Completed the first round.",
            "final_summary",
        ),
    )

    assert validate_run_directory(run_dir, evaluations_dir) == {
        "rounds": 1,
        "neo4j_artifacts": 0,
        "rules": 0,
        "predictions": 0,
        "research_events": 1,
        "evaluations": 0,
    }

    recorded_execution = record_agent_execution(
        run_dir=run_dir,
        round_id="round-0001",
        model="gpt-5.6-sol",
        model_provider="azure",
        reasoning_effort="xhigh",
    )
    loaded_run = load_run(run_dir, evaluations_dir)
    assert loaded_run["agent_executions"]["round-0001"] == recorded_execution

    boundary = finish_round(
        run_dir=run_dir,
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        config=config,
    )
    assert boundary["status"] == "round_complete"
    assert boundary["current_round_id"] is None

    prompt_path = start_round(
        run_dir=run_dir,
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        config=config,
        deadline="2026-08-20T07:00:00-04:00",
        instruction="Explore pathway and anatomy mechanisms not covered in round one.",
    )
    assert prompt_path.name == "agent-prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    assert "round-0002" in prompt
    assert "Explore pathway and anatomy mechanisms" in prompt
    assert "Do not rewrite or delete prior JSONL records" in prompt
    assert "Every new Neo4j artifact" in prompt
    assert "Biolink Model `4.3.2`" in prompt
    assert "miner-expand-predicate biolink:affects" in prompt
    assert "training statistics, ablations, predictions, and reruns" in prompt
    assert "uses_treatment_edges" in prompt
    assert "Derived-feature engineering is an expected part of the search" in prompt
    assert "Do not treat Neo4j as read-only" in prompt
    assert "Derived features provide many opportunities to overfit" in prompt
    assert "otherwise identical rule without that feature" in prompt
    assert "Do not reduce this assignment to two-hop templates" in prompt
    assert "A failed first" in prompt and "query is not a failed hypothesis" in prompt
    assert "Expensive joins are a signal to engineer the search" in prompt
    assert "pre-aggregate or materialize reusable neighborhoods" in prompt
    assert "Research events use schema `1.0`" in prompt
    assert "`materialization`" in prompt
    assert "miner-record-rule" in prompt
    assert "Do not write `rules.jsonl` or `predictions.jsonl` directly" in prompt
    assert "feedback minimum is five predictions" in prompt

    _append_event(
        run_dir,
        _event(
            "test-run",
            "round-0002",
            2,
            "Completed the second round.",
            "final_summary",
        ),
    )
    artifact = neo4j_artifact(
        run_id="test-run",
        round_id="round-0002",
    )
    with (run_dir / "neo4j-artifacts.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(artifact) + "\n")
    with (run_dir / "rules.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                _rule(
                    "test-run",
                    "round-0002",
                    "rule-1",
                    neo4j_artifact_id=artifact["artifact_id"],
                )
            )
            + "\n"
        )
    validation = validate_run_directory(run_dir, evaluations_dir)
    assert validation["rounds"] == 2
    assert validation["neo4j_artifacts"] == 1

    boundary = finish_round(
        run_dir=run_dir,
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        config=config,
    )
    assert boundary["status"] == "round_complete"

    manifest = close_run(
        run_dir=run_dir,
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        config=config,
    )
    assert manifest["status"] == "completed"
    assert manifest["current_round_id"] is None
    authorization = load_run_authorization(authorization_dir, "test-run")
    assert authorization["status"] == "completed"
    assert authorization["round_ids"] == ["round-0001", "round-0002"]

    final_evaluation = score_predictions(
        config=config,
        labels=LabelStore(
            training=frozenset(),
            feedback=frozenset(),
            final=frozenset({("CHEBI:1", "MONDO:1")}),
        ),
        run_id="test-run",
        round_id="round-0002",
        rule_id="rule-1",
        pairs={("CHEBI:1", "MONDO:1")},
        partition="final",
    )
    append_evaluation(evaluations_dir / "test-run.jsonl", final_evaluation)
    assert validate_run_directory(run_dir, evaluations_dir)["evaluations"] == 1


def test_round_instruction_files_are_immutable(tmp_path: Path):
    evaluations_dir = tmp_path / "evaluations"
    authorization_dir = tmp_path / "sealed" / "authorized-runs"
    run_dir = initialize_run(
        runs_dir=tmp_path / "runs",
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        run_id="test-run",
        config=load_benchmark_config(),
        prompt_path=Path("prompts/treats-rule-mining.md"),
        deadline=None,
    )
    instructions = run_dir / "rounds" / "round-0001" / "instructions.md"
    instructions.write_text("Changed after the round started.\n", encoding="utf-8")

    with pytest.raises(ValueError, match="modified after creation"):
        validate_run_directory(run_dir, evaluations_dir)


def test_round_cannot_finish_without_final_summary(tmp_path: Path):
    evaluations_dir = tmp_path / "evaluations"
    authorization_dir = tmp_path / "sealed" / "authorized-runs"
    config = load_benchmark_config()
    run_dir = initialize_run(
        runs_dir=tmp_path / "runs",
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        run_id="test-run",
        config=config,
        prompt_path=Path("prompts/treats-rule-mining.md"),
        deadline=None,
    )

    with pytest.raises(ValueError, match="final_summary"):
        finish_round(
            run_dir=run_dir,
            evaluations_dir=evaluations_dir,
            authorization_dir=authorization_dir,
            config=config,
        )

    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "running"
    assert manifest["current_round_id"] == "round-0001"


def test_failed_round_transition_restores_the_active_round(tmp_path: Path):
    evaluations_dir = tmp_path / "evaluations"
    authorization_dir = tmp_path / "sealed" / "authorized-runs"
    config = load_benchmark_config()
    run_dir = initialize_run(
        runs_dir=tmp_path / "runs",
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        run_id="test-run",
        config=config,
        prompt_path=Path("prompts/treats-rule-mining.md"),
        deadline=None,
    )
    _append_event(
        run_dir,
        _event(
            "test-run",
            "round-0001",
            1,
            "Completed the first round.",
            "final_summary",
        ),
    )
    finish_round(
        run_dir=run_dir,
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        config=config,
    )

    with pytest.raises(ValueError, match="date-time"):
        start_round(
            run_dir=run_dir,
            evaluations_dir=evaluations_dir,
            authorization_dir=authorization_dir,
            config=config,
            deadline="not-a-date",
        )

    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    first_round = json.loads(
        (run_dir / "rounds" / "round-0001" / "round.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "round_complete"
    assert manifest["current_round_id"] is None
    assert manifest["round_count"] == 1
    assert first_round["status"] == "completed"
    assert not (run_dir / "rounds" / "round-0002").exists()
    assert validate_run_directory(run_dir, evaluations_dir)["rounds"] == 1


def test_rule_cannot_reference_an_unrecorded_neo4j_artifact(tmp_path: Path):
    evaluations_dir = tmp_path / "evaluations"
    run_dir = initialize_run(
        runs_dir=tmp_path / "runs",
        evaluations_dir=evaluations_dir,
        authorization_dir=tmp_path / "sealed" / "authorized-runs",
        run_id="test-run",
        config=load_benchmark_config(),
        prompt_path=Path("prompts/treats-rule-mining.md"),
        deadline=None,
    )
    with (run_dir / "rules.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                _rule(
                    "test-run",
                    "round-0001",
                    "rule-1",
                    neo4j_artifact_id="missing-artifact",
                )
            )
            + "\n"
        )

    with pytest.raises(ValueError, match="references unknown Neo4j artifact"):
        validate_run_directory(run_dir, evaluations_dir)
