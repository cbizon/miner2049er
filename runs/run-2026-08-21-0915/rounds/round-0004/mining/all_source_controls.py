"""Render and profile matched sign controls; print candidate JSON without persistence."""

import argparse
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import shutil

from neo4j import GraphDatabase, Query, READ_ACCESS

from miner2049er.rule_recorder import build_rule
from miner2049er.schema_validation import validate_document

from audit import TRAIN_QUERY, records
from candidates import trapi
from causal_context import CUTOFF
from context_regulation import QUERY, run_query
from grouped_regulation import QUERY as RAW_QUERY
from probe import REQUIRED, RUN, log_event


DIRECTIVE = "    AND drug_direction<>bridge.object_direction_qualifier"
SELECTOR = (
    "CASE WHEN drug_direction='increased' THEN context.decreased_gene_element_ids\n"
    "         ELSE context.increased_gene_element_ids END"
)


def candidate_document(sign, full):
    suffix = "-full-closure" if full else ""
    root = Path(__file__).resolve().parent
    source_key = "r4-regulatory-net-decrease-no-curation" + suffix
    source = json.loads((root / "active-candidates" / (source_key + ".json")).read_text())
    candidate = deepcopy(source)
    name = "unsigned" if sign == "unsigned" else "net-increase-control"
    key = "r4-regulatory-" + name + "-no-curation" + suffix
    candidate["rule_id"] = key
    candidate["parent_rule_id"] = (
        key.removesuffix("-full-closure") if full else "r4-regulatory-net-decrease-no-curation"
    )
    candidate["status"] = "baseline"
    candidate["name"] = (
        "All-Source Signed Regulatory Composition Without Net Direction"
        if sign == "unsigned" else "All-Source Net-Increasing Regulatory Control"
    ) + (" (Full Descendant Control)" if full else "")
    candidate["hypothesis"] = (
        "Hold every source, constituent-edge qualifier, causal-disease arm, and direct "
        "corroboration condition fixed to test whether net-decreasing composition adds "
        "specific predictive value beyond signed network proximity or its opposite direction."
    )
    candidate["mechanism"] = {
        "score": "low",
        "rationale": "This is a matched direction control, not a corrective-treatment claim. Gene-disease causation does not establish the risk direction of normal gene function.",
    }
    constraints = candidate["graph_pattern"]["constraints"]
    sign_constraints = [c for c in constraints if "direction" in c["explanation"].lower() or "sign" in c["id"]]
    if len(sign_constraints) != 1:
        raise RuntimeError("Expected exactly one composed-direction constraint")
    if sign == "unsigned":
        constraints.remove(sign_constraints[0])
        selection = "context.increased_gene_element_ids + context.decreased_gene_element_ids"
        query = QUERY.replace(SELECTOR, selection).replace(DIRECTIVE + "\n", "")
        query = query.replace(
            "WITH DISTINCT regulator,target.object_direction_qualifier AS drug_direction,diseases",
            "WITH DISTINCT regulator,diseases",
        ).replace(
            "WITH regulator,disease,drug_direction,", "WITH regulator,disease,",
        ).replace(
            "  UNWIND downstream_gene_ids AS downstream_gene_id",
            "  UNWIND downstream_gene_ids AS downstream_gene_id\n"
            "  WITH DISTINCT regulator,disease,downstream_gene_id",
        )
        raw = RAW_QUERY.replace(DIRECTIVE + "\n", "")
        interpretation = (
            "Ignore composed direction while still requiring increased or decreased direction "
            "on each constituent edge. Retrieve both regulatory sign lists, then rematch all "
            "raw predicates and qualifiers. A gene present in both lists is counted only once "
            "per drug-disease prediction."
        )
    else:
        text = "The two recorded causal activity directions must agree, composing to net increase in the downstream gene."
        sign_constraints[0]["expression"] = text
        sign_constraints[0]["explanation"] = text
        selection = (
            "CASE WHEN drug_direction='increased' THEN context.increased_gene_element_ids\n"
            "         ELSE context.decreased_gene_element_ids END"
        )
        query = QUERY.replace(SELECTOR, selection).replace(DIRECTIVE, DIRECTIVE.replace("<>", "="))
        raw = RAW_QUERY.replace(DIRECTIVE, DIRECTIVE.replace("<>", "="))
        interpretation = (
            "Retrieve the same-sign regulatory gene list as the drug-regulator direction, "
            "then require equality of the two raw direction qualifiers. This composes to net "
            "increase, not a demonstrated increase or decrease in clinical disease risk."
        )
    candidate["execution"]["cypher_template"] = query
    candidate["execution"]["trapi"] = trapi(
        candidate["graph_pattern"]["edges"], candidate["graph_pattern"]["nodes"], constraints
    )
    candidate["plain_language_rule"] = (
        "Predict treatment when " + "; ".join(e["explanation"] for e in candidate["graph_pattern"]["edges"])
        + " " + " ".join(c["explanation"] for c in constraints) + " " + interpretation
    )
    feature = candidate["derived_features"][0]
    feature["formula"] = interpretation + " Prediction support is count(distinct rematched downstream gene nodes), with no numerical support threshold."
    candidate["limitations"].append(
        "This control isolates composed direction under the all-source policy; predictive association is not mechanistic validation."
    )
    validate_document(candidate, "rule-candidate.schema.json")
    return candidate, raw, source_key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sign", choices=["unsigned", "increase"], required=True)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=180)
    args = parser.parse_args()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing service variables: " + ", ".join(missing))
    candidate, raw_template, source_key = candidate_document(args.sign, args.full)
    manifest = json.loads((RUN / "run.json").read_text())
    if manifest["current_round_id"] != "round-0004":
        raise RuntimeError("These controls belong only to the fourth round")
    if args.profile:
        if datetime.now().astimezone() >= CUTOFF or shutil.disk_usage(RUN).free < 5 * 1024**3:
            raise RuntimeError("New-work time or disk reserve reached")
        if any(r["rule_id"] == candidate["rule_id"] for r in records(RUN / "rules.jsonl")):
            raise RuntimeError("Do not regenerate a recorded rule")
        ledger = list(records(RUN / "research-log.jsonl"))
        sample = [
            e["details"]["parameters"] for e in ledger
            if e["details"].get("candidate_id") == source_key
            and e["details"].get("formulation") == "drug-first-bounded"
            and e["details"].get("outcome") == "completed"
        ][-1]
        rendered = build_rule(candidate, manifest)["execution"]["cypher"]
        raw_candidate = deepcopy(candidate)
        raw_candidate["execution"]["cypher_template"] = raw_template
        raw_candidate["derived_features"] = []
        raw = build_rule(raw_candidate, manifest)["execution"]["cypher"]
        with GraphDatabase.driver(
            os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
            max_transaction_retry_time=0, connection_timeout=15,
        ) as driver:
            with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                training = {(r["subject_id"], r["object_id"]) for r in session.run(Query(TRAIN_QUERY, timeout=60))}
            log_event("query", "Read visible targets for matched all-source sign controls.", {
                "purpose": "Profile complete sign controls against visible targets only.",
                "query_language": "cypher", "query_text": TRAIN_QUERY, "outcome": "completed",
                "result_summary": str(len(training)) + " visible target pairs; no export.",
                "next_action": "Check raw bounded equivalence and complete candidate output before official recording.",
            })
            results = {}
            for form, query in (("raw-all-source-control-bounded", raw), ("context-all-source-control-bounded", rendered)):
                bounded = query.replace(
                    "\nWITH chemical,", " AND disease.id IN $diseases\nWITH chemical,", 1
                )
                results[form] = run_query(driver, bounded, sample, candidate["rule_id"], form,
                                          args.timeout_seconds, training)
            a, b = results.values()
            same = a["predictions"] == b["predictions"] and a["payload_sha256"] == b["payload_sha256"]
            log_event("ablation", "Bounded raw comparison for matched all-source direction control: " + candidate["rule_id"], {
                "baseline": "Raw signed-regulatory query on the same ten graph-selected diseases",
                "variant": "Complete context access with otherwise identical source and sign semantics",
                "changed_components": ["computational access path only"],
                "metrics": {"exact_payload_match": same, "raw_predictions": a["predictions"],
                            "context_predictions": b["predictions"],
                            "raw_payload_sha256": a["payload_sha256"], "context_payload_sha256": b["payload_sha256"]},
                "interpretation": "This checks bounded execution equivalence, not whole-graph equivalence or efficacy.",
                "decision": "keep_change" if same else "retest",
            })
            if not same:
                raise RuntimeError("Matched control raw and materialized outputs disagree")
            run_query(driver, rendered, {}, candidate["rule_id"], "candidate", args.timeout_seconds, training)
    print(json.dumps(candidate, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
