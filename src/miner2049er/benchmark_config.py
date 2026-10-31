from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from miner2049er.biolink_semantics import predicate_closure
from miner2049er.gandalf_runtime import BIOLINK_VERSION
from miner2049er.settings import ROOT

DEFAULT_BENCHMARK_CONFIG = ROOT / "config" / "benchmark.json"


@dataclass(frozen=True)
class SplitConfig:
    algorithm: str
    seed: str
    training_fraction: float
    feedback_fraction: float
    final_fraction: float

    def validate(self) -> None:
        if self.algorithm != "sha256-ranked-pairs-v1":
            raise ValueError(f"Unsupported split algorithm: {self.algorithm}")
        fractions = (
            self.training_fraction,
            self.feedback_fraction,
            self.final_fraction,
        )
        if any(value <= 0 or value >= 1 for value in fractions):
            raise ValueError("Every split fraction must be between zero and one")
        if abs(sum(fractions) - 1.0) > 1e-9:
            raise ValueError("Split fractions must sum to one")


@dataclass(frozen=True)
class ScoringConfig:
    minimum_predictions: int
    maximum_feedback_submissions_per_run: int
    metric_decimal_places: int

    def validate(self) -> None:
        if self.minimum_predictions < 1:
            raise ValueError("minimum_predictions must be positive")
        if self.maximum_feedback_submissions_per_run < 1:
            raise ValueError("maximum_feedback_submissions_per_run must be positive")
        if not 0 <= self.metric_decimal_places <= 12:
            raise ValueError("metric_decimal_places must be between 0 and 12")


@dataclass(frozen=True)
class BenchmarkConfig:
    schema_version: str
    benchmark_id: str
    graph_version: str
    biolink_version: str
    predicate_expansion: str
    target_predicate: str
    target_predicates: tuple[str, ...]
    split: SplitConfig
    scoring: ScoringConfig

    @property
    def split_id(self) -> str:
        payload = json.dumps(
            {
                "benchmark_id": self.benchmark_id,
                "graph_version": self.graph_version,
                "biolink_version": self.biolink_version,
                "predicate_expansion": self.predicate_expansion,
                "target_predicates": self.target_predicates,
                "split": self.split.__dict__,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> BenchmarkConfig:
        biolink = value["biolink"]
        if biolink["version"] != BIOLINK_VERSION:
            raise ValueError(
                f"Benchmark Biolink version {biolink['version']} does not match "
                f"the pinned runtime version {BIOLINK_VERSION}"
            )
        if biolink["predicate_expansion"] != "descendants":
            raise ValueError(
                "The benchmark requires Biolink descendant predicate expansion"
            )
        target = value["target"]
        split = SplitConfig(**value["split"])
        scoring = ScoringConfig(**value["scoring"])
        split.validate()
        scoring.validate()
        predicates = tuple(target["predicate_closure"])
        expected_predicates = predicate_closure([target["predicate"]])
        if set(predicates) != set(expected_predicates):
            raise ValueError(
                "The configured target predicate closure does not match the pinned "
                f"Biolink model: expected {list(expected_predicates)}"
            )
        return cls(
            schema_version=value["schema_version"],
            benchmark_id=value["benchmark_id"],
            graph_version=value["graph_version"],
            biolink_version=biolink["version"],
            predicate_expansion=biolink["predicate_expansion"],
            target_predicate=target["predicate"],
            target_predicates=predicates,
            split=split,
            scoring=scoring,
        )


def load_benchmark_config(path: Path = DEFAULT_BENCHMARK_CONFIG) -> BenchmarkConfig:
    return BenchmarkConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
