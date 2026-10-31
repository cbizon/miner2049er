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

RELATIONS = ("parent_only", "child_only", "intersection")
EXAMPLE_PARTITIONS = ("training", "validation", "novel")


def membership_union(parent: Rule, child: Rule, target_union: str) -> str:
    parent_cypher = render_rule_cypher(parent, target_union)
    child_cypher = render_rule_cypher(child, target_union)
    return f"""
    CALL () {{
      CALL () {{
        {parent_cypher}
      }}
      RETURN subject_id, object_id, 'parent' AS membership
      UNION ALL
      CALL () {{
        {child_cypher}
      }}
      RETURN subject_id, object_id, 'child' AS membership
    }}
    WITH subject_id, object_id, collect(DISTINCT membership) AS memberships
    WITH subject_id, object_id,
         CASE
           WHEN 'parent' IN memberships AND 'child' IN memberships THEN 'intersection'
           WHEN 'parent' IN memberships THEN 'parent_only'
           ELSE 'child_only'
         END AS relation
    """


def comparison_query(parent: Rule, child: Rule, target_union: str) -> str:
    union = membership_union(parent, child, target_union)
    return f"""
    {union}
    MATCH (subject:Entity {{id: subject_id}})
    MATCH (object:Entity {{id: object_id}})
    OPTIONAL MATCH (subject)-[target:{target_union}]->(object)
    WITH relation, subject, object,
         reduce(
           raw_sources = [],
           edge IN collect(target) |
           raw_sources + coalesce(edge.primary_knowledge_sources, [])
         ) AS raw_sources
    WITH relation, subject, object,
         reduce(
           sources = [],
           source IN raw_sources |
           CASE WHEN source IN sources THEN sources ELSE sources + source END
         ) AS sources
    RETURN relation,
           count(*) AS candidate_pairs,
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
               WHEN size(sources) = 0
                    OR (size(sources) = 1 AND sources[0] = $blind_source)
               THEN 1
               ELSE 0
             END
           ) AS unresolved_or_blind_pairs,
           sum(
             CASE
               WHEN EXISTS {{
                 MATCH (subject)-[:CONTRAINDICATED_IN]->(object)
               }}
               THEN 1
               ELSE 0
             END
           ) AS contraindicated_pairs
    ORDER BY relation
    """


def examples_query(
    parent: Rule,
    child: Rule,
    target_union: str,
    relation: str,
    partition: str,
) -> str:
    conditions = {
        "training": (
            "size(sources) > 0 "
            "AND NOT (size(sources) = 1 AND sources[0] = $validation_source) "
            "AND NOT (size(sources) = 1 AND sources[0] = $blind_source)"
        ),
        "validation": "size(sources) = 1 AND sources[0] = $validation_source",
        # TTD-only pairs are deliberately not included in novel examples.
        "novel": "size(sources) = 0",
    }
    union = membership_union(parent, child, target_union)
    return f"""
    {union}
    WHERE relation = $relation
    MATCH (subject:Entity {{id: subject_id}})
    MATCH (object:Entity {{id: object_id}})
    OPTIONAL MATCH (subject)-[target:{target_union}]->(object)
    WITH subject, object,
         reduce(
           raw_sources = [],
           edge IN collect(target) |
           raw_sources + coalesce(edge.primary_knowledge_sources, [])
         ) AS raw_sources
    WITH subject, object,
         reduce(
           sources = [],
           source IN raw_sources |
           CASE WHEN source IN sources THEN sources ELSE sources + source END
         ) AS sources
    WHERE {conditions[partition]}
    RETURN subject.id AS subject_id,
           subject.name AS subject_name,
           object.id AS object_id,
           object.name AS object_name,
           sources,
           EXISTS {{
             MATCH (subject)-[:CONTRAINDICATED_IN]->(object)
           }} AS contraindicated
    ORDER BY subject_id, object_id
    LIMIT $limit
    """


def compare_rules(
    uri: str,
    password: str,
    parent: Rule,
    child: Rule,
    target_union: str,
    relation: str,
    partition: str,
    limit: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    with (
        GraphDatabase.driver(uri, auth=("neo4j", password)) as driver,
        driver.session(database="neo4j") as session,
    ):
        counts = [
            record.data()
            for record in session.run(
                Query(comparison_query(parent, child, target_union), timeout=timeout_seconds),
                validation_source=VALIDATION_SOURCE,
                blind_source=BLIND_SOURCE,
            )
        ]
        examples = [
            record.data()
            for record in session.run(
                Query(
                    examples_query(parent, child, target_union, relation, partition),
                    timeout=timeout_seconds,
                ),
                validation_source=VALIDATION_SOURCE,
                blind_source=BLIND_SOURCE,
                relation=relation,
                limit=limit,
            )
        ]
    return {
        "parent": parent.id,
        "child": child.id,
        "counts": counts,
        "example_relation": relation,
        "example_partition": partition,
        "examples": examples,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two rule candidate sets")
    parser.add_argument("--parent", required=True)
    parser.add_argument("--child", required=True)
    parser.add_argument(
        "--rules",
        type=Path,
        default=ROOT / "rules" / "treats-rules.toml",
    )
    parser.add_argument("--relation", choices=RELATIONS, default="parent_only")
    parser.add_argument("--partition", choices=EXAMPLE_PARTITIONS, default="novel")
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
    selected = load_rules(
        args.rules,
        {args.parent, args.child},
        include_inactive=True,
    )
    by_id = {rule.id: rule for rule in selected}
    inventory = collect_inventory(args.neo4j_uri, args.neo4j_password)
    target_union = relationship_union(inventory["neo4j_relationship_types"])
    report = compare_rules(
        args.neo4j_uri,
        args.neo4j_password,
        by_id[args.parent],
        by_id[args.child],
        target_union,
        args.relation,
        args.partition,
        args.limit,
        args.timeout_seconds,
    )
    print(json.dumps(report, indent=2))
