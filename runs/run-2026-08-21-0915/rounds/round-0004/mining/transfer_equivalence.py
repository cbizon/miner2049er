"""Remove each transfer access artifact and compare exact recorded payloads."""

import argparse
from datetime import datetime
import hashlib
import json
import os
import shutil
import time

from neo4j import GraphDatabase, Query, READ_ACCESS

from miner2049er.biolink_semantics import neo4j_relationship_type, predicate_expansion_record

from audit import normalized, records
from probe import REQUIRED, RUN, log_event


BOUNDARY = "WITH DISTINCT chemical,parent,gene,disease "
ROLES = ["infores:semmeddb", "infores:faers", "infores:multiomics-clinicaltrials"]


def raw_forms(rule):
    prefix, body = rule["execution"]["cypher"].split(BOUNDARY, 1)
    cohort, targets = prefix.split("MATCH (parent)-[parent_access:", 1)
    targets = "MATCH (parent)-[parent_access:" + targets
    indication = next(e for e in rule["graph_pattern"]["edges"] if e["id"] == "indication")
    predicates = indication["predicate_expansion"]["expanded_predicates"]
    types = "|".join(sorted(neo4j_relationship_type(p) for p in predicates))
    raw_cohort = (
        f"MATCH (parent:Drug)-[raw_indication:{types}]->(disease:Disease) "
        f"WHERE raw_indication.predicate IN {json.dumps(predicates)} "
        "UNWIND coalesce(raw_indication.primary_knowledge_sources,[]) AS raw_source "
        "WITH parent,disease,collect(DISTINCT raw_source) AS cohort_sources "
        f"WHERE all(source IN {json.dumps(ROLES)} WHERE source IN cohort_sources) "
    )
    # Both curated target joins already occur in the biological body. Removing
    # their access prefix avoids an unnecessary Cartesian expansion by gene.
    closure = predicate_expansion_record(["biolink:affects"])["expanded_predicates"]
    target_types = "|".join(sorted(neo4j_relationship_type(p) for p in closure))
    grouped_source = (
        "CALL () { "
        f"MATCH (drug:Drug)-[raw_target:{target_types}]->(gene:GeneOrGeneProduct) "
        f"WHERE raw_target.predicate IN {json.dumps(closure)} "
        "AND raw_target.qualified_predicate='biolink:causes' "
        "AND any(source IN ['infores:chembl','infores:gtopdb','infores:drugcentral'] "
        "WHERE source IN coalesce(raw_target.primary_knowledge_sources,[])) "
        "RETURN gene,collect(DISTINCT drug) AS drugs } "
    )
    grouped = grouped_source + "UNWIND drugs AS parent "
    bound_raw_cohort = raw_cohort.replace(
        "WITH parent,disease,collect", "WITH parent,gene,drugs,disease,collect"
    )
    expand_candidates = " UNWIND drugs AS chemical " + BOUNDARY + body
    eager_all = (
        "CALL () { " + raw_cohort
        + "RETURN collect(DISTINCT {parent:parent,disease:disease}) AS indications } "
        + grouped_source
        + "UNWIND drugs AS parent "
        + "UNWIND [indication IN indications WHERE indication.parent=parent] AS matched_indication "
        + "WITH parent,gene,drugs,matched_indication.disease AS disease "
        + expand_candidates
    )
    return [
        ("raw-parent-source-union", raw_cohort + targets + BOUNDARY + body),
        ("raw-both-target-neighborhoods", cohort + body),
        ("raw-target-gene-grouped", grouped + cohort + expand_candidates),
        ("raw-all-gene-grouped", grouped + bound_raw_cohort + expand_candidates),
        ("raw-all-access-features", raw_cohort + body),
        ("raw-all-eager-neighborhoods", eager_all),
    ]


