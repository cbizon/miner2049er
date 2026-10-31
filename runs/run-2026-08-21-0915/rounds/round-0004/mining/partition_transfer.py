"""Verify complete raw transfer bodies in disjoint candidate-drug partitions."""

import argparse
from datetime import datetime
import hashlib
import json
import os
import shutil
import time

from neo4j import GraphDatabase, Query, READ_ACCESS

from miner2049er.biolink_semantics import neo4j_relationship_type

from audit import normalized, records
from probe import REQUIRED, RUN, log_event
from transfer_equivalence import BOUNDARY


FORM = "raw-all-drug-partitioned-indexed-domain-v2"


def formulation(rule):
    body = rule["execution"]["cypher"].split(BOUNDARY, 1)[1]
    if "MINER_" in body or "raw_sources" not in body:
        raise RuntimeError("The complete raw transfer body was not identified")
    target = next(e for e in rule["graph_pattern"]["edges"] if e["id"] == "candidate_target")
    if target.get("qualifiers", {}).get("qualified_predicate") != "biolink:causes":
        raise RuntimeError("The target-domain assumption does not apply")
    predicates = target["predicate_expansion"]["expanded_predicates"]
    types = "|".join(sorted(neo4j_relationship_type(p) for p in predicates))
    sources = target["source_constraints"]
    target_test = (
        f"MATCH (chemical)-[target:{types}]->(:GeneOrGeneProduct) "
        f"WHERE target.predicate IN {json.dumps(predicates)} "
        "AND target.qualified_predicate='biolink:causes' "
        f"AND any(source IN {json.dumps(sources)} "
        "WHERE source IN coalesce(target.primary_knowledge_sources,[]))"
    )
    direct = next((e for e in rule["graph_pattern"]["edges"] if e["id"] == "direct"), None)
    if direct:
        predicates = direct["predicate_expansion"]["expanded_predicates"]
        types = "|".join(sorted(neo4j_relationship_type(p) for p in predicates))
        domain = (
            f"MATCH (chemical:Drug)-[direct:{types}]->(:Disease) "
            f"WHERE direct.predicate IN {json.dumps(predicates)} "
            "WITH DISTINCT chemical "
        )
    else:
        domain = "MATCH (chemical:Drug) USING SCAN chemical:Drug "
    selector = (
        domain + "WHERE EXISTS { " + target_test + " } "
        "RETURN DISTINCT elementId(chemical) AS chemical_node ORDER BY chemical_node"
    )
    query = (
        "MATCH (chemical:Drug) WHERE elementId(chemical) IN $chemical_nodes "
        "WITH chemical " + body
    )
    return selector, query


