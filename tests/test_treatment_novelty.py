from __future__ import annotations

from miner2049er.treatment_novelty import build_report, classify_prediction

TREATERS = {"D:known": {"C:treater"}}
TARGETS = {"C:treater": {"G:1"}, "C:same-target": {"G:1"}, "C:other": {"G:2"}}
NEIGHBORS = {"C:salt": {"C:treater"}}


def _classify(chemical: str, disease: str = "D:known") -> str:
    return classify_prediction(
        (chemical, disease),
        treaters_by_disease=TREATERS,
        targets=TARGETS,
        neighbors=NEIGHBORS,
    )


def test_prediction_classes_follow_closeness_to_known_treaters():
    assert _classify("C:other", "D:untreated") == "no_known_treater"
    assert _classify("C:same-target") == "shared_target"
    assert _classify("C:salt") == "chemical_neighbor"
    assert _classify("C:other") == "other"


def test_known_treater_is_not_its_own_comparison():
    assert _classify("C:treater") == "no_known_treater"


def _fake_fetch(cypher, parameters):
    if ":Gene" in cypher:
        return [
            {"chemical": chemical, "gene": gene}
            for chemical, genes in TARGETS.items()
            if chemical in parameters["ids"]
            for gene in genes
        ]
    return [{"chemical": "C:salt", "parent": "C:treater", "siblings": ["C:salt"]}]


def test_report_groups_eligible_predictions_by_rule_and_tier():
    rules = [
        {"rule_id": "transfer", "evidence_tier": "transfer"},
        {"rule_id": "free", "evidence_tier": "treatment_free"},
    ]
    predictions = {
        "transfer": {
            ("C:same-target", "D:known"),
            ("C:salt", "D:known"),
            ("C:treater", "D:known"),
        },
        "free": {("C:other", "D:known"), ("C:other", "D:untreated")},
    }

    report = build_report(
        rules=rules,
        predictions=predictions,
        training_labels={("C:treater", "D:known")},
        fetch=_fake_fetch,
    )

    by_rule = {item["rule_id"]: item for item in report["by_rule"]}
    assert by_rule["transfer"]["eligible_predictions"] == 2
    assert by_rule["transfer"]["classes"]["shared_target"] == 1
    assert by_rule["transfer"]["classes"]["chemical_neighbor"] == 1
    assert report["by_tier"]["treatment_free"] == {
        "no_known_treater": 1,
        "shared_target": 0,
        "chemical_neighbor": 0,
        "other": 1,
    }
