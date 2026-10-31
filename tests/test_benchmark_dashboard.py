import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from miner2049er.benchmark_config import load_benchmark_config
from miner2049er.benchmark_dashboard import (
    _main_table_round_id,
    _pareto_ids,
    _surface_evaluations,
    install_benchmark_dashboard,
    render_run,
)
from miner2049er.research_log import append_research_event
from miner2049er.run_artifacts import initialize_run, record_agent_execution
from tests.benchmark_examples import benchmark_rule, neo4j_artifact


def test_dashboard_handles_empty_and_initialized_run_directories(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    evaluations_dir = tmp_path / "evaluations"
    rule_set_root = tmp_path / "rule-sets"
    rule_set_evaluations_dir = tmp_path / "rule-set-evaluations"
    runs_dir.mkdir()
    app = FastAPI()
    install_benchmark_dashboard(
        app,
        runs_dir,
        evaluations_dir,
        rule_set_root,
        rule_set_evaluations_dir,
    )
    client = TestClient(app)

    empty = client.get("/benchmark")
    assert empty.status_code == 200
    assert "No benchmark runs" in empty.text

    run_dir = initialize_run(
        runs_dir=runs_dir,
        evaluations_dir=evaluations_dir,
        authorization_dir=tmp_path / "sealed" / "authorized-runs",
        run_id="test-run",
        config=load_benchmark_config(),
        prompt_path=Path("prompts/treats-rule-mining.md"),
        deadline="2026-08-19T07:00:00-04:00",
    )
    artifact = neo4j_artifact()
    (run_dir / "neo4j-artifacts.jsonl").write_text(
        json.dumps(artifact) + "\n",
        encoding="utf-8",
    )
    rule = benchmark_rule()
    (run_dir / "rules.jsonl").write_text(
        json.dumps(rule) + "\n",
        encoding="utf-8",
    )
    analysis_dir = rule_set_root / "test-run"
    analysis_dir.mkdir(parents=True)
    overlap = {
        "schema_version": "1.0",
        "run_id": "test-run",
        "through_round_id": "round-0001",
        "generated_at": "2026-08-19T12:00:00Z",
        "rule_count": 1,
        "distinct_prediction_pairs": 10,
        "rules": [
            {
                "rule_id": "test-rule",
                "round_id": "round-0001",
                "family_id": "test-family",
                "uses_treatment_edges": True,
                "prediction_count": 10,
                "feedback_eligible_predictions": 8,
                "training_hits": 2,
                "feedback_scored": True,
                "feedback_precision": 0.75,
                "feedback_hits": 6,
                "selection_status": "eligible",
                "selection_explanation": "Scored rule with nonzero feedback precision.",
            }
        ],
        "relations": [],
        "limitations": [
            "Logical equivalence is reported only for identical normalized patterns."
        ],
    }
    (analysis_dir / "overlap.json").write_text(
        json.dumps(overlap),
        encoding="utf-8",
    )
    rule_set = {
        "schema_version": "1.0",
        "run_id": "test-run",
        "through_round_id": "round-0001",
        "rule_set_id": "treats-included-k001",
        "surface": "treats-included",
        "selection_method": "greedy_marginal_f0_5_coverage_v1",
        "generated_at": "2026-08-19T12:00:00Z",
        "is_estimated_pareto": True,
        "members": [
            {
                "position": 1,
                "rule_id": "test-rule",
                "feedback_precision": 0.75,
                "prediction_count": 10,
                "eligible_prediction_count": 8,
                "new_predictions": 10,
                "new_eligible_predictions": 8,
                "overlapping_eligible_predictions": 0,
                "guaranteed_new_feedback_hits": 6,
                "estimated_new_feedback_hits": 6.0,
                "new_training_hits": 2,
                "cumulative_predictions": 10,
                "cumulative_eligible_predictions": 8,
                "cumulative_training_hits": 2,
                "cumulative_training_recall": 0.2,
                "cumulative_estimated_feedback_hits": 6.0,
                "cumulative_estimated_feedback_precision": 0.75,
                "cumulative_estimated_feedback_recall": 0.3,
                "cumulative_estimated_f0_5": 0.576923,
            }
        ],
        "excluded_rules": [],
        "union": {
            "member_count": 1,
            "prediction_count": 10,
            "eligible_prediction_count": 8,
            "training_hits": 2,
            "training_labels": 10,
            "training_recall": 0.2,
            "guaranteed_feedback_hits": 6,
            "estimated_feedback_hits": 6.0,
            "estimated_feedback_precision": 0.75,
            "estimated_feedback_recall": 0.3,
            "estimated_f0_5": 0.576923,
            "feedback_partition_labels": 20,
        },
        "limitations": [
            "Estimated union metrics are not a substitute for aggregate scoring."
        ],
    }
    (analysis_dir / "rule-sets.jsonl").write_text(
        json.dumps(rule_set) + "\n",
        encoding="utf-8",
    )
    rule_set_evaluations_dir.mkdir()
    rule_set_evaluation = {
        "schema_version": "1.0",
        "benchmark_id": "test-benchmark",
        "split_id": "test-split",
        "run_id": "test-run",
        "through_round_id": "round-0001",
        "rule_set_id": "treats-included-k001",
        "member_rule_ids": ["test-rule"],
        "partition": "feedback",
        "prediction_sha256": "a" * 64,
        "counts": {
            "submitted_predictions": 10,
            "eligible_predictions": 8,
            "known_hits": 5,
            "partition_labels": 20,
        },
        "metrics": {
            "precision_lower_bound": 0.625,
            "recall": 0.25,
            "f0_5": 0.480769,
        },
        "scored_at": "2026-08-19T12:05:00Z",
    }
    (rule_set_evaluations_dir / "test-run.jsonl").write_text(
        json.dumps(rule_set_evaluation) + "\n",
        encoding="utf-8",
    )
    append_research_event(
        run_dir=run_dir,
        event_type="query",
        summary="Profiled a pathway convergence query.",
        details={
            "purpose": "Measure the tractability of a pathway-mediated rule.",
            "query_language": "cypher",
            "query_text": "MATCH (drug)-[]->(gene)-[]->(pathway) RETURN count(*)",
            "parameters": {"maximum_pathway_degree": 100},
            "outcome": "completed",
            "result_summary": "The bounded query returned a tractable candidate set.",
            "runtime_seconds": 1.5,
            "next_action": "Materialize compact pathway support.",
        },
    )
    record_agent_execution(
        run_dir=run_dir,
        round_id="round-0001",
        model="gpt-5.6-sol",
        model_provider="azure",
        reasoning_effort="xhigh",
    )
    run = client.get("/benchmark/run/test-run")
    assert run.status_code == 200
    assert "Feedback · Treats included" in run.text
    assert "round-0001" in run.text
    assert "Run history" in run.text
    assert "Disease-associated gene count" in run.text
    assert "Biolink 4.4.4 with descendant expansion" in run.text
    assert "Treats included" in run.text
    assert "Treats excluded" in run.text
    assert "All rules" in run.text
    assert "Pareto only" in run.text
    assert "view=pareto" in run.text
    assert "Run status: running" in run.text
    assert "Showing all rounds." in run.text
    assert "Pareto is computed across the entire run." in run.text
    assert "round_id=round-0001" in run.text
    assert 'id="rules-table"' in run.text
    assert "data-sort-type" in run.text
    assert "[sort]" in run.text
    assert "gpt-5.6-sol" in run.text
    assert "azure · extra-high reasoning" in run.text
    assert "Test treatment rule" in run.text
    assert "Not scored" in run.text
    assert "Research log" in run.text
    assert "Profiled a pathway convergence query." in run.text
    assert "Query: 1" in run.text
    assert "/benchmark/run/test-run/research" in run.text
    assert "Rule portfolios" in run.text
    assert "/benchmark/run/test-run/rule-sets" in run.text
    research_page = client.get("/benchmark/run/test-run/research")
    assert research_page.status_code == 200
    assert "Append-only experiment history" in research_page.text
    assert "Measure the tractability of a pathway-mediated rule." in research_page.text
    assert "maximum_pathway_degree" in research_page.text
    assert "Raw event JSON" in research_page.text
    rule_page = client.get("/benchmark/run/test-run/rule/test-rule")
    assert rule_page.status_code == 200
    assert "Biolink predicate semantics" in rule_page.text
    assert "247 effective predicates after Biolink expansion" in rule_page.text
    assert "trapi_subpredicate_expansion" in rule_page.text
    assert "Treatment-oriented premises:" in rule_page.text
    assert 'class="rule-diagram"' in rule_page.text
    assert "Required graph evidence" in rule_page.text
    assert "<summary>Graph pattern JSON</summary>" in rule_page.text
    assert '<details class="rule-fold" open' not in rule_page.text
    assert rule_page.text.index('class="rule-diagram"') < rule_page.text.index("Technical details")
    artifact_page = client.get(
        "/benchmark/run/test-run/neo4j-artifact/disease-associated-gene-count"
    )
    assert artifact_page.status_code == 200
    assert "Create Cypher" in artifact_page.text
    assert "_miner_associated_gene_count" in artifact_page.text
    rule_sets_page = client.get("/benchmark/run/test-run/rule-sets")
    assert rule_sets_page.status_code == 200
    assert "treats-included-k001" in rule_sets_page.text
    assert "Estimated Pareto" in rule_sets_page.text
    assert "62.50%" in rule_sets_page.text
    rule_set_page = client.get(
        "/benchmark/run/test-run/rule-set/treats-included-k001"
    )
    assert rule_set_page.status_code == 200
    assert "Ordered members" in rule_set_page.text
    assert "Test treatment rule" in rule_set_page.text
    assert "Estimated feedback precision" in rule_set_page.text
    assert "Feedback</strong>: 5 hits" in rule_set_page.text
    assert client.get("/benchmark/run/test-run?partition=unknown").status_code == 404
    assert client.get("/benchmark/run/test-run?surface=unknown").status_code == 404
    assert client.get("/benchmark/run/test-run?view=unknown").status_code == 404
    assert client.get("/benchmark/run/test-run?round_id=unknown").status_code == 404
    round_page = client.get(
        "/benchmark/run/test-run?round_id=round-0001&surface=treats-excluded&view=pareto"
    )
    assert round_page.status_code == 200
    assert "Showing round-0001." in round_page.text
    assert "within this round only" in round_page.text
    assert "surface=treats-excluded&amp;view=pareto&amp;round_id=round-0001" in round_page.text
    assert (
        client.get("/benchmark/run/test-run/rule-sets?surface=unknown").status_code
        == 404
    )


def test_dashboard_computes_all_rule_and_treatment_free_fronts_separately():
    rules = {
        "treatment-free": {"uses_treatment_edges": False},
        "treatment-using": {"uses_treatment_edges": True},
    }
    evaluations = [
        {
            "rule_id": "treatment-free",
            "metrics": {"precision_lower_bound": 0.5, "recall": 0.4},
        },
        {
            "rule_id": "treatment-using",
            "metrics": {"precision_lower_bound": 0.9, "recall": 0.5},
        },
    ]

    included = _surface_evaluations(evaluations, rules, "treats-included")
    excluded = _surface_evaluations(evaluations, rules, "treats-excluded")

    assert _pareto_ids(included) == {"treatment-using"}
    assert _pareto_ids(excluded) == {"treatment-free"}


def test_main_table_uses_active_or_latest_completed_round():
    rounds = [
        {
            "round_id": "round-0001",
            "round_number": 1,
            "status": "completed",
        },
        {
            "round_id": "round-0002",
            "round_number": 2,
            "status": "completed",
        },
    ]

    assert (
        _main_table_round_id(
            {"current_round_id": "round-0002"},
            rounds,
        )
        == "round-0002"
    )
    assert (
        _main_table_round_id(
            {"current_round_id": None},
            rounds,
        )
        == "round-0002"
    )
    assert _main_table_round_id({"current_round_id": None}, []) is None


def test_dashboard_can_show_only_pareto_rules():
    run = {
        "manifest": {
            "run_id": "test-run",
            "graph_version": "2026_06_21",
            "biolink_version": "4.3.2",
            "split_id": "test-split",
            "status": "round_complete",
            "artifacts": {"rounds": "rounds"},
        },
        "rounds": [],
        "neo4j_artifacts": [],
        "rules": [
            {
                "rule_id": "pareto-rule",
                "name": "Pareto rule",
                "family_id": "test-family",
                "mechanism": {"score": "high"},
                "uses_treatment_edges": False,
            },
            {
                "rule_id": "dominated-rule",
                "name": "Dominated rule",
                "family_id": "test-family",
                "mechanism": {"score": "medium"},
                "uses_treatment_edges": False,
            },
            {
                "rule_id": "unscored-rule",
                "name": "Unscored rule",
                "family_id": "test-family",
                "mechanism": {"score": "high"},
                "uses_treatment_edges": False,
                "status": "candidate",
            },
        ],
        "evaluations": [
            {
                "rule_id": "pareto-rule",
                "round_id": "round-0001",
                "partition": "feedback",
                "counts": {"eligible_predictions": 10, "known_hits": 8},
                "metrics": {
                    "precision_lower_bound": 0.8,
                    "recall": 0.6,
                    "f0_5": 0.75,
                },
            },
            {
                "rule_id": "dominated-rule",
                "round_id": "round-0001",
                "partition": "feedback",
                "counts": {"eligible_predictions": 20, "known_hits": 8},
                "metrics": {
                    "precision_lower_bound": 0.4,
                    "recall": 0.3,
                    "f0_5": 0.37,
                },
            },
        ],
        "research_events": [],
    }

    all_rules = render_run(run, "feedback", "treats-included", "all")
    pareto_only = render_run(run, "feedback", "treats-included", "pareto")

    assert "Pareto rule" in all_rules
    assert "Dominated rule" in all_rules
    assert "Unscored rule" in all_rules
    assert "3 of 3 shown" in all_rules
    assert "Pareto rule" in pareto_only
    assert "Dominated rule" not in pareto_only
    assert "Unscored rule" not in pareto_only
    assert "1 of 3 shown" in pareto_only
    assert "surface=treats-excluded&amp;view=pareto" in pareto_only


def test_dashboard_scopes_completed_run_table_to_latest_round(tmp_path: Path):
    checkpoint_zero = {"rules": {"records": 0}}
    checkpoint_one = {"rules": {"records": 1}}
    checkpoint_two = {"rules": {"records": 2}}
    run = {
        "run_dir": tmp_path,
        "manifest": {
            "run_id": "test-run",
            "graph_version": "2026_06_21",
            "biolink_version": "4.3.2",
            "split_id": "test-split",
            "status": "round_complete",
            "current_round_id": None,
            "artifacts": {"rounds": "rounds"},
        },
        "rounds": [
            {
                "round_id": "round-0001",
                "round_number": 1,
                "status": "completed",
                "deadline": None,
                "starting_artifacts": checkpoint_zero,
                "ending_artifacts": checkpoint_one,
            },
            {
                "round_id": "round-0002",
                "round_number": 2,
                "status": "completed",
                "deadline": None,
                "starting_artifacts": checkpoint_one,
                "ending_artifacts": checkpoint_two,
            },
        ],
        "neo4j_artifacts": [],
        "rules": [
            {
                "rule_id": "older-rule",
                "round_id": "round-0001",
                "name": "Older round rule",
                "family_id": "older-family",
                "mechanism": {"score": "high"},
                "uses_treatment_edges": False,
                "status": "evaluated",
            },
            {
                "rule_id": "newer-rule",
                "round_id": "round-0002",
                "name": "Newer round rule",
                "family_id": "newer-family",
                "mechanism": {"score": "medium"},
                "uses_treatment_edges": False,
                "status": "evaluated",
            },
        ],
        "evaluations": [
            {
                "rule_id": "older-rule",
                "round_id": "round-0001",
                "partition": "feedback",
                "counts": {"eligible_predictions": 10, "known_hits": 9},
                "metrics": {
                    "precision_lower_bound": 0.9,
                    "recall": 0.8,
                    "f0_5": 0.87,
                },
            },
            {
                "rule_id": "newer-rule",
                "round_id": "round-0002",
                "partition": "feedback",
                "counts": {"eligible_predictions": 20, "known_hits": 8},
                "metrics": {
                    "precision_lower_bound": 0.4,
                    "recall": 0.3,
                    "f0_5": 0.37,
                },
            },
        ],
        "prediction_counts": {},
        "research_events": [],
    }

    cumulative = render_run(run, "feedback", "treats-included", "all")
    assert "Showing all rounds." in cumulative
    assert "Newer round rule" in cumulative
    assert "Older round rule" in cumulative
    assert "1 Pareto rules · 2 of 2 shown" in cumulative
    pareto = render_run(run, "feedback", "treats-included", "pareto")
    assert "Older round rule" in pareto
    assert "Newer round rule" not in pareto
    assert "1 Pareto rules · 1 of 2 shown" in pareto
    # The explicit round-local view remains available, but is no longer the default.
    html = render_run(run, "feedback", "treats-included", "all", "latest")

    assert "Run status: round complete" in html
    assert "Showing round-0002." in html
    assert "earlier and later rounds are not compared" in html
    assert "Newer round rule" in html
    assert "Older round rule" not in html
    assert "1 Pareto rules · 1 of 1 shown" in html
    first_round = render_run(run, "feedback", "treats-included", "pareto", "round-0001")
    assert "Older round rule" in first_round
    assert "Newer round rule" not in first_round
    assert "round_id=round-0001" in first_round
    run["manifest"]["current_round_id"] = "round-0002"
    assert "Older round rule" in render_run(run, "feedback", "treats-included", "pareto")
