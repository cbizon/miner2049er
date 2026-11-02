import pytest

from miner2049er.biolink_semantics import (
    BIOLINK_VERSION,
    FULL_EXPANSION,
    predicate_expansion_record,
)
from miner2049er.schema_validation import validate_document
from tests.benchmark_examples import neo4j_artifact


def test_complete_rule_contract_validates():
    rule = {
        "schema_version": "1.0",
        "run_id": "run-1",
        "round_id": "round-0001",
        "rule_id": "RULE-1",
        "family_id": "direct-causal-target",
        "parent_rule_id": None,
        "name": "Direct causal target correction",
        "status": "candidate",
        "plain_language_rule": (
            "A drug inhibits a gene whose increased activity causes the disease."
        ),
        "hypothesis": "Reducing the causal gene activity should improve the disease.",
        "variant_parameters": {"maximum_target_degree": 20},
        "graph_pattern": {
            "nodes": [
                {
                    "id": "drug",
                    "role": "predicted treatment",
                    "categories": ["biolink:Drug"],
                    "explanation": "The candidate drug.",
                },
                {
                    "id": "disease",
                    "role": "target disease",
                    "categories": ["biolink:Disease"],
                    "explanation": "The disease predicted to be treated.",
                },
            ],
            "edges": [
                {
                    "id": "target",
                    "subject": "drug",
                    "object": "disease",
                    "predicates": ["biolink:related_to"],
                    "predicate_expansion": predicate_expansion_record(
                        ["biolink:related_to"]
                    ),
                    "direction": "forward",
                    "explanation": "Placeholder test edge.",
                }
            ],
            "constraints": [
                {
                    "id": "degree",
                    "kind": "degree",
                    "expression": "target degree <= 20",
                    "explanation": "Excludes nonspecific drugs.",
                }
            ],
        },
        "derived_features": [],
        "mechanism": {
            "score": "high",
            "rationale": "The intervention reverses a directional causal mechanism.",
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
                "expressibility": "partial",
                "query": None,
                "limitations": "The degree constraint requires post-processing.",
            },
        },
        "limitations": ["Direction depends on source qualifier quality."],
    }

    validate_document(rule, "rule.schema.json")


def test_neo4j_artifact_contract_validates():
    validate_document(neo4j_artifact(), "neo4j-artifact.schema.json")


def test_structured_research_event_contract_validates():
    validate_document(
        {
            "schema_version": "1.0",
            "run_id": "run-1",
            "round_id": "round-0001",
            "sequence": 1,
            "timestamp": "2026-08-20T12:00:00Z",
            "event_type": "hypothesis",
            "rule_id": None,
            "summary": "Pathway convergence may improve specificity.",
            "details": {
                "mechanism_family": "pathway convergence",
                "rationale": "Independent pathway support may suppress noisy genes.",
                "proposed_test": "Compare direct and pathway-mediated variants.",
                "variables_to_explore": ["pathway degree", "source count"],
                "success_criterion": "Higher precision with useful volume.",
                "next_action": "Profile each path leg.",
            },
        },
        "research-event.schema.json",
    )


def test_structured_research_event_rejects_missing_required_details():
    with pytest.raises(ValueError, match="mechanism_family"):
        validate_document(
            {
                "schema_version": "1.0",
                "run_id": "run-1",
                "round_id": "round-0001",
                "sequence": 1,
                "timestamp": "2026-08-20T12:00:00Z",
                "event_type": "hypothesis",
                "rule_id": None,
                "summary": "Incomplete hypothesis.",
                "details": {},
            },
            "research-event.schema.json",
        )


PINNED_PREDICTION_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://renci.org/miner2049er/schemas/prediction.schema.json",
    "title": "Rule prediction",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "run_id", "round_id", "rule_id", "subject_id", "object_id"],
    "properties": {
        "schema_version": {"const": "1.0"},
        "run_id": {"type": "string", "minLength": 1},
        "round_id": {"type": "string", "pattern": "^round-[0-9]{4}$"},
        "rule_id": {"type": "string", "minLength": 1},
        "subject_id": {"type": "string", "minLength": 1},
        "object_id": {"type": "string", "minLength": 1},
        "support_count": {"type": "integer", "minimum": 0},
        "evidence_bindings": {"type": "array", "items": {"type": "string"}},
    },
}


def test_prediction_schema_matches_the_hand_written_check():
    """If this fails, update prediction_is_valid to match the schema change."""
    from miner2049er.schema_validation import load_schema

    assert load_schema("prediction.schema.json") == PINNED_PREDICTION_SCHEMA


def test_fast_prediction_check_agrees_with_jsonschema():
    from jsonschema import Draft202012Validator

    from miner2049er.schema_validation import prediction_is_valid

    validator = Draft202012Validator(PINNED_PREDICTION_SCHEMA)
    base = {
        "schema_version": "1.0",
        "run_id": "r",
        "round_id": "round-0001",
        "rule_id": "rule",
        "subject_id": "CHEBI:1",
        "object_id": "MONDO:1",
    }
    cases = [
        base,
        {**base, "support_count": 0, "evidence_bindings": ["e1"]},
        {**base, "support_count": -1},
        {**base, "support_count": True},
        {**base, "support_count": 1.5},
        {**base, "evidence_bindings": [1]},
        {**base, "evidence_bindings": "e1"},
        {**base, "round_id": "round-1"},
        {**base, "round_id": "x-round-0001-y"},
        {**base, "schema_version": "2.0"},
        {**base, "subject_id": ""},
        {**base, "extra": 1},
        {key: value for key, value in base.items() if key != "object_id"},
        [],
    ]
    for case in cases:
        assert prediction_is_valid(case) == validator.is_valid(case), case
