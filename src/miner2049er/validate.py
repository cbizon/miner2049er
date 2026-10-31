from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import httpx
import orjson
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from miner2049er.settings import edges_path


def first_edge(path: Path) -> dict:
    with path.open("rb") as stream:
        return orjson.loads(next(stream))


def gandalf_query(base_url: str, edge: dict) -> dict:
    payload = {
        "message": {
            "query_graph": {
                "nodes": {
                    "n0": {"ids": [edge["subject"]]},
                    "n1": {"ids": [edge["object"]]},
                },
                "edges": {
                    "e0": {
                        "subject": "n0",
                        "object": "n1",
                        "predicates": [edge["predicate"]],
                    }
                },
            }
        },
        "parameters": {
            "subclass": False,
            "dehydrated": False,
        },
    }
    response = httpx.post(f"{base_url.rstrip('/')}/query", json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def neo4j_query(uri: str, password: str, edge: dict) -> list[dict]:
    query = """
    MATCH (s:Entity {id: $subject})-[r]->(o:Entity {id: $object})
    WHERE r.predicate = $predicate
    RETURN r.edge_id AS edge_id,
           r.predicate AS predicate,
           r.primary_knowledge_sources AS primary_knowledge_sources
    ORDER BY edge_id
    """
    with GraphDatabase.driver(uri, auth=("neo4j", password)) as driver:
        return [
            record.data()
            for record in driver.execute_query(
                query,
                subject=edge["subject"],
                object=edge["object"],
                predicate=edge["predicate"],
                database_="neo4j",
            ).records
        ]


def gandalf_edge_ids(response: dict) -> set[str]:
    knowledge_graph = response.get("message", {}).get("knowledge_graph", {})
    return set(knowledge_graph.get("edges", {}))


def wait_for_services(gandalf_url: str, neo4j_uri: str, password: str, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    gandalf_ready = False
    neo4j_ready = False
    while time.monotonic() < deadline:
        if not gandalf_ready:
            try:
                response = httpx.get(f"{gandalf_url.rstrip('/')}/metadata", timeout=5)
                gandalf_ready = response.is_success
            except httpx.HTTPError:
                pass
        if not neo4j_ready:
            try:
                with GraphDatabase.driver(neo4j_uri, auth=("neo4j", password)) as driver:
                    driver.verify_connectivity()
                neo4j_ready = True
            except (Neo4jError, OSError):
                neo4j_ready = False
        if gandalf_ready and neo4j_ready:
            return
        time.sleep(2)
    raise TimeoutError(
        f"Services not ready after {timeout}s: gandalf={gandalf_ready}, neo4j={neo4j_ready}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cross-check Gandalf and Neo4j")
    parser.add_argument("--edge-file", type=Path, default=edges_path())
    parser.add_argument("--gandalf-url", default=os.environ.get("GANDALF_URL", "http://localhost:6429"))
    parser.add_argument("--neo4j-uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument(
        "--neo4j-password",
        default=os.environ.get("NEO4J_PASSWORD", "translator-local"),
    )
    parser.add_argument("--wait-seconds", type=int, default=180)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    wait_for_services(
        args.gandalf_url,
        args.neo4j_uri,
        args.neo4j_password,
        args.wait_seconds,
    )
    edge = first_edge(args.edge_file)
    gandalf_response = gandalf_query(args.gandalf_url, edge)
    neo4j_rows = neo4j_query(args.neo4j_uri, args.neo4j_password, edge)

    gandalf_ids = gandalf_edge_ids(gandalf_response)
    neo4j_ids = {row["edge_id"] for row in neo4j_rows if row["edge_id"]}
    expected = edge.get("id")
    if expected not in gandalf_ids:
        raise AssertionError(f"Gandalf did not return source edge {expected}")
    if expected not in neo4j_ids:
        raise AssertionError(f"Neo4j did not return source edge {expected}")

    summary = {
        "source_edge": edge,
        "gandalf_edge_count": len(gandalf_ids),
        "neo4j_edge_count": len(neo4j_ids),
        "shared_edge_ids": sorted(gandalf_ids & neo4j_ids),
    }
    print(json.dumps(summary, indent=2))