def component(form):
    if form == "raw-parent-source-union":
        return "parent"
    if form in ("raw-both-target-neighborhoods", "raw-target-gene-grouped"):
        return "targets"
    return "all"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=150)
    parser.add_argument("--rule-id")
    parser.add_argument("--stop-at")
    args = parser.parse_args()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing service variables: " + ", ".join(missing))
    selected = {
        r["rule_id"]: r for r in records(RUN / "rules.jsonl")
        if r["rule_id"].startswith("r4-transfer-")
        and (args.rule_id is None or r["rule_id"] == args.rule_id)
    }
    hashes = {key: hashlib.sha256() for key in selected}
    counts = {key: 0 for key in selected}
    for row in records(RUN / "predictions.jsonl"):
        if row["rule_id"] in selected:
            hashes[row["rule_id"]].update(normalized(row))
            counts[row["rule_id"]] += 1
    ledger = list(records(RUN / "research-log.jsonl"))
    done = {
        (e["details"].get("candidate_id"), e["details"].get("formulation"))
        for e in ledger
        if e["event_type"] == "query" and e["details"].get("outcome") in ("completed", "empty")
    }
    blocked = {
        (e["details"].get("candidate_id"), e["details"].get("formulation"))
        for e in ledger
        if e["event_type"] == "failure"
        and str(e["details"].get("formulation", "")).startswith("raw-")
        and str(e["details"].get("candidate_id", "")).startswith("r4-transfer-")
    }
    verified = {
        (e["details"]["candidate_id"], component(e["details"]["formulation"]))
        for e in ledger if e["event_type"] == "query"
        and str(e["details"].get("candidate_id", "")).startswith("r4-transfer-")
        and str(e["details"].get("formulation", "")).startswith("raw-")
        and e["details"].get("outcome") in ("completed", "empty")
        and json.loads(e["details"]["result_summary"]).get("exact_payload_match")
    }
    with GraphDatabase.driver(
        os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        max_transaction_retry_time=0, connection_timeout=15,
    ) as driver:
        for key, rule in selected.items():
            for form, query in raw_forms(rule):
                if args.stop_at and datetime.now().astimezone() >= datetime.fromisoformat(args.stop_at):
                    print("Access verification time reserve reached; leave remaining checks explicit.")
                    return
                if (key, form) in done or (key, form) in blocked or (key, component(form)) in verified:
                    continue
                if shutil.disk_usage(RUN).free < 5 * 1024**3:
                    raise RuntimeError("Disk reserve breached")
                start = time.monotonic()
                print(key, form, flush=True)
                try:
                    rows = {}
                    with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                        for record in session.run(Query(query, timeout=args.timeout_seconds)):
                            row = record.data()
                            pair = row["subject_id"], row["object_id"]
                            payload = normalized(row)
                            if pair in rows and rows[pair] != payload:
                                raise RuntimeError("Conflicting duplicate raw prediction")
                            rows[pair] = payload
                            if len(rows) > 500000:
                                raise RuntimeError("In-memory pair bound exceeded")
                    actual = hashlib.sha256()
                    for pair in sorted(rows):
                        actual.update(rows[pair])
                    same = len(rows) == counts[key] and actual.hexdigest() == hashes[key].hexdigest()
                    metrics = {
                        "exact_payload_match": same, "raw_rows": len(rows),
                        "stored_rows": counts[key], "raw_sha256": actual.hexdigest(),
                        "stored_sha256": hashes[key].hexdigest(),
                    }
                    log_event("query", "Transfer raw-data component removal: " + key + " " + form, {
                        "purpose": "Remove stored access summaries without changing any biological rule condition.",
                        "query_language": "cypher", "query_text": query,
                        "outcome": "completed" if rows else "empty",
                        "result_summary": json.dumps(metrics), "candidate_id": key,
                        "formulation": form, "runtime_seconds": time.monotonic() - start,
                        "next_action": "Retain materialized access only if exact outputs agree.",
                    })
                    log_event("ablation", "Access-feature component removal: " + key + " " + form, {
                        "baseline": "Raw data computation of " + form,
                        "variant": "Recorded compact-access query " + key,
                        "changed_components": [form],
                        "metrics": metrics,
                        "interpretation": "Computational equivalence is separate from predictive improvement or mechanistic proof.",
                        "decision": "keep_change" if same else "retest",
                    })
                    if not same:
                        raise RuntimeError("Raw access removal changed exact predictions")
                    verified.add((key, component(form)))
                except Exception as error:
                    log_event("failure", "Transfer raw-data comparison did not verify: " + key + " " + form, {
                        "stage": "raw access component removal", "error": str(error),
                        "diagnosis": "The specified bounded formulation failed; no biological failure is inferred.",
                        "next_action": "Profile the raw plan and preserve the unmatched verification as incomplete.",
                        "hypothesis_status": "blocked", "candidate_id": key, "formulation": form,
                        "query_text": query, "runtime_seconds": time.monotonic() - start,
                    })


if __name__ == "__main__":
    main()
