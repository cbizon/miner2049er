import pytest

from miner2049er.biolink_semantics import (
    BIOLINK_VERSION,
    FILTERED_EXPANSION,
    predicate_closure,
    predicate_expansion_record,
    validate_rule_biolink_semantics,
)
from tests.benchmark_examples import benchmark_rule

TARGET_PREDICATES = (
    "biolink:treats",
    "biolink:ameliorates_condition",
    "biolink:preventative_for_condition",
)


def test_parent_predicate_closure_includes_treatment_descendants():
    closure = predicate_closure(["biolink:affects"])

    assert "biolink:regulates" in closure
    assert "biolink:ameliorates_condition" in closure


def test_rule_validation_rejects_an_incomplete_recorded_closure():
    rule = benchmark_rule()
    rule["graph_pattern"]["edges"][0]["predicate_expansion"][
        "expanded_predicates"
    ].remove("biolink:treats")

    with pytest.raises(ValueError, match="incorrect predicate expansion"):
        validate_rule_biolink_semantics(
            rule,
            BIOLINK_VERSION,
            TARGET_PREDICATES,
        )


def test_rule_validation_detects_treatment_evidence_after_expansion():
    rule = benchmark_rule()
    rule["uses_treatment_edges"] = False

    with pytest.raises(ValueError, match="must set uses_treatment_edges true"):
        validate_rule_biolink_semantics(
            rule,
            BIOLINK_VERSION,
            TARGET_PREDICATES,
        )


@pytest.mark.parametrize(
    "predicate",
    (
        "biolink:applied_to_treat",
        "biolink:studied_to_treat",
        "biolink:in_clinical_trials_for",
    ),
)
def test_treatment_evidence_family_requires_treatment_flag(predicate: str):
    rule = benchmark_rule()
    edge = rule["graph_pattern"]["edges"][0]
    edge["predicates"] = [predicate]
    edge["predicate_expansion"] = predicate_expansion_record([predicate])
    rule["uses_treatment_edges"] = False

    with pytest.raises(ValueError, match="must set uses_treatment_edges true"):
        validate_rule_biolink_semantics(
            rule,
            BIOLINK_VERSION,
            TARGET_PREDICATES,
        )


def test_non_treatment_rule_cannot_claim_treatment_edges():
    rule = benchmark_rule()
    edge = rule["graph_pattern"]["edges"][0]
    edge["predicates"] = ["biolink:subclass_of"]
    edge["predicate_expansion"] = predicate_expansion_record(["biolink:subclass_of"])
    rule["uses_treatment_edges"] = True

    with pytest.raises(ValueError, match="must set uses_treatment_edges false"):
        validate_rule_biolink_semantics(
            rule,
            BIOLINK_VERSION,
            TARGET_PREDICATES,
        )


def test_explicit_descendant_exclusion_requires_partial_trapi_execution():
    rule = benchmark_rule()
    edge = rule["graph_pattern"]["edges"][0]
    edge["predicates"] = ["biolink:affects"]
    edge["predicate_expansion"] = predicate_expansion_record(
        ["biolink:affects"],
        ["biolink:ameliorates_condition"],
        "Treatment assertions would make the body circular.",
    )
    rule["uses_treatment_edges"] = False
    rule["execution"]["predicate_expansion"]["semantics"] = FILTERED_EXPANSION
    rule["execution"]["trapi"]["expressibility"] = "partial"

    validate_rule_biolink_semantics(
        rule,
        BIOLINK_VERSION,
        TARGET_PREDICATES,
    )

    rule["execution"]["trapi"]["expressibility"] = "full"
    with pytest.raises(ValueError, match="cannot be fully expressed"):
        validate_rule_biolink_semantics(
            rule,
            BIOLINK_VERSION,
            TARGET_PREDICATES,
        )
