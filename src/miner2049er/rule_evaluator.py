from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase, Query
from neo4j.exceptions import Neo4jError

from miner2049er.rule_descriptions import apply_rule_descriptions
from miner2049er.rules import Rule, f_beta, load_rules, pareto_rule_ids
from miner2049er.settings import ROOT
from miner2049er.target_inventory import (
    BLIND_SOURCE,
    VALIDATION_SOURCE,
    collect_inventory,
    relationship_union,
)

PARETO_ELIGIBLE_LIBRARY_STATUSES = {"active", "baseline", "candidate", "retained"}


def render_rule_cypher(rule: Rule, target_union: str) -> str:
    return rule.cypher.replace("__TARGET_RELATIONSHIPS__", target_union)


def scoring_query(rule: Rule, target_union: str) -> str:
    rule_cypher = render_rule_cypher(rule, target_union)
    return f"""
    CALL () {{
      {rule_cypher}
    }}
    WITH DISTINCT subject_id, object_id
    WHERE subject_id IS NOT NULL AND object_id IS NOT NULL
    MATCH (subject:Entity {{id: subject_id}})
    MATCH (object:Entity {{id: object_id}})
    OPTIONAL MATCH (subject)-[target:{target_union}]->(object)
    WITH subject, object,
         reduce(
           raw_sources = [],
           relation IN collect(target) |
           raw_sources + coalesce(relation.primary_knowledge_sources, [])
         ) AS raw_sources
    WITH subject, object,
         reduce(
           sources = [],
           source IN raw_sources |
           CASE WHEN source IN sources THEN sources ELSE sources + source END
         ) AS sources
    RETURN count(*) AS candidate_pairs,
           sum(
             CASE
               WHEN size(sources) = 1 AND sources[0] = $validation_source THEN 1
               ELSE 0
             END
           ) AS validation_hits,
           sum(
             CASE
               WHEN size(sources) > 0
                    AND NOT (size(sources) = 1 AND sources[0] = $validation_source)
                    AND NOT (size(sources) = 1 AND sources[0] = $blind_source)
               THEN 1
               ELSE 0
             END
           ) AS training_hits,
           sum(
             CASE
               WHEN EXISTS {{
                 MATCH (subject)-[:CONTRAINDICATED_IN]->(object)
               }}
               THEN 1
               ELSE 0
             END
           ) AS contraindicated_pairs
    """


def evaluate_rule(
    driver,
    rule: Rule,
    visible_total: int,
    validation_total: int,
    target_union: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {
        "id": rule.id,
        "name": rule.name,
        "iteration": rule.iteration,
        "parent_rule": rule.parent_rule,
        "library_status": rule.status,
        "status": "running",
        "hypothesis": rule.hypothesis,
        "body": rule.body,
        "description": rule.description,
        "criteria": list(rule.criteria),
        "mechanism_score": rule.mechanism_score,
        "mechanism_rationale": rule.mechanism_rationale,
        "uses_treatment_edges": rule.uses_treatment_edges,
        "trapi_expressibility": rule.trapi_expressibility,
        "trapi_notes": rule.trapi_notes,
        "trapi_template": rule.trapi_template,
        "cypher": render_rule_cypher(rule, target_union),
    }
    try:
        with driver.session(database="neo4j") as session:
            record = session.run(
                Query(scoring_query(rule, target_union), timeout=timeout_seconds),
                validation_source=VALIDATION_SOURCE,
                blind_source=BLIND_SOURCE,
            ).single(strict=True)
        counts = record.data()
        candidate_pairs = counts["candidate_pairs"]
        training_hits = counts["training_hits"]
        validation_hits = counts["validation_hits"]
        validation_candidates = candidate_pairs - training_hits
        validation_precision = (
            validation_hits / validation_candidates if validation_candidates else 0.0
        )
        validation_recall = validation_hits / validation_total if validation_total else 0.0
        visible_hits = training_hits + validation_hits
        visible_precision = visible_hits / candidate_pairs if candidate_pairs else 0.0
        visible_recall = visible_hits / visible_total if visible_total else 0.0
        result["status"] = "completed"
        result["counts"] = {
            **counts,
            "unresolved_or_blind_pairs": validation_candidates - validation_hits,
        }
        result["metrics"] = {
            "visible_target_precision_lower_bound": visible_precision,
            "visible_target_recall": visible_recall,
            "visible_target_f0_5": f_beta(visible_precision, visible_recall, beta=0.5),
            "validation_precision_lower_bound": validation_precision,
            "validation_recall": validation_recall,
            "validation_f0_5": f_beta(validation_precision, validation_recall, beta=0.5),
        }
    except (Neo4jError, RuntimeError, ValueError) as error:
        result["status"] = "failed"
        result["error"] = f"{type(error).__name__}: {error}"
    result["runtime_seconds"] = time.monotonic() - started
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate hypothesis-guided treats rules")
    parser.add_argument(
        "--rules",
        type=Path,
        default=ROOT / "rules" / "treats-rules.toml",
    )
    parser.add_argument("--rule", action="append", dest="rule_ids")
    parser.add_argument("--neo4j-uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument(
        "--neo4j-password",
        default=os.environ.get("NEO4J_PASSWORD", "translator-local"),
    )
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results" / "runs",
    )
    return parser.parse_args()


