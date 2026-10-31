from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any

import orjson
from fastapi import FastAPI, Header, HTTPException

from miner2049er.benchmark_config import load_benchmark_config
from miner2049er.biolink_semantics import validate_rule_biolink_semantics
from miner2049er.run_artifacts import load_run_authorization
from miner2049er.schema_validation import read_jsonl
from miner2049er.scorer import (
    LabelStore,
    SubmissionLedger,
    append_evaluation,
    eligible_prediction_pairs,
    prediction_pairs,
    prediction_sha256,
    score_predictions,
    score_rule_set_predictions,
)

CONFIG_PATH = Path(os.environ.get("BENCHMARK_CONFIG", "/app/config/benchmark.json"))
SEALED_MANIFEST = Path(os.environ.get("BENCHMARK_SEALED_MANIFEST", "/sealed/sealed-manifest.json"))
STATE_DB = Path(os.environ.get("SCORER_STATE_DB", "/state/submissions.sqlite3"))
EVALUATIONS_DIR = Path(os.environ.get("SCORER_EVALUATIONS_DIR", "/evaluations"))
AUTHORIZED_RUNS_DIR = Path(
    os.environ.get("SCORER_AUTHORIZED_RUNS_DIR", "/sealed/authorized-runs")
)
RUNS_DIR = Path(os.environ.get("SCORER_RUNS_DIR", "/runs"))
RULE_SET_ROOT = Path(os.environ.get("SCORER_RULE_SET_ROOT", "/rule-sets"))
RULE_SET_EVALUATIONS_DIR = Path(
    os.environ.get("SCORER_RULE_SET_EVALUATIONS_DIR", "/rule-set-evaluations")
)
FINAL_TOKEN = os.environ.get("SCORER_FINAL_TOKEN")

APP = FastAPI(
    title="Miner2049er aggregate scorer",
    description="Scores prediction sets without exposing held-out pair identities.",
)


def _runtime():
    config = load_benchmark_config(CONFIG_PATH)
    labels = LabelStore.from_sealed_manifest(SEALED_MANIFEST)
    ledger = SubmissionLedger(STATE_DB)
    return config, labels, ledger


def _parse_submission(
    payload: dict[str, Any],
) -> tuple[str, str, str, set[tuple[str, str]]]:
    run_id = payload.get("run_id")
    round_id = payload.get("round_id")
    rule_id = payload.get("rule_id")
    predictions = payload.get("predictions")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id is required")
    if not isinstance(round_id, str) or not round_id:
        raise ValueError("round_id is required")
    if not isinstance(rule_id, str) or not rule_id:
        raise ValueError("rule_id is required")
    if not isinstance(predictions, list):
        raise TypeError("predictions must be an array")
    for prediction in predictions:
        if not isinstance(prediction, dict):
            raise TypeError("Every prediction must be an object")
        if not prediction.get("subject_id") or not prediction.get("object_id"):
            raise ValueError("Every prediction needs subject_id and object_id")
    return run_id, round_id, rule_id, prediction_pairs(predictions)


def _authorize_submission(
    *,
    config,
    run_id: str,
    round_id: str,
    rule_id: str,
    partition: str,
) -> dict[str, Any]:
    authorization = load_run_authorization(AUTHORIZED_RUNS_DIR, run_id)
    for field, expected in (
        ("benchmark_id", config.benchmark_id),
        ("split_id", config.split_id),
        ("graph_version", config.graph_version),
        ("biolink_version", config.biolink_version),
        ("predicate_expansion", config.predicate_expansion),
        (
            "feedback_submission_limit",
            config.scoring.maximum_feedback_submissions_per_run,
        ),
    ):
        if authorization[field] != expected:
            raise ValueError(
                f"Run {run_id} is not authorized for this benchmark: {field}"
            )
    if round_id not in authorization["round_ids"]:
        raise ValueError(f"Round is not authorized for run {run_id}: {round_id}")
    rules_path = RUNS_DIR / run_id / "rules.jsonl"
    if not rules_path.is_file():
        raise ValueError(f"Run has no rule artifact: {run_id}")
    matching_rules = [
        rule
        for rule in read_jsonl(rules_path, "rule.schema.json")
        if rule["rule_id"] == rule_id
    ]
    if len(matching_rules) != 1:
        raise ValueError(f"Rule is not uniquely recorded in run {run_id}: {rule_id}")
    rule = matching_rules[0]
    validate_rule_biolink_semantics(
        rule,
        config.biolink_version,
        config.target_predicates,
    )
    if rule["run_id"] != run_id or rule["round_id"] != round_id:
        raise ValueError("Submitted run and round must match the recorded rule")
    if partition == "feedback":
        if authorization["status"] != "running":
            raise ValueError("Feedback scoring is closed for this run")
        if authorization["current_round_id"] != round_id:
            raise ValueError("Feedback scoring is available only to the active round")
    elif authorization["status"] != "completed":
        raise ValueError("Final scoring is available only after the run is closed")
    return authorization


