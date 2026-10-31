"""Serial mining workflow; only the designated CLIs persist research and rules."""

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from neo4j import GraphDatabase, Query, READ_ACCESS

from miner2049er.rule_recorder import build_rule

from audit import TRAIN_QUERY, EVALUATIONS, pair_bytes, records
from probe import RUN, REQUIRED, log_event


CUTOFF = datetime.fromisoformat("2026-09-15T15:22:23-04:00")
ACTIVE = Path(__file__).resolve().parent / "active-candidates"


def events():
    return list(records(RUN / "research-log.jsonl"))


def command(args):
    print("COMMAND", " ".join(args), flush=True)
    return subprocess.run(args, text=True, capture_output=True)


def resource_check():
    if datetime.now().astimezone() >= CUTOFF:
        raise RuntimeError("New-work cutoff reached; switch to wrap-up.")
    free = shutil.disk_usage(RUN).free
    if free < 5 * 1024**3:
        raise RuntimeError(f"Disk reserve breached: {free} bytes free")


def dependency_order(candidates, priority=(), recorded=()):
    pending = {c["rule_id"]: c for c in candidates}
    available = set(recorded)
    ordered = []
    ranks = {key: index for index, key in enumerate(priority)}
    while pending:
        ready = [
            c for c in pending.values()
            if c.get("parent_rule_id") not in pending or c.get("parent_rule_id") in available
        ]
        if not ready:
            raise ValueError("Candidate parent dependencies contain a cycle")
        ready.sort(key=lambda c: (
            ranks.get(c["rule_id"], len(ranks)),
            c["rule_id"].endswith("-full-closure"), c["family_id"], c["rule_id"],
        ))
        candidate = ready[0]
        ordered.append(candidate)
        available.add(candidate["rule_id"])
        del pending[candidate["rule_id"]]
    return ordered


