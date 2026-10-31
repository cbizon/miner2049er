"""Test complete regulatory context access without persisting rule predictions."""

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
from miner2049er.schema_validation import validate_document

from audit import TRAIN_QUERY, normalized, pair_bytes, records
from causal_context import ARTIFACT, CUTOFF
from probe import REQUIRED, RUN, log_event


QUERY = """
MATCH (chemical:Drug)-[direct:{{relationship_types:direct}}]->(disease:Disease)
WHERE direct.predicate IN {{predicates:direct}}
WITH chemical,collect(DISTINCT disease) AS diseases
CALL (chemical,diseases) {
  MATCH (chemical)-[target:{{relationship_types:target}}]->(regulator:GeneOrGeneProduct)
  WHERE target.predicate IN {{predicates:target}}
    AND target.qualified_predicate='biolink:causes'
    AND target.object_direction_qualifier IN ['increased','decreased']
    AND target.object_aspect_qualifier IN ['activity','activity_or_abundance']
  WITH DISTINCT regulator,target.object_direction_qualifier AS drug_direction,diseases
  MATCH (regulator)-[context:MINER_R0004_SIGNED_CAUSAL_CONTEXT]->(disease:Disease)
  WHERE context.artifact_id='r0004-signed-regulator-causal-context-v1'
    AND context.run_id='run-2026-08-21-0915'
    AND disease IN diseases
  WITH regulator,disease,drug_direction,
    CASE WHEN drug_direction='increased' THEN context.decreased_gene_element_ids
         ELSE context.increased_gene_element_ids END AS downstream_gene_ids
  UNWIND downstream_gene_ids AS downstream_gene_id
  MATCH (gene:GeneOrGeneProduct)
  WHERE elementId(gene)=downstream_gene_id
  MATCH (regulator)-[bridge:{{relationship_types:bridge}}]->(gene)
  WHERE bridge.predicate IN {{predicates:bridge}}
    AND bridge.qualified_predicate='biolink:causes'
    AND bridge.object_direction_qualifier IN ['increased','decreased']
    AND bridge.object_aspect_qualifier IN ['activity','activity_or_abundance']
    AND regulator<>gene
    AND drug_direction<>bridge.object_direction_qualifier
  MATCH (gene)-[causal:{{relationship_types:causal}}]->(disease)
  WHERE causal.predicate IN {{predicates:causal}}
  RETURN disease,count(DISTINCT gene) AS support_count
}
RETURN chemical.id AS subject_id,disease.id AS object_id,support_count
""".strip()

FEATURE = {
    "name": "complete signed regulator-to-causal-disease context",
    "definition": (
        "A regulator has a causes-qualified affects-descendant edge to a distinct downstream "
        "gene with increased or decreased activity or activity_or_abundance, and that gene "
        "causes or contributes to a disease. Every such regulator-disease context is stored."
    ),
    "inputs": [
        "All raw GeneOrGeneProduct-to-GeneOrGeneProduct edges in the full Biolink 4.3.2 affects closure, with the stated causal, direction, and activity qualifiers",
        "All raw downstream-gene-to-Disease edges in the complete contributes_to closure, namely causes and contributes_to",
        "Original Neo4j endpoint identity, without treatment labels, external mappings, or feedback data",
    ],
    "construction": (
        "Deduplicate disease neighbors by downstream gene, then regulator-direction pairs by "
        "downstream gene. Group all paths by regulator and disease, and collect distinct "
        "downstream-gene node element identifiers separately for increased and decreased "
        "regulatory directions. Store both lists and their summed length in one relationship. "
        "Parallel source edges do not multiply support; a gene with both signs appears in "
        "both lists. Missing causal, direction, or aspect qualifiers do not qualify. Empty "
        "sign neighborhoods are empty lists. Write complete results in thousand-row "
        "transactions; no context is ranked or removed to satisfy resource limits."
    ),
    "formula": (
        "For a drug-regulator direction, retrieve the opposite regulatory-direction gene "
        "list to propose net-decreasing paths. Rematch every raw bridge and causal edge "
        "against this rule's exact expanded predicates and qualifiers. Prediction support "
        "is count(distinct rematched downstream gene nodes), not the stored list length."
    ),
    "interpretation": (
        "This is computational access, not an additional biological condition or a "
        "predictive score. No numerical support threshold is applied. Raw rematching "
        "prevents the full affects closure, including ameliorates_condition, from silently "
        "contributing excluded evidence. Element identifiers are local to the fixed Neo4j "
        "instance. Sign composition does not establish disease risk direction or efficacy."
    ),
    "neo4j_artifact_id": ARTIFACT,
}