def _parse_rule_set_submission(
    payload: dict[str, Any],
) -> tuple[str, str, str, list[str]]:
    run_id = payload.get("run_id")
    through_round_id = payload.get("through_round_id")
    rule_set_id = payload.get("rule_set_id")
    member_rule_ids = payload.get("member_rule_ids")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id is required")
    if not isinstance(through_round_id, str) or not through_round_id:
        raise ValueError("through_round_id is required")
    if not isinstance(rule_set_id, str) or not rule_set_id:
        raise ValueError("rule_set_id is required")
    if (
        not isinstance(member_rule_ids, list)
        or not member_rule_ids
        or any(not isinstance(rule_id, str) or not rule_id for rule_id in member_rule_ids)
    ):
        raise ValueError("member_rule_ids must be a non-empty array of rule IDs")
    if len(member_rule_ids) != len(set(member_rule_ids)):
        raise ValueError("member_rule_ids must be unique")
    return run_id, through_round_id, rule_set_id, member_rule_ids


def _recorded_rule_set(
    run_id: str,
    rule_set_id: str,
) -> dict[str, Any]:
    path = RULE_SET_ROOT / run_id / "rule-sets.jsonl"
    if not path.is_file():
        raise ValueError(f"Run has no recorded rule-set analysis: {run_id}")
    matches = [
        rule_set
        for rule_set in read_jsonl(path, "rule-set.schema.json")
        if rule_set["rule_set_id"] == rule_set_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Rule set is not uniquely recorded in run {run_id}: {rule_set_id}"
        )
    return matches[0]


def _authorize_rule_set_submission(
    *,
    config,
    run_id: str,
    through_round_id: str,
    rule_set_id: str,
    member_rule_ids: list[str],
    partition: str,
) -> dict[str, Any]:
    authorization = load_run_authorization(AUTHORIZED_RUNS_DIR, run_id)
    for field, expected in (
        ("benchmark_id", config.benchmark_id),
        ("split_id", config.split_id),
        ("graph_version", config.graph_version),
        ("biolink_version", config.biolink_version),
        ("predicate_expansion", config.predicate_expansion),
        (
            "feedback_submission_limit",
            config.scoring.maximum_feedback_submissions_per_run,
        ),
    ):
        if authorization[field] != expected:
            raise ValueError(
                f"Run {run_id} is not authorized for this benchmark: {field}"
            )
    if through_round_id != authorization["round_ids"][-1]:
        raise ValueError("Rule-set analysis must cover the latest authorized round")

    recorded = _recorded_rule_set(run_id, rule_set_id)
    recorded_member_ids = [member["rule_id"] for member in recorded["members"]]
    if recorded["through_round_id"] != through_round_id:
        raise ValueError("Submitted through_round_id does not match the rule set")
    if recorded_member_ids != member_rule_ids:
        raise ValueError("Submitted members do not match the recorded rule set")

    rules_path = RUNS_DIR / run_id / "rules.jsonl"
    rules = {
        rule["rule_id"]: rule
        for rule in read_jsonl(rules_path, "rule.schema.json")
        if rule["rule_id"] in set(member_rule_ids)
    }
    if set(rules) != set(member_rule_ids):
        raise ValueError("A rule-set member is not recorded in the run")
    for rule in rules.values():
        validate_rule_biolink_semantics(
            rule,
            config.biolink_version,
            config.target_predicates,
        )
        if rule["round_id"] not in authorization["round_ids"]:
            raise ValueError("A rule-set member uses an unauthorized round")

    if partition == "feedback":
        if authorization["status"] != "round_complete":
            raise ValueError(
                "Rule-set feedback scoring requires a completed round boundary"
            )
    elif authorization["status"] != "completed":
        raise ValueError("Final rule-set scoring is available only after the run closes")
    return authorization


def _rule_set_prediction_union(
    *,
    run_id: str,
    member_rule_ids: list[str],
) -> set[tuple[str, str]]:
    selected = set(member_rule_ids)
    seen_rules: set[str] = set()
    pairs: set[tuple[str, str]] = set()
    path = RUNS_DIR / run_id / "predictions.jsonl"
    with path.open("rb") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                prediction = orjson.loads(line)
                rule_id = prediction["rule_id"]
            except (KeyError, TypeError, orjson.JSONDecodeError) as error:
                raise ValueError(f"{path}:{line_number}: invalid prediction") from error
            if rule_id not in selected:
                continue
            seen_rules.add(rule_id)
            pairs.add((prediction["subject_id"], prediction["object_id"]))
    missing = selected - seen_rules
    if missing:
        raise ValueError(f"Rule-set members have no predictions: {sorted(missing)}")
    return pairs


