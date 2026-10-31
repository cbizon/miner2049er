import pytest

from miner2049er.biolink_semantics import (
    BIOLINK_VERSION,
    FILTERED_EXPANSION,
    predicate_closure,
    predicate_expansion_record,
    rule_evidence_tier,
    rule_treatment_predicates,
    validate_rule_biolink_semantics,
)
from miner2049er.schema_validation import validate_document
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


def _tiered_rule(edges: list[tuple[str, str, str]]) -> dict:
    """Benchmark rule over chemical, disease, a second drug and a gene."""
    rule = benchmark_rule()
    pattern = rule["graph_pattern"]
    pattern["head"] = {"subject": "chemical", "object": "disease"}
    pattern["nodes"].extend(
        [
            {
                "id": "known_drug",
                "role": "known treatment",
                "categories": ["biolink:ChemicalEntity"],
                "explanation": "A drug already known to treat the disease.",
            },
            {
                "id": "gene",
                "role": "shared target",
                "categories": ["biolink:Gene"],
                "explanation": "The target both drugs affect.",
            },
        ]
    )
    pattern["edges"] = [
        {
            "id": f"e{index}",
            "subject": subject,
            "object": object_,
            "predicates": [predicate],
            "predicate_expansion": predicate_expansion_record([predicate]),
            "direction": "forward",
            "explanation": "Test edge.",
        }
        for index, (subject, predicate, object_) in enumerate(edges)
    ]
    rule["uses_treatment_edges"] = bool(rule_treatment_predicates(rule))
    rule["evidence_tier"] = rule_evidence_tier(rule)
    return rule


SHARED_TARGET = [
    ("chemical", "biolink:directly_physically_interacts_with", "gene"),
    ("known_drug", "biolink:directly_physically_interacts_with", "gene"),
]


@pytest.mark.parametrize(
    ("edges", "tier"),
    (
        (SHARED_TARGET, "treatment_free"),
        (
            [*SHARED_TARGET, ("known_drug", "biolink:treats", "disease")],
            "transfer",
        ),
        (
            [*SHARED_TARGET, ("chemical", "biolink:studied_to_treat", "disease")],
            "same_pair",
        ),
    ),
)
def test_evidence_tier_follows_where_treatment_edges_sit(edges, tier):
    rule = _tiered_rule(edges)

    assert rule["evidence_tier"] == tier
    validate_document(rule, "rule.schema.json")
    validate_rule_biolink_semantics(rule, BIOLINK_VERSION, TARGET_PREDICATES)


def test_same_pair_tier_wins_over_transfer():
    rule = _tiered_rule(
        [
            *SHARED_TARGET,
            ("known_drug", "biolink:treats", "disease"),
            ("chemical", "biolink:studied_to_treat", "disease"),
        ]
    )

    assert rule["evidence_tier"] == "same_pair"


def test_rule_validation_rejects_a_misstated_evidence_tier():
    rule = _tiered_rule([*SHARED_TARGET, ("known_drug", "biolink:treats", "disease")])
    rule["evidence_tier"] = "treatment_free"

    with pytest.raises(ValueError, match="pattern is transfer"):
        validate_rule_biolink_semantics(rule, BIOLINK_VERSION, TARGET_PREDICATES)


def test_evidence_tier_rejects_head_on_unknown_node():
    rule = _tiered_rule(SHARED_TARGET)
    rule["graph_pattern"]["head"]["object"] = "missing"

    with pytest.raises(ValueError, match="head references unknown nodes"):
        rule_evidence_tier(rule)


def test_rule_schema_requires_head_and_tier_together():
    rule = _tiered_rule(SHARED_TARGET)
    del rule["evidence_tier"]
    with pytest.raises(ValueError):
        validate_document(rule, "rule.schema.json")

    legacy = benchmark_rule()
    legacy["evidence_tier"] = "same_pair"
    with pytest.raises(ValueError):
        validate_document(legacy, "rule.schema.json")


def test_rules_validate_against_their_recorded_biolink_version():
    legacy = benchmark_rule()
    edge = legacy["graph_pattern"]["edges"][0]
    edge["predicates"] = ["biolink:affects"]
    edge["predicate_expansion"] = predicate_expansion_record(
        ["biolink:affects"], version="4.3.2"
    )
    legacy["execution"]["predicate_expansion"]["biolink_version"] = "4.3.2"

    assert "biolink:affects_response_to" in edge["predicate_expansion"][
        "expanded_predicates"
    ]
    validate_rule_biolink_semantics(legacy, "4.3.2", TARGET_PREDICATES)
    with pytest.raises(ValueError, match="uses Biolink 4.3.2, expected 4.4.4"):
        validate_rule_biolink_semantics(legacy, BIOLINK_VERSION, TARGET_PREDICATES)
