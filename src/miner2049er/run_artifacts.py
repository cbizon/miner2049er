from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from miner2049er.benchmark_config import BenchmarkConfig
from miner2049er.biolink_semantics import validate_rule_biolink_semantics
from miner2049er.schema_validation import read_jsonl, validate_document
from miner2049er.settings import ROOT
from miner2049er.settings import evaluations_dir as configured_evaluations_dir

DEFAULT_RUNS_DIR = ROOT / "runs"
DEFAULT_EVALUATIONS_DIR = configured_evaluations_dir()
DEFAULT_INITIAL_INSTRUCTION = (
    "Begin the rule-mining experiment. Establish baselines, explore distinct "
    "mechanism families, and follow the complete base assignment."
)
DEFAULT_CONTINUATION_INSTRUCTION = (
    "Continue the experiment from the existing research log and evaluations. "
    "Preserve prior artifacts, avoid repeating exhausted hypotheses, and pursue "
    "new mechanisms or justified refinements."
)
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
AGENT_EXECUTION_FILENAME = "agent-execution.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_json(path: Path, value: dict[str, Any], schema_name: str) -> None:
    validate_document(value, schema_name)
    _atomic_write_text(path, json.dumps(value, indent=2) + "\n")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(
            "run_id must start with an alphanumeric character and contain only "
            "letters, numbers, dots, underscores, and hyphens"
        )
    return run_id


def _resolve_run_path(run_dir: Path, relative_path: str) -> Path:
    root = run_dir.resolve()
    path = (run_dir / relative_path).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"Artifact path escapes the run directory: {relative_path}")
    return path


def _file_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"records": 0, "bytes": 0, "sha256": EMPTY_SHA256}
    digest = hashlib.sha256()
    byte_count = 0
    newline_count = 0
    final_byte = b""
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            byte_count += len(chunk)
            newline_count += chunk.count(b"\n")
            final_byte = chunk[-1:]
    records = newline_count + (1 if byte_count and final_byte != b"\n" else 0)
    return {
        "records": records,
        "bytes": byte_count,
        "sha256": digest.hexdigest(),
    }


def _prediction_counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with path.open("rb") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                rule_id = orjson.loads(line)["rule_id"]
            except (KeyError, orjson.JSONDecodeError, TypeError) as error:
                raise ValueError(f"{path}:{line_number}: invalid prediction record") from error
            if not isinstance(rule_id, str) or not rule_id:
                raise ValueError(f"{path}:{line_number}: invalid prediction rule_id")
            counts[rule_id] = counts.get(rule_id, 0) + 1
    return counts