def _score_rule_set(payload: dict[str, Any], partition: str) -> dict[str, Any]:
    config, labels, ledger = _runtime()
    run_id, through_round_id, rule_set_id, member_rule_ids = (
        _parse_rule_set_submission(payload)
    )
    authorization = _authorize_rule_set_submission(
        config=config,
        run_id=run_id,
        through_round_id=through_round_id,
        rule_set_id=rule_set_id,
        member_rule_ids=member_rule_ids,
        partition=partition,
    )
    pairs = _rule_set_prediction_union(
        run_id=run_id,
        member_rule_ids=member_rule_ids,
    )
    eligible = eligible_prediction_pairs(labels, pairs, partition)
    if len(eligible) < config.scoring.minimum_predictions:
        raise ValueError(
            f"At least {config.scoring.minimum_predictions} partition-eligible "
            "unique predictions are required after excluding visible labels"
        )
    digest = prediction_sha256(pairs)
    if partition == "feedback":
        ledger.record_rule_set_feedback(
            run_id=run_id,
            through_round_id=through_round_id,
            rule_set_id=rule_set_id,
            digest=digest,
            maximum_per_run=authorization["feedback_submission_limit"],
        )
    else:
        ledger.record_rule_set_final(
            run_id=run_id,
            through_round_id=through_round_id,
            rule_set_id=rule_set_id,
            digest=digest,
        )
    result = score_rule_set_predictions(
        config=config,
        labels=labels,
        run_id=run_id,
        through_round_id=through_round_id,
        rule_set_id=rule_set_id,
        member_rule_ids=member_rule_ids,
        pairs=pairs,
        partition=partition,
    )
    append_evaluation(
        RULE_SET_EVALUATIONS_DIR / f"{run_id}.jsonl",
        result,
    )
    return result


def _score(payload: dict[str, Any], partition: str) -> dict[str, Any]:
    config, labels, ledger = _runtime()
    run_id, round_id, rule_id, pairs = _parse_submission(payload)
    authorization = _authorize_submission(
        config=config,
        run_id=run_id,
        round_id=round_id,
        rule_id=rule_id,
        partition=partition,
    )
    eligible = eligible_prediction_pairs(labels, pairs, partition)
    if len(eligible) < config.scoring.minimum_predictions:
        raise ValueError(
            f"At least {config.scoring.minimum_predictions} partition-eligible "
            "unique predictions are required after excluding visible labels"
        )
    digest = prediction_sha256(pairs)
    if partition == "feedback":
        ledger.record_feedback(
            run_id=run_id,
            round_id=round_id,
            rule_id=rule_id,
            digest=digest,
            maximum_per_run=authorization["feedback_submission_limit"],
        )
    else:
        ledger.record_final(
            run_id=run_id,
            round_id=round_id,
            rule_id=rule_id,
            digest=digest,
        )
    result = score_predictions(
        config=config,
        labels=labels,
        run_id=run_id,
        round_id=round_id,
        rule_id=rule_id,
        pairs=pairs,
        partition=partition,
    )
    append_evaluation(EVALUATIONS_DIR / f"{run_id}.jsonl", result)
    return result


@APP.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@APP.post("/score/feedback")
def score_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return _score(payload, "feedback")
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@APP.post("/score/final")
def score_final(
    payload: dict[str, Any],
    x_final_token: str | None = Header(default=None),
) -> dict[str, Any]:
    if not FINAL_TOKEN or not x_final_token or not hmac.compare_digest(
        FINAL_TOKEN,
        x_final_token,
    ):
        raise HTTPException(status_code=403, detail="Final scoring is sealed")
    try:
        return _score(payload, "final")
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@APP.post("/score/rule-set/feedback")
def score_rule_set_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return _score_rule_set(payload, "feedback")
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@APP.post("/score/rule-set/final")
def score_rule_set_final(
    payload: dict[str, Any],
    x_final_token: str | None = Header(default=None),
) -> dict[str, Any]:
    if not FINAL_TOKEN or not x_final_token or not hmac.compare_digest(
        FINAL_TOKEN,
        x_final_token,
    ):
        raise HTTPException(status_code=403, detail="Final scoring is sealed")
    try:
        return _score_rule_set(payload, "final")
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


__all__ = ["APP"]
