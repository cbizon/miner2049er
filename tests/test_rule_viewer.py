import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from miner2049er.rule_viewer import install_rule_viewer


def _result(
    rule_id: str,
    name: str,
    *,
    visible: bool = False,
    visible_treatment_free: bool = False,
    validation: bool = False,
    validation_treatment_free: bool = False,
    parent_rule: str | None = None,
) -> dict:
    return {
        "id": rule_id,
        "name": name,
        "iteration": 9,
        "parent_rule": parent_rule,
        "library_status": "candidate",
        "status": "completed",
        "hypothesis": f"Hypothesis for {name}",
        "body": f"Detailed body for {name}",
        "description": f"Complete interpretation for {name}",
        "criteria": [
            f"First required condition for {name}",
            f"Second required condition for {name}",
        ],
        "mechanism_score": "high",
        "mechanism_rationale": f"Mechanism rationale for {name}",
        "uses_treatment_edges": not visible_treatment_free,
        "trapi_expressibility": "partial",
        "trapi_notes": f"TRAPI notes for {name}",
        "trapi_template": None,
        "cypher": (
            "MATCH (subject:Drug)-[:AFFECTS]->(object:Disease)\n"
            "WHERE subject.name = '<unsafe>'\n"
            "RETURN subject.id AS subject_id, object.id AS object_id"
        ),
        "counts": {
            "candidate_pairs": 10,
            "training_hits": 4,
            "validation_hits": 1,
            "contraindicated_pairs": 2,
            "unresolved_or_blind_pairs": 5,
        },
        "metrics": {
            "visible_target_precision_lower_bound": 0.5,
            "visible_target_recall": 0.01,
            "visible_target_f0_5": 0.04,
            "validation_precision_lower_bound": 1 / 6,
            "validation_recall": 0.002,
            "validation_f0_5": 0.009,
        },
        "runtime_seconds": 1.25,
        "pareto_visible": visible,
        "pareto_validation": validation,
        "pareto_visible_without_treatment_edges": visible_treatment_free,
        "pareto_validation_without_treatment_edges": validation_treatment_free,
        "pareto_visible_within_mechanism": True,
    }


def _client(tmp_path: Path) -> TestClient:
    library = {
        "updated_at": "2026-08-13T00:00:00+00:00",
        "target_inventory": {"counts": {"semantic_pairs": 28_988}},
        "results": [
            _result(
                "TREAT-I09-R001",
                "Visible rule",
                visible=True,
                visible_treatment_free=True,
                validation=True,
            ),
            _result(
                "TREAT-I09-R002",
                "Validation-only rule",
                validation=True,
                validation_treatment_free=True,
                parent_rule="TREAT-I09-R001",
            ),
            _result("TREAT-I09-R003", "Off-surface rule"),
        ],
    }
    path = tmp_path / "rule-library.json"
    path.write_text(json.dumps(library), encoding="utf-8")
    app = FastAPI()
    install_rule_viewer(app, path)
    return TestClient(app)


def test_main_page_lists_visible_surface_and_navigation(tmp_path):
    response = _client(tmp_path).get("/rules")

    assert response.status_code == 200
    assert "Visible rule" in response.text
    assert "Validation-only rule" not in response.text
    assert "Visible · treatment-free" in response.text
    assert "Hub-exclusive · all" in response.text
    assert "/rules/rule/TREAT-I09-R001" in response.text
    assert "50.00%" in response.text


def test_validation_surface_uses_validation_metrics(tmp_path):
    response = _client(tmp_path).get("/rules/surface/validation")

    assert response.status_code == 200
    assert "Visible rule" in response.text
    assert "Validation-only rule" in response.text
    assert "Hub-exclusive hits" in response.text
    assert "16.67%" in response.text
    assert "6 non-training predictions" in response.text


def test_rule_detail_includes_description_cypher_and_surface_links(tmp_path):
    response = _client(tmp_path).get("/rules/rule/TREAT-I09-R002")

    assert response.status_code == 200
    assert "Complete interpretation for Validation-only rule" in response.text
    assert "First required condition for Validation-only rule" in response.text
    assert "Mining provenance" in response.text
    assert "Detailed body for Validation-only rule" in response.text
    assert "Hypothesis for Validation-only rule" not in response.text
    assert "Mechanism rationale for Validation-only rule" in response.text
    assert "MATCH (subject:Drug)" in response.text
    assert "&lt;unsafe&gt;" in response.text
    assert "/rules/surface/validation-treatment-free" in response.text
    assert "/rules/rule/TREAT-I09-R001" in response.text


def test_unknown_surface_and_rule_return_404(tmp_path):
    client = _client(tmp_path)

    assert client.get("/rules/surface/not-a-surface").status_code == 404
    assert client.get("/rules/rule/TREAT-I09-R999").status_code == 404
