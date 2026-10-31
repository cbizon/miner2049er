"""Exhaustively partition raw regulation by graph node identity, without exports."""

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

from neo4j import GraphDatabase, Query, READ_ACCESS

from miner2049er.rule_recorder import build_rule

from all_source_controls import candidate_document
from audit import TRAIN_QUERY, normalized, records
from context_regulation import digest, run_query
from grouped_regulation import QUERY as RAW_TEMPLATE
from probe import REQUIRED, RUN, log_event


FORM = "exhaustive-drug-partitioned-raw"
BATCH_SIZE = 50
FALLBACK_SIZE = 5


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=120)
    parser.add_argument("--stop-at", type=datetime.fromisoformat)
    args = parser.parse_args()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing service variables: " + ", ".join(missing))
    if args.stop_at and datetime.now().astimezone() >= args.stop_at:
        print("Raw partition verification window has closed; no graph query launched.")
        return
    manifest = json.loads((RUN / "run.json").read_text())
    if manifest["current_round_id"] != "round-0004":
        raise RuntimeError("This check belongs only to the fourth round")
    rules = {r["rule_id"]: r for r in records(RUN / "rules.jsonl")}
    ledger = list(records(RUN / "research-log.jsonl"))
    terminal = {
        e["details"].get("candidate_id") for e in ledger
        if e["details"].get("formulation") == FORM
        and (e["event_type"] == "failure" or e["details"].get("outcome") == "completed")
    }
    raw_templates = {
        "r4-regulatory-net-decrease-no-curation" + suffix: RAW_TEMPLATE
        for suffix in ("", "-full-closure")
    }
    for sign in ("unsigned", "increase"):
        for full in (False, True):
            control, raw, _ = candidate_document(sign, full)
            raw_templates[control["rule_id"]] = raw
    selected = [key for key in raw_templates if key in rules and key not in terminal]
    if not selected:
        print("No unattempted recorded all-source context rules need raw partition checks.")
        return
    hashes = {key: hashlib.sha256() for key in selected}
    counts = {key: 0 for key in selected}
    for row in records(RUN / "predictions.jsonl"):
        if row["rule_id"] in hashes:
            hashes[row["rule_id"]].update(normalized(row))
            counts[row["rule_id"]] += 1
    active = Path(__file__).resolve().parent / "active-candidates"
    with GraphDatabase.driver(
        os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        max_transaction_retry_time=0, connection_timeout=15,
    ) as driver:
        with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
            training = {(r["subject_id"], r["object_id"]) for r in session.run(Query(TRAIN_QUERY, timeout=60))}
        log_event("query", "Read visible targets for exhaustive raw execution ablation.", {
            "purpose": "Use only visible targets for aggregate batch statistics.",
            "query_language": "cypher", "query_text": TRAIN_QUERY, "outcome": "completed",
            "result_summary": str(len(training)) + " visible target pairs; no export.",
            "next_action": "Partition every qualifying graph drug node without dropping any node or prediction.",
        })
        for key in selected:
            started = time.monotonic()
            covered, accumulated = set(), {}
            try:
                candidate = deepcopy(json.loads((active / (key + ".json")).read_text()))
                candidate["execution"]["cypher_template"] = raw_templates[key]
                candidate["derived_features"] = []
                raw = build_rule(candidate, manifest)["execution"]["cypher"]
                direct = raw.split("\nWITH chemical,", 1)[0]
                target = "MATCH (chemical)-[target:" + raw.split(
                    "  MATCH (chemical)-[target:", 1
                )[1].split("\n  WITH DISTINCT regulator,", 1)[0]
                selector = (
                    direct + " AND EXISTS { " + target + " } "
                    "RETURN DISTINCT elementId(chemical) AS chemical_node ORDER BY chemical_node"
                )
                with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                    nodes = [r["chemical_node"] for r in session.run(Query(selector, timeout=60))]
                log_event("query", "Select the complete drug-node domain for raw partitioning: " + key, {
                    "purpose": "Enumerate all drug nodes meeting necessary direct and signed-target arms, without treatment-label selection.",
                    "query_language": "cypher", "query_text": selector, "outcome": "completed",
                    "result_summary": json.dumps({"qualifying_drug_nodes": len(nodes),
                                                  "node_domain_sha256": hashlib.sha256(json.dumps(nodes).encode()).hexdigest()}),
                    "candidate_id": key, "formulation": FORM + "-domain",
                    "next_action": "Run every node in one disjoint batch; a failed batch may be split once from fifty to five nodes, never dropped.",
                })
                bounded = raw.replace(
                    "\nWITH chemical,", " AND elementId(chemical) IN $chemical_nodes\nWITH chemical,", 1
                )
                if nodes:
                    run_query(driver, "EXPLAIN " + bounded, {"chemical_nodes": nodes[:BATCH_SIZE]},
                              key, FORM + "-explain", 30, training)
                queue = [(nodes[i:i+BATCH_SIZE], False) for i in range(0, len(nodes), BATCH_SIZE)]
                batches = 0
                while queue:
                    if args.stop_at and datetime.now().astimezone() >= args.stop_at:
                        raise RuntimeError("Raw partition verification time reserve reached before all nodes completed")
                    if time.monotonic() - started >= 1800 or shutil.disk_usage(RUN).free < 5 * 1024**3:
                        raise RuntimeError("Raw partition runtime or disk reserve reached")
                    batch, split_once = queue.pop(0)
                    try:
                        _, rows = run_query(
                            driver, bounded, {"chemical_nodes": batch}, key,
                            FORM + "-batch-" + str(batches), args.timeout_seconds, training, return_rows=True,
                        )
                    except Exception:
                        if split_once or len(batch) <= FALLBACK_SIZE:
                            raise
                        queue[0:0] = [
                            (batch[i:i+FALLBACK_SIZE], True) for i in range(0, len(batch), FALLBACK_SIZE)
                        ]
                        continue
                    if covered.intersection(batch):
                        raise RuntimeError("Raw partition domain overlaps a completed batch")
                    covered.update(batch)
                    for pair, row in rows.items():
                        if pair in accumulated and normalized(accumulated[pair]) != normalized(row):
                            raise RuntimeError("Conflicting complete raw output across drug-node partitions")
                        accumulated[pair] = row
                    batches += 1
                if covered != set(nodes):
                    raise RuntimeError("Not all qualifying drug nodes were evaluated")
                exact, _ = digest(accumulated)
                same = len(accumulated) == counts[key] and exact == hashes[key].hexdigest()
                metrics = {
                    "exact_payload_match": same, "raw_predictions": len(accumulated),
                    "stored_predictions": counts[key], "raw_payload_sha256": exact,
                    "stored_payload_sha256": hashes[key].hexdigest(),
                    "qualifying_drug_nodes": len(nodes), "covered_drug_nodes": len(covered),
                    "completed_batches": batches,
                }
                log_event("query", "Exhaustive raw regulatory partition comparison: " + key, {
                    "purpose": "Compare every raw prediction, support count, and evidence payload without any stored access feature.",
                    "query_language": "cypher", "query_text": raw, "outcome": "completed",
                    "result_summary": json.dumps(metrics), "candidate_id": key, "formulation": FORM,
                    "runtime_seconds": time.monotonic() - started,
                    "next_action": "Use only exact complete agreement as evidence that materialized access preserves the rule.",
                    "partition_algorithm": "Select every qualifying drug-node element identifier, sort it, and run disjoint groups of fifty. Split a failed group once into groups of five. Merge all returned endpoint payloads with duplicate-conflict checking. Require full domain coverage and compare the sorted complete payload hash.",
                })
                log_event("ablation", "Remove stored regulatory context through exhaustive raw execution: " + key, {
                    "baseline": "Every original drug-first raw query partition, with exhaustive domain coverage",
                    "variant": "Recorded complete materialized-access rule",
                    "changed_components": ["computational materialization and execution partitioning only"],
                    "metrics": metrics,
                    "interpretation": "Partition sizes are operational bounds, not biological filters or prediction thresholds. No completed subset stands in for the whole graph.",
                    "decision": "keep_change" if same else "retest",
                })
                if not same:
                    raise RuntimeError("Complete raw partitioned predictions do not match the stored rule")
            except Exception as error:
                log_event("failure", "Exhaustive raw regulation did not verify: " + key, {
                    "stage": "complete raw partitioned equivalence", "error": str(error),
                    "diagnosis": "The whole-graph raw comparison remains unresolved; partial batches are not a completed baseline.",
                    "next_action": "Preserve the completed bounded evidence and disclose the remaining verification gap without automatically repeating this formulation.",
                    "hypothesis_status": "blocked", "candidate_id": key, "formulation": FORM,
                    "covered_drug_nodes": len(covered), "partial_prediction_count": len(accumulated),
                    "runtime_seconds": time.monotonic() - started,
                })


if __name__ == "__main__":
    main()
