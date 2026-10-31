"""Test a disease-first raw execution plan without changing the biological rule."""

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

from audit import normalized, pair_bytes, records
from probe import REQUIRED, RUN, log_event


QUERY = """
MATCH (chemical:Drug)-[direct:{{relationship_types:direct}}]->(disease:Disease)
WHERE direct.predicate IN {{predicates:direct}}
WITH disease,collect(DISTINCT chemical) AS chemicals
CALL (disease,chemicals) {
  MATCH (gene:GeneOrGeneProduct)-[causal:{{relationship_types:causal}}]->(disease)
  WHERE causal.predicate IN {{predicates:causal}}
  WITH DISTINCT gene,chemicals
  MATCH (regulator:GeneOrGeneProduct)-[bridge:{{relationship_types:bridge}}]->(gene)
  WHERE bridge.predicate IN {{predicates:bridge}}
    AND bridge.qualified_predicate='biolink:causes'
    AND bridge.object_direction_qualifier IN ['increased','decreased']
    AND bridge.object_aspect_qualifier IN ['activity','activity_or_abundance']
    AND regulator<>gene
  WITH DISTINCT gene,regulator,bridge.object_direction_qualifier AS regulatory_direction,chemicals
  MATCH (chemical:Drug)-[target:{{relationship_types:target}}]->(regulator)
  WHERE target.predicate IN {{predicates:target}}
    AND target.qualified_predicate='biolink:causes'
    AND target.object_direction_qualifier IN ['increased','decreased']
    AND target.object_aspect_qualifier IN ['activity','activity_or_abundance']
    AND target.object_direction_qualifier<>regulatory_direction
    AND chemical IN chemicals
  RETURN chemical,count(DISTINCT gene) AS support_count
}
RETURN chemical.id AS subject_id,disease.id AS object_id,support_count
""".strip()


