"""Finish the all-source ablation with bounded endpoint-pair execution."""

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from neo4j import GraphDatabase, Query, READ_ACCESS

from miner2049er.rule_recorder import build_rule
from miner2049er.schema_validation import validate_document

from audit import TRAIN_QUERY, normalized, pair_bytes, records
from probe import REQUIRED, RUN, log_event
from reverse_regulation import bounded


QUERY = """
MATCH (chemical:Drug)-[direct:{{relationship_types:direct}}]->(disease:Disease)
WHERE direct.predicate IN {{predicates:direct}}
WITH DISTINCT chemical,disease
CALL (chemical,disease) {
  MATCH (gene:GeneOrGeneProduct)-[causal:{{relationship_types:causal}}]->(disease)
  WHERE causal.predicate IN {{predicates:causal}}
  WITH DISTINCT chemical,gene
  MATCH (regulator:GeneOrGeneProduct)-[bridge:{{relationship_types:bridge}}]->(gene)
  WHERE bridge.predicate IN {{predicates:bridge}}
    AND bridge.qualified_predicate='biolink:causes'
    AND bridge.object_direction_qualifier IN ['increased','decreased']
    AND bridge.object_aspect_qualifier IN ['activity','activity_or_abundance']
    AND regulator<>gene
  WITH DISTINCT chemical,regulator,gene,bridge.object_direction_qualifier AS regulatory_direction
  MATCH (chemical)-[target:{{relationship_types:target}}]->(regulator)
  WHERE target.predicate IN {{predicates:target}}
    AND target.qualified_predicate='biolink:causes'
    AND target.object_direction_qualifier IN ['increased','decreased']
    AND target.object_aspect_qualifier IN ['activity','activity_or_abundance']
    AND target.object_direction_qualifier<>regulatory_direction
  RETURN count(DISTINCT gene) AS support_count
}
WITH chemical,disease,support_count WHERE support_count>0
RETURN chemical.id AS subject_id,disease.id AS object_id,support_count
""".strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=120)
    parser.add_argument("--stop-at")
    args = parser.parse_args()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing service variables: " + ", ".join(missing))
    ledger = list(records(RUN / "research-log.jsonl"))
    attempted = {
        e["details"].get("candidate_id") for e in ledger
        if e["details"].get("formulation") in (
            "pairwise-causal-first-complete", "pairwise-causal-first-terminal"
        )
    }
    manifest = json.loads((RUN / "run.json").read_text())
    here = Path(__file__).resolve().parent
    with GraphDatabase.driver(
        os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        max_transaction_retry_time=0, connection_timeout=15,
    ) as driver:
        for suffix in ("", "-full-closure"):
            key = "r4-regulatory-net-decrease-no-curation" + suffix
            if key in attempted:
                continue
            if args.stop_at and datetime.now().astimezone() >= datetime.fromisoformat(args.stop_at):
                return
            if shutil.disk_usage(RUN).free < 5 * 1024**3:
                raise RuntimeError("Disk reserve breached before all-source execution engineering")
            if key in {r["rule_id"] for r in records(RUN / "rules.jsonl")}:
                continue
            path = here / "active-candidates" / (key + ".json")
            candidate = json.loads(path.read_text())
            prior_template = candidate["execution"]["cypher_template"]
            candidate["execution"]["cypher_template"] = QUERY
            rule = build_rule(candidate, manifest)
            query = rule["execution"]["cypher"]
            log_event("observation", "Bind both direct endpoints before the all-source regulatory expansion: " + key, {
                "source": "The earlier flat, drug-grouped, and disease-grouped complete queries timed out; their bounded comparisons matched exactly.",
                "finding": "The new query starts from distinct direct drug-disease endpoint pairs, binds the disease causal genes first, deduplicates regulator-direction contexts, and only then tests signed target evidence from the already bound drug.",
                "implication": "This changes execution shape only. No source, predicate, qualifier, endpoint, gene-distinctness, or support definition is weakened.",
                "next_action": "Attempt the complete query once within the existing timeout. If it completes, record its unchanged biological rule and evaluate the previously missing curation-removal control, subject to the shared duplicate ledger.",
                "candidate_id": key, "prior_cypher_template": prior_template,
                "replacement_cypher_template": QUERY,
            })
            start = time.monotonic()
            stage_statement = "EXPLAIN " + query
            stage_form = "pairwise-causal-first-explain"
            stage_parameters = {}
            try:
                with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                    plan = session.run(Query("EXPLAIN " + query, timeout=30)).consume().plan
                log_event("query", "Inspect the per-pair regulatory execution plan: " + key, {
                    "purpose": "Inspect the endpoint-bound plan before the complete execution attempt.",
                    "query_language": "cypher", "query_text": "EXPLAIN " + query,
                    "outcome": "completed", "result_summary": json.dumps(plan),
                    "candidate_id": key, "formulation": "pairwise-causal-first-explain",
                    "next_action": "Compare the same ten previously selected disease neighborhoods before the complete run.",
                })
                prior_samples = [
                    e for e in ledger if e["details"].get("candidate_id") == key
                    and e["details"].get("formulation") == "disease-first-sample-identifiers"
                ]
                prior_results = [
                    e for e in ledger if e["details"].get("candidate_id") == key
                    and e["details"].get("formulation") == "disease-first-bounded"
                    and e["event_type"] == "query"
                ]
                if prior_samples and prior_results:
                    parameters = {"diseases": json.loads(prior_samples[-1]["details"]["result_summary"])}
                    sample_query = bounded(query)
                    stage_statement = sample_query
                    stage_form = "pairwise-causal-first-bounded"
                    stage_parameters = parameters
                    with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                        sample = {
                            (row["subject_id"], row["object_id"]): normalized(row.data())
                            for row in session.run(Query(sample_query, timeout=60), parameters)
                        }
                    sample_hash = hashlib.sha256()
                    for pair in sorted(sample):
                        sample_hash.update(sample[pair])
                    reference = json.loads(prior_results[-1]["details"]["result_summary"])
                    same = len(sample) == reference["predictions"] and sample_hash.hexdigest() == reference["payload_sha256"]
                    metrics = {
                        "exact_payload_match": same, "baseline_predictions": reference["predictions"],
                        "variant_predictions": len(sample),
                        "baseline_payload_sha256": reference["payload_sha256"],
                        "variant_payload_sha256": sample_hash.hexdigest(),
                    }
                    log_event("query", "Bounded per-pair regulatory comparison: " + key, {
                        "purpose": "Check endpoint-and-support equality on the identical graph-selected disease sample.",
                        "query_language": "cypher", "query_text": sample_query, "parameters": parameters,
                        "outcome": "completed", "result_summary": json.dumps(metrics),
                        "candidate_id": key, "formulation": "pairwise-causal-first-bounded",
                        "next_action": "Proceed to the complete query only if the bounded payloads agree.",
                    })
                    log_event("ablation", "Per-pair versus disease-grouped regulatory execution: " + key, {
                        "baseline": "The earlier disease-grouped query on the same ten disease identifiers",
                        "variant": "The per-drug-disease causal-first query on those identifiers",
                        "changed_components": ["endpoint binding and deduplication order only"],
                        "metrics": metrics, "interpretation": "Bounded equality is an execution check, not a whole-graph or biological validation.",
                        "decision": "keep_change" if same else "retest",
                    })
                    if not same:
                        raise RuntimeError("Bounded regulatory payloads differ")
                start = time.monotonic()
                stage_statement = query
                stage_form = "pairwise-causal-first-complete"
                stage_parameters = {}
                actual = {}
                with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                    for record in session.run(Query(query, timeout=args.timeout_seconds)):
                        row = record.data()
                        pair = row["subject_id"], row["object_id"]
                        payload = normalized(row)
                        if pair in actual and actual[pair] != payload:
                            raise RuntimeError("Conflicting duplicate raw output")
                        actual[pair] = payload
                        if len(actual) > 500000:
                            raise RuntimeError("Declared in-memory pair bound exceeded")
                digest, payload_digest = hashlib.sha256(), hashlib.sha256()
                for pair in sorted(actual):
                    digest.update(pair_bytes({"subject_id": pair[0], "object_id": pair[1]}))
                    payload_digest.update(actual[pair])
                runtime = time.monotonic() - start
                log_event("query", "Pairwise causal-first complete regulatory query: " + key, {
                    "purpose": "Complete the otherwise-identical removal of target-source curation.",
                    "query_language": "cypher", "query_text": query,
                    "outcome": "completed" if actual else "empty",
                    "result_summary": json.dumps({"predictions": len(actual), "pair_sha256": digest.hexdigest(), "payload_sha256": payload_digest.hexdigest()}),
                    "runtime_seconds": runtime, "candidate_id": key,
                    "formulation": "pairwise-causal-first-complete",
                    "next_action": "Compute visible-label aggregates and record the complete candidate using only the designated writer.",
                })
            except Exception as error:
                log_event("failure", "Pairwise causal-first regulation did not complete: " + key, {
                    "stage": "all-source raw execution engineering", "error": str(error),
                    "diagnosis": "The bounded per-pair formulation failed. This is an execution limitation, not evidence that the biological hypothesis is false.",
                    "next_action": "Preserve the complete query and timeout; do not automatically repeat it.",
                    "hypothesis_status": "blocked", "candidate_id": key,
                    "formulation": "pairwise-causal-first-terminal",
                    "failed_formulation": stage_form, "query_text": stage_statement,
                    "parameters": stage_parameters,
                    "runtime_seconds": time.monotonic() - start,
                })
                continue
            with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                training = {(r["subject_id"], r["object_id"]) for r in session.run(Query(TRAIN_QUERY, timeout=60))}
            log_event("query", "Read visible training targets after completed all-source regulation.", {
                "purpose": "Compute training-only aggregates for the complete candidate, never individual held-out labels.",
                "query_language": "cypher", "query_text": TRAIN_QUERY, "outcome": "completed",
                "result_summary": f"{len(training)} distinct visible target pairs.",
                "next_action": "Record the candidate profile before invoking the official recorder.",
            })
            hits = sum(pair in training for pair in actual)
            metrics = {
                "candidate_id": key, "formulation": "candidate", "predictions": len(actual),
                "visible_hits": hits, "eligible_predictions": len(actual) - hits,
                "visible_precision_lower_bound": hits / len(actual) if actual else 0,
                "pair_sha256": digest.hexdigest(), "uses_treatment_edges": rule["uses_treatment_edges"],
            }
            parent = candidate.get("parent_rule_id")
            if parent and parent not in {r["rule_id"] for r in records(RUN / "rules.jsonl")}:
                candidate.pop("parent_rule_id")
                log_event("observation", "Record an executable closure control independently of its unrecorded draft parent.", {
                    "source": "Current rule ledger and the completed all-source candidate query.",
                    "finding": f"The draft parent {parent} is not recorded, but {key} completed. Its optional ledger parent link is removed; the full rule remains self-contained.",
                    "implication": "Only publication dependency metadata changes. No graph condition or prediction changes.",
                    "next_action": "Retain the failed-parent comparison in the research history and record this completed rule independently.",
                    "candidate_id": key,
                })
            validate_document(candidate, "rule-candidate.schema.json")
            path.write_text(json.dumps(candidate, indent=2) + "\n")
            log_event("query", "Candidate aggregate profile: " + key + " (candidate)", {
                "purpose": candidate["hypothesis"], "query_language": "cypher", "query_text": query,
                "outcome": "completed" if actual else "empty", "result_summary": json.dumps(metrics),
                "runtime_seconds": runtime, "candidate_id": key, "formulation": "candidate",
                "metrics": metrics, "next_action": "Record this complete executable rule through miner-record-rule.",
            })
            command = [
                "uv", "run", "python", str(here / "work.py"), "record",
                "--rule-id", key, "--include-full", "--timeout-seconds", str(args.timeout_seconds),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            print(result.stdout, flush=True)
            if result.returncode:
                raise RuntimeError(result.stderr[-8000:])
            if not suffix:
                from work import feedback_after_record
                feedback_after_record(key, 60)


if __name__ == "__main__":
    main()
