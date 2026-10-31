"""Read-only ledger analysis and serial exact reruns with official event logging."""

import argparse
from collections import defaultdict
from fractions import Fraction
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from neo4j import GraphDatabase, Query, READ_ACCESS
import orjson

from probe import REQUIRED, RUN, log_event


EVALUATIONS = Path("data/evaluations/run-2026-08-21-0915.jsonl")
INELIGIBLE = {
    "direct-curated-target-associated-disease": "Superseded by the HPO-source-enforced rule; prior research event 183 excludes the omitted-source formulation.",
    "direct-curated-decreased-target-associated-disease": "Superseded by the HPO-source-enforced rule; prior research event 183 excludes the omitted-source formulation.",
    "direct-curated-increased-target-associated-control": "Superseded by the HPO-source-enforced rule; prior research event 183 excludes the omitted-source formulation.",
    "shared-two-curated-targets-direct-transfer": "Research event 405 identifies a grouping mismatch: the explanation requires two targets with one parent, while the query pools targets across parents. The round-four pooled and same-parent candidates distinguish these semantics.",
}
TRAIN_QUERY = (
    "MATCH (s)-[t:TREATS|AMELIORATES_CONDITION|PREVENTATIVE_FOR_CONDITION]->(o) "
    "WHERE t.predicate IN ['biolink:treats','biolink:ameliorates_condition',"
    "'biolink:preventative_for_condition'] "
    "RETURN DISTINCT s.id AS subject_id,o.id AS object_id"
)


def records(path):
    with path.open("rb") as stream:
        for line in stream:
            if line.strip():
                yield orjson.loads(line)


def normalized(row):
    result = {k: row[k] for k in ("subject_id", "object_id", "support_count") if k in row}
    if "evidence_bindings" in row:
        result["evidence_bindings"] = sorted(row["evidence_bindings"])
    return orjson.dumps(result, option=orjson.OPT_SORT_KEYS) + b"\n"


def pair_bytes(row):
    return orjson.dumps([row["subject_id"], row["object_id"]]) + b"\n"