def bounded(query):
    boundary = "\nWITH "
    before, after = query.split(boundary, 1)
    return before + " AND disease.id IN $diseases" + boundary + after


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=120)
    parser.add_argument("--stop-at")
    args = parser.parse_args()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing service variables: " + ", ".join(missing))
    done = {
        (event["details"].get("candidate_id"), event["details"].get("formulation"))
        for event in records(RUN / "research-log.jsonl")
    }
    manifest = json.loads((RUN / "run.json").read_text())
    active = Path(__file__).resolve().parent / "active-candidates"
    with GraphDatabase.driver(
        os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        max_transaction_retry_time=0, connection_timeout=15,
    ) as driver:
        for suffix in ("", "-full-closure"):
            key = "r4-regulatory-net-decrease-no-curation" + suffix
            if (key, "disease-first-complete") in done:
                continue
            if args.stop_at and datetime.now().astimezone() >= datetime.fromisoformat(args.stop_at):
                return
            if shutil.disk_usage(RUN).free < 5 * 1024**3:
                raise RuntimeError("Disk reserve breached before bounded raw engineering")
            candidate = json.loads((active / (key + ".json")).read_text())
            old = build_rule(candidate, manifest)["execution"]["cypher"]
            changed = deepcopy(candidate)
            changed["execution"]["cypher_template"] = QUERY
            new = build_rule(changed, manifest)["execution"]["cypher"]
            causal_arm = new.split("CALL (disease,chemicals) {\n", 1)[1].split(
                "\n  WITH DISTINCT gene", 1
            )[0]
            selection = old.split("\nWITH ", 1)[0] + " AND EXISTS { " + causal_arm + " } " + (
                "\nRETURN DISTINCT disease.id AS disease_id ORDER BY disease_id LIMIT 10"
            )
            sample = []
            try:
                with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                    sample = [row["disease_id"] for row in session.run(Query(selection, timeout=60))]
                log_event("query", "Bound disease-first regulation by visible graph identifiers: " + key, {
                    "purpose": "Select ten lexical disease identifiers with direct and causal-gene evidence, without consulting any treatment label.",
                    "query_language": "cypher", "query_text": selection, "outcome": "completed",
                    "result_summary": json.dumps(sample),
                    "candidate_id": key, "formulation": "disease-first-sample-identifiers",
                    "next_action": "Compare drug-first and disease-first execution on identical bounded graph neighborhoods.",
                })
            except Exception as error:
                log_event("failure", "Could not select a bounded regulatory neighborhood: " + key, {
                    "stage": "raw execution engineering", "error": str(error),
                    "diagnosis": "The sample selector failed; do not interpret this as a biological result.",
                    "next_action": "Inspect the direct-arm access path before another formulation.",
                    "hypothesis_status": "blocked", "candidate_id": key,
                    "formulation": "disease-first-complete", "query_text": selection,
                })
                continue
            results = {}
            for form, query, parameters in (
                ("disease-first-explain", "EXPLAIN " + new, {}),
                ("drug-first-bounded", bounded(old), {"diseases": sample}),
                ("disease-first-bounded", bounded(new), {"diseases": sample}),
                ("disease-first-complete", new, {}),
            ):
                if (key, form) in done:
                    continue
                start = time.monotonic()
                try:
                    with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                        result = session.run(Query(query, timeout=args.timeout_seconds), parameters)
                        if form.endswith("explain"):
                            summary = {"plan": result.consume().plan}
                        else:
                            rows = {}
                            for record in result:
                                row = record.data()
                                pair = row["subject_id"], row["object_id"]
                                payload = normalized(row)
                                if pair in rows and rows[pair] != payload:
                                    raise RuntimeError("Conflicting duplicate output")
                                rows[pair] = payload
                                if len(rows) > 500000:
                                    raise RuntimeError("In-memory pair reserve exceeded")
                            exact, pairs = hashlib.sha256(), hashlib.sha256()
                            for pair in sorted(rows):
                                exact.update(rows[pair])
                                pairs.update(pair_bytes({"subject_id": pair[0], "object_id": pair[1]}))
                            summary = {
                                "predictions": len(rows), "payload_sha256": exact.hexdigest(),
                                "pair_sha256": pairs.hexdigest(),
                            }
                            results[form] = summary
                    log_event("query", "Disease-first raw regulatory engineering: " + key + " " + form, {
                        "purpose": "Constrain direct disease neighborhoods, deduplicate causal genes and regulator-sign pairs, then join incoming signed drug targets.",
                        "query_language": "cypher", "query_text": query, "parameters": parameters,
                        "outcome": "completed", "result_summary": json.dumps(summary),
                        "runtime_seconds": time.monotonic() - start,
                        "candidate_id": key, "formulation": form,
                        "next_action": "Compare complete endpoint and support payloads for bounded plans; only a completed full query can become a recorded candidate.",
                    })
                    print(key, form, json.dumps(summary)[:1000], flush=True)
                except Exception as error:
                    log_event("failure", "Disease-first raw regulation did not complete: " + key + " " + form, {
                        "stage": "raw execution engineering", "error": str(error),
                        "diagnosis": "This bounded formulation failed; the no-curation biological ablation remains unresolved.",
                        "next_action": "Preserve the plan and cardinality evidence; do not repeat the same failed formulation automatically.",
                        "hypothesis_status": "blocked", "candidate_id": key, "formulation": form,
                        "query_text": query, "parameters": parameters,
                        "runtime_seconds": time.monotonic() - start,
                    })
            if "drug-first-bounded" in results and "disease-first-bounded" in results:
                a, b = results["drug-first-bounded"], results["disease-first-bounded"]
                same = a == b
                log_event("ablation", "Bounded raw regulatory execution equivalence: " + key, {
                    "baseline": "Drug-first grouped query on ten prespecified disease identifiers",
                    "variant": "Disease-first grouped query on exactly the same identifiers",
                    "changed_components": ["join order and early deduplication only"],
                    "metrics": {
                        "exact_payload_match": same,
                        "baseline_predictions": a["predictions"],
                        "variant_predictions": b["predictions"],
                        "baseline_payload_sha256": a["payload_sha256"],
                        "variant_payload_sha256": b["payload_sha256"],
                    },
                    "interpretation": "A bounded equality check validates execution reformulation only, not whole-graph success or biological efficacy.",
                    "decision": "keep_change" if same else "retest",
                    "candidate_id": key,
                })


if __name__ == "__main__":
    main()
