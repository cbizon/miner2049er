from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from miner2049er.benchmark_config import (
    DEFAULT_BENCHMARK_CONFIG,
    BenchmarkConfig,
    load_benchmark_config,
)
from miner2049er.settings import ROOT, edges_path, graph_version
from miner2049er.source_files import open_source

DEFAULT_PUBLIC_DIR = ROOT / "data" / "benchmark"
DEFAULT_SEALED_DIR = ROOT.parent / f"{ROOT.name}-sealed"

Pair = tuple[str, str]


@dataclass
class TargetPair:
    subject_id: str
    object_id: str
    predicates: set[str] = field(default_factory=set)
    primary_knowledge_sources: set[str] = field(default_factory=set)
    edge_count: int = 0

    def as_record(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "subject_id": self.subject_id,
            "object_id": self.object_id,
            "predicates": sorted(self.predicates),
            "primary_knowledge_sources": sorted(self.primary_knowledge_sources),
            "edge_count": self.edge_count,
        }


def primary_sources(edge: dict[str, Any]) -> set[str]:
    return {
        str(source.get("resource_id") or source.get("id"))
        for source in edge.get("sources", [])
        if isinstance(source, dict)
        and source.get("resource_role") == "primary_knowledge_source"
        and (source.get("resource_id") or source.get("id"))
    }


def collect_target_pairs(
    source: Path,
    target_predicates: Iterable[str],
) -> dict[Pair, TargetPair]:
    predicates = set(target_predicates)
    pairs: dict[Pair, TargetPair] = {}
    with open_source(source) as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                edge = orjson.loads(line)
            except orjson.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON at {source}:{line_number}") from error
            predicate = edge.get("predicate")
            if predicate not in predicates:
                continue
            pair = (edge["subject"], edge["object"])
            record = pairs.setdefault(
                pair,
                TargetPair(subject_id=pair[0], object_id=pair[1]),
            )
            record.predicates.add(predicate)
            record.primary_knowledge_sources.update(primary_sources(edge))
            record.edge_count += 1
    return pairs


def pair_digest(config: BenchmarkConfig, pair: Pair) -> str:
    value = f"{config.split.seed}\0{pair[0]}\0{pair[1]}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def assign_partitions(
    pairs: dict[Pair, TargetPair],
    config: BenchmarkConfig,
) -> dict[str, list[TargetPair]]:
    ordered = sorted(pairs, key=lambda pair: (pair_digest(config, pair), pair))
    total = len(ordered)
    training_end = round(total * config.split.training_fraction)
    feedback_end = training_end + round(total * config.split.feedback_fraction)
    assignments = {
        "training": ordered[:training_end],
        "feedback": ordered[training_end:feedback_end],
        "final": ordered[feedback_end:],
    }
    return {
        partition: [pairs[pair] for pair in partition_pairs]
        for partition, partition_pairs in assignments.items()
    }


def _atomic_jsonl(path: Path, records: Iterable[dict[str, Any]], mode: int) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    digest = hashlib.sha256()
    with temporary.open("wb") as stream:
        for record in records:
            line = orjson.dumps(record, option=orjson.OPT_SORT_KEYS) + b"\n"
            stream.write(line)
            digest.update(line)
    os.chmod(temporary, mode)
    temporary.replace(path)
    return digest.hexdigest()


def build_partition_artifacts(
    source: Path,
    config: BenchmarkConfig,
    public_root: Path,
    sealed_root: Path,
) -> dict[str, Any]:
    if public_root.resolve() == sealed_root.resolve():
        raise ValueError("Public and sealed artifact directories must differ")
    if config.graph_version != graph_version():
        raise ValueError(
            f"Config graph version {config.graph_version} does not match "
            f"configured graph version {graph_version()}"
        )

    pairs = collect_target_pairs(source, config.target_predicates)
    assignments = assign_partitions(pairs, config)
    public_dir = public_root / config.split_id
    sealed_dir = sealed_root / config.split_id
    public_dir.mkdir(parents=True, exist_ok=True)
    sealed_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(sealed_dir, 0o700)

    training_path = public_dir / "training-labels.jsonl"
    sealed_training_path = sealed_dir / "training-labels.jsonl"
    feedback_path = sealed_dir / "feedback-labels.jsonl"
    final_path = sealed_dir / "final-labels.jsonl"
    training_records = [record.as_record() for record in assignments["training"]]
    hashes = {
        "training": _atomic_jsonl(
            training_path,
            training_records,
            0o644,
        ),
        "feedback": _atomic_jsonl(
            feedback_path,
            (record.as_record() for record in assignments["feedback"]),
            0o600,
        ),
        "final": _atomic_jsonl(
            final_path,
            (record.as_record() for record in assignments["final"]),
            0o600,
        ),
    }
    sealed_training_hash = _atomic_jsonl(
        sealed_training_path,
        training_records,
        0o600,
    )
    if sealed_training_hash != hashes["training"]:
        raise AssertionError("Public and sealed training-label copies differ")

    manifest = {
        "schema_version": "1.0",
        "benchmark_id": config.benchmark_id,
        "split_id": config.split_id,
        "created_at": datetime.now(UTC).isoformat(),
        "graph_version": config.graph_version,
        "biolink_version": config.biolink_version,
        "predicate_expansion": config.predicate_expansion,
        "source_edges": str(source),
        "target_predicate": config.target_predicate,
        "target_predicates": list(config.target_predicates),
        "split": {
            **config.split.__dict__,
            "counts": {
                "total_pairs": len(pairs),
                "training": len(assignments["training"]),
                "feedback": len(assignments["feedback"]),
                "final": len(assignments["final"]),
            },
        },
        "artifacts": {
            "training_labels": {
                "path": training_path.name,
                "sha256": hashes["training"],
            },
            "feedback_labels": {
                "sha256": hashes["feedback"],
                "location": "sealed",
            },
            "final_labels": {
                "sha256": hashes["final"],
                "location": "sealed",
            },
        },
    }
    manifest_path = public_dir / "partition-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    sealed_manifest = {
        "schema_version": "1.0",
        "split_id": config.split_id,
        "training_labels": sealed_training_path.name,
        "feedback_labels": feedback_path.name,
        "final_labels": final_path.name,
    }
    sealed_manifest_path = sealed_dir / "sealed-manifest.json"
    sealed_manifest_path.write_text(
        json.dumps(sealed_manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(sealed_manifest_path, 0o600)
    return manifest


def load_label_pairs(path: Path) -> set[Pair]:
    pairs: set[Pair] = set()
    with path.open("rb") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                record = orjson.loads(line)
            except orjson.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON at {path}:{line_number}") from error
            pairs.add((record["subject_id"], record["object_id"]))
    return pairs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create deterministic training, feedback, and final target partitions"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_BENCHMARK_CONFIG)
    parser.add_argument("--edges", type=Path, default=edges_path())
    parser.add_argument("--public-dir", type=Path, default=DEFAULT_PUBLIC_DIR)
    parser.add_argument(
        "--sealed-dir",
        type=Path,
        default=Path(os.environ.get("BENCHMARK_SEALED_DIR", DEFAULT_SEALED_DIR)),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_benchmark_config(args.config)
    manifest = build_partition_artifacts(
        args.edges,
        config,
        args.public_dir,
        args.sealed_dir,
    )
    print(json.dumps(manifest, indent=2))
