from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import orjson
from neo4j import READ_ACCESS, GraphDatabase, Query

from miner2049er.benchmark_config import (
    DEFAULT_BENCHMARK_CONFIG,
    load_benchmark_config,
)
from miner2049er.biolink_semantics import (
    FILTERED_EXPANSION,
    FULL_EXPANSION,
    neo4j_relationship_type,
    predicate_expansion_record,
    rule_evidence_tier,
    rule_treatment_predicates,
    validate_rule_biolink_semantics,
)
from miner2049er.feedback_submitter import FeedbackSubmissionError, submit_feedback
from miner2049er.run_artifacts import (
    DEFAULT_EVALUATIONS_DIR,
    validate_run_directory,
)
from miner2049er.schema_validation import read_jsonl, validate_document

PREDICATE_TOKEN = re.compile(r"\{\{predicates:([A-Za-z][A-Za-z0-9_.:-]*)\}\}")
RELATIONSHIP_TOKEN = re.compile(
    r"\{\{relationship_types:([A-Za-z][A-Za-z0-9_.:-]*)\}\}"
)
ALLOWED_RESULT_FIELDS = {
    "subject_id",
    "object_id",
    "support_count",
    "evidence_bindings",
}


def _load_active_manifest(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    validate_document(manifest, "run.schema.json")
    if manifest["status"] != "running" or not manifest["current_round_id"]:
        raise ValueError("Rules can be recorded only during an active round")
    return manifest


def _render_cypher(
    template: str,
    edges: list[dict[str, Any]],
) -> str:
    expansions = {
        edge["id"]: edge["predicate_expansion"]["expanded_predicates"]
        for edge in edges
    }
    referenced_predicate_edges = set(PREDICATE_TOKEN.findall(template))
    unknown_predicate_edges = referenced_predicate_edges - set(expansions)
    if unknown_predicate_edges:
        raise ValueError(
            "Cypher references unknown predicate edge IDs: "
            f"{sorted(unknown_predicate_edges)}"
        )
    missing_predicate_edges = set(expansions) - referenced_predicate_edges
    if missing_predicate_edges:
        raise ValueError(
            "Cypher must use a {{predicates:<edge-id>}} token for every graph edge: "
            f"{sorted(missing_predicate_edges)}"
        )

    referenced_relationship_edges = set(RELATIONSHIP_TOKEN.findall(template))
    unknown_relationship_edges = referenced_relationship_edges - set(expansions)
    if unknown_relationship_edges:
        raise ValueError(
            "Cypher references unknown relationship edge IDs: "
            f"{sorted(unknown_relationship_edges)}"
        )

    def predicate_replacement(match: re.Match[str]) -> str:
        predicates = expansions[match.group(1)]
        return json.dumps(predicates, separators=(",", ":"))

    def relationship_replacement(match: re.Match[str]) -> str:
        relationship_types = sorted(
            {
                neo4j_relationship_type(predicate)
                for predicate in expansions[match.group(1)]
            }
        )
        return "|".join(relationship_types)

    cypher = PREDICATE_TOKEN.sub(predicate_replacement, template)
    cypher = RELATIONSHIP_TOKEN.sub(relationship_replacement, cypher)
    if PREDICATE_TOKEN.search(cypher) or RELATIONSHIP_TOKEN.search(cypher):
        raise ValueError("Cypher contains unresolved Biolink expansion tokens")
    return cypher


def build_rule(candidate: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    validate_document(candidate, "rule-candidate.schema.json")
    if manifest["biolink_version"] != load_benchmark_config().biolink_version:
        raise ValueError("Run Biolink version does not match the pinned runtime")

    edges = []
    has_exclusions = False
    for candidate_edge in candidate["graph_pattern"]["edges"]:
        edge = {
            key: value
            for key, value in candidate_edge.items()
            if key not in {"excluded_predicates", "exclusion_rationale"}
        }
        excluded = candidate_edge.get("excluded_predicates", [])
        rationale = candidate_edge.get("exclusion_rationale")
        edge["predicate_expansion"] = predicate_expansion_record(
            candidate_edge["predicates"],
            excluded,
            rationale,
        )
        has_exclusions = has_exclusions or bool(excluded)
        edges.append(edge)

    cypher = _render_cypher(candidate["execution"]["cypher_template"], edges)
    rule = {
        "schema_version": "1.0",
        "run_id": manifest["run_id"],
        "round_id": manifest["current_round_id"],
        "rule_id": candidate["rule_id"],
        "family_id": candidate["family_id"],
        "parent_rule_id": candidate.get("parent_rule_id"),
        "name": candidate["name"],
        "status": candidate["status"],
        "plain_language_rule": candidate["plain_language_rule"],
        "hypothesis": candidate["hypothesis"],
        "variant_parameters": candidate.get("variant_parameters", {}),
        "graph_pattern": {
            "head": candidate["graph_pattern"]["head"],
            "nodes": candidate["graph_pattern"]["nodes"],
            "edges": edges,
            "constraints": candidate["graph_pattern"]["constraints"],
        },
        "derived_features": candidate.get("derived_features", []),
        "mechanism": candidate["mechanism"],
        "uses_treatment_edges": False,
        "evidence_tier": "treatment_free",
        "execution": {
            "cypher": cypher,
            "predicate_expansion": {
                "semantics": FILTERED_EXPANSION
                if has_exclusions
                else FULL_EXPANSION,
                "biolink_version": manifest["biolink_version"],
                "implementation": (
                    "miner-record-rule rendered each {{predicates:<edge-id>}} "
                    "placeholder from the pinned Biolink descendant closure "
                    "recorded for that graph-pattern edge before executing and "
                    "storing this Cypher."
                ),
            },
            "trapi": candidate["execution"]["trapi"],
        },
        "limitations": candidate.get("limitations", []),
    }
    rule["uses_treatment_edges"] = bool(rule_treatment_predicates(rule))
    rule["evidence_tier"] = rule_evidence_tier(rule)
    validate_document(rule, "rule.schema.json")
    validate_rule_biolink_semantics(
        rule,
        manifest["biolink_version"],
        manifest["target_predicates"],
    )
    return rule


def _neo4j_records(
    cypher: str,
    *,
    uri: str,
    user: str,
    password: str,
    timeout_seconds: float,
) -> Iterable[Mapping[str, Any]]:
    with GraphDatabase.driver(uri, auth=(user, password)) as driver, driver.session(
        database="neo4j",
        default_access_mode=READ_ACCESS,
    ) as session:
        result = session.run(Query(cypher, timeout=timeout_seconds))
        for record in result:
            yield record.data()


def _prediction_record(
    record: Mapping[str, Any],
    *,
    run_id: str,
    round_id: str,
    rule_id: str,
) -> dict[str, Any]:
    unknown_fields = set(record) - ALLOWED_RESULT_FIELDS
    if unknown_fields:
        raise ValueError(
            f"Rule {rule_id} returned unsupported fields: {sorted(unknown_fields)}"
        )
    subject_id = record.get("subject_id")
    object_id = record.get("object_id")
    if not isinstance(subject_id, str) or not subject_id:
        raise ValueError(f"Rule {rule_id} returned an invalid subject_id")
    if not isinstance(object_id, str) or not object_id:
        raise ValueError(f"Rule {rule_id} returned an invalid object_id")
    prediction = {
        "schema_version": "1.0",
        "run_id": run_id,
        "round_id": round_id,
        "rule_id": rule_id,
        "subject_id": subject_id,
        "object_id": object_id,
    }
    if "support_count" in record:
        support_count = record["support_count"]
        if (
            isinstance(support_count, bool)
            or not isinstance(support_count, int)
            or support_count < 0
        ):
            raise ValueError(f"Rule {rule_id} returned an invalid support_count")
        prediction["support_count"] = support_count
    if "evidence_bindings" in record:
        evidence_bindings = record["evidence_bindings"]
        if not isinstance(evidence_bindings, (list, tuple)) or not all(
            isinstance(binding, str) for binding in evidence_bindings
        ):
            raise ValueError(f"Rule {rule_id} returned invalid evidence_bindings")
        prediction["evidence_bindings"] = list(evidence_bindings)
    validate_document(prediction, "prediction.schema.json")
    return prediction


def _stage_predictions(
    records: Iterable[Mapping[str, Any]],
    *,
    run_dir: Path,
    run_id: str,
    round_id: str,
    rule_id: str,
) -> tuple[Path, int, int]:
    seen: dict[tuple[str, str], bytes] = {}
    duplicate_rows = 0
    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{rule_id}.",
        suffix=".predictions.jsonl",
        dir=run_dir,
        delete=False,
    ) as stream:
        path = Path(stream.name)
        try:
            for record in records:
                prediction = _prediction_record(
                    record,
                    run_id=run_id,
                    round_id=round_id,
                    rule_id=rule_id,
                )
                key = (prediction["subject_id"], prediction["object_id"])
                line = orjson.dumps(prediction, option=orjson.OPT_SORT_KEYS)
                prior = seen.get(key)
                if prior is not None:
                    if prior != line:
                        raise ValueError(
                            f"Rule {rule_id} returned conflicting duplicate "
                            f"prediction {key}"
                        )
                    duplicate_rows += 1
                    continue
                seen[key] = line
            for key in sorted(seen):
                stream.write(seen[key] + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise
    return path, len(seen), duplicate_rows


def _append_recording(
    *,
    run_dir: Path,
    evaluations_dir: Path,
    rule: dict[str, Any],
    staged_predictions: Path,
) -> dict[str, int]:
    lock_path = run_dir / ".record-rule.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        manifest = _load_active_manifest(run_dir)
        if manifest["run_id"] != rule["run_id"]:
            raise ValueError("The run changed while the rule query was executing")
        if manifest["current_round_id"] != rule["round_id"]:
            raise ValueError("The active round changed while the rule query was executing")
        validate_run_directory(run_dir, evaluations_dir)

        rules_path = run_dir / manifest["artifacts"]["rules"]
        predictions_path = run_dir / manifest["artifacts"]["predictions"]
        existing_rules = list(read_jsonl(rules_path, "rule.schema.json"))
        existing_rule_ids = {existing["rule_id"] for existing in existing_rules}
        if rule["rule_id"] in existing_rule_ids:
            raise ValueError(f"Rule ID is already recorded: {rule['rule_id']}")
        parent_rule_id = rule["parent_rule_id"]
        if parent_rule_id is not None and parent_rule_id not in existing_rule_ids:
            raise ValueError(f"Parent rule is not recorded: {parent_rule_id}")

        rules_size = rules_path.stat().st_size
        predictions_size = predictions_path.stat().st_size
        try:
            with rules_path.open("ab") as rules_stream:
                rules_stream.write(
                    orjson.dumps(rule, option=orjson.OPT_SORT_KEYS) + b"\n"
                )
                rules_stream.flush()
                os.fsync(rules_stream.fileno())
            with (
                staged_predictions.open("rb") as source,
                predictions_path.open("ab") as predictions_stream,
            ):
                while chunk := source.read(1024 * 1024):
                    predictions_stream.write(chunk)
                predictions_stream.flush()
                os.fsync(predictions_stream.fileno())
            return validate_run_directory(run_dir, evaluations_dir)
        except Exception:
            with rules_path.open("r+b") as stream:
                stream.truncate(rules_size)
            with predictions_path.open("r+b") as stream:
                stream.truncate(predictions_size)
            raise
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def record_rule(
    *,
    run_dir: Path,
    candidate: dict[str, Any],
    evaluations_dir: Path = DEFAULT_EVALUATIONS_DIR,
    config_path: Path = DEFAULT_BENCHMARK_CONFIG,
    query_records: Callable[[str], Iterable[Mapping[str, Any]]] | None = None,
    submit: bool = False,
    scorer_url: str | None = None,
    feedback_timeout_seconds: float = 60.0,
    query_timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    evaluations_dir = evaluations_dir.resolve()
    manifest = _load_active_manifest(run_dir)
    validate_run_directory(run_dir, evaluations_dir)
    rule = build_rule(candidate, manifest)

    if query_records is None:
        required = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ValueError(
                f"Missing Neo4j service variables: {', '.join(missing)}"
            )
        records = _neo4j_records(
            rule["execution"]["cypher"],
            uri=os.environ["NEO4J_URI"],
            user=os.environ["NEO4J_USER"],
            password=os.environ["NEO4J_PASSWORD"],
            timeout_seconds=query_timeout_seconds,
        )
    else:
        records = query_records(rule["execution"]["cypher"])

    staged_path, prediction_count, duplicate_rows = _stage_predictions(
        records,
        run_dir=run_dir,
        run_id=manifest["run_id"],
        round_id=manifest["current_round_id"],
        rule_id=rule["rule_id"],
    )
    try:
        validation = _append_recording(
            run_dir=run_dir,
            evaluations_dir=evaluations_dir,
            rule=rule,
            staged_predictions=staged_path,
        )
    finally:
        staged_path.unlink(missing_ok=True)

    result: dict[str, Any] = {
        "rule_id": rule["rule_id"],
        "status": "recorded",
        "prediction_count": prediction_count,
        "duplicate_rows_collapsed": duplicate_rows,
        "uses_treatment_edges": rule["uses_treatment_edges"],
        "evidence_tier": rule["evidence_tier"],
        "validation": validation,
        "feedback": {"status": "not_requested"},
    }
    if not submit:
        return result

    minimum = load_benchmark_config(config_path).scoring.minimum_predictions
    if prediction_count < minimum:
        result["feedback"] = {
            "status": "skipped",
            "reason": (
                f"Recorded prediction count {prediction_count} is below the "
                f"configured feedback minimum of {minimum}; the rule remains recorded."
            ),
        }
        return result
    try:
        evaluation = submit_feedback(
            run_dir=run_dir,
            rule_id=rule["rule_id"],
            scorer_url=scorer_url
            or os.environ.get("SCORER_URL", "http://127.0.0.1:6430"),
            timeout_seconds=feedback_timeout_seconds,
        )
    except FeedbackSubmissionError as error:
        if error.status_code == 400 and "partition-eligible" in error.detail:
            result["feedback"] = {
                "status": "skipped",
                "reason": error.detail,
            }
            return result
        raise RuntimeError(
            f"Rule {rule['rule_id']} was recorded successfully, but feedback "
            "submission failed. Retry with miner-submit-feedback; do not rerun "
            "miner-record-rule."
        ) from error
    except Exception as error:
        raise RuntimeError(
            f"Rule {rule['rule_id']} was recorded successfully, but feedback "
            "submission failed. Retry with miner-submit-feedback; do not rerun "
            "miner-record-rule."
        ) from error
    result["feedback"] = {"status": "submitted", "evaluation": evaluation}
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build, execute, validate, and append one rule candidate and its "
            "complete prediction set"
        )
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument(
        "--evaluations-dir",
        type=Path,
        default=DEFAULT_EVALUATIONS_DIR,
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_BENCHMARK_CONFIG)
    parser.add_argument("--submit-feedback", action="store_true")
    parser.add_argument(
        "--scorer-url",
        default=os.environ.get("SCORER_URL", "http://127.0.0.1:6430"),
    )
    parser.add_argument("--feedback-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--query-timeout-seconds", type=float, default=300.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    result = record_rule(
        run_dir=args.run_dir,
        candidate=candidate,
        evaluations_dir=args.evaluations_dir,
        config_path=args.config,
        submit=args.submit_feedback,
        scorer_url=args.scorer_url,
        feedback_timeout_seconds=args.feedback_timeout_seconds,
        query_timeout_seconds=args.query_timeout_seconds,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
