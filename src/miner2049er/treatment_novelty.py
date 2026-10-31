"""Break down rule predictions by how close each one is to a known treatment.

A rule can score well by predicting near-copies of training treatments: another
drug on the same target, or a salt or subclass of a known treater. This report
classifies every feedback-eligible prediction (chemical, disease) against the
disease's training treaters, so a reviewer can see what share of each rule's
output is cheap transfer and what share is new. It reads only public training
labels and the training graph, never hidden labels.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from neo4j import READ_ACCESS, GraphDatabase, Query

from miner2049er.biolink_semantics import neo4j_relationship_type, predicate_closure
from miner2049er.partitioning import Pair, load_label_pairs
from miner2049er.rule_set_selector import (
    DEFAULT_PUBLIC_BENCHMARK_ROOT,
    _load_prediction_sets,
)
from miner2049er.schema_validation import read_jsonl

# Checked in order; a prediction takes the first class that applies.
NOVELTY_CLASSES = (
    "no_known_treater",
    "shared_target",
    "chemical_neighbor",
    "other",
)
TARGET_PREDICATE = "biolink:directly_physically_interacts_with"
HIERARCHY_PREDICATE = "biolink:subclass_of"

Fetch = Callable[[str, dict[str, Any]], Iterable[Mapping[str, Any]]]


def classify_prediction(
    pair: Pair,
    *,
    treaters_by_disease: Mapping[str, set[str]],
    targets: Mapping[str, set[str]],
    neighbors: Mapping[str, set[str]],
) -> str:
    chemical, disease = pair
    treaters = treaters_by_disease.get(disease, set()) - {chemical}
    if not treaters:
        return "no_known_treater"
    chemical_targets = targets.get(chemical, set())
    if any(chemical_targets & targets.get(treater, set()) for treater in treaters):
        return "shared_target"
    if neighbors.get(chemical, set()) & treaters:
        return "chemical_neighbor"
    return "other"


def _relationship_types(predicate: str) -> str:
    return "|".join(
        sorted({neo4j_relationship_type(item) for item in predicate_closure([predicate])})
    )


def fetch_targets(fetch: Fetch, chemicals: set[str]) -> dict[str, set[str]]:
    cypher = (
        f"MATCH (c:ChemicalEntity)-[e:{_relationship_types(TARGET_PREDICATE)}]-"
        "(g:Gene) WHERE c.id IN $ids AND e.predicate IN $predicates "
        "RETURN DISTINCT c.id AS chemical, g.id AS gene"
    )
    targets: dict[str, set[str]] = {}
    for record in fetch(
        cypher,
        {"ids": sorted(chemicals), "predicates": list(predicate_closure([TARGET_PREDICATE]))},
    ):
        targets.setdefault(record["chemical"], set()).add(record["gene"])
    return targets


def fetch_neighbors(fetch: Fetch, chemicals: set[str]) -> dict[str, set[str]]:
    """Chemicals one subclass_of step away, or sharing a direct parent."""
    relationship = _relationship_types(HIERARCHY_PREDICATE)
    cypher = (
        f"MATCH (c:ChemicalEntity)-[e:{relationship}]->(p:ChemicalEntity) "
        "WHERE c.id IN $ids AND e.predicate IN $predicates "
        "OPTIONAL MATCH (s:ChemicalEntity)-[f:"
        f"{relationship}]->(p) WHERE f.predicate IN $predicates AND s.id IN $ids "
        "RETURN c.id AS chemical, p.id AS parent, collect(DISTINCT s.id) AS siblings"
    )
    neighbors: dict[str, set[str]] = {}
    for record in fetch(
        cypher,
        {"ids": sorted(chemicals), "predicates": list(predicate_closure([HIERARCHY_PREDICATE]))},
    ):
        chemical, parent = record["chemical"], record["parent"]
        related = {parent, *record["siblings"]} - {chemical}
        neighbors.setdefault(chemical, set()).update(related)
        neighbors.setdefault(parent, set()).add(chemical)
    return neighbors


def build_report(
    *,
    rules: list[dict[str, Any]],
    predictions: Mapping[str, set[Pair]],
    training_labels: set[Pair],
    fetch: Fetch,
) -> dict[str, Any]:
    treaters_by_disease: dict[str, set[str]] = {}
    for chemical, disease in training_labels:
        treaters_by_disease.setdefault(disease, set()).add(chemical)
    eligible = {rule_id: pairs - training_labels for rule_id, pairs in predictions.items()}
    chemicals = {chemical for pairs in eligible.values() for chemical, _ in pairs}
    chemicals |= {chemical for chemical, _ in training_labels}
    targets = fetch_targets(fetch, chemicals)
    neighbors = fetch_neighbors(fetch, chemicals)

    by_rule = []
    by_tier: dict[str, Counter[str]] = {}
    for rule in rules:
        counts = Counter(
            classify_prediction(
                pair,
                treaters_by_disease=treaters_by_disease,
                targets=targets,
                neighbors=neighbors,
            )
            for pair in eligible.get(rule["rule_id"], set())
        )
        tier = rule.get("evidence_tier", "untiered")
        by_tier.setdefault(tier, Counter()).update(counts)
        by_rule.append(
            {
                "rule_id": rule["rule_id"],
                "evidence_tier": tier,
                "eligible_predictions": sum(counts.values()),
                "classes": {name: counts[name] for name in NOVELTY_CLASSES},
            }
        )
    return {
        "classes": list(NOVELTY_CLASSES),
        "by_tier": {
            tier: {name: counts[name] for name in NOVELTY_CLASSES}
            for tier, counts in sorted(by_tier.items())
        },
        "by_rule": by_rule,
    }


def neo4j_fetch(uri: str, user: str, password: str, timeout_seconds: float) -> Fetch:
    def fetch(cypher: str, parameters: dict[str, Any]) -> Iterable[Mapping[str, Any]]:
        with GraphDatabase.driver(uri, auth=(user, password)) as driver, driver.session(
            database="neo4j",
            default_access_mode=READ_ACCESS,
        ) as session:
            result = session.run(Query(cypher, timeout=timeout_seconds), parameters)
            return [record.data() for record in result]

    return fetch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Classify each rule's feedback-eligible predictions by closeness to "
            "known training treatments"
        )
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--public-benchmark-root",
        type=Path,
        default=DEFAULT_PUBLIC_BENCHMARK_ROOT,
    )
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    required = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError(f"Missing Neo4j service variables: {', '.join(missing)}")
    manifest = json.loads((args.run_dir / "run.json").read_text(encoding="utf-8"))
    rules = list(
        read_jsonl(args.run_dir / manifest["artifacts"]["rules"], "rule.schema.json")
    )
    predictions = _load_prediction_sets(
        args.run_dir / manifest["artifacts"]["predictions"],
        run_id=manifest["run_id"],
        rule_ids={rule["rule_id"] for rule in rules},
    )
    training_labels = load_label_pairs(
        args.public_benchmark_root / manifest["split_id"] / "training-labels.jsonl"
    )
    report = build_report(
        rules=rules,
        predictions=predictions,
        training_labels=training_labels,
        fetch=neo4j_fetch(
            os.environ["NEO4J_URI"],
            os.environ["NEO4J_USER"],
            os.environ["NEO4J_PASSWORD"],
            args.timeout_seconds,
        ),
    )
    text = json.dumps({"run_id": manifest["run_id"], **report}, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