def surface(data, rules, treatment_free):
    eligible = [
        r for r in data if r["rule_id"] not in INELIGIBLE
        and (not treatment_free or not rules[r["rule_id"]]["uses_treatment_edges"])
    ]
    frontier = []
    for row in eligible:
        p = Fraction(row["hits"], row["predictions"]) if row["predictions"] else Fraction(0)
        r = Fraction(row["hits"], row["labels"]) if row["labels"] else Fraction(0)
        if not row["predictions"]:
            continue
        dominated = False
        for other in eligible:
            op = Fraction(other["hits"], other["predictions"]) if other["predictions"] else Fraction(0)
            ore = Fraction(other["hits"], other["labels"]) if other["labels"] else Fraction(0)
            if op >= p and ore >= r and (op > p or ore > r):
                dominated = True
                break
        if not dominated:
            frontier.append({
                "rule_id": row["rule_id"],
                "precision_lower_bound": float(p),
                "recall": float(r),
                "predictions": row["predictions"],
                "known_hits": row["hits"],
            })
    return sorted(frontier, key=lambda x: (x["precision_lower_bound"], x["rule_id"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--training", action="store_true")
    parser.add_argument("--rerun", action="store_true")
    parser.add_argument("--all-round-additions", action="store_true")
    parser.add_argument("--rerun-prefix", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=float, default=300)
    args = parser.parse_args()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing service variables: " + ", ".join(missing))
    snapshot_lock = (RUN / ".record-rule.lock").open("rb")
    fcntl.flock(snapshot_lock.fileno(), fcntl.LOCK_SH)
    rules = {r["rule_id"]: r for r in records(RUN / "rules.jsonl")}
    evaluations = list(records(EVALUATIONS))
    prior_rules = {key for key, rule in rules.items() if rule["round_id"] != "round-0004"}
    prior_feedback = [
        {"rule_id": e["rule_id"], "hits": e["counts"]["known_hits"],
         "predictions": e["counts"]["eligible_predictions"],
         "labels": e["counts"]["partition_labels"]}
        for e in evaluations if e["rule_id"] in prior_rules and e["partition"] == "feedback"
    ]
    prior_frontiers = {
        title: {row["rule_id"] for row in surface(prior_feedback, rules, free)}
        for title, free in (("treats_included", False), ("treats_excluded", True))
    }
    prior_sets = {
        "all_prior_rules": set(), "prior_treatment_free_rules": set(),
        "prior_treats_included_frontier": set(), "prior_treats_excluded_frontier": set(),
    }
    novelty = defaultdict(lambda: defaultdict(int))
    novel_mechanism_pairs = {
        "r4-family-genetic": set(),
        "r4-taxon-target-decreased": set(),
    }
    signed_groups = {
        context: {
            sign: "r4-regulatory-" + name + context
            for sign, name in (("unsigned", "unsigned"), ("decrease", "net-decrease"),
                               ("increase", "net-increase-control"))
        }
        for context in ("", "-genetic-disease", "-genetic-corroboration",
                        "-no-curation", "-no-curation-full-closure")
    }
    signed_pairs = {key: set() for group in signed_groups.values() for key in group.values()}
    train_pairs = set()
    driver = None
    if args.training or args.rerun:
        driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
            max_transaction_retry_time=0, connection_timeout=15,
        )
    if args.training:
        started = time.monotonic()
        with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
            for row in session.run(Query(TRAIN_QUERY, timeout=60)):
                train_pairs.add((row["subject_id"], row["object_id"]))
        log_event("query", "Read only visible training targets for complete-ledger aggregate analysis.", {
            "purpose": "Compute visible training statistics, never held-out pair labels.",
            "query_language": "cypher", "query_text": TRAIN_QUERY, "outcome": "completed",
            "result_summary": f"{len(train_pairs)} distinct visible target pairs.",
            "runtime_seconds": time.monotonic() - started,
            "next_action": "Stream recorded predictions and compute both independent training Pareto surfaces.",
        })
    counts, hits = defaultdict(int), defaultdict(int)
    hashes = {key: hashlib.sha256() for key in rules}
    pair_hashes = {key: hashlib.sha256() for key in rules}
    last_pairs = {}
    ordering_errors = 0
    for row in records(RUN / "predictions.jsonl"):
        key = row["rule_id"]
        pair = (row["subject_id"], row["object_id"])
        if key in last_pairs and pair <= last_pairs[key]:
            ordering_errors += 1
        last_pairs[key] = pair
        counts[key] += 1
        hashes[key].update(normalized(row))
        pair_hashes[key].update(pair_bytes(row))
        hits[key] += pair in train_pairs
        if key in prior_rules:
            prior_sets["all_prior_rules"].add(pair)
            if not rules[key]["uses_treatment_edges"]:
                prior_sets["prior_treatment_free_rules"].add(pair)
            for title, members in prior_frontiers.items():
                if key in members:
                    prior_sets["prior_" + title + "_frontier"].add(pair)
        elif args.training and pair not in train_pairs:
            novelty[key]["eligible_predictions"] += 1
            for title, pairs in prior_sets.items():
                novelty[key]["novel_vs_" + title] += pair not in pairs
            if key in novel_mechanism_pairs and pair not in prior_sets["all_prior_rules"]:
                novel_mechanism_pairs[key].add(pair)
        if args.training and key in signed_pairs and pair not in train_pairs:
            signed_pairs[key].add(pair)
    fcntl.flock(snapshot_lock.fileno(), fcntl.LOCK_UN)
    snapshot_lock.close()
    partitions = {
        "feedback": [{
            "rule_id": e["rule_id"], "hits": e["counts"]["known_hits"],
            "predictions": e["counts"]["eligible_predictions"],
            "labels": e["counts"]["partition_labels"],
        } for e in evaluations if e["partition"] == "feedback"]
    }
    if args.training:
        partitions["training"] = [{
            "rule_id": key, "hits": hits[key], "predictions": counts[key],
            "labels": len(train_pairs),
        } for key in rules]
    survivors = set()
    surfaces = {}
    for partition, data in partitions.items():
        surfaces[partition] = {}
        for title, free in [("treats_included", False), ("treats_excluded", True)]:
            front = surface(data, rules, free)
            surfaces[partition][title] = front
            survivors.update(x["rule_id"] for x in front)
            print(partition, title, len(front), json.dumps(front), flush=True)
    log_event("evaluation", "Recomputed separate precision-recall surfaces from complete available ledgers.", {
        "method": (
            "Strict Pareto dominance is computed independently within all evaluated rules and "
            "within treatment-free rules, using exact rational hit/count ratios rather than "
            "rounded metrics. Equal metric points retain separate memberships. Visible training "
            "statistics use only the current graph target closure. Feedback uses only read-only "
            "aggregate evaluator counts; it never exposes individual held-out pairs."
        ),
        "metrics": {
            "rules": len(rules), "distinct_families": len({r["family_id"] for r in rules.values()}),
            "prediction_rows_streamed": sum(counts.values()), "ordering_errors": ordering_errors,
            "feedback_evaluations": len(evaluations),
            "ineligible_superseded_rule_count": len(set(rules) & set(INELIGIBLE)),
            **{
                partition + "_" + title + "_count": len(front)
                for partition, values in surfaces.items() for title, front in values.items()
            },
        },
        "interpretation": "The surfaces have independent eligibility and dominance; association and mechanism strength are not inferred from predictive precision.",
        "decision": "retain",
        "next_action": "Rerun frontier members and selected round additions from their recorded executable Cypher.",
        "surfaces": surfaces,
        "eligibility_exclusions": INELIGIBLE,
        "all_rule_training_counts": [
            {"rule_id": key, "predictions": counts[key], "visible_hits": hits[key]}
            for key in rules
        ] if args.training else [],
        "prediction_pair_digests": {key: h.hexdigest() for key, h in pair_hashes.items()},
        "round_four_eligible_prediction_novelty": dict(novelty) if args.training else {},
        "novelty_reference_rule_counts": {
            "all_prior_rules": len(prior_rules),
            "prior_treatment_free_rules": sum(not rules[key]["uses_treatment_edges"] for key in prior_rules),
            **{"prior_" + title + "_frontier": len(members) for title, members in prior_frontiers.items()},
        },
        "novelty_definition": (
            "Each round-four complete endpoint set is compared with the union of prior-round "
            "recorded endpoint sets, once for all prior rules, once for prior treatment-free "
            "rules, and independently for each prior feedback Pareto frontier. Only visible "
            "training targets are excluded. Counts are not held-out false positives or "
            "estimated therapeutic discoveries. The append-only ledger places all prior-round "
            "predictions before round-four additions."
        ),
        "new_mechanism_novelty_overlap": {
            "reference": "All prior-round recorded predictions, with visible training labels excluded",
            "rule_counts": {key: len(pairs) for key, pairs in novel_mechanism_pairs.items()},
            "union_pairs": len(set.union(*novel_mechanism_pairs.values())),
            "intersection_pairs": len(set.intersection(*novel_mechanism_pairs.values())),
            "interpretation": (
                "This is a deduplicated novel endpoint volume comparison between protein-family "
                "genetic transfer and taxon-identified target inhibition. It is not a scored "
                "portfolio, and aggregate rule feedback cannot identify hits or precision in "
                "these novel subsets or their union."
            ),
        } if args.training and set(novel_mechanism_pairs) <= set(rules) else {},
        "regulatory_direction_overlap": {
            context or "causal_disease": {
                "eligible_unsigned": len(signed_pairs[group["unsigned"]]),
                "eligible_net_decrease": len(signed_pairs[group["decrease"]]),
                "eligible_net_increase": len(signed_pairs[group["increase"]]),
                "eligible_both_path_signs": len(signed_pairs[group["decrease"]] & signed_pairs[group["increase"]]),
                "unsigned_equals_signed_union": signed_pairs[group["unsigned"]] == (
                    signed_pairs[group["decrease"]] | signed_pairs[group["increase"]]
                ),
            }
            for context, group in signed_groups.items() if set(group.values()) <= set(rules)
        } if args.training else {},
        "direction_overlap_interpretation": (
            "Both signs mean that a pair has qualifying paths of both composed directions, "
            "possibly through different genes. This is not necessarily a contradictory "
            "assertion on one edge, and neither path establishes the net clinical effect."
        ),
        "corrected_transfer_payload_equivalence": [
            {
                "earlier_rule_id": earlier, "corrected_rule_id": corrected,
                "earlier_rows": counts[earlier], "corrected_rows": counts[corrected],
                "exact_endpoint_support_and_evidence_match": (
                    counts[earlier] == counts[corrected]
                    and hashes[earlier].hexdigest() == hashes[corrected].hexdigest()
                ),
                "earlier_payload_sha256": hashes[earlier].hexdigest(),
                "corrected_payload_sha256": hashes[corrected].hexdigest(),
            }
            for earlier, corrected in (
                ("shared-curated-target-direct-transfer", "r4-transfer-pooled-one-direct"),
                ("shared-two-curated-targets-direct-transfer", "r4-transfer-pooled-two-direct"),
            )
            if earlier in rules and corrected in rules
        ],
    })
    del prior_sets
    if args.rerun:
        if args.all_round_additions:
            survivors.update(key for key, r in rules.items() if r["round_id"] == "round-0004")
        survivors.update(
            key for key in rules
            if any(key.startswith(prefix) for prefix in args.rerun_prefix)
        )
        for key in sorted(survivors):
            query = rules[key]["execution"]["cypher"]
            started = time.monotonic()
            print("RERUN", key, flush=True)
            try:
                actual = {}
                duplicates = 0
                with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                    for record in session.run(Query(query, timeout=args.timeout_seconds)):
                        row = record.data()
                        pair = (row["subject_id"], row["object_id"])
                        value = normalized(row)
                        if pair in actual:
                            if actual[pair] != value:
                                raise RuntimeError("Conflicting duplicate returned")
                            duplicates += 1
                        actual[pair] = value
                digest = hashlib.sha256()
                for pair in sorted(actual):
                    digest.update(actual[pair])
                same = len(actual) == counts[key] and digest.hexdigest() == hashes[key].hexdigest()
                info = {
                    "rule_id": key, "stored_rows": counts[key], "live_rows": len(actual),
                    "same": same, "identical_duplicate_rows": duplicates,
                    "stored_sha256": hashes[key].hexdigest(), "live_sha256": digest.hexdigest(),
                }
                print(json.dumps(info), flush=True)
                log_event("query", "Exact stored-output rerun: " + key, {
                    "purpose": "Compare all live endpoint, support, and normalized evidence-binding payloads with the immutable recorded predictions.",
                    "query_language": "cypher", "query_text": query, "outcome": "completed",
                    "runtime_seconds": time.monotonic() - started,
                    "result_summary": json.dumps(info),
                    "next_action": "Retain reproducible outputs; investigate any mismatch before final synthesis.",
                })
                if not same:
                    raise RuntimeError("Live predictions differ from recorded predictions")
            except Exception as error:
                log_event("failure", "Survivor rerun did not verify: " + key, {
                    "stage": "exact stored-prediction rerun", "error": str(error),
                    "diagnosis": "This rule has not passed this round's exact reproduction check.",
                    "next_action": "Inspect the recorded query and resource bound without changing prior records.",
                    "hypothesis_status": "blocked",
                    "rule_id": key, "query_text": query,
                    "runtime_seconds": time.monotonic() - started,
                })
    if driver is not None:
        driver.close()
    if args.training and not args.rerun:
        directory = Path(__file__).resolve().parent
        pause = directory / "pause-after-checkpoint.json"
        if pause.exists():
            request = json.loads(pause.read_text())
            log_event("checkpoint", "Pause the serial queue at a completed writer boundary.", {
                "progress": [
                    "All preceding official recording commands have returned, and the current ledger snapshot and both Pareto surfaces are complete.",
                    request["reason"],
                    "No graph query from this checkpoint remains active.",
                ],
                "active_hypotheses": request.get(
                    "active_hypotheses",
                    ["Compact signed regulatory context as an execution optimization, not a new biological threshold"],
                ),
                "next_actions": [request["next_action"]],
            })
            print("SAFE_PAUSE: " + request["reason"], file=sys.stderr, flush=True)
            raise SystemExit(75)
        for helper in (
            "reverse_regulation.py", "pairwise_regulation.py", "component_baselines.py",
            "partition_regulation.py", "equivalence.py", "partition_transfer.py",
            "transfer_equivalence.py",
        ):
            command = [
                "uv", "run", "python", str(directory / helper),
                "--timeout-seconds", "120",
                "--stop-at", "2026-09-15T14:57:23-04:00",
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            print(result.stdout, flush=True)
            if result.returncode:
                log_event("failure", "Checkpoint access verification helper failed: " + helper, {
                    "stage": "serial checkpoint access verification",
                    "error": result.stderr[-8000:] or result.stdout[-8000:],
                    "diagnosis": "The helper did not complete; its recorded per-rule results remain authoritative.",
                    "next_action": "Investigate the failure before any retry; do not infer raw equivalence.",
                    "hypothesis_status": "blocked",
                })


if __name__ == "__main__":
    main()