def feedback_after_record(key, timeout_seconds):
    """Check eligible-set identity locally before asking for aggregate feedback."""
    evaluated = {e["rule_id"] for e in records(EVALUATIONS)}
    if key in evaluated or len(evaluated) >= 180:
        return
    with GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        max_transaction_retry_time=0, connection_timeout=15,
    ) as driver:
        with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
            training = {
                (r["subject_id"], r["object_id"])
                for r in session.run(Query(TRAIN_QUERY, timeout=60))
            }
    hashes = {rule_id: hashlib.sha256() for rule_id in evaluated | {key}}
    counts = {rule_id: 0 for rule_id in hashes}
    for row in records(RUN / "predictions.jsonl"):
        rule_id = row["rule_id"]
        if rule_id in hashes and (row["subject_id"], row["object_id"]) not in training:
            hashes[rule_id].update(pair_bytes(row))
            counts[rule_id] += 1
    digest = hashes[key].hexdigest()
    duplicate_ids = sorted(other for other in evaluated if hashes[other].hexdigest() == digest)
    log_event("query", "Visible-label exclusion and feedback duplicate preflight: " + key, {
        "purpose": "Compare complete eligible endpoint sets without inspecting any held-out pair labels.",
        "query_language": "cypher", "query_text": TRAIN_QUERY, "outcome": "completed",
        "result_summary": json.dumps({
            "visible_target_pairs": len(training), "eligible_predictions": counts[key],
            "eligible_pair_sha256": digest, "identical_already_scored_rules": duplicate_ids,
        }),
        "candidate_id": key,
        "next_action": "Submit only if at least five eligible predictions remain and no already scored eligible set is identical.",
    })
    if counts[key] < 5 or duplicate_ids:
        return
    args_list = [
        "uv", "run", "miner-submit-feedback", "--run-dir", str(RUN),
        "--rule", key, "--timeout-seconds", str(timeout_seconds),
    ]
    # The submitter owns all persistence of evaluator output.
    started = time.monotonic()
    result = command(args_list)
    print(result.stdout, flush=True)
    if result.returncode:
        log_event("failure", "Selected feedback submission did not complete: " + key, {
            "stage": "aggregate feedback", "error": result.stderr[-8000:] or result.stdout[-8000:],
            "diagnosis": "The rule is already recorded; never run its recorder again.",
            "next_action": "Inspect aggregate evaluations and retry only the official feedback submitter if no result exists.",
            "hypothesis_status": "active", "candidate_id": key,
        })
        return
    log_event("query", "Official feedback completed: " + key, {
        "purpose": "Obtain aggregate held-out counts for a prespecified scientific comparison.",
        "query_language": "shell", "query_text": " ".join(args_list),
        "outcome": "completed", "result_summary": result.stdout,
        "runtime_seconds": time.monotonic() - started, "candidate_id": key,
        "next_action": "Compare matched component removals without interpreting unknown predictions as negatives.",
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["profile", "record", "feedback"])
    parser.add_argument("--family", default=".")
    parser.add_argument("--rule-id")
    parser.add_argument("--exclude", default=r"^$")
    parser.add_argument("--timeout-seconds", type=float, default=120)
    parser.add_argument("--maximum-pairs", type=int, default=500000)
    parser.add_argument("--include-full", action="store_true")
    parser.add_argument("--compare-raw", action="store_true")
    parser.add_argument("--repeat-profile", action="store_true")
    parser.add_argument("--approved-feedback", type=Path)
    parser.add_argument("--feedback-after-record", action="store_true")
    parser.add_argument("--priority-file", type=Path)
    parser.add_argument("--checkpoint-every", type=int, default=0)
    parser.add_argument("--stop-at", type=datetime.fromisoformat)
    args = parser.parse_args()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing service variables: " + ", ".join(missing))
    candidates = [json.loads(p.read_text()) for p in ACTIVE.glob("*.json")]
    candidates = [
        c for c in candidates if re.search(args.family, c["family_id"])
        and (not args.rule_id or c["rule_id"] == args.rule_id)
        and not re.search(args.exclude, c["rule_id"])
        and (args.include_full or not c["rule_id"].endswith("-full-closure"))
    ]
    priority = args.priority_file.read_text().splitlines() if args.priority_file else []
    candidates = dependency_order(
        candidates, priority, {r["rule_id"] for r in records(RUN / "rules.jsonl")}
    )
    manifest = json.loads((RUN / "run.json").read_text())
    if manifest["current_round_id"] != "round-0004":
        raise RuntimeError("This workflow belongs only to round-0004")
    rules = {c["rule_id"]: build_rule(c, manifest) for c in candidates}
    if args.mode == "profile":
        with GraphDatabase.driver(
            os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
            max_transaction_retry_time=0, connection_timeout=15,
        ) as driver:
            resource_check()
            start = time.monotonic()
            with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                training = {
                    (r["subject_id"], r["object_id"])
                    for r in session.run(Query(TRAIN_QUERY, timeout=60))
                }
            log_event("query", "Load visible targets for candidate-only aggregate profiling.", {
                "purpose": "Evaluate candidates against visible training labels, not hidden labels.",
                "query_language": "cypher", "query_text": TRAIN_QUERY, "outcome": "completed",
                "result_summary": f"{len(training)} visible target pairs; no target-pair export.",
                "runtime_seconds": time.monotonic() - start,
                "next_action": "Execute biologically specified candidate queries serially with explicit timeouts.",
            })
            known_families = {
                e["details"].get("mechanism_family") for e in events() if e["event_type"] == "hypothesis"
            }
            failed_families = set()
            for candidate in candidates:
                resource_check()
                key, family = candidate["rule_id"], candidate["family_id"]
                query = rules[key]["execution"]["cypher"]
                previous_profiles = [
                    e for e in events() if e["event_type"] == "query"
                    and e["details"].get("candidate_id") == key
                    and e["details"].get("formulation") == "candidate"
                    and e["details"].get("query_text") == query
                ]
                if previous_profiles and not args.repeat_profile:
                    print("PROFILE ALREADY LOGGED; NOT REPEATING", key, flush=True)
                    continue
                if family in failed_families:
                    print("DEFER FAMILY AFTER FAILURE", key, flush=True)
                    continue
                if family not in known_families:
                    log_event("hypothesis", "Test " + candidate["name"] + " and structural controls.", {
                        "mechanism_family": family, "rationale": candidate["hypothesis"],
                        "proposed_test": "Compare the specified baseline, structural corroboration, component-removal, direction, and full-descendant controls.",
                        "variables_to_explore": [
                            "graph topology", "causal activity direction", "independent evidence arms",
                            "full versus explicitly filtered predicate closure",
                        ],
                        "success_criterion": "Useful treatment prediction volume and precision with ablation-supported biological interpretation, not only source-count tuning.",
                        "next_action": "Execute complete candidates serially, recording zero results and failures.",
                    })
                    known_families.add(family)
                forms = [("candidate", query)]
                if args.compare_raw and "/* END CURATED ACCESS PATH */" in query:
                    forms.append(("unmaterialized", query.split("/* END CURATED ACCESS PATH */", 1)[1].strip()))
                form_results = {}
                for form, statement in forms:
                    resource_check()
                    started = time.monotonic()
                    print("PROFILE", key, form, flush=True)
                    try:
                        result_rows = {}
                        with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                            for record in session.run(Query(statement, timeout=args.timeout_seconds)):
                                row = record.data()
                                pair = (row["subject_id"], row["object_id"])
                                if pair in result_rows and result_rows[pair] != row:
                                    raise RuntimeError("Conflicting duplicate candidate output")
                                result_rows[pair] = row
                                if len(result_rows) > args.maximum_pairs:
                                    raise RuntimeError("Candidate output exceeds the declared in-memory pair bound")
                        digest = hashlib.sha256()
                        for pair in sorted(result_rows):
                            digest.update(pair_bytes(result_rows[pair]))
                        count = len(result_rows)
                        hit_count = sum(pair in training for pair in result_rows)
                        result = {
                            "candidate_id": key, "formulation": form,
                            "predictions": count, "visible_hits": hit_count,
                            "eligible_predictions": count - hit_count,
                            "visible_precision_lower_bound": hit_count / count if count else 0,
                            "pair_sha256": digest.hexdigest(),
                            "uses_treatment_edges": rules[key]["uses_treatment_edges"],
                        }
                        form_results[form] = result
                        print(json.dumps(result), flush=True)
                        log_event("query", "Candidate aggregate profile: " + key + " (" + form + ")", {
                            "purpose": candidate["hypothesis"],
                            "query_language": "cypher", "query_text": statement,
                            "outcome": "completed" if count else "empty",
                            "runtime_seconds": time.monotonic() - started,
                            "timeout_seconds": args.timeout_seconds,
                            "result_summary": json.dumps(result),
                            "candidate_id": key, "formulation": form,
                            "metrics": result,
                            "next_action": "Record this complete executable candidate through miner-record-rule; select feedback independently of arbitrary threshold sweeps.",
                        })
                    except Exception as error:
                        print("PROFILE FAILED", key, form, type(error).__name__, str(error), flush=True)
                        log_event("query", "Bounded candidate profile failure: " + key + " (" + form + ")", {
                            "purpose": candidate["hypothesis"],
                            "query_language": "cypher", "query_text": statement, "outcome": "failed",
                            "runtime_seconds": time.monotonic() - started,
                            "result_summary": type(error).__name__ + ": " + str(error),
                            "candidate_id": key, "formulation": form,
                            "next_action": "Engineer the query shape before retrying; failure is not a biological negative.",
                        })
                        log_event("failure", "Candidate formulation requires engineering: " + key, {
                            "stage": form + " candidate profile", "error": str(error),
                            "diagnosis": "The complete query did not finish within the resource contract.",
                            "next_action": "Inspect cardinalities and plan; reuse compact access paths or bounded per-pair existence tests.",
                            "hypothesis_status": "active", "candidate_id": key,
                        })
                        if form == "candidate":
                            failed_families.add(family)
                if len(form_results) == 2:
                    same = form_results["candidate"]["pair_sha256"] == form_results["unmaterialized"]["pair_sha256"]
                    log_event("ablation", "Raw-versus-materialized query equivalence: " + key, {
                        "baseline": "Otherwise-identical raw graph query without the compact target access path.",
                        "variant": "Recorded candidate using the documented curated target access path and raw predicate rematching.",
                        "changed_components": ["execution access path only; no biological condition changed"],
                        "metrics": {"identical_pair_sets": same, "predictions": form_results["candidate"]["predictions"]},
                        "interpretation": "A semantics-preserving optimization is required; no predictive improvement is attributed to materialization.",
                        "decision": "keep_change" if same else "retest",
                    })
        return

    approved = set(args.approved_feedback.read_text().splitlines()) if args.approved_feedback else set()
    completed_since_checkpoint = 0
    for position, candidate in enumerate(candidates):
        if args.stop_at and datetime.now().astimezone() >= min(args.stop_at, CUTOFF):
            recorded = {r["rule_id"] for r in records(RUN / "rules.jsonl")}
            pending = [c["rule_id"] for c in candidates[position:] if c["rule_id"] not in recorded]
            log_event("checkpoint", "Serial queue reached its reserved verification window.", {
                "progress": [
                    "Every preceding official command has returned; no new recording or feedback command is launched.",
                    f"{len(pending)} candidate documents remain unrecorded in this queue.",
                ],
                "active_hypotheses": ["Final reproduction and schema validation of the actual recorded experiment"],
                "next_actions": [
                    "Rerun surviving recorded queries, verify all artifacts, recompute both independent Pareto surfaces, and disclose pending work.",
                ],
                "unrecorded_candidate_ids": pending,
                "scheduled_stop_at": args.stop_at.isoformat(),
            })
            return
        resource_check()
        key = candidate["rule_id"]
        prior_rules = {r["rule_id"] for r in records(RUN / "rules.jsonl")}
        if args.mode == "record" and key in prior_rules:
            print("ALREADY RECORDED; NEVER APPENDING AGAIN", key, flush=True)
            if args.feedback_after_record and key in approved:
                feedback_after_record(key, 60)
            continue
        parent = candidate.get("parent_rule_id")
        if args.mode == "record" and parent and parent not in prior_rules:
            print("PARENT MUST BE RECORDED FIRST", key, parent, flush=True)
            continue
        profiles = [
            e for e in events() if e["event_type"] == "query"
            and e["details"].get("candidate_id") == key
            and e["details"].get("formulation") == "candidate"
            and e["details"].get("outcome") in ("completed", "empty")
            and e["details"]["query_text"] == rules[key]["execution"]["cypher"]
        ]
        if not profiles:
            print("NO COMPLETE MATCHING PROFILE", key, flush=True)
            continue
        profile = profiles[-1]["details"]["metrics"]
        if args.mode == "feedback":
            if key not in approved or key not in prior_rules:
                continue
            if not any(
                e["event_type"] == "query"
                and e["details"].get("candidate_id") == key
                and e["summary"] == "Official record completed: " + key
                and e["details"].get("outcome") == "completed"
                for e in events()
            ):
                print("WAIT FOR COMPLETED OFFICIAL RECORD VALIDATION", key, flush=True)
                continue
            evaluated = {e["rule_id"] for e in records(EVALUATIONS)}
            if key in evaluated:
                print("ALREADY SCORED", key, flush=True)
                continue
            if len(evaluated) >= 180:
                print("RESERVING TWENTY RUN SUBMISSIONS FOR LATER PORTFOLIO WORK", flush=True)
                break
            if profile["eligible_predictions"] < 5:
                print("BELOW FEEDBACK MINIMUM; RULE REMAINS RECORDED", key, flush=True)
                continue
            duplicate = False
            for event in events():
                details = event["details"]
                digest_map = details.get("prediction_pair_digests", {})
                if any(digest_map.get(other) == profile["pair_sha256"] for other in evaluated):
                    duplicate = True
                other = details.get("candidate_id")
                if other in evaluated and details.get("metrics", {}).get("pair_sha256") == profile["pair_sha256"]:
                    duplicate = True
            if duplicate:
                print("IDENTICAL SCORED SET; NO RESUBMISSION", key, flush=True)
                continue
            args_list = ["uv", "run", "miner-submit-feedback", "--run-dir", str(RUN), "--rule", key]
        else:
            args_list = [
                "uv", "run", "miner-record-rule", "--run-dir", str(RUN),
                "--candidate", str(ACTIVE / (key + ".json")),
                "--query-timeout-seconds", str(args.timeout_seconds),
            ]
        started = time.monotonic()
        result = command(args_list)
        print(result.stdout, flush=True)
        if result.returncode:
            print(result.stderr[-12000:], flush=True)
            persisted = key in {r["rule_id"] for r in records(RUN / "rules.jsonl")}
            log_event("failure", "Official command did not complete cleanly: " + key, {
                "stage": args.mode, "error": result.stderr[-8000:] or result.stdout[-8000:],
                "diagnosis": "The rule is already persisted." if persisted else "No rule record exists for this candidate.",
                "next_action": "If persisted, retry feedback only with miner-submit-feedback; otherwise diagnose before any recorder retry.",
                "hypothesis_status": "active", "candidate_id": key,
                "command": args_list, "runtime_seconds": time.monotonic() - started,
            })
            break
        log_event("query", "Official " + args.mode + " completed: " + key, {
            "purpose": "Use the deterministic designated writer without manual ledger persistence.",
            "query_language": "shell", "query_text": " ".join(args_list),
            "outcome": "completed", "result_summary": result.stdout,
            "runtime_seconds": time.monotonic() - started, "candidate_id": key,
            "next_action": "Compare aggregate feedback and component removals; preserve every prior record.",
        })
        if args.mode == "record" and args.feedback_after_record and key in approved:
            feedback_after_record(key, 60)
        completed_since_checkpoint += 1
        if args.checkpoint_every > 0 and completed_since_checkpoint >= args.checkpoint_every:
            directory = Path(__file__).resolve().parent
            for checkpoint_args in [
                ["uv", "run", "python", str(directory / "ablate.py"), "--partition", "training"],
                ["uv", "run", "python", str(directory / "ablate.py"), "--partition", "feedback"],
                ["uv", "run", "python", str(directory / "audit.py"), "--training"],
            ]:
                checkpoint = command(checkpoint_args)
                print(checkpoint.stdout, flush=True)
                if checkpoint.returncode:
                    raise RuntimeError(checkpoint.stderr[-8000:])
            completed_since_checkpoint = 0


if __name__ == "__main__":
    main()
