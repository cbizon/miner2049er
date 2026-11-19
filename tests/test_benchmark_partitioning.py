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


def _cells_config(groups_path: Path) -> BenchmarkConfig:
    import hashlib

    return BenchmarkConfig.from_dict(
        {
            "schema_version": "1.0",
            "benchmark_id": "test-benchmark",
            "graph_version": "1.0.2",
            "biolink": {"version": BIOLINK_VERSION, "predicate_expansion": "descendants"},
            "target": {
                "predicate": "biolink:treats",
                "predicate_closure": [
                    "biolink:treats",
                    "biolink:ameliorates_condition",
                    "biolink:preventative_for_condition",
                ],
            },
            "split": {
                "algorithm": "sha256-ranked-cells-v1",
                "seed": "test-seed",
                "training_fraction": 0.6,
                "feedback_fraction": 0.2,
                "final_fraction": 0.2,
                "subject_groups": str(groups_path),
                "subject_groups_sha256": hashlib.sha256(groups_path.read_bytes()).hexdigest(),
            },
            "scoring": {"minimum_predictions": 2, "maximum_feedback_submissions_per_run": 3,
                        "metric_decimal_places": 6},
        }
    )


def test_cells_keep_a_subject_group_together_per_disease(tmp_path: Path):
    from miner2049er.partitioning import TargetPair, assign_partitions, load_subject_groups

    groups_path = tmp_path / "groups.tsv"
    groups_path.write_text("node_id\tgroup_id\tnote\nCHEBI:1\tCHEBI:1\t\nCHEBI:2\tCHEBI:1\t\nCHEBI:3\tCHEBI:1\t\n")
    config = _cells_config(groups_path)
    groups = load_subject_groups(groups_path, config.split.subject_groups_sha256)
    pairs = {}
    for drug in range(1, 8):
        for disease in range(1, 6):
            pair = (f"CHEBI:{drug}", f"MONDO:{disease}")
            pairs[pair] = TargetPair(subject_id=pair[0], object_id=pair[1])

    assignments = assign_partitions(pairs, config, groups)

    where = {(p.subject_id, p.object_id): name for name, members in assignments.items() for p in members}
    assert len(where) == len(pairs)
    for disease in range(1, 6):
        sides = {where[(f"CHEBI:{drug}", f"MONDO:{disease}")] for drug in (1, 2, 3)}
        assert len(sides) == 1
    # The split still follows the fractions, within one cell's size.
    assert abs(len(assignments["training"]) - 0.6 * len(pairs)) <= 3


def test_cells_split_fails_on_an_unpinned_groups_file(tmp_path: Path):
    import pytest

    from miner2049er.partitioning import load_subject_groups

    groups_path = tmp_path / "groups.tsv"
    groups_path.write_text("node_id\tgroup_id\nCHEBI:1\tCHEBI:1\n")
    with pytest.raises(ValueError, match="pins"):
        load_subject_groups(groups_path, "0" * 64)


def test_cells_algorithm_requires_groups():
    import pytest

    from miner2049er.benchmark_config import SplitConfig

    with pytest.raises(ValueError, match="needs subject_groups"):
        SplitConfig("sha256-ranked-cells-v1", "seed", 0.7, 0.2, 0.1).validate()
