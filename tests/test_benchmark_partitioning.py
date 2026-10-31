import json
from pathlib import Path

from miner2049er.benchmark_config import BenchmarkConfig
from miner2049er.gandalf_runtime import BIOLINK_VERSION
from miner2049er.graph_filter import edge_is_visible
from miner2049er.partitioning import (
    build_partition_artifacts,
    collect_target_pairs,
    load_label_pairs,
)


def _config() -> BenchmarkConfig:
    return BenchmarkConfig.from_dict(
        {
            "schema_version": "1.0",
            "benchmark_id": "test-benchmark",
            "graph_version": "1.0.2",
            "biolink": {
                "version": BIOLINK_VERSION,
                "predicate_expansion": "descendants",
            },
            "target": {
                "predicate": "biolink:treats",
                "predicate_closure": [
                    "biolink:treats",
                    "biolink:ameliorates_condition",
                    "biolink:preventative_for_condition",
                ],
            },
            "split": {
                "algorithm": "sha256-ranked-pairs-v1",
                "seed": "test-seed",
                "training_fraction": 0.7,
                "feedback_fraction": 0.2,
                "final_fraction": 0.1,
            },
            "scoring": {
                "minimum_predictions": 2,
                "maximum_feedback_submissions_per_run": 3,
                "metric_decimal_places": 6,
            },
        }
    )


def _write_edges(path: Path) -> None:
    records = []
    for index in range(10):
        records.append(
            {
                "id": f"target-{index}",
                "subject": f"CHEBI:{index}",
                "predicate": "biolink:treats",
                "object": f"MONDO:{index}",
                "sources": [
                    {
                        "resource_id": "infores:test",
                        "resource_role": "primary_knowledge_source",
                    }
                ],
            }
        )
    records.extend(
        [
            {
                "id": "duplicate-target",
                "subject": "CHEBI:0",
                "predicate": "biolink:ameliorates_condition",
                "object": "MONDO:0",
                "sources": [
                    {
                        "resource_id": "infores:second",
                        "resource_role": "primary_knowledge_source",
                    }
                ],
            },
            {
                "id": "non-target",
                "subject": "CHEBI:0",
                "predicate": "biolink:affects",
                "object": "MONDO:0",
                "sources": [],
            },
        ]
    )
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_partition_artifacts_are_pair_level_and_sealed(tmp_path):
    edges = tmp_path / "edges.jsonl"
    public = tmp_path / "public"
    sealed = tmp_path / "sealed"
    _write_edges(edges)

    manifest = build_partition_artifacts(edges, _config(), public, sealed)

    assert manifest["split"]["counts"] == {
        "total_pairs": 10,
        "training": 7,
        "feedback": 2,
        "final": 1,
    }
    public_split = public / _config().split_id
    sealed_split = sealed / _config().split_id
    assert (public_split / "training-labels.jsonl").is_file()
    assert not (public_split / "feedback-labels.jsonl").exists()
    assert (sealed_split / "training-labels.jsonl").is_file()
    assert (sealed_split / "feedback-labels.jsonl").is_file()
    all_pairs = (
        load_label_pairs(public_split / "training-labels.jsonl")
        | load_label_pairs(sealed_split / "feedback-labels.jsonl")
        | load_label_pairs(sealed_split / "final-labels.jsonl")
    )
    assert len(all_pairs) == 10


def test_target_pair_aggregation_and_filter_preserve_non_target_edges(tmp_path):
    edges = tmp_path / "edges.jsonl"
    _write_edges(edges)
    pairs = collect_target_pairs(
        edges,
        {"biolink:treats", "biolink:ameliorates_condition"},
    )

    assert pairs[("CHEBI:0", "MONDO:0")].edge_count == 2
    assert pairs[("CHEBI:0", "MONDO:0")].primary_knowledge_sources == {
        "infores:test",
        "infores:second",
    }
    holdouts = {("CHEBI:0", "MONDO:0")}
    assert not edge_is_visible(
        {
            "subject": "CHEBI:0",
            "predicate": "biolink:treats",
            "object": "MONDO:0",
        },
        {"biolink:treats"},
        holdouts,
    )
    assert edge_is_visible(
        {
            "subject": "CHEBI:0",
            "predicate": "biolink:affects",
            "object": "MONDO:0",
        },
        {"biolink:treats"},
        holdouts,
    )
