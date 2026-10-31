from __future__ import annotations

from copy import deepcopy

import pytest

from miner2049er.rule_set_selector import (
    UNTIERED_SURFACES,
    build_overlap_report,
    build_rule_sets,
    run_surfaces,
    surface_eligible,
)
from tests.benchmark_examples import benchmark_rule


def _rule(rule_id: str, *, treatment: bool = False) -> dict:
    rule = deepcopy(benchmark_rule(rule_id=rule_id))
    rule["name"] = f"Rule {rule_id}"
    rule["family_id"] = "portfolio-test"
    rule["uses_treatment_edges"] = treatment
    return rule


def _evaluation(
    rule_id: str,
    precision: float,
    hits: int,
    eligible: int,
) -> dict:
    return {
        "rule_id": rule_id,
        "partition": "feedback",
        "counts": {
            "submitted_predictions": eligible,
            "eligible_predictions": eligible,
            "known_hits": hits,
            "partition_labels": 10,
        },
        "metrics": {
            "precision_lower_bound": precision,
            "recall": hits / 10,
            "f0_5": precision,
        },
    }


def test_selector_keeps_precise_subset_until_superset_adds_value():
    rules = [_rule("a"), _rule("b"), _rule("c"), _rule("d")]
    predictions = {
        "a": {("C:1", "D:1"), ("C:2", "D:2")},
        "b": {("C:1", "D:1"), ("C:2", "D:2"), ("C:3", "D:3")},
        "c": {("C:4", "D:4")},
        "d": {("C:1", "D:1"), ("C:2", "D:2")},
    }
    evaluations = {
        "a": _evaluation("a", 0.8, 2, 2),
        "b": _evaluation("b", 0.5, 2, 3),
        "c": _evaluation("c", 0.7, 1, 1),
        "d": _evaluation("d", 0.4, 1, 2),
    }

    overlap = build_overlap_report(
        run_id="test-run",
        through_round_id="round-0001",
        rules=rules,
        predictions=predictions,
        training_labels=set(),
        evaluations=evaluations,
        generated_at="2026-08-25T12:00:00+00:00",
    )
    rule_sets = build_rule_sets(
        run_id="test-run",
        through_round_id="round-0001",
        surface="treats-included",
        rules=rules,
        predictions=predictions,
        training_labels=set(),
        evaluations=evaluations,
        generated_at="2026-08-25T12:00:00+00:00",
    )

    assert any(
        relation["left_rule_id"] == "a"
        and relation["right_rule_id"] == "b"
        and relation["prediction_relation"] == "left_strict_subset"
        for relation in overlap["relations"]
    )
    assert any(
        relation["left_rule_id"] == "a"
        and relation["right_rule_id"] == "d"
        and relation["prediction_relation"] == "exact_duplicate"
        and relation["logical_equivalent"]
        for relation in overlap["relations"]
    )
    assert [member["rule_id"] for member in rule_sets[0]["members"]] == ["a"]
    assert [member["rule_id"] for member in rule_sets[1]["members"]] == ["a", "c"]
    assert [member["rule_id"] for member in rule_sets[-1]["members"]] == [
        "a",
        "c",
        "b",
    ]
    excluded = {
        item["rule_id"]: item for item in rule_sets[-1]["excluded_rules"]
    }
    assert excluded["d"]["reason"] == "zero_marginal_confidence"
    assert excluded["d"]["redundant_with"] == ["a", "b"]


def test_treatment_excluded_surface_filters_treatment_rules():
    rules = [_rule("free"), _rule("treatment", treatment=True)]
    predictions = {
        "free": {("C:1", "D:1")},
        "treatment": {("C:2", "D:2")},
    }
    evaluations = {
        "free": _evaluation("free", 0.5, 1, 1),
        "treatment": _evaluation("treatment", 0.9, 1, 1),
    }

    rule_sets = build_rule_sets(
        run_id="test-run",
        through_round_id="round-0001",
        surface="treats-excluded",
        rules=rules,
        predictions=predictions,
        training_labels=set(),
        evaluations=evaluations,
        generated_at="2026-08-25T12:00:00+00:00",
    )

    assert [member["rule_id"] for member in rule_sets[-1]["members"]] == ["free"]
    excluded = {
        item["rule_id"]: item for item in rule_sets[-1]["excluded_rules"]
    }
    assert excluded["treatment"]["reason"] == "surface_ineligible"