def execute(driver, query, parameters, key, suffix, timeout):
    start = time.monotonic()
    try:
        rows = {}
        with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
            result = session.run(Query(query, timeout=timeout), parameters)
            if suffix.endswith("explain"):
                summary = {"plan": result.consume().plan}
            else:
                for record in result:
                    row = record.data()
                    pair = row["subject_id"], row["object_id"]
                    payload = normalized(row)
                    if pair in rows and rows[pair] != payload:
                        raise RuntimeError("Conflicting raw payload for one endpoint pair")
                    rows[pair] = payload
                    if len(rows) > 500000:
                        raise RuntimeError("Raw batch exceeds the in-memory output reserve")
                summary = {"predictions": len(rows)}
        log_event("query", "Raw transfer candidate partition: " + key + " " + suffix, {
            "purpose": "Execute the original biological body without any stored access feature.",
            "query_language": "cypher", "query_text": query, "parameters": parameters,
            "outcome": "completed" if rows or suffix.endswith("explain") else "empty",
            "result_summary": json.dumps(summary), "runtime_seconds": time.monotonic() - start,
            "candidate_id": key, "formulation": FORM + "-" + suffix,
            "next_action": "Require full candidate-node coverage and exact whole-output agreement.",
        })
        print(key, suffix, len(rows), flush=True)
        return rows
    except Exception as error:
        log_event("failure", "Raw transfer candidate partition failed: " + key + " " + suffix, {
            "stage": "raw transfer partition execution", "error": str(error),
            "diagnosis": "This batch is not complete; no partial result is substituted.",
            "next_action": "Split a fifty-node batch once into fives, or retain the unresolved verification.",
            "hypothesis_status": "blocked", "candidate_id": key,
            "formulation": FORM + "-" + suffix, "query_text": query,
            "parameters": parameters, "runtime_seconds": time.monotonic() - start,
        })
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rule-id")
    parser.add_argument("--timeout-seconds", type=float, default=120)
    parser.add_argument("--stop-at", type=datetime.fromisoformat)
    args = parser.parse_args()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing service variables: " + ", ".join(missing))
    if args.stop_at and datetime.now().astimezone() >= args.stop_at:
        print("Raw transfer verification window is closed.")
        return
    manifest = json.loads((RUN / "run.json").read_text())
    if manifest["current_round_id"] != "round-0004":
        raise RuntimeError("This verifier belongs only to round-0004")
    ledger = list(records(RUN / "research-log.jsonl"))
    terminal = {
        e["details"].get("candidate_id") for e in ledger
        if e["details"].get("formulation") == FORM
        and (e["event_type"] == "failure" or e["details"].get("outcome") == "completed")
    }
    terminal.update(
        e["details"]["candidate_id"] for e in ledger
        if str(e["details"].get("candidate_id", "")).startswith("r4-transfer-")
        and str(e["details"].get("formulation", "")).startswith("raw-all")
        and e["details"].get("outcome") in ("completed", "empty")
        and json.loads(e["details"]["result_summary"]).get("exact_payload_match")
    )
    selected = {
        r["rule_id"]: r for r in records(RUN / "rules.jsonl")
        if r["rule_id"].startswith("r4-transfer-") and r["rule_id"] not in terminal
        and (not args.rule_id or args.rule_id == r["rule_id"])
    }
    if not selected:
        print("No unattempted raw transfer partitions remain.")
        return
    hashes = {key: hashlib.sha256() for key in selected}
    counts = {key: 0 for key in selected}
    for row in records(RUN / "predictions.jsonl"):
        key = row["rule_id"]
        if key in selected:
            hashes[key].update(normalized(row))
            counts[key] += 1
    with GraphDatabase.driver(
        os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        max_transaction_retry_time=0, connection_timeout=15,
    ) as driver:
        for key, rule in selected.items():
            if args.stop_at and datetime.now().astimezone() >= args.stop_at:
                return
            started = time.monotonic()
            covered, combined = set(), {}
            selector, query = formulation(rule)
            active_query = selector
            try:
                if shutil.disk_usage(RUN).free < 5 * 1024**3:
                    raise RuntimeError("Disk reserve reached")
                execute(driver, "EXPLAIN " + selector, {}, key, "domain-explain", 30)
                with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                    nodes = [r["chemical_node"] for r in session.run(Query(selector, timeout=60))]
                log_event("query", "Select every raw transfer candidate node: " + key, {
                    "purpose": "Build a necessary-condition domain from raw target predicates, causal qualification, curated sources, and the direct-disease arm when that arm is required, without labels or materializations.",
                    "query_language": "cypher", "query_text": selector, "outcome": "completed",
                    "result_summary": json.dumps({"candidate_nodes": len(nodes), "node_domain_sha256": hashlib.sha256(json.dumps(nodes).encode()).hexdigest()}),
                    "candidate_id": key, "formulation": FORM + "-domain",
                    "next_action": "Partition every selected candidate node without truncation.",
                })
                active_query = query
                if nodes:
                    execute(driver, "EXPLAIN " + query, {"chemical_nodes": nodes[:50]},
                            key, "explain", 30)
                pending = [(nodes[i:i+50], False) for i in range(0, len(nodes), 50)]
                batches = 0
                while pending:
                    if (args.stop_at and datetime.now().astimezone() >= args.stop_at
                            or time.monotonic() - started >= 600
                            or shutil.disk_usage(RUN).free < 5 * 1024**3):
                        raise RuntimeError("Time or disk reserve reached before complete coverage")
                    batch, split = pending.pop(0)
                    try:
                        rows = execute(driver, query, {"chemical_nodes": batch}, key,
                                       "batch-" + str(batches), args.timeout_seconds)
                    except Exception:
                        if split or len(batch) <= 5:
                            raise
                        pending[0:0] = [(batch[i:i+5], True) for i in range(0, len(batch), 5)]
                        continue
                    if covered.intersection(batch):
                        raise RuntimeError("Candidate-node partitions overlap")
                    covered.update(batch)
                    for pair, payload in rows.items():
                        if pair in combined and combined[pair] != payload:
                            raise RuntimeError("Conflicting payload across complete drug-node partitions")
                        combined[pair] = payload
                    if len(combined) > 500000:
                        raise RuntimeError("Complete output exceeds the in-memory reserve")
                    batches += 1
                if covered != set(nodes):
                    raise RuntimeError("Candidate-node coverage is incomplete")
                actual = hashlib.sha256()
                for pair in sorted(combined):
                    actual.update(combined[pair])
                same = len(combined) == counts[key] and actual.hexdigest() == hashes[key].hexdigest()
                metrics = {
                    "exact_payload_match": same, "raw_rows": len(combined), "stored_rows": counts[key],
                    "raw_sha256": actual.hexdigest(), "stored_sha256": hashes[key].hexdigest(),
                    "candidate_nodes": len(nodes), "covered_nodes": len(covered), "completed_batches": batches,
                }
                log_event("query", "Complete raw transfer candidate partition comparison: " + key, {
                    "purpose": "Remove all stored access features while retaining every original biological condition.",
                    "query_language": "cypher", "query_text": query, "outcome": "completed",
                    "result_summary": json.dumps(metrics), "candidate_id": key, "formulation": FORM,
                    "runtime_seconds": time.monotonic() - started,
                    "partition_algorithm": "All raw qualifying drug-node identities, sorted and partitioned into fifties, with one fallback split into fives. Entire biological support for each candidate remains within one query. Require complete coverage and conflict-checked payload merging.",
                    "next_action": "Treat only complete exact agreement as computational equivalence.",
                })
                log_event("ablation", "Joint access-feature removal by raw candidate partitioning: " + key, {
                    "baseline": "Entire raw biological body evaluated across every qualifying drug node",
                    "variant": "Recorded compact-access rule",
                    "changed_components": ["all computational access summaries and execution partitioning only"],
                    "metrics": metrics,
                    "interpretation": "Batch sizes and runtime ceilings are operational bounds, never biological thresholds or truncated prediction sets.",
                    "decision": "keep_change" if same else "retest",
                })
                if not same:
                    raise RuntimeError("Raw transfer partitions disagree with recorded predictions")
            except Exception as error:
                log_event("failure", "Complete raw transfer candidate partition check remains unresolved: " + key, {
                    "stage": "joint raw access verification", "error": str(error),
                    "diagnosis": "Partial batches are not a verified whole-graph baseline.",
                    "next_action": "Retain the verified individual feature removals and disclose this remaining joint gap; do not repeat this formulation automatically.",
                    "hypothesis_status": "blocked", "candidate_id": key, "formulation": FORM,
                    "query_text": active_query, "covered_nodes": len(covered), "partial_pairs": len(combined),
                    "runtime_seconds": time.monotonic() - started,
                })


if __name__ == "__main__":
    main()