def update_rule_library(
    path: Path,
    inventory: dict[str, Any],
    current_results: list[dict[str, Any]],
    rule_catalog: list[Rule] | None = None,
) -> None:
    by_id: dict[str, dict[str, Any]] = {}
    if path.is_file():
        previous = json.loads(path.read_text(encoding="utf-8"))
        by_id.update({result["id"]: result for result in previous.get("results", [])})
    by_id.update({result["id"]: result for result in current_results})
    results = sorted(by_id.values(), key=lambda result: result["id"])

    if rule_catalog:
        target_union = relationship_union(inventory["neo4j_relationship_types"])
        rules_by_id = {rule.id: rule for rule in rule_catalog}
        for result in results:
            rule = rules_by_id.get(result["id"])
            if rule is None:
                continue
            result.update(
                {
                    "library_status": rule.status,
                    "hypothesis": rule.hypothesis,
                    "body": rule.body,
                    "description": rule.description,
                    "criteria": list(rule.criteria),
                    "mechanism_score": rule.mechanism_score,
                    "mechanism_rationale": rule.mechanism_rationale,
                    "uses_treatment_edges": rule.uses_treatment_edges,
                    "trapi_expressibility": rule.trapi_expressibility,
                    "trapi_notes": rule.trapi_notes,
                    "trapi_template": rule.trapi_template,
                    "cypher": render_rule_cypher(rule, target_union),
                }
            )

    eligible_results = [
        result
        for result in results
        if result.get("library_status") in PARETO_ELIGIBLE_LIBRARY_STATUSES
    ]
    treatment_free_results = [
        result
        for result in eligible_results
        if not result.get("uses_treatment_edges", False)
    ]
    validation_front = pareto_rule_ids(eligible_results)
    visible_front = pareto_rule_ids(
        eligible_results,
        "visible_target_precision_lower_bound",
        "visible_target_recall",
    )
    treatment_free_validation_front = pareto_rule_ids(treatment_free_results)
    treatment_free_visible_front = pareto_rule_ids(
        treatment_free_results,
        "visible_target_precision_lower_bound",
        "visible_target_recall",
    )
    mechanism_fronts: dict[str, set[str]] = {}
    for mechanism_score in ("low", "medium", "high"):
        mechanism_results = [
            result
            for result in eligible_results
            if result.get("mechanism_score") == mechanism_score
        ]
        mechanism_fronts[mechanism_score] = pareto_rule_ids(
            mechanism_results,
            "visible_target_precision_lower_bound",
            "visible_target_recall",
        )

    for result in results:
        result["pareto_validation"] = result["id"] in validation_front
        result["pareto_visible"] = result["id"] in visible_front
        result["pareto_validation_without_treatment_edges"] = (
            result["id"] in treatment_free_validation_front
        )
        result["pareto_visible_without_treatment_edges"] = (
            result["id"] in treatment_free_visible_front
        )
        result["pareto_visible_within_mechanism"] = (
            result["id"] in mechanism_fronts.get(result.get("mechanism_score"), set())
        )

    library = {
        "updated_at": datetime.now(UTC).isoformat(),
        "target_inventory": inventory,
        "results": results,
    }
    apply_rule_descriptions(library)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(library, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    selected_ids = set(args.rule_ids) if args.rule_ids else None
    rules = load_rules(args.rules, selected_ids)
    rule_catalog = load_rules(args.rules, include_inactive=True)
    inventory = collect_inventory(args.neo4j_uri, args.neo4j_password)
    visible_total = (
        inventory["counts"]["training_pairs"]
        + inventory["counts"]["validation_pairs"]
    )
    validation_total = inventory["counts"]["validation_pairs"]
    target_union = relationship_union(inventory["neo4j_relationship_types"])

    with GraphDatabase.driver(
        args.neo4j_uri,
        auth=("neo4j", args.neo4j_password),
    ) as driver:
        results = []
        for rule in rules:
            print(f"Evaluating {rule.id}: {rule.name}", flush=True)
            result = evaluate_rule(
                driver,
                rule,
                visible_total,
                validation_total,
                target_union,
                args.timeout_seconds,
            )
            results.append(result)
            print(json.dumps(result, indent=2), flush=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "rules_file": str(args.rules),
        "target_inventory": inventory,
        "results": results,
    }
    report_path = run_dir / "summary.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    latest_path = ROOT / "results" / "latest-rule-evaluation.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    update_rule_library(
        ROOT / "results" / "rule-library.json",
        inventory,
        results,
        rule_catalog,
    )
    print(f"Wrote {report_path}")
