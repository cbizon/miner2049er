"""Compare each recorded compact-target rule with its raw access-path equivalent."""

import argparse
from datetime import datetime
import hashlib
import json
import os
import re
import shutil
import time

from neo4j import GraphDatabase, Query, READ_ACCESS

from miner2049er.biolink_semantics import neo4j_relationship_type, predicate_expansion_record
from miner2049er.rule_recorder import build_rule

from audit import normalized, records
from candidates import match
from probe import REQUIRED, RUN, log_event


MARKER = "/* END CURATED ACCESS PATH */"


def genetic_first_family_query(key):
    path = RUN / "rounds/round-0004/mining/active-candidates" / (key + ".json")
    candidate = json.loads(path.read_text())
    edges = {edge["id"]: edge for edge in candidate["graph_pattern"]["edges"]}
    first = " ".join(match(edges[name]) for name in ("direct", "target", "target_genetics"))
    second = " ".join(match(edges[name]) for name in (
        "target_member", "disease_member", "association"
    ))
    candidate["execution"]["cypher_template"] = (
        "CALL () { " + first + " RETURN DISTINCT chemical,disease,regulator } "
        + second + " AND regulator<>gene "
        "RETURN chemical.id AS subject_id,disease.id AS object_id,"
        "count(DISTINCT family) AS support_count"
    )
    candidate["derived_features"] = []
    manifest = json.loads((RUN / "run.json").read_text())
    return build_rule(candidate, manifest)["execution"]["cypher"]


