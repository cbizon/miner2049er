from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from functools import cache
from typing import Any

from miner2049er.gandalf_runtime import BIOLINK_VERSION, local_toolkit

FULL_EXPANSION = "trapi_subpredicate_expansion"
FILTERED_EXPANSION = "trapi_subpredicate_expansion_with_exclusions"
TREATMENT_EVIDENCE_ROOT = "biolink:treats_or_applied_or_studied_to_treat"
TOKEN_PATTERN = re.compile(r"[^A-Za-z0-9_]")
# What a rule's premises know about the pair it predicts:
# same_pair: a treatment-evidence edge joins the predicted chemical and disease.
# transfer: treatment-evidence edges appear only elsewhere, e.g. another drug
#   treating the same disease, so known treatments carry over by mechanism.
# treatment_free: no treatment-evidence edge in the pattern.
EVIDENCE_TIERS = ("same_pair", "transfer", "treatment_free")


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


@cache
def predicate_descendants(predicate: str) -> tuple[str, ...]:
    if not predicate.startswith("biolink:"):
        raise ValueError(f"Biolink predicates must use the biolink: prefix: {predicate}")
    descendants = local_toolkit().get_descendants(
        predicate,
        formatted=True,
        reflexive=True,
    )
    if predicate not in descendants:
        raise ValueError(f"Unknown Biolink predicate in version {BIOLINK_VERSION}: {predicate}")
    return _ordered_unique(descendants)


def predicate_closure(predicates: Iterable[str]) -> tuple[str, ...]:
    authored = _ordered_unique(predicates)
    if not authored:
        raise ValueError("At least one predicate is required")
    return _ordered_unique(
        descendant
        for predicate in authored
        for descendant in predicate_descendants(predicate)
    )


@cache
def treatment_evidence_predicates() -> frozenset[str]:
    return frozenset(predicate_descendants(TREATMENT_EVIDENCE_ROOT))


def rule_treatment_predicates(rule: dict[str, Any]) -> frozenset[str]:
    effective_predicates = {
        predicate
        for edge in rule["graph_pattern"]["edges"]
        for predicate in edge["predicate_expansion"]["expanded_predicates"]
    }
    return frozenset(effective_predicates & treatment_evidence_predicates())


def rule_evidence_tier(rule: dict[str, Any]) -> str:
    pattern = rule["graph_pattern"]
    head = pattern["head"]
    node_ids = {node["id"] for node in pattern["nodes"]}
    missing = {head["subject"], head["object"]} - node_ids
    if missing:
        raise ValueError(
            f"Rule {rule['rule_id']} head references unknown nodes: {sorted(missing)}"
        )
    if head["subject"] == head["object"]:
        raise ValueError(f"Rule {rule['rule_id']} head subject and object must differ")
    head_nodes = {head["subject"], head["object"]}
    treatment = treatment_evidence_predicates()
    treatment_edges = [
        edge
        for edge in pattern["edges"]
        if set(edge["predicate_expansion"]["expanded_predicates"]) & treatment
    ]
    if not treatment_edges:
        return "treatment_free"
    if any({edge["subject"], edge["object"]} == head_nodes for edge in treatment_edges):
        return "same_pair"
    return "transfer"


def neo4j_relationship_type(predicate: str) -> str:
    return TOKEN_PATTERN.sub("_", predicate.removeprefix("biolink:")).upper()


def predicate_expansion_record(
    predicates: Iterable[str],
    excluded_predicates: Iterable[str] = (),
    exclusion_rationale: str | None = None,
) -> dict[str, Any]:
    authored = _ordered_unique(predicates)
    closure = predicate_closure(authored)
    excluded = _ordered_unique(excluded_predicates)
    unknown_exclusions = set(excluded) - set(closure)
    if unknown_exclusions:
        raise ValueError(
            "Excluded predicates are not descendants of the authored predicates: "
            f"{sorted(unknown_exclusions)}"
        )
    authored_exclusions = set(excluded) & set(authored)
    if authored_exclusions:
        raise ValueError(
            f"Authored predicates cannot be excluded: {sorted(authored_exclusions)}"
        )
    if excluded and not (exclusion_rationale or "").strip():
        raise ValueError("Predicate exclusions require a rationale")
    if not excluded and exclusion_rationale is not None:
        raise ValueError("An exclusion rationale is allowed only with exclusions")
    return {
        "policy": "biolink_descendants",
        "biolink_version": BIOLINK_VERSION,
        "expanded_predicates": sorted(set(closure) - set(excluded)),
        "excluded_predicates": list(excluded),
        "exclusion_rationale": exclusion_rationale,
    }