def _artifact_checkpoint(
    run_dir: Path,
    evaluations_dir: Path,
    manifest: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    artifacts = manifest["artifacts"]
    return {
        "neo4j_artifacts": _file_state(
            _resolve_run_path(run_dir, artifacts["neo4j_artifacts"])
        ),
        "rules": _file_state(_resolve_run_path(run_dir, artifacts["rules"])),
        "predictions": _file_state(
            _resolve_run_path(run_dir, artifacts["predictions"])
        ),
        "research_log": _file_state(
            _resolve_run_path(run_dir, artifacts["research_log"])
        ),
        "evaluations": _file_state(evaluations_dir / f"{manifest['run_id']}.jsonl"),
    }


def _prefix_sha256(path: Path, byte_count: int) -> str:
    digest = hashlib.sha256()
    remaining = byte_count
    with path.open("rb") as stream:
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    if remaining:
        raise ValueError(f"{path} is shorter than a recorded append checkpoint")
    return digest.hexdigest()


def _validate_checkpoint_prefix(
    path: Path,
    state: dict[str, Any],
    label: str,
) -> None:
    if not path.is_file():
        if state["bytes"] == 0 and state["sha256"] == EMPTY_SHA256:
            return
        raise ValueError(f"{label} is missing after data was recorded")
    actual_size = path.stat().st_size
    if actual_size < state["bytes"]:
        raise ValueError(f"{label} was truncated after a round boundary")
    if _prefix_sha256(path, state["bytes"]) != state["sha256"]:
        raise ValueError(f"{label} was rewritten before a round boundary")


def _round_id(round_number: int) -> str:
    return f"round-{round_number:04d}"


def _round_prompt(
    *,
    base_prompt: str,
    run_dir: Path,
    run_id: str,
    round_id: str,
    round_number: int,
    deadline: str | None,
    instruction: str,
) -> str:
    deadline_text = deadline or "No deadline was supplied for this round."
    return f"""{base_prompt.rstrip()}

# Active Round

- Run ID: `{run_id}`
- Round ID: `{round_id}`
- Round number: {round_number}
- Round deadline: {deadline_text}
- Repository root: `{ROOT}`
- Run directory: `{run_dir.resolve()}`

This is an append-only continuation of one experiment. Review all existing
rules, predictions, aggregate evaluations, and research events before starting.
Do not rewrite or delete prior JSONL records. Every new Neo4j artifact, rule,
prediction, and research event must use this round ID. The feedback budget and
duplicate prediction checks are cumulative across every round in the run.

## Operator Instruction

{instruction.strip()}
"""


def _create_round(
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    round_number: int,
    parent_round_id: str | None,
    deadline: str | None,
    instruction: str,
    starting_artifacts: dict[str, Any],
) -> dict[str, Any]:
    if not instruction.strip():
        raise ValueError("Round instructions cannot be empty")
    round_id = _round_id(round_number)
    relative_dir = Path(manifest["artifacts"]["rounds"]) / round_id
    round_dir = _resolve_run_path(run_dir, str(relative_dir))
    instruction_text = instruction.strip() + "\n"
    instruction_path = relative_dir / "instructions.md"
    base_prompt = _resolve_run_path(
        run_dir,
        manifest["artifacts"]["base_prompt"],
    ).read_text(encoding="utf-8")
    agent_prompt = _round_prompt(
        base_prompt=base_prompt,
        run_dir=run_dir,
        run_id=manifest["run_id"],
        round_id=round_id,
        round_number=round_number,
        deadline=deadline,
        instruction=instruction,
    )
    agent_prompt_path = relative_dir / "agent-prompt.md"
    round_manifest = {
        "schema_version": "1.0",
        "run_id": manifest["run_id"],
        "round_id": round_id,
        "round_number": round_number,
        "parent_round_id": parent_round_id,
        "status": "running",
        "started_at": _now(),
        "deadline": deadline,
        "completed_at": None,
        "instruction_path": str(instruction_path),
        "instruction_sha256": _sha256_text(instruction_text),
        "agent_prompt_path": str(agent_prompt_path),
        "agent_prompt_sha256": _sha256_text(agent_prompt),
        "starting_artifacts": starting_artifacts,
        "ending_artifacts": None,
    }
    validate_document(round_manifest, "round.schema.json")

    round_dir.mkdir(parents=True, exist_ok=False)
    _atomic_write_text(
        _resolve_run_path(run_dir, str(instruction_path)),
        instruction_text,
    )
    _atomic_write_text(
        _resolve_run_path(run_dir, str(agent_prompt_path)),
        agent_prompt,
    )
    _atomic_write_json(round_dir / "round.json", round_manifest, "round.schema.json")
    return round_manifest


def authorization_path(authorization_dir: Path, run_id: str) -> Path:
    return authorization_dir / f"{_safe_run_id(run_id)}.json"


def load_run_authorization(
    authorization_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    path = authorization_path(authorization_dir, run_id)
    if not path.is_file():
        raise ValueError(f"Run is not authorized: {run_id}")
    authorization = json.loads(path.read_text(encoding="utf-8"))
    validate_document(authorization, "run-authorization.schema.json")
    if authorization["run_id"] != run_id:
        raise ValueError(f"Authorization file does not match run {run_id}")
    return authorization


def _write_authorization(
    *,
    authorization_dir: Path,
    manifest: dict[str, Any],
    config: BenchmarkConfig,
    round_ids: list[str],
) -> None:
    _assert_config_matches_manifest(config=config, manifest=manifest)
    authorization = {
        "schema_version": "1.0",
        "run_id": manifest["run_id"],
        "benchmark_id": manifest["benchmark_id"],
        "split_id": manifest["split_id"],
        "graph_version": manifest["graph_version"],
        "biolink_version": manifest["biolink_version"],
        "predicate_expansion": manifest["predicate_expansion"],
        "status": manifest["status"],
        "current_round_id": manifest["current_round_id"],
        "round_ids": round_ids,
        "feedback_submission_limit": (
            config.scoring.maximum_feedback_submissions_per_run
        ),
        "updated_at": _now(),
    }
    _atomic_write_json(
        authorization_path(authorization_dir, manifest["run_id"]),
        authorization,
        "run-authorization.schema.json",
    )


def _assert_config_matches_manifest(
    *,
    config: BenchmarkConfig,
    manifest: dict[str, Any],
) -> None:
    for field, expected in (
        ("benchmark_id", config.benchmark_id),
        ("split_id", config.split_id),
        ("graph_version", config.graph_version),
        ("biolink_version", config.biolink_version),
        ("predicate_expansion", config.predicate_expansion),
        ("target_predicates", list(config.target_predicates)),
    ):
        if manifest[field] != expected:
            raise ValueError(
                f"Run {manifest['run_id']} does not belong to this benchmark: {field}"
            )


def _assert_authorization_matches(
    *,
    authorization_dir: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    authorization = load_run_authorization(authorization_dir, manifest["run_id"])
    for field in (
        "benchmark_id",
        "split_id",
        "graph_version",
        "biolink_version",
        "predicate_expansion",
        "status",
        "current_round_id",
    ):
        if authorization[field] != manifest[field]:
            raise ValueError(
                f"Public run manifest and sealed authorization disagree on {field}"
            )
    if len(authorization["round_ids"]) != manifest["round_count"]:
        raise ValueError(
            "Public run manifest and sealed authorization disagree on round count"
        )
    return authorization


def initialize_run(
    *,
    runs_dir: Path,
    evaluations_dir: Path,
    authorization_dir: Path,
    run_id: str,
    config: BenchmarkConfig,
    prompt_path: Path,
    deadline: str | None,
    instruction: str = DEFAULT_INITIAL_INSTRUCTION,
) -> Path:
    _safe_run_id(run_id)
    if not prompt_path.is_file():
        raise FileNotFoundError(prompt_path)
    run_dir = runs_dir / run_id
    authorization_file = authorization_path(authorization_dir, run_id)
    if authorization_file.exists():
        raise FileExistsError(authorization_file)
    run_dir.mkdir(parents=True, exist_ok=False)
    evaluations_dir.mkdir(parents=True, exist_ok=True)
    try:
        for name in (
            "neo4j-artifacts.jsonl",
            "rules.jsonl",
            "predictions.jsonl",
            "research-log.jsonl",
        ):
            (run_dir / name).touch()
        (run_dir / "rounds").mkdir()
        _atomic_write_text(
            run_dir / "base-prompt.md",
            prompt_path.read_text(encoding="utf-8"),
        )
        manifest = {
            "schema_version": "1.0",
            "run_id": run_id,
            "benchmark_id": config.benchmark_id,
            "split_id": config.split_id,
            "graph_version": config.graph_version,
            "biolink_version": config.biolink_version,
            "predicate_expansion": config.predicate_expansion,
            "target_predicates": list(config.target_predicates),
            "prompt_path": str(prompt_path),
            "started_at": _now(),
            "completed_at": None,
            "current_round_id": _round_id(1),
            "round_count": 1,
            "status": "running",
            "artifacts": {
                "base_prompt": "base-prompt.md",
                "rounds": "rounds",
                "neo4j_artifacts": "neo4j-artifacts.jsonl",
                "rules": "rules.jsonl",
                "predictions": "predictions.jsonl",
                "research_log": "research-log.jsonl",
                # Informational; tools take the directory from
                # MINER_EVALUATIONS_DIR / --evaluations-dir.
                "evaluations": os.path.relpath(
                    evaluations_dir / f"{run_id}.jsonl", run_dir
                ),
            },
        }
        validate_document(manifest, "run.schema.json")
        starting_artifacts = _artifact_checkpoint(run_dir, evaluations_dir, manifest)
        first_round = _create_round(
            run_dir=run_dir,
            manifest=manifest,
            round_number=1,
            parent_round_id=None,
            deadline=deadline,
            instruction=instruction,
            starting_artifacts=starting_artifacts,
        )
        _atomic_write_json(run_dir / "run.json", manifest, "run.schema.json")
        _write_authorization(
            authorization_dir=authorization_dir,
            manifest=manifest,
            config=config,
            round_ids=[first_round["round_id"]],
        )
    except Exception:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    return run_dir


def load_rounds(run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rounds_dir = _resolve_run_path(run_dir, manifest["artifacts"]["rounds"])
    rounds: list[dict[str, Any]] = []
    for path in sorted(rounds_dir.glob("round-*/round.json")):
        round_manifest = json.loads(path.read_text(encoding="utf-8"))
        validate_document(round_manifest, "round.schema.json")
        rounds.append(round_manifest)
    return rounds


def load_agent_executions(
    run_dir: Path,
    manifest: dict[str, Any],
    rounds: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    executions: dict[str, dict[str, Any]] = {}
    rounds_by_id = {round_manifest["round_id"]: round_manifest for round_manifest in rounds}
    rounds_dir = _resolve_run_path(run_dir, manifest["artifacts"]["rounds"])
    for path in sorted(rounds_dir.glob(f"round-*/{AGENT_EXECUTION_FILENAME}")):
        execution = json.loads(path.read_text(encoding="utf-8"))
        validate_document(execution, "agent-execution.schema.json")
        round_manifest = rounds_by_id.get(execution["round_id"])
        if round_manifest is None:
            raise ValueError(f"{path} references an unknown round")
        if execution["run_id"] != round_manifest["run_id"]:
            raise ValueError(
                f"{path} does not match run {round_manifest['run_id']}"
            )
        expected_path = rounds_dir / execution["round_id"] / AGENT_EXECUTION_FILENAME
        if path != expected_path:
            raise ValueError(f"{path} does not match round {execution['round_id']}")
        executions[execution["round_id"]] = execution
    return executions


def record_agent_execution(
    *,
    run_dir: Path,
    round_id: str,
    model: str,
    model_provider: str,
    reasoning_effort: str,
) -> dict[str, Any]:
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    validate_document(manifest, "run.schema.json")
    round_dir = _resolve_run_path(
        run_dir,
        str(Path(manifest["artifacts"]["rounds"]) / round_id),
    )
    round_manifest = json.loads(
        (round_dir / "round.json").read_text(encoding="utf-8")
    )
    validate_document(round_manifest, "round.schema.json")
    if round_manifest["run_id"] != manifest["run_id"]:
        raise ValueError(f"Round {round_id} does not belong to {manifest['run_id']}")
    if round_manifest["round_id"] != round_id:
        raise ValueError(f"Round manifest does not match {round_id}")

    execution = {
        "schema_version": "1.0",
        "run_id": manifest["run_id"],
        "round_id": round_id,
        "model": model,
        "model_provider": model_provider,
        "reasoning_effort": reasoning_effort,
    }
    validate_document(execution, "agent-execution.schema.json")
    path = round_dir / AGENT_EXECUTION_FILENAME
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        validate_document(existing, "agent-execution.schema.json")
        if existing != execution:
            raise ValueError(
                f"Agent execution settings are already recorded for {round_id}"
            )
        return existing
    _atomic_write_json(path, execution, "agent-execution.schema.json")
    return execution


def load_run(run_dir: Path, evaluations_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "run.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_document(manifest, "run.schema.json")
    rules = list(
        read_jsonl(
            _resolve_run_path(run_dir, manifest["artifacts"]["rules"]),
            "rule.schema.json",
        )
    )
    for rule in rules:
        validate_rule_biolink_semantics(
            rule,
            manifest["biolink_version"],
            manifest["target_predicates"],
        )
    neo4j_artifacts = list(
        read_jsonl(
            _resolve_run_path(run_dir, manifest["artifacts"]["neo4j_artifacts"]),
            "neo4j-artifact.schema.json",
        )
    )
    if not evaluations_dir.is_dir():
        # A missing file means nothing has been scored yet; a missing directory
        # means the tool is looking in the wrong place, which would otherwise
        # read as zero evaluations.
        raise FileNotFoundError(
            f"Evaluations directory {evaluations_dir} does not exist; set "
            "MINER_EVALUATIONS_DIR or pass --evaluations-dir"
        )
    evaluations_path = evaluations_dir / f"{manifest['run_id']}.jsonl"
    evaluations = (
        list(read_jsonl(evaluations_path, "evaluation.schema.json"))
        if evaluations_path.is_file()
        else []
    )
    research_events = list(
        read_jsonl(
            _resolve_run_path(run_dir, manifest["artifacts"]["research_log"]),
            "research-event.schema.json",
        )
    )
    prediction_counts = _prediction_counts(
        _resolve_run_path(run_dir, manifest["artifacts"]["predictions"])
    )
    rounds = load_rounds(run_dir, manifest)
    return {
        "run_dir": run_dir,
        "manifest": manifest,
        "rounds": rounds,
        "agent_executions": load_agent_executions(run_dir, manifest, rounds),
        "neo4j_artifacts": neo4j_artifacts,
        "rules": rules,
        "prediction_counts": prediction_counts,
        "research_events": research_events,
        "evaluations": evaluations,
    }


def append_jsonl(path: Path, value: dict[str, Any], schema_name: str) -> None:
    validate_document(value, schema_name)
    with path.open("ab") as stream:
        stream.write(orjson.dumps(value, option=orjson.OPT_SORT_KEYS) + b"\n")


def _close_round(
    *,
    run_dir: Path,
    round_manifest: dict[str, Any],
    ending_artifacts: dict[str, Any],
    completed_at: str,
) -> dict[str, Any]:
    closed = {
        **round_manifest,
        "status": "completed",
        "completed_at": completed_at,
        "ending_artifacts": ending_artifacts,
    }
    round_path = (
        _resolve_run_path(run_dir, closed["agent_prompt_path"]).parent / "round.json"
    )
    _atomic_write_json(round_path, closed, "round.schema.json")
    return closed


def _has_round_final_summary(
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    round_id: str,
) -> bool:
    events = read_jsonl(
        _resolve_run_path(run_dir, manifest["artifacts"]["research_log"]),
        "research-event.schema.json",
    )
    return any(
        event["round_id"] == round_id and event["event_type"] == "final_summary"
        for event in events
    )


def validate_round_completion(
    run_dir: Path,
    evaluations_dir: Path,
) -> dict[str, int]:
    validation = validate_run_directory(run_dir, evaluations_dir)
    run = load_run(run_dir, evaluations_dir)
    manifest = run["manifest"]
    if manifest["status"] != "running" or not manifest["current_round_id"]:
        raise ValueError("Run does not have an active round to finish")
    if not _has_round_final_summary(
        run_dir=run_dir,
        manifest=manifest,
        round_id=manifest["current_round_id"],
    ):
        raise ValueError("The active round requires a final_summary research event")
    return validation


def finish_round(
    *,
    run_dir: Path,
    evaluations_dir: Path,
    authorization_dir: Path,
    config: BenchmarkConfig,
) -> dict[str, Any]:
    validate_round_completion(run_dir, evaluations_dir)
    run = load_run(run_dir, evaluations_dir)
    manifest = run["manifest"]
    _assert_config_matches_manifest(config=config, manifest=manifest)
    if manifest["status"] != "running" or not manifest["current_round_id"]:
        raise ValueError("Only an active round can be finished")
    authorization = _assert_authorization_matches(
        authorization_dir=authorization_dir,
        manifest=manifest,
    )
    current = run["rounds"][-1]
    if current["round_id"] != manifest["current_round_id"]:
        raise ValueError("The active round does not match the run manifest")
    checkpoint = _artifact_checkpoint(run_dir, evaluations_dir, manifest)
    completed_at = _now()
    try:
        _close_round(
            run_dir=run_dir,
            round_manifest=current,
            ending_artifacts=checkpoint,
            completed_at=completed_at,
        )
        updated_manifest = {
            **manifest,
            "status": "round_complete",
            "current_round_id": None,
        }
        _atomic_write_json(run_dir / "run.json", updated_manifest, "run.schema.json")
        validate_run_directory(run_dir, evaluations_dir)
        _write_authorization(
            authorization_dir=authorization_dir,
            manifest=updated_manifest,
            config=config,
            round_ids=authorization["round_ids"],
        )
    except Exception:
        _atomic_write_json(
            _resolve_run_path(run_dir, current["agent_prompt_path"]).parent
            / "round.json",
            current,
            "round.schema.json",
        )
        _atomic_write_json(run_dir / "run.json", manifest, "run.schema.json")
        raise
    return updated_manifest


def start_round(
    *,
    run_dir: Path,
    evaluations_dir: Path,
    authorization_dir: Path,
    config: BenchmarkConfig,
    deadline: str | None,
    instruction: str = DEFAULT_CONTINUATION_INSTRUCTION,
) -> Path:
    validate_run_directory(run_dir, evaluations_dir)
    run = load_run(run_dir, evaluations_dir)
    manifest = run["manifest"]
    _assert_config_matches_manifest(config=config, manifest=manifest)
    if manifest["status"] != "round_complete" or manifest["current_round_id"]:
        raise ValueError("The previous round must be finished before starting another")
    authorization = _assert_authorization_matches(
        authorization_dir=authorization_dir,
        manifest=manifest,
    )
    current = run["rounds"][-1]
    if current["status"] != "completed" or current["ending_artifacts"] is None:
        raise ValueError("The previous round does not have a completed checkpoint")

    checkpoint = _artifact_checkpoint(run_dir, evaluations_dir, manifest)
    if checkpoint != current["ending_artifacts"]:
        raise ValueError("Run artifacts changed after the previous round was finished")
    round_number = manifest["round_count"] + 1
    next_round_dir = _resolve_run_path(
        run_dir,
        str(Path(manifest["artifacts"]["rounds"]) / _round_id(round_number)),
    )
    if next_round_dir.exists():
        raise FileExistsError(next_round_dir)
    try:
        next_round = _create_round(
            run_dir=run_dir,
            manifest=manifest,
            round_number=round_number,
            parent_round_id=current["round_id"],
            deadline=deadline,
            instruction=instruction,
            starting_artifacts=checkpoint,
        )
        updated_manifest = {
            **manifest,
            "status": "running",
            "current_round_id": next_round["round_id"],
            "round_count": round_number,
        }
        _atomic_write_json(run_dir / "run.json", updated_manifest, "run.schema.json")
        validate_run_directory(run_dir, evaluations_dir)
        _write_authorization(
            authorization_dir=authorization_dir,
            manifest=updated_manifest,
            config=config,
            round_ids=[*authorization["round_ids"], next_round["round_id"]],
        )
    except Exception:
        shutil.rmtree(next_round_dir, ignore_errors=True)
        _atomic_write_json(run_dir / "run.json", manifest, "run.schema.json")
        raise
    return _resolve_run_path(run_dir, next_round["agent_prompt_path"])


def close_run(
    *,
    run_dir: Path,
    evaluations_dir: Path,
    authorization_dir: Path,
    config: BenchmarkConfig,
) -> dict[str, Any]:
    validate_run_directory(run_dir, evaluations_dir)
    run = load_run(run_dir, evaluations_dir)
    manifest = run["manifest"]
    _assert_config_matches_manifest(config=config, manifest=manifest)
    if manifest["status"] != "round_complete" or manifest["current_round_id"]:
        raise ValueError("The active round must be finished before closing the run")
    authorization = _assert_authorization_matches(
        authorization_dir=authorization_dir,
        manifest=manifest,
    )
    completed_at = _now()
    try:
        updated_manifest = {
            **manifest,
            "status": "completed",
            "current_round_id": None,
            "completed_at": completed_at,
        }
        _atomic_write_json(run_dir / "run.json", updated_manifest, "run.schema.json")
        validate_run_directory(run_dir, evaluations_dir)
        _write_authorization(
            authorization_dir=authorization_dir,
            manifest=updated_manifest,
            config=config,
            round_ids=authorization["round_ids"],
        )
    except Exception:
        _atomic_write_json(run_dir / "run.json", manifest, "run.schema.json")
        raise
    return updated_manifest


def _verify_round_text_files(run_dir: Path, round_manifest: dict[str, Any]) -> None:
    for path_field, hash_field in (
        ("instruction_path", "instruction_sha256"),
        ("agent_prompt_path", "agent_prompt_sha256"),
    ):
        path = _resolve_run_path(run_dir, round_manifest[path_field])
        if not path.is_file():
            raise ValueError(f"Missing round artifact: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != round_manifest[hash_field]:
            raise ValueError(f"Round artifact was modified after creation: {path}")


def _validate_round_record_ranges(
    *,
    records: list[dict[str, Any]],
    artifact_name: str,
    rounds: list[dict[str, Any]],
) -> None:
    for round_manifest in rounds:
        start = round_manifest["starting_artifacts"][artifact_name]["records"]
        ending = round_manifest["ending_artifacts"]
        end = ending[artifact_name]["records"] if ending is not None else len(records)
        if end < start or end > len(records):
            raise ValueError(
                f"Invalid {artifact_name} record boundary for "
                f"{round_manifest['round_id']}"
            )
        if any(
            record["round_id"] != round_manifest["round_id"]
            for record in records[start:end]
        ):
            raise ValueError(
                f"{artifact_name} records cross the boundary for "
                f"{round_manifest['round_id']}"
            )


def validate_run_directory(run_dir: Path, evaluations_dir: Path) -> dict[str, int]:
    run = load_run(run_dir, evaluations_dir)
    manifest = run["manifest"]
    run_id = manifest["run_id"]
    rounds = run["rounds"]
    if len(rounds) != manifest["round_count"]:
        raise ValueError("Round count does not match the run manifest")
    expected_round_ids = [_round_id(number) for number in range(1, len(rounds) + 1)]
    if [round_manifest["round_id"] for round_manifest in rounds] != expected_round_ids:
        raise ValueError("Round IDs must be contiguous and ordered")

    previous_ending: dict[str, Any] | None = None
    artifacts = manifest["artifacts"]
    artifact_paths = {
        "neo4j_artifacts": _resolve_run_path(
            run_dir,
            artifacts["neo4j_artifacts"],
        ),
        "rules": _resolve_run_path(run_dir, artifacts["rules"]),
        "predictions": _resolve_run_path(run_dir, artifacts["predictions"]),
        "research_log": _resolve_run_path(run_dir, artifacts["research_log"]),
        "evaluations": evaluations_dir / f"{run_id}.jsonl",
    }
    for index, round_manifest in enumerate(rounds):
        if round_manifest["run_id"] != run_id:
            raise ValueError("Every round must use the run manifest's run_id")
        expected_parent = rounds[index - 1]["round_id"] if index else None
        if round_manifest["parent_round_id"] != expected_parent:
            raise ValueError("Round parentage must form one contiguous chain")
        _verify_round_text_files(run_dir, round_manifest)
        if (
            previous_ending is not None
            and round_manifest["starting_artifacts"] != previous_ending
        ):
            raise ValueError("A round does not start at the prior round checkpoint")
        for artifact_name, state in round_manifest["starting_artifacts"].items():
            _validate_checkpoint_prefix(
                artifact_paths[artifact_name],
                state,
                artifact_name,
            )
        if round_manifest["status"] == "completed":
            if (
                round_manifest["completed_at"] is None
                or round_manifest["ending_artifacts"] is None
            ):
                raise ValueError("Completed rounds require an ending checkpoint")
            for artifact_name, state in round_manifest["ending_artifacts"].items():
                _validate_checkpoint_prefix(
                    artifact_paths[artifact_name],
                    state,
                    artifact_name,
                )
            previous_ending = round_manifest["ending_artifacts"]
        else:
            if (
                round_manifest["completed_at"] is not None
                or round_manifest["ending_artifacts"] is not None
            ):
                raise ValueError("Running rounds cannot have an ending checkpoint")
            if index != len(rounds) - 1:
                raise ValueError("Only the last round may be running")

    if manifest["status"] == "running":
        if rounds[-1]["status"] != "running":
            raise ValueError("A running run must have one active round")
        if manifest["current_round_id"] != rounds[-1]["round_id"]:
            raise ValueError("current_round_id does not identify the active round")
        if manifest["completed_at"] is not None:
            raise ValueError("A running run cannot have completed_at")
    elif manifest["status"] == "round_complete":
        if manifest["current_round_id"] is not None:
            raise ValueError("A finished round cannot remain active")
        if any(round_manifest["status"] != "completed" for round_manifest in rounds):
            raise ValueError("Every round must be completed at a round boundary")
        if manifest["completed_at"] is not None:
            raise ValueError("A round-complete run cannot have completed_at")
        current_checkpoint = _artifact_checkpoint(run_dir, evaluations_dir, manifest)
        if current_checkpoint != previous_ending:
            raise ValueError("Run artifacts changed after the round was finished")
    else:
        if manifest["current_round_id"] is not None:
            raise ValueError("A completed run cannot have an active round")
        if any(round_manifest["status"] != "completed" for round_manifest in rounds):
            raise ValueError("Every round must be completed before the run closes")
        if manifest["completed_at"] is None:
            raise ValueError("A completed run requires completed_at")
        current_checkpoint = _artifact_checkpoint(run_dir, evaluations_dir, manifest)
        for artifact_name in (
            "neo4j_artifacts",
            "rules",
            "predictions",
            "research_log",
        ):
            if current_checkpoint[artifact_name] != previous_ending[artifact_name]:
                raise ValueError(
                    f"{artifact_name} changed after the run was closed"
                )

    round_numbers = {
        round_manifest["round_id"]: round_manifest["round_number"]
        for round_manifest in rounds
    }
    neo4j_artifacts = run["neo4j_artifacts"]
    neo4j_artifact_ids: set[str] = set()
    neo4j_artifact_rounds: dict[str, str] = {}
    for artifact in neo4j_artifacts:
        artifact_id = artifact["artifact_id"]
        if artifact_id in neo4j_artifact_ids:
            raise ValueError(f"Duplicate Neo4j artifact ID: {artifact_id}")
        if artifact["run_id"] != run_id:
            raise ValueError("Every Neo4j artifact must use the run manifest's run_id")
        if artifact["round_id"] not in round_numbers:
            raise ValueError(
                f"Neo4j artifact {artifact_id} uses an unknown round "
                f"{artifact['round_id']}"
            )
        unresolved_dependencies = set(artifact["dependencies"]) - neo4j_artifact_ids
        if unresolved_dependencies:
            raise ValueError(
                f"Neo4j artifact {artifact_id} has unknown or forward dependencies: "
                f"{sorted(unresolved_dependencies)}"
            )
        supersedes = artifact["supersedes_artifact_id"]
        if supersedes is not None and supersedes not in neo4j_artifact_ids:
            raise ValueError(
                f"Neo4j artifact {artifact_id} supersedes unknown artifact {supersedes}"
            )
        neo4j_artifact_ids.add(artifact_id)
        neo4j_artifact_rounds[artifact_id] = artifact["round_id"]

    rules = run["rules"]
    rule_ids = [rule["rule_id"] for rule in rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("Duplicate rule IDs in rules.jsonl")
    if any(rule["run_id"] != run_id for rule in rules):
        raise ValueError("Every rule must use the run manifest's run_id")
    for rule in rules:
        for feature in rule["derived_features"]:
            artifact_id = feature["neo4j_artifact_id"]
            if artifact_id is None:
                continue
            if artifact_id not in neo4j_artifact_rounds:
                raise ValueError(
                    f"Rule {rule['rule_id']} references unknown Neo4j artifact "
                    f"{artifact_id}"
                )
            if (
                round_numbers[neo4j_artifact_rounds[artifact_id]]
                > round_numbers[rule["round_id"]]
            ):
                raise ValueError(
                    f"Rule {rule['rule_id']} references a Neo4j artifact from a "
                    "later round"
                )
    rule_rounds = {rule["rule_id"]: rule["round_id"] for rule in rules}

    predictions = list(
        read_jsonl(
            _resolve_run_path(run_dir, artifacts["predictions"]),
            "prediction.schema.json",
        )
    )
    prediction_keys: set[tuple[str, str, str]] = set()
    for prediction in predictions:
        if prediction["run_id"] != run_id:
            raise ValueError("Every prediction must use the run manifest's run_id")
        if prediction["rule_id"] not in rule_rounds:
            raise ValueError(
                f"Prediction references unknown rule {prediction['rule_id']}"
            )
        if prediction["round_id"] != rule_rounds[prediction["rule_id"]]:
            raise ValueError("A prediction must use the same round as its rule")
        key = (
            prediction["rule_id"],
            prediction["subject_id"],
            prediction["object_id"],
        )
        if key in prediction_keys:
            raise ValueError(f"Duplicate prediction for rule {prediction['rule_id']}")
        prediction_keys.add(key)

    events = run["research_events"]
    expected_sequences = list(range(1, len(events) + 1))
    actual_sequences = [event["sequence"] for event in events]
    if actual_sequences != expected_sequences:
        raise ValueError("Research event sequences must be contiguous and append-only")
    if any(event["run_id"] != run_id for event in events):
        raise ValueError("Every research event must use the run manifest's run_id")
    timestamps = [datetime.fromisoformat(event["timestamp"]) for event in events]
    if timestamps != sorted(timestamps):
        raise ValueError("Research event timestamps must be nondecreasing")

    evaluations = run["evaluations"]
    for evaluation in evaluations:
        if evaluation["run_id"] != run_id:
            raise ValueError("Every evaluation must use the run manifest's run_id")
        if evaluation["rule_id"] not in rule_rounds:
            raise ValueError(
                f"Evaluation references unknown rule {evaluation['rule_id']}"
            )
        if evaluation["round_id"] != rule_rounds[evaluation["rule_id"]]:
            raise ValueError("An evaluation must use the same round as its rule")

    for artifact_name, records in (
        ("neo4j_artifacts", neo4j_artifacts),
        ("rules", rules),
        ("predictions", predictions),
        ("research_log", events),
    ):
        _validate_round_record_ranges(
            records=records,
            artifact_name=artifact_name,
            rounds=rounds,
        )

    return {
        "rounds": len(rounds),
        "neo4j_artifacts": len(neo4j_artifacts),
        "rules": len(rules),
        "predictions": len(predictions),
        "research_events": len(events),
        "evaluations": len(evaluations),
    }
