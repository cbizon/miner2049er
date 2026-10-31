from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

from miner2049er.gandalf_runtime import configure_local_biolink
from miner2049er.graph_filter import FilteredKGXJsonlSource, load_holdout_pairs
from miner2049er.settings import edges_path, gandalf_path, nodes_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and save the Gandalf mmap graph")
    parser.add_argument("--nodes", type=Path, default=nodes_path())
    parser.add_argument("--edges", type=Path, default=edges_path())
    parser.add_argument("--output", type=Path, default=gandalf_path())
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--exclude-labels", type=Path, action="append", default=[])
    parser.add_argument("--target-predicate", action="append", default=[])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_local_biolink()

    from gandalf import build_graph_from_jsonl
    from gandalf.loader import _build_graph_from_source
    from gandalf.logging_config import configure_logging

    configure_logging(logging.INFO)

    for path in (args.nodes, args.edges):
        if not path.is_file():
            raise FileNotFoundError(path)

    if args.output.exists():
        if not args.overwrite:
            raise FileExistsError(f"{args.output} already exists; pass --overwrite to rebuild")
        shutil.rmtree(args.output)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    holdout_pairs = load_holdout_pairs(args.exclude_labels)
    target_predicates = set(args.target_predicate)
    if holdout_pairs and not target_predicates:
        raise ValueError("--target-predicate is required when --exclude-labels is used")
    if holdout_pairs:
        source = FilteredKGXJsonlSource(
            args.edges,
            args.nodes,
            target_predicates,
            holdout_pairs,
        )
        graph = _build_graph_from_source(source)
    else:
        graph = build_graph_from_jsonl(
            edge_jsonl_path=str(args.edges),
            node_jsonl_path=str(args.nodes),
        )
    graph.save_mmap(args.output)

    if graph.lmdb_store is not None:
        graph.lmdb_store.close()

    print(f"Saved Gandalf graph to {args.output}")
