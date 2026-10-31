import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from miner2049er.benchmark_config import BenchmarkConfig
from miner2049er.biolink_semantics import (
    BIOLINK_VERSION,
    FULL_EXPANSION,
    predicate_expansion_record,
)
from miner2049er.schema_validation import validate_document
from miner2049er.scorer import (
    LabelStore,
    SubmissionLedger,
    score_predictions,
    score_rule_set_predictions,
)
from miner2049er.scorer_server import (
    _authorize_rule_set_submission,
    _authorize_submission,
    _rule_set_prediction_union,
    _score,
)


def _config() -> BenchmarkConfig:
    return BenchmarkConfig.from_dict(
        {
            "schema_version": "1.0",
            "benchmark_id": "test",
            "graph_version": "2026_06_21",
            "biolink": {
                "version": BIOLINK_VERSION,
                "predicate_expansion": "descendants",
            },
            "target": {
                "predicate": "biolink:treats",
                "predicate_closure": [
                    "biolink:treats",
                    "biolink:ameliorates_condition",
                    "biolink:preventative_for_condition",
                ],
            },
            "split": {
                "algorithm": "sha256-ranked-pairs-v1",
                "seed": "test",
                "training_fraction": 0.7,
                "feedback_fraction": 0.2,
                "final_fraction": 0.1,
            },
            "scoring": {
                "minimum_predictions": 2,
                "maximum_feedback_submissions_per_run": 2,
                "metric_decimal_places": 6,
            },
        }
    )


