from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase, Query

from miner2049er.rule_evaluator import render_rule_cypher
from miner2049er.rules import Rule, load_rules
from miner2049er.settings import ROOT
from miner2049er.target_inventory import (
    BLIND_SOURCE,
    VALIDATION_SOURCE,
    collect_inventory,
    relationship_union,
)


def inspection_query(rule: Rule, target_union: str, partition: str) -> str:
    conditions = {
        "training": (
            "size(sources) > 0 "
            "AND NOT (size(sources) = 1 AND sources[0] = $validation_source) "
            "AND NOT (size(sources) = 1 AND sources[0] = $blind_source)"
        ),
        "validation": "size(sources) = 1 AND sources[0] = $validation_source",
        "novel": "size(sources) = 0",
    }
    condition = conditions[partition]
    rule_cypher = render_rule_cypher(rule, target_union)
    return f"""
    CALL () {{
      {rule_cypher}
    }}
    WITH DISTINCT subject_id, object_id
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
    WHERE {condition}
    RETURN subject.id AS subject_id,
           subject.name AS subject_name,
           subject.categories AS subject_categories,
           object.id AS object_id,
           object.name AS object_name,
           object.categories AS object_categories,
           sources,
           EXISTS {{
             MATCH (subject)-[:CONTRAINDICATED_IN]->(object)
           }} AS contraindicated
    ORDER BY subject_id, object_id
    LIMIT $limit
    """


def inspect_rule(
    uri: str,
    password: str,
    rule: Rule,
    target_union: str,
    partition: str,
    limit: int,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    query = inspection_query(rule, target_union, partition)
    with (
        GraphDatabase.driver(uri, auth=("neo4j", password)) as driver,
        driver.session(database="neo4j") as session,
    ):
        return [
            record.data()
            for record in session.run(
                Query(query, timeout=timeout_seconds),
                validation_source=VALIDATION_SOURCE,
                blind_source=BLIND_SOURCE,
                limit=limit,
            )
        ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect examples produced by one rule")
    parser.add_argument("--rule", required=True)
    parser.add_argument(
        "--rules",
        type=Path,
        default=ROOT / "rules" / "treats-rules.toml",
    )
    parser.add_argument(
        "--partition",
        choices=("training", "validation", "novel"),
        default="novel",
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--neo4j-uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument(
        "--neo4j-password",
        default=os.environ.get("NEO4J_PASSWORD", "translator-local"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rule = load_rules(args.rules, {args.rule})[0]
    inventory = collect_inventory(args.neo4j_uri, args.neo4j_password)
    target_union = relationship_union(inventory["neo4j_relationship_types"])
    examples = inspect_rule(
        args.neo4j_uri,
        args.neo4j_password,
        rule,
        target_union,
        args.partition,
        args.limit,
        args.timeout_seconds,
    )
    print(
        json.dumps(
            {
                "rule": rule.id,
                "partition": args.partition,
                "examples": examples,
            },
            indent=2,
        )
    )