def digest(rows):
    exact, pairs = hashlib.sha256(), hashlib.sha256()
    for pair in sorted(rows):
        exact.update(normalized(rows[pair]))
        pairs.update(pair_bytes(rows[pair]))
    return exact.hexdigest(), pairs.hexdigest()


def run_query(driver, query, parameters, key, form, timeout, training, return_rows=False):
    started = time.monotonic()
    try:
        rows = {}
        with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
            result = session.run(Query(query, timeout=timeout), parameters)
            if form.endswith("explain"):
                metrics = {"plan": result.consume().plan}
            else:
                for record in result:
                    row = record.data()
                    pair = row["subject_id"], row["object_id"]
                    if pair in rows and normalized(rows[pair]) != normalized(row):
                        raise RuntimeError("Conflicting duplicate context prediction")
                    rows[pair] = row
                    if len(rows) > 500000:
                        raise RuntimeError("In-memory complete-output bound exceeded")
                exact, pairs = digest(rows)
                hits = sum(pair in training for pair in rows)
                metrics = {
                    "candidate_id": key, "formulation": form,
                    "predictions": len(rows), "visible_hits": hits,
                    "eligible_predictions": len(rows) - hits,
                    "visible_precision_lower_bound": hits / len(rows) if rows else 0,
                    "payload_sha256": exact, "pair_sha256": pairs,
                }
        log_event("query", "Signed-context regulatory execution: " + key + " " + form, {
            "purpose": (
                "Compute the original raw biological rule without stored context access."
                if form.startswith(("raw-", "exhaustive-drug-partitioned-raw"))
                else "Use complete context access and rematch every raw biological edge without changing the hypothesis."
            ),
            "query_language": "cypher", "query_text": query, "parameters": parameters,
            "outcome": "completed" if rows or form.endswith("explain") else "empty",
            "result_summary": json.dumps(metrics), "metrics": metrics if rows or not form.endswith("explain") else {},
            "runtime_seconds": time.monotonic() - started,
            "candidate_id": key, "formulation": form, "artifact_id": ARTIFACT,
            "next_action": (
                "Require exhaustive domain coverage and exact complete payload agreement before claiming raw equivalence."
                if form.startswith(("raw-", "exhaustive-drug-partitioned-raw"))
                else "Require exact bounded and curated comparisons before recording the complete all-source candidate."
            ),
        })
        print(key, form, json.dumps(metrics)[:1000], flush=True)
        return (metrics, rows) if return_rows else metrics
    except Exception as error:
        log_event("failure", "Signed-context query did not complete: " + key + " " + form, {
            "stage": "regulatory context execution", "error": str(error),
            "diagnosis": "This formulation is not verified; no biological failure is inferred.",
            "next_action": "Preserve the exact query and investigate its plan rather than silently filtering support.",
            "hypothesis_status": "blocked", "candidate_id": key, "formulation": form,
            "artifact_id": ARTIFACT, "query_text": query, "parameters": parameters,
            "runtime_seconds": time.monotonic() - started,
        })
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=180)
    args = parser.parse_args()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing service variables: " + ", ".join(missing))
    if datetime.now().astimezone() >= CUTOFF or shutil.disk_usage(RUN).free < 5 * 1024**3:
        raise RuntimeError("New-work time or disk reserve reached")
    artifacts = {a["artifact_id"]: a for a in records(RUN / "neo4j-artifacts.jsonl")}
    if ARTIFACT not in artifacts:
        raise RuntimeError("Context artifact must be verified and inventoried first")
    manifest = json.loads((RUN / "run.json").read_text())
    if manifest["current_round_id"] != "round-0004":
        raise RuntimeError("This formulation belongs only to the active fourth round")
    active = Path(__file__).resolve().parent / "active-candidates"
    ledger = list(records(RUN / "research-log.jsonl"))
    existing = {r["rule_id"]: r for r in records(RUN / "rules.jsonl")}
    curated_rows = {
        (r["subject_id"], r["object_id"]): r
        for r in records(RUN / "predictions.jsonl")
        if r["rule_id"] == "r4-regulatory-net-decrease"
    }
    with GraphDatabase.driver(
        os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        max_transaction_retry_time=0, connection_timeout=15,
    ) as driver:
        with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
            training = {(r["subject_id"], r["object_id"]) for r in session.run(Query(TRAIN_QUERY, timeout=60))}
        log_event("query", "Read visible targets for context-access ablation profiling.", {
            "purpose": "Measure only visible training support for complete candidate outputs.",
            "query_language": "cypher", "query_text": TRAIN_QUERY, "outcome": "completed",
            "result_summary": str(len(training)) + " visible target pairs; no pair export.",
            "next_action": "Compare context-access outputs to existing raw execution hashes.",
        })
        for suffix in ("", "-full-closure"):
            key = "r4-regulatory-net-decrease-no-curation" + suffix
            if key in existing:
                raise RuntimeError("Never replace a recorded candidate: " + key)
            candidate = json.loads((active / (key + ".json")).read_text())
            changed = deepcopy(candidate)
            changed["execution"]["cypher_template"] = QUERY
            changed["derived_features"] = [FEATURE]
            validate_document(changed, "rule-candidate.schema.json")
            rendered = build_rule(changed, manifest)["execution"]["cypher"]
            run_query(driver, "EXPLAIN " + rendered, {}, key, "context-access-explain", 30, training)
            reference = [
                e for e in ledger if e["details"].get("candidate_id") == key
                and e["details"].get("formulation") == "drug-first-bounded"
                and e["details"].get("outcome") == "completed"
            ][-1]
            reference_metrics = json.loads(reference["details"]["result_summary"])
            bounded = rendered.replace(
                "\nWITH chemical,", " AND disease.id IN $diseases\nWITH chemical,", 1
            )
            result = run_query(driver, bounded, reference["details"]["parameters"], key,
                               "context-access-bounded", args.timeout_seconds, training)
            same = (
                result["predictions"] == reference_metrics["predictions"]
                and result["payload_sha256"] == reference_metrics["payload_sha256"]
            )
            log_event("ablation", "Bounded all-source context access versus raw regulation: " + key, {
                "baseline": "Prior drug-first raw query on the same ten graph-selected disease identifiers",
                "variant": "Complete materialized context access with exact raw predicate rematching",
                "changed_components": ["computational access path only"],
                "metrics": {"exact_payload_match": same, "baseline_predictions": reference_metrics["predictions"],
                            "variant_predictions": result["predictions"],
                            "baseline_payload_sha256": reference_metrics["payload_sha256"],
                            "variant_payload_sha256": result["payload_sha256"]},
                "interpretation": "Bounded equivalence does not establish whole-graph raw equivalence or therapeutic efficacy.",
                "decision": "keep_change" if same else "retest",
            })
            if not same:
                raise RuntimeError("Bounded context access changed exact outputs")
            if not suffix:
                curated = rendered.replace(
                    "\n  WITH DISTINCT regulator,",
                    "\n    AND any(source IN ['infores:chembl','infores:gtopdb','infores:drugcentral'] "
                    "WHERE source IN coalesce(target.primary_knowledge_sources,[]))\n  WITH DISTINCT regulator,", 1
                )
                curated_result = run_query(driver, curated, {}, key, "context-access-curated-complete",
                                           args.timeout_seconds, training)
                same = curated_result["predictions"] == len(curated_rows) and curated_result["payload_sha256"] == digest(curated_rows)[0]
                log_event("ablation", "Complete curated context access reproduces the recorded regulatory baseline.", {
                    "baseline": "Recorded curated-target net-decrease query, previously verified against raw data",
                    "variant": "The same curated biological rule executed through complete signed contexts",
                    "changed_components": ["computational access path only"],
                    "metrics": {"exact_payload_match": same, "baseline_predictions": len(curated_rows),
                                "variant_predictions": curated_result["predictions"],
                                "baseline_payload_sha256": digest(curated_rows)[0],
                                "variant_payload_sha256": curated_result["payload_sha256"]},
                    "interpretation": "An exact complete comparison tests acceleration without a biological restriction.",
                    "decision": "keep_change" if same else "retest",
                })
                if not same:
                    raise RuntimeError("Complete curated output mismatch")
            complete = run_query(driver, rendered, {}, key, "candidate", args.timeout_seconds, training)
            print("VERIFIED_CANDIDATE_FIELDS", key, json.dumps({
                "execution.cypher_template": QUERY, "derived_features": [FEATURE],
                "complete_profile": complete,
            }), flush=True)


if __name__ == "__main__":
    main()