def _rule(run_id: str, round_id: str, rule_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "round_id": round_id,
        "rule_id": rule_id,
        "family_id": "test-family",
        "parent_rule_id": None,
        "name": "Test treatment rule",
        "status": "candidate",
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
        "derived_features": [],
        "mechanism": {
            "score": "low",
            "rationale": "This fixture tests scorer authorization behavior.",
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


def test_feedback_and_final_use_different_eligible_prediction_sets():
    labels = LabelStore(
        training=frozenset({("C:train", "D:train")}),
        feedback=frozenset({("C:feedback", "D:feedback")}),
        final=frozenset({("C:final", "D:final")}),
    )
    predictions = {
        ("C:train", "D:train"),
        ("C:feedback", "D:feedback"),
        ("C:final", "D:final"),
        ("C:unknown", "D:unknown"),
    }

    feedback = score_predictions(
        config=_config(),
        labels=labels,
        run_id="run",
        round_id="round-0001",
        rule_id="rule",
        pairs=predictions,
        partition="feedback",
    )
    final = score_predictions(
        config=_config(),
        labels=labels,
        run_id="run",
        round_id="round-0001",
        rule_id="rule",
        pairs=predictions,
        partition="final",
    )

    assert feedback["counts"]["eligible_predictions"] == 3
    assert feedback["counts"]["known_hits"] == 1
    assert feedback["metrics"]["precision_lower_bound"] == 0.333333
    assert final["counts"]["eligible_predictions"] == 2
    assert final["counts"]["known_hits"] == 1
    assert final["metrics"]["precision_lower_bound"] == 0.5


def test_rule_set_scoring_records_members_and_union_metrics():
    labels = LabelStore(
        training=frozenset({("C:train", "D:train")}),
        feedback=frozenset({("C:feedback", "D:feedback")}),
        final=frozenset(),
    )
    result = score_rule_set_predictions(
        config=_config(),
        labels=labels,
        run_id="run",
        through_round_id="round-0002",
        rule_set_id="portfolio",
        member_rule_ids=["rule-1", "rule-2"],
        pairs={
            ("C:train", "D:train"),
            ("C:feedback", "D:feedback"),
            ("C:unknown", "D:unknown"),
        },
        partition="feedback",
    )

    assert result["member_rule_ids"] == ["rule-1", "rule-2"]
    assert result["counts"]["submitted_predictions"] == 3
    assert result["counts"]["eligible_predictions"] == 2
    assert result["counts"]["known_hits"] == 1
    assert result["metrics"]["precision_lower_bound"] == 0.5


def test_scorer_minimum_counts_only_feedback_eligible_predictions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _config()
    labels = LabelStore(
        training=frozenset({("C:train", "D:train")}),
        feedback=frozenset(),
        final=frozenset(),
    )
    ledger = SubmissionLedger(tmp_path / "state.sqlite3")
    monkeypatch.setattr(
        "miner2049er.scorer_server._runtime",
        lambda: (config, labels, ledger),
    )
    monkeypatch.setattr(
        "miner2049er.scorer_server._authorize_submission",
        lambda **kwargs: {"feedback_submission_limit": 2},
    )

    with pytest.raises(ValueError, match="partition-eligible"):
        _score(
            {
                "run_id": "run",
                "round_id": "round-0001",
                "rule_id": "rule",
                "predictions": [
                    {"subject_id": "C:train", "object_id": "D:train"},
                    {"subject_id": "C:new", "object_id": "D:new"},
                ],
            },
            "feedback",
        )


def test_submission_ledger_rejects_reused_rule_and_prediction_sets(tmp_path: Path):
    ledger = SubmissionLedger(tmp_path / "state.sqlite3")
    ledger.record_feedback(
        run_id="run",
        round_id="round-0001",
        rule_id="rule-1",
        digest="a" * 64,
        maximum_per_run=2,
    )

    with pytest.raises(ValueError, match="already scored"):
        ledger.record_feedback(
            run_id="run",
            round_id="round-0002",
            rule_id="rule-1",
            digest="b" * 64,
            maximum_per_run=2,
        )

    with pytest.raises(ValueError, match="identical prediction union"):
        ledger.record_rule_set_feedback(
            run_id="run",
            through_round_id="round-0002",
            rule_set_id="portfolio",
            digest="a" * 64,
            maximum_per_run=2,
        )
    with pytest.raises(ValueError, match="already scored"):
        ledger.record_feedback(
            run_id="run",
            round_id="round-0002",
            rule_id="rule-2",
            digest="a" * 64,
            maximum_per_run=2,
        )


def test_submission_budget_is_cumulative_across_rounds(tmp_path: Path):
    ledger = SubmissionLedger(tmp_path / "state.sqlite3")
    ledger.record_feedback(
        run_id="run",
        round_id="round-0001",
        rule_id="rule-1",
        digest="a" * 64,
        maximum_per_run=2,
    )
    ledger.record_feedback(
        run_id="run",
        round_id="round-0002",
        rule_id="rule-2",
        digest="b" * 64,
        maximum_per_run=2,
    )

    with pytest.raises(ValueError, match="limit reached"):
        ledger.record_feedback(
            run_id="run",
            round_id="round-0002",
            rule_id="rule-3",
            digest="c" * 64,
            maximum_per_run=2,
        )


def test_rule_and_rule_set_submissions_share_feedback_budget(tmp_path: Path):
    ledger = SubmissionLedger(tmp_path / "state.sqlite3")
    ledger.record_feedback(
        run_id="run",
        round_id="round-0001",
        rule_id="rule-1",
        digest="a" * 64,
        maximum_per_run=2,
    )
    ledger.record_rule_set_feedback(
        run_id="run",
        through_round_id="round-0002",
        rule_set_id="portfolio-1",
        digest="b" * 64,
        maximum_per_run=2,
    )

    with pytest.raises(ValueError, match="limit reached"):
        ledger.record_rule_set_feedback(
            run_id="run",
            through_round_id="round-0002",
            rule_set_id="portfolio-2",
            digest="c" * 64,
            maximum_per_run=2,
        )


def test_scorer_authorizes_only_the_active_round_then_final(monkeypatch, tmp_path: Path):
    config = _config()
    authorization_dir = tmp_path / "authorized-runs"
    authorization_dir.mkdir()
    authorization_path = authorization_dir / "run.json"
    authorization = {
        "schema_version": "1.0",
        "run_id": "run",
        "benchmark_id": config.benchmark_id,
        "split_id": config.split_id,
        "graph_version": config.graph_version,
        "biolink_version": config.biolink_version,
        "predicate_expansion": config.predicate_expansion,
        "status": "running",
        "current_round_id": "round-0002",
        "round_ids": ["round-0001", "round-0002"],
        "feedback_submission_limit": 2,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    validate_document(authorization, "run-authorization.schema.json")
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "rules.jsonl").write_text(
        "\n".join(
            (
                json.dumps(_rule("run", "round-0001", "rule-1")),
                json.dumps(_rule("run", "round-0002", "rule-2")),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "miner2049er.scorer_server.AUTHORIZED_RUNS_DIR",
        authorization_dir,
    )
    monkeypatch.setattr("miner2049er.scorer_server.RUNS_DIR", runs_dir)

    with pytest.raises(ValueError, match="active round"):
        _authorize_submission(
            config=config,
            run_id="run",
            round_id="round-0001",
            rule_id="rule-1",
            partition="feedback",
        )
    assert _authorize_submission(
        config=config,
        run_id="run",
        round_id="round-0002",
        rule_id="rule-2",
        partition="feedback",
    )["status"] == "running"
    with pytest.raises(ValueError, match="only after the run is closed"):
        _authorize_submission(
            config=config,
            run_id="run",
            round_id="round-0002",
            rule_id="rule-2",
            partition="final",
        )

    authorization.update(
        {
            "status": "round_complete",
            "current_round_id": None,
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
    with pytest.raises(ValueError, match="closed for this run"):
        _authorize_submission(
            config=config,
            run_id="run",
            round_id="round-0002",
            rule_id="rule-2",
            partition="feedback",
        )
    with pytest.raises(ValueError, match="only after the run is closed"):
        _authorize_submission(
            config=config,
            run_id="run",
            round_id="round-0002",
            rule_id="rule-2",
            partition="final",
        )

    authorization.update(
        {
            "status": "completed",
            "current_round_id": None,
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
    assert _authorize_submission(
        config=config,
        run_id="run",
        round_id="round-0001",
        rule_id="rule-1",
        partition="final",
    )["status"] == "completed"

    with pytest.raises(ValueError, match="must match the recorded rule"):
        _authorize_submission(
            config=config,
            run_id="run",
            round_id="round-0002",
            rule_id="rule-1",
            partition="final",
        )


def test_rule_set_authorization_requires_recorded_members_and_round_boundary(
    monkeypatch,
    tmp_path: Path,
):
    config = _config()
    authorization_dir = tmp_path / "authorized-runs"
    authorization_dir.mkdir()
    authorization = {
        "schema_version": "1.0",
        "run_id": "run",
        "benchmark_id": config.benchmark_id,
        "split_id": config.split_id,
        "graph_version": config.graph_version,
        "biolink_version": config.biolink_version,
        "predicate_expansion": config.predicate_expansion,
        "status": "round_complete",
        "current_round_id": None,
        "round_ids": ["round-0001", "round-0002"],
        "feedback_submission_limit": 2,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    (authorization_dir / "run.json").write_text(
        json.dumps(authorization),
        encoding="utf-8",
    )
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "run"
    run_dir.mkdir(parents=True)
    rules = [
        _rule("run", "round-0001", "rule-1"),
        _rule("run", "round-0002", "rule-2"),
    ]
    (run_dir / "rules.jsonl").write_text(
        "\n".join(json.dumps(rule) for rule in rules) + "\n",
        encoding="utf-8",
    )
    rule_set_root = tmp_path / "rule-sets"
    analysis_dir = rule_set_root / "run"
    analysis_dir.mkdir(parents=True)
    rule_set = {
        "schema_version": "1.0",
        "run_id": "run",
        "through_round_id": "round-0002",
        "rule_set_id": "portfolio",
        "surface": "treats-included",
        "selection_method": "greedy_marginal_f0_5_coverage_v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "is_estimated_pareto": True,
        "members": [
            {
                "position": index,
                "rule_id": rule_id,
                "feedback_precision": 0.5,
                "prediction_count": 2,
                "eligible_prediction_count": 2,
                "new_predictions": 1,
                "new_eligible_predictions": 1,
                "overlapping_eligible_predictions": 1,
                "guaranteed_new_feedback_hits": 0,
                "estimated_new_feedback_hits": 0.5,
                "new_training_hits": 0,
                "cumulative_predictions": index + 1,
                "cumulative_eligible_predictions": index + 1,
                "cumulative_training_hits": 0,
                "cumulative_training_recall": 0.0,
                "cumulative_estimated_feedback_hits": 0.5 * index,
                "cumulative_estimated_feedback_precision": 0.5,
                "cumulative_estimated_feedback_recall": 0.1 * index,
                "cumulative_estimated_f0_5": 0.2,
            }
            for index, rule_id in enumerate(["rule-1", "rule-2"], start=1)
        ],
        "excluded_rules": [],
        "union": {
            "member_count": 2,
            "prediction_count": 3,
            "eligible_prediction_count": 3,
            "training_hits": 0,
            "training_labels": 7,
            "training_recall": 0.0,
            "guaranteed_feedback_hits": 0,
            "estimated_feedback_hits": 1.0,
            "estimated_feedback_precision": 0.333333,
            "estimated_feedback_recall": 0.1,
            "estimated_f0_5": 0.25,
            "feedback_partition_labels": 10,
        },
        "limitations": ["Test portfolio."],
    }
    validate_document(rule_set, "rule-set.schema.json")
    (analysis_dir / "rule-sets.jsonl").write_text(
        json.dumps(rule_set) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "miner2049er.scorer_server.AUTHORIZED_RUNS_DIR",
        authorization_dir,
    )
    monkeypatch.setattr("miner2049er.scorer_server.RUNS_DIR", runs_dir)
    monkeypatch.setattr("miner2049er.scorer_server.RULE_SET_ROOT", rule_set_root)

    assert _authorize_rule_set_submission(
        config=config,
        run_id="run",
        through_round_id="round-0002",
        rule_set_id="portfolio",
        member_rule_ids=["rule-1", "rule-2"],
        partition="feedback",
    )["status"] == "round_complete"
    with pytest.raises(ValueError, match="members do not match"):
        _authorize_rule_set_submission(
            config=config,
            run_id="run",
            through_round_id="round-0002",
            rule_set_id="portfolio",
            member_rule_ids=["rule-2", "rule-1"],
            partition="feedback",
        )


def test_rule_set_prediction_union_reads_member_pairs(monkeypatch, tmp_path: Path):
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "run"
    run_dir.mkdir(parents=True)
    predictions = [
        {
            "rule_id": "rule-1",
            "subject_id": "C:1",
            "object_id": "D:1",
        },
        {
            "rule_id": "rule-2",
            "subject_id": "C:1",
            "object_id": "D:1",
        },
        {
            "rule_id": "rule-2",
            "subject_id": "C:2",
            "object_id": "D:2",
        },
        {
            "rule_id": "other",
            "subject_id": "C:3",
            "object_id": "D:3",
        },
    ]
    (run_dir / "predictions.jsonl").write_text(
        "\n".join(json.dumps(prediction) for prediction in predictions) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("miner2049er.scorer_server.RUNS_DIR", runs_dir)

    assert _rule_set_prediction_union(
        run_id="run",
        member_rule_ids=["rule-1", "rule-2"],
    ) == {("C:1", "D:1"), ("C:2", "D:2")}