def validate_rule_biolink_semantics(
    rule: dict[str, Any],
    expected_biolink_version: str,
    target_predicates: Iterable[str],
) -> None:
    if expected_biolink_version != BIOLINK_VERSION:
        raise ValueError(
            f"Benchmark requires Biolink {expected_biolink_version}, but the local "
            f"runtime is pinned to {BIOLINK_VERSION}"
        )
    has_exclusions = False
    effective_predicates: set[str] = set()
    for edge in rule["graph_pattern"]["edges"]:
        expansion = edge["predicate_expansion"]
        edge_id = edge["id"]
        if expansion["biolink_version"] != expected_biolink_version:
            raise ValueError(
                f"Rule {rule['rule_id']} edge {edge_id} uses Biolink "
                f"{expansion['biolink_version']}, expected {expected_biolink_version}"
            )
        expected = predicate_expansion_record(
            edge["predicates"],
            expansion["excluded_predicates"],
            expansion["exclusion_rationale"],
        )
        for field in (
            "policy",
            "expanded_predicates",
            "excluded_predicates",
            "exclusion_rationale",
        ):
            if expansion[field] != expected[field]:
                raise ValueError(
                    f"Rule {rule['rule_id']} edge {edge_id} has incorrect "
                    f"predicate expansion field {field}"
                )
        has_exclusions = has_exclusions or bool(expansion["excluded_predicates"])
        effective_predicates.update(expansion["expanded_predicates"])

    expected_semantics = FILTERED_EXPANSION if has_exclusions else FULL_EXPANSION
    execution = rule["execution"]["predicate_expansion"]
    if execution["semantics"] != expected_semantics:
        raise ValueError(
            f"Rule {rule['rule_id']} must declare {expected_semantics} statistics"
        )
    if execution["biolink_version"] != expected_biolink_version:
        raise ValueError(
            f"Rule {rule['rule_id']} execution uses Biolink "
            f"{execution['biolink_version']}, expected {expected_biolink_version}"
        )
    if has_exclusions and rule["execution"]["trapi"]["expressibility"] == "full":
        raise ValueError(
            f"Rule {rule['rule_id']} excludes predicate descendants and cannot be "
            "fully expressed by an unfiltered TRAPI predicate"
        )
    configured_targets = set(target_predicates)
    missing_targets = configured_targets - treatment_evidence_predicates()
    if missing_targets:
        raise ValueError(
            "Benchmark target predicates are outside the treatment-evidence closure: "
            f"{sorted(missing_targets)}"
        )
    treatment_predicates = effective_predicates & treatment_evidence_predicates()
    if bool(treatment_predicates) != rule["uses_treatment_edges"]:
        required_value = str(bool(treatment_predicates)).lower()
        raise ValueError(
            f"Rule {rule['rule_id']} expands to treatment-evidence predicates "
            f"{sorted(treatment_predicates)} and must set uses_treatment_edges "
            f"{required_value}"
        )
    # Rules recorded before head marking carry neither field; the schema
    # requires them together.
    if "head" in rule["graph_pattern"]:
        expected_tier = rule_evidence_tier(rule)
        if rule["evidence_tier"] != expected_tier:
            raise ValueError(
                f"Rule {rule['rule_id']} has evidence_tier "
                f"{rule['evidence_tier']} but its pattern is {expected_tier}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Expand authored Biolink predicates to the descendant set used by TRAPI"
        )
    )
    parser.add_argument("predicate", nargs="+")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Exclude one descendant predicate; may be repeated",
    )
    parser.add_argument("--exclusion-rationale")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    expansion = predicate_expansion_record(
        args.predicate,
        args.exclude,
        args.exclusion_rationale,
    )
    output = {
        "authored_predicates": sorted(set(args.predicate)),
        **expansion,
        "neo4j_relationship_types": [
            neo4j_relationship_type(predicate)
            for predicate in expansion["expanded_predicates"]
        ],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
