from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from miner2049er.benchmark_config import (
    DEFAULT_BENCHMARK_CONFIG,
    BenchmarkConfig,
    load_benchmark_config,
)
from miner2049er.partitioning import Pair, load_label_pairs
from miner2049er.rules import f_beta
from miner2049er.schema_validation import read_jsonl, validate_document


@dataclass(frozen=True)
class LabelStore:
    training: frozenset[Pair]
    feedback: frozenset[Pair]
    final: frozenset[Pair]

    @classmethod
    def from_sealed_manifest(cls, path: Path) -> LabelStore:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        root = path.parent
        return cls(
            training=frozenset(load_label_pairs(root / manifest["training_labels"])),
            feedback=frozenset(load_label_pairs(root / manifest["feedback_labels"])),
            final=frozenset(load_label_pairs(root / manifest["final_labels"])),
        )


def prediction_pairs(records: Iterable[dict[str, Any]]) -> set[Pair]:
    return {(record["subject_id"], record["object_id"]) for record in records}


def prediction_sha256(pairs: set[Pair]) -> str:
    digest = hashlib.sha256()
    for subject_id, object_id in sorted(pairs):
        digest.update(subject_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(object_id.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def eligible_prediction_pairs(
    labels: LabelStore,
    pairs: set[Pair],
    partition: str,
) -> set[Pair]:
    if partition == "feedback":
        return pairs - labels.training
    if partition == "final":
        return pairs - labels.training - labels.feedback
    raise ValueError(f"Unsupported score partition: {partition}")


def score_predictions(
    *,
    config: BenchmarkConfig,
    labels: LabelStore,
    run_id: str,
    round_id: str,
    rule_id: str,
    pairs: set[Pair],
    partition: str,
) -> dict[str, Any]:
    eligible = eligible_prediction_pairs(labels, pairs, partition)
    positives = labels.feedback if partition == "feedback" else labels.final
    hits = eligible & positives
    precision = len(hits) / len(eligible) if eligible else 0.0
    recall = len(hits) / len(positives) if positives else 0.0
    digits = config.scoring.metric_decimal_places
    result = {
        "schema_version": "1.0",
        "benchmark_id": config.benchmark_id,
        "split_id": config.split_id,
        "run_id": run_id,
        "round_id": round_id,
        "rule_id": rule_id,
        "partition": partition,
        "prediction_sha256": prediction_sha256(pairs),
        "counts": {
            "submitted_predictions": len(pairs),
            "eligible_predictions": len(eligible),
            "known_hits": len(hits),
            "partition_labels": len(positives),
        },
        "metrics": {
            "precision_lower_bound": round(precision, digits),
            "recall": round(recall, digits),
            "f0_5": round(f_beta(precision, recall, beta=0.5), digits),
        },
        "scored_at": datetime.now(UTC).isoformat(),
    }
    validate_document(result, "evaluation.schema.json")
    return result


def score_rule_set_predictions(
    *,
    config: BenchmarkConfig,
    labels: LabelStore,
    run_id: str,
    through_round_id: str,
    rule_set_id: str,
    member_rule_ids: list[str],
    pairs: set[Pair],
    partition: str,
) -> dict[str, Any]:
    eligible = eligible_prediction_pairs(labels, pairs, partition)
    positives = labels.feedback if partition == "feedback" else labels.final
    hits = eligible & positives
    precision = len(hits) / len(eligible) if eligible else 0.0
    recall = len(hits) / len(positives) if positives else 0.0
    digits = config.scoring.metric_decimal_places
    result = {
        "schema_version": "1.0",
        "benchmark_id": config.benchmark_id,
        "split_id": config.split_id,
        "run_id": run_id,
        "through_round_id": through_round_id,
        "rule_set_id": rule_set_id,
        "member_rule_ids": member_rule_ids,
        "partition": partition,
        "prediction_sha256": prediction_sha256(pairs),
        "counts": {
            "submitted_predictions": len(pairs),
            "eligible_predictions": len(eligible),
            "known_hits": len(hits),
            "partition_labels": len(positives),
        },
        "metrics": {
            "precision_lower_bound": round(precision, digits),
            "recall": round(recall, digits),
            "f0_5": round(f_beta(precision, recall, beta=0.5), digits),
        },
        "scored_at": datetime.now(UTC).isoformat(),
    }
    validate_document(result, "rule-set-evaluation.schema.json")
    return result


class SubmissionLedger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
              run_id TEXT NOT NULL,
              round_id TEXT NOT NULL,
              rule_id TEXT NOT NULL,
              partition TEXT NOT NULL,
              prediction_sha256 TEXT NOT NULL,
              submitted_at TEXT NOT NULL,
              PRIMARY KEY (run_id, rule_id, partition),
              UNIQUE (run_id, partition, prediction_sha256)
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS rule_set_submissions (
              run_id TEXT NOT NULL,
              through_round_id TEXT NOT NULL,
              rule_set_id TEXT NOT NULL,
              partition TEXT NOT NULL,
              prediction_sha256 TEXT NOT NULL,
              submitted_at TEXT NOT NULL,
              PRIMARY KEY (run_id, rule_set_id, partition),
              UNIQUE (run_id, partition, prediction_sha256)
            )
            """
        )
        self.connection.commit()

    def _feedback_count(self, run_id: str) -> int:
        rule_count = self.connection.execute(
            "SELECT count(*) FROM submissions WHERE run_id = ? AND partition = 'feedback'",
            (run_id,),
        ).fetchone()[0]
        rule_set_count = self.connection.execute(
            """
            SELECT count(*) FROM rule_set_submissions
            WHERE run_id = ? AND partition = 'feedback'
            """,
            (run_id,),
        ).fetchone()[0]
        return rule_count + rule_set_count

    def _digest_exists(self, run_id: str, partition: str, digest: str) -> bool:
        rule_match = self.connection.execute(
            """
            SELECT 1 FROM submissions
            WHERE run_id = ? AND partition = ? AND prediction_sha256 = ?
            """,
            (run_id, partition, digest),
        ).fetchone()
        rule_set_match = self.connection.execute(
            """
            SELECT 1 FROM rule_set_submissions
            WHERE run_id = ? AND partition = ? AND prediction_sha256 = ?
            """,
            (run_id, partition, digest),
        ).fetchone()
        return rule_match is not None or rule_set_match is not None

    def record_feedback(
        self,
        *,
        run_id: str,
        round_id: str,
        rule_id: str,
        digest: str,
        maximum_per_run: int,
    ) -> None:
        count = self._feedback_count(run_id)
        if count >= maximum_per_run:
            raise ValueError(
                f"Feedback submission limit reached for run {run_id}: {maximum_per_run}"
            )
        if self._digest_exists(run_id, "feedback", digest):
            raise ValueError("This rule ID or identical prediction set was already scored")
        try:
            self.connection.execute(
                """
                INSERT INTO submissions
                  (run_id, round_id, rule_id, partition, prediction_sha256, submitted_at)
                VALUES (?, ?, ?, 'feedback', ?, ?)
                """,
                (
                    run_id,
                    round_id,
                    rule_id,
                    digest,
                    datetime.now(UTC).isoformat(),
                ),
            )
            self.connection.commit()
        except sqlite3.IntegrityError as error:
            raise ValueError(
                "This rule ID or identical prediction set was already scored"
            ) from error

    def record_final(
        self,
        *,
        run_id: str,
        round_id: str,
        rule_id: str,
        digest: str,
    ) -> None:
        if self._digest_exists(run_id, "final", digest):
            raise ValueError(
                "This rule ID or identical prediction set already received final scoring"
            )
        try:
            self.connection.execute(
                """
                INSERT INTO submissions
                  (run_id, round_id, rule_id, partition, prediction_sha256, submitted_at)
                VALUES (?, ?, ?, 'final', ?, ?)
                """,
                (
                    run_id,
                    round_id,
                    rule_id,
                    digest,
                    datetime.now(UTC).isoformat(),
                ),
            )
            self.connection.commit()
        except sqlite3.IntegrityError as error:
            raise ValueError(
                "This rule ID or identical prediction set already received final scoring"
            ) from error

    def record_rule_set_feedback(
        self,
        *,
        run_id: str,
        through_round_id: str,
        rule_set_id: str,
        digest: str,
        maximum_per_run: int,
    ) -> None:
        count = self._feedback_count(run_id)
        if count >= maximum_per_run:
            raise ValueError(
                f"Feedback submission limit reached for run {run_id}: {maximum_per_run}"
            )
        if self._digest_exists(run_id, "feedback", digest):
            raise ValueError("This rule set or identical prediction union was already scored")
        try:
            self.connection.execute(
                """
                INSERT INTO rule_set_submissions
                  (run_id, through_round_id, rule_set_id, partition,
                   prediction_sha256, submitted_at)
                VALUES (?, ?, ?, 'feedback', ?, ?)
                """,
                (
                    run_id,
                    through_round_id,
                    rule_set_id,
                    digest,
                    datetime.now(UTC).isoformat(),
                ),
            )
            self.connection.commit()
        except sqlite3.IntegrityError as error:
            raise ValueError(
                "This rule set or identical prediction union was already scored"
            ) from error

    def record_rule_set_final(
        self,
        *,
        run_id: str,
        through_round_id: str,
        rule_set_id: str,
        digest: str,
    ) -> None:
        if self._digest_exists(run_id, "final", digest):
            raise ValueError(
                "This rule set or identical prediction union already received final scoring"
            )
        try:
            self.connection.execute(
                """
                INSERT INTO rule_set_submissions
                  (run_id, through_round_id, rule_set_id, partition,
                   prediction_sha256, submitted_at)
                VALUES (?, ?, ?, 'final', ?, ?)
                """,
                (
                    run_id,
                    through_round_id,
                    rule_set_id,
                    digest,
                    datetime.now(UTC).isoformat(),
                ),
            )
            self.connection.commit()
        except sqlite3.IntegrityError as error:
            raise ValueError(
                "This rule set or identical prediction union already received final scoring"
            ) from error


def append_evaluation(path: Path, evaluation: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = orjson.dumps(evaluation, option=orjson.OPT_SORT_KEYS) + b"\n"
    with path.open("ab") as stream:
        try:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        except ImportError:
            pass
        stream.write(line)
        stream.flush()


def load_predictions(path: Path) -> tuple[str, str, str, set[Pair]]:
    records = list(read_jsonl(path, "prediction.schema.json"))
    if not records:
        raise ValueError(f"No predictions in {path}")
    run_ids = {record["run_id"] for record in records}
    round_ids = {record["round_id"] for record in records}
    rule_ids = {record["rule_id"] for record in records}
    if len(run_ids) != 1 or len(round_ids) != 1 or len(rule_ids) != 1:
        raise ValueError(
            "A prediction file must contain exactly one run ID, round ID, and rule ID"
        )
    return (
        next(iter(run_ids)),
        next(iter(round_ids)),
        next(iter(rule_ids)),
        prediction_pairs(records),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score predictions against sealed labels")
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--partition", choices=("feedback", "final"), required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_BENCHMARK_CONFIG)
    parser.add_argument("--sealed-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--release-final",
        action="store_true",
        help="Required acknowledgement for final-partition scoring",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.partition == "final" and not args.release_final:
        raise PermissionError("Final scoring requires --release-final")
    config = load_benchmark_config(args.config)
    labels = LabelStore.from_sealed_manifest(args.sealed_manifest)
    run_id, round_id, rule_id, pairs = load_predictions(args.predictions)
    eligible = eligible_prediction_pairs(labels, pairs, args.partition)
    if len(eligible) < config.scoring.minimum_predictions:
        raise ValueError(
            f"At least {config.scoring.minimum_predictions} partition-eligible "
            "unique predictions are required after excluding visible labels"
        )
    result = score_predictions(
        config=config,
        labels=labels,
        run_id=run_id,
        round_id=round_id,
        rule_id=rule_id,
        pairs=pairs,
        partition=args.partition,
    )
    if args.output:
        append_evaluation(args.output, result)
    print(json.dumps(result, indent=2))