def test_selector_excludes_rejected_rules_and_requires_matching_execution_for_logic():
    accepted = _rule("accepted")
    rejected = _rule("rejected")
    rejected["status"] = "rejected"
    execution_variant = _rule("execution-variant")
    execution_variant["execution"]["cypher"] += " LIMIT 1"
    rules = [accepted, rejected, execution_variant]
    shared_predictions = {("C:1", "D:1"), ("C:2", "D:2")}
    predictions = {
        "accepted": shared_predictions,
        "rejected": {("C:3", "D:3")},
        "execution-variant": shared_predictions,
    }
    evaluations = {
        "accepted": _evaluation("accepted", 0.5, 1, 2),
        "rejected": _evaluation("rejected", 1.0, 1, 1),
        "execution-variant": _evaluation("execution-variant", 0.4, 1, 2),
    }

    overlap = build_overlap_report(
        run_id="test-run",
        through_round_id="round-0001",
        rules=rules,
        predictions=predictions,
        training_labels=set(),
        evaluations=evaluations,
        generated_at="2026-08-25T12:00:00+00:00",
    )
    rule_sets = build_rule_sets(
        run_id="test-run",
        through_round_id="round-0001",
        surface="treats-included",
        rules=rules,
        predictions=predictions,
        training_labels=set(),
        evaluations=evaluations,
        generated_at="2026-08-25T12:00:00+00:00",
    )

    duplicate = next(
        relation
        for relation in overlap["relations"]
        if relation["prediction_relation"] == "exact_duplicate"
    )
    assert not duplicate["logical_equivalent"]
    assert [member["rule_id"] for member in rule_sets[-1]["members"]] == [
        "accepted"
    ]
    exclusions = {
        item["rule_id"]: item for item in rule_sets[-1]["excluded_rules"]
    }
    assert exclusions["rejected"]["reason"] == "rule_rejected"
    assert exclusions["execution-variant"]["reason"] == "zero_marginal_confidence"


def _tiered(rule_id: str, tier: str) -> dict:
    rule = _rule(rule_id, treatment=tier != "treatment_free")
    rule["evidence_tier"] = tier
    return rule


def test_same_pair_excluded_surface_keeps_transfer_and_treatment_free_rules():
    rules = [
        _tiered("free", "treatment_free"),
        _tiered("transfer", "transfer"),
        _tiered("same", "same_pair"),
    ]
    predictions = {
        "free": {("C:1", "D:1")},
        "transfer": {("C:2", "D:2")},
        "same": {("C:3", "D:3")},
    }
    evaluations = {
        "free": _evaluation("free", 0.5, 1, 1),
        "transfer": _evaluation("transfer", 0.7, 1, 1),
        "same": _evaluation("same", 0.9, 1, 1),
    }

    rule_sets = build_rule_sets(
        run_id="test-run",
        through_round_id="round-0001",
        surface="same-pair-excluded",
        rules=rules,
        predictions=predictions,
        training_labels=set(),
        evaluations=evaluations,
        generated_at="2026-10-31T12:00:00+00:00",
    )

    assert sorted(member["rule_id"] for member in rule_sets[-1]["members"]) == [
        "free",
        "transfer",
    ]
    excluded = {item["rule_id"]: item for item in rule_sets[-1]["excluded_rules"]}
    assert excluded["same"]["reason"] == "surface_ineligible"
    assert "predicted pair" in excluded["same"]["explanation"]


def test_run_surfaces_depend_on_whether_rules_carry_tiers():
    tiered = [_tiered("a", "transfer"), _tiered("b", "treatment_free")]
    legacy = [_rule("c"), _rule("d", treatment=True)]

    assert "same-pair-excluded" in run_surfaces(tiered)
    assert run_surfaces(legacy) == UNTIERED_SURFACES
    with pytest.raises(ValueError, match="mixes rules"):
        run_surfaces([*tiered, *legacy])


def test_same_pair_surface_refuses_untiered_rules():
    with pytest.raises(ValueError, match="no evidence_tier"):
        surface_eligible(_rule("legacy"), "same-pair-excluded")