def compare(driver, key, form, query, expected, count, args):
    started = time.monotonic()
    print("RAW EQUIVALENCE", key, form, flush=True)
    try:
        actual = {}
        with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
            for record in session.run(Query(query, timeout=args.timeout_seconds)):
                row = record.data()
                pair = (row["subject_id"], row["object_id"])
                payload = normalized(row)
                if pair in actual and actual[pair] != payload:
                    raise RuntimeError("Conflicting duplicate raw output")
                actual[pair] = payload
                if len(actual) > args.maximum_pairs:
                    raise RuntimeError("Raw output exceeds the declared in-memory pair reserve")
        digest = hashlib.sha256()
        for pair in sorted(actual):
            digest.update(actual[pair])
        same = len(actual) == count and digest.hexdigest() == expected.hexdigest()
        metrics = {
            "stored_rows": count, "raw_rows": len(actual), "exact_payload_match": same,
            "stored_sha256": expected.hexdigest(), "raw_sha256": digest.hexdigest(),
            "runtime_seconds": time.monotonic() - started,
        }
        log_event("query", "Unmaterialized exact-output comparison: " + key + " " + form, {
            "purpose": "Remove the stored target access path while retaining every biological condition and complete predicate expansion.",
            "query_language": "cypher", "query_text": query,
            "outcome": "completed" if actual else "empty",
            "result_summary": json.dumps(metrics), "runtime_seconds": metrics["runtime_seconds"],
            "candidate_id": key, "formulation": form,
            "next_action": "Retain the stored access path only as a computational optimization when complete payloads match.",
        })
        log_event("ablation", "Remove materialized target access without changing biology: " + key, {
            "baseline": "The same rule using raw evidence joins without the stored target relationship: " + form,
            "variant": "The immutable recorded rule using the documented compact target relationship and rematching all original evidence.",
            "baseline_rule_id": key, "variant_rule_id": key,
            "changed_components": ["stored versus raw target access; no source, qualifier, node, predicate, or biological threshold change"],
            "metrics": metrics,
            "interpretation": "This checks computational equivalence, not a claim that a new biological feature improves precision.",
            "decision": "keep_change" if same else "retest",
        })
        print(json.dumps(metrics), flush=True)
        if not same:
            raise RuntimeError("The raw formulation differs from the recorded complete payload")
        return True
    except Exception as error:
        log_event("failure", "Raw equivalence check did not verify: " + key + " " + form, {
            "stage": "remove compact target access", "error": str(error),
            "diagnosis": "A failed computational comparison is not evidence against the biological mechanism.",
            "next_action": "Inspect the raw query plan and compare bounded neighborhoods before attempting a new formulation.",
            "hypothesis_status": "blocked", "candidate_id": key, "formulation": form,
            "query_text": query, "runtime_seconds": time.monotonic() - started,
        })
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", default=".")
    parser.add_argument("--rule-id")
    parser.add_argument("--timeout-seconds", type=float, default=180)
    parser.add_argument("--maximum-pairs", type=int, default=500000)
    parser.add_argument("--stop-at")
    args = parser.parse_args()
    missing = [x for x in REQUIRED if not os.environ.get(x)]
    if missing:
        raise RuntimeError("Missing service variables: " + ",".join(missing))
    selected = {
        r["rule_id"]: r for r in records(RUN / "rules.jsonl")
        if r["round_id"] == "round-0004" and MARKER in r["execution"]["cypher"]
        and re.search(args.family, r["family_id"])
        and (not args.rule_id or args.rule_id == r["rule_id"])
    }
    ledger = list(records(RUN / "research-log.jsonl"))
    forms = {
        "raw-preaggregated-equivalent", "raw-body-equivalent",
        "raw-eager-neighborhood-equivalent", "raw-genetic-first-family-equivalent",
    }
    done = {(e["details"].get("candidate_id"), e["details"].get("formulation"))
            for e in ledger if e["details"].get("formulation") in forms}
    verified = {
        e["details"].get("candidate_id") for e in ledger
        if e["details"].get("formulation") in forms and e["event_type"] == "query"
        and e["details"].get("outcome") in ("completed", "empty")
        and json.loads(e["details"]["result_summary"]).get("exact_payload_match")
    }
    expected = {key: hashlib.sha256() for key in selected}
    counts = {key: 0 for key in selected}
    for row in records(RUN / "predictions.jsonl"):
        key = row["rule_id"]
        if key in selected:
            expected[key].update(normalized(row))
            counts[key] += 1
    closure = predicate_expansion_record(["biolink:affects"])
    types = "|".join(sorted(neo4j_relationship_type(p) for p in closure["expanded_predicates"]))
    predicates = json.dumps(closure["expanded_predicates"], separators=(",", ":"))
    with GraphDatabase.driver(
        os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        max_transaction_retry_time=0, connection_timeout=15,
    ) as driver:
        for key, rule in selected.items():
            if args.stop_at and datetime.now().astimezone() >= datetime.fromisoformat(args.stop_at):
                print("Access verification time reserve reached; leave remaining checks explicit.")
                return
            if key in verified:
                print("RAW EQUIVALENCE ALREADY VERIFIED", key, flush=True)
                continue
            if shutil.disk_usage(RUN).free < 5 * 1024**3:
                raise RuntimeError("Disk reserve breached before raw equivalence check")
            prefix, body = rule["execution"]["cypher"].split(MARKER, 1)
            variable = re.search(r"WITH DISTINCT chemical,(\w+)", prefix).group(1)
            raw_match = (
                f"MATCH (chemical:Drug)-[uncached:{types}]->({variable}:GeneOrGeneProduct) "
                f"WHERE uncached.predicate IN {predicates} "
                "AND uncached.qualified_predicate='biolink:causes' "
                "AND any(source IN ['infores:chembl','infores:gtopdb','infores:drugcentral'] "
                "WHERE source IN coalesce(uncached.primary_knowledge_sources,[])) "
            )
            preaggregated = raw_match + f"WITH DISTINCT chemical,{variable} " + body.strip()
            eager = (
                "CALL () { " + raw_match
                + f"RETURN collect(DISTINCT {{chemical:chemical,target:{variable}}}) AS neighborhood "
                + "} UNWIND neighborhood AS access_pair "
                + f"WITH access_pair.chemical AS chemical,access_pair.target AS {variable} "
                + body.strip()
            )
            alternatives = [
                ("raw-body-equivalent", body.strip()),
                ("raw-preaggregated-equivalent", preaggregated),
                ("raw-eager-neighborhood-equivalent", eager),
            ]
            if key.removesuffix("-full-closure") == "r4-family-genetic-direct-target-genetics":
                alternatives.append(("raw-genetic-first-family-equivalent", genetic_first_family_query(key)))
            for form, query in alternatives:
                if (key, form) in done:
                    continue
                if args.stop_at and datetime.now().astimezone() >= datetime.fromisoformat(args.stop_at):
                    return
                if compare(driver, key, form, query, expected[key], counts[key], args):
                    break


if __name__ == "__main__":
    main()
