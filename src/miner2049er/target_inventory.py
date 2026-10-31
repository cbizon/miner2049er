from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from miner2049er.gandalf_runtime import local_toolkit
from miner2049er.neo4j_export import sanitize_token
from miner2049er.settings import ROOT

TARGET_PREDICATE = "biolink:treats"
VALIDATION_SOURCE = "infores:drug-repurposing-hub"
BLIND_SOURCE = "infores:ttd"


def target_predicates() -> list[str]:
    return local_toolkit().get_descendants(
        TARGET_PREDICATE,
        formatted=True,
        reflexive=True,
    )


def target_relationship_types() -> list[str]:
    return [sanitize_token(predicate, uppercase=True) for predicate in target_predicates()]


def relationship_union(types: list[str]) -> str:
    return "|".join(types)


def collect_inventory(uri: str, password: str) -> dict[str, Any]:
    predicates = target_predicates()
    closure_relationship_types = target_relationship_types()
    with GraphDatabase.driver(uri, auth=("neo4j", password)) as driver:
        available_relationship_types = {
            record["relationshipType"]
            for record in driver.execute_query(
                "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType",
                database_="neo4j",
            ).records
        }
        relationship_types = [
            relationship_type
            for relationship_type in closure_relationship_types
            if relationship_type in available_relationship_types
        ]
        union = relationship_union(relationship_types)
        query = f"""
    MATCH (subject)-[target:{union}]->(object)
    WITH subject, object, target,
         coalesce(target.primary_knowledge_sources, []) AS edge_sources
    UNWIND edge_sources AS source
    WITH subject, object,
         collect(DISTINCT target.predicate) AS predicates,
         collect(DISTINCT source) AS sources,
         count(target) AS edge_rows
    WITH subject, object, predicates, sources, edge_rows,
         CASE
           WHEN size(sources) = 1 AND sources[0] = $validation_source THEN 'validation'
           WHEN size(sources) = 1 AND sources[0] = $blind_source THEN 'blind'
           ELSE 'training'
         END AS partition
    RETURN count(*) AS semantic_pairs,
           sum(edge_rows) AS edge_rows,
           sum(CASE WHEN partition = 'training' THEN 1 ELSE 0 END) AS training_pairs,
           sum(CASE WHEN partition = 'validation' THEN 1 ELSE 0 END) AS validation_pairs,
           sum(CASE WHEN partition = 'blind' THEN 1 ELSE 0 END) AS blind_pairs,
           count(DISTINCT subject) AS subjects,
           count(DISTINCT object) AS objects
    """
        source_query = f"""
    MATCH (subject)-[target:{union}]->(object)
    UNWIND coalesce(target.primary_knowledge_sources, []) AS source
    WITH subject, object, collect(DISTINCT source) AS sources
    UNWIND sources AS source
    RETURN source,
           count(*) AS supported_pairs,
           sum(CASE WHEN size(sources) = 1 THEN 1 ELSE 0 END) AS exclusive_pairs
    ORDER BY supported_pairs DESC
    """
        counts = driver.execute_query(
            query,
            validation_source=VALIDATION_SOURCE,
            blind_source=BLIND_SOURCE,
            database_="neo4j",
        ).records[0].data()
        sources = [
            record.data()
            for record in driver.execute_query(source_query, database_="neo4j").records
        ]
    return {
        "target_predicate": TARGET_PREDICATE,
        "predicate_closure": predicates,
        "neo4j_relationship_types": relationship_types,
        "absent_neo4j_relationship_types": sorted(
            set(closure_relationship_types) - set(relationship_types)
        ),
        "partition_policy": {
            "training": "all target facts except source-exclusive validation and blind facts",
            "validation_source": VALIDATION_SOURCE,
            "blind_source": BLIND_SOURCE,
        },
        "counts": counts,
        "sources": sources,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory the semantic treats target")
    parser.add_argument("--neo4j-uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument(
        "--neo4j-password",
        default=os.environ.get("NEO4J_PASSWORD", "translator-local"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "target-inventory.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inventory = collect_inventory(args.neo4j_uri, args.neo4j_password)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(inventory, indent=2))
