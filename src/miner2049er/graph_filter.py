from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import orjson

from miner2049er.partitioning import Pair, load_label_pairs


def load_holdout_pairs(paths: list[Path]) -> set[Pair]:
    pairs: set[Pair] = set()
    for path in paths:
        pairs.update(load_label_pairs(path))
    return pairs


def edge_is_visible(
    edge: dict[str, Any],
    target_predicates: set[str],
    holdout_pairs: set[Pair],
) -> bool:
    if edge.get("predicate") not in target_predicates:
        return True
    return (edge.get("subject"), edge.get("object")) not in holdout_pairs


class FilteredKGXJsonlSource:
    """Gandalf graph source that omits held-out target edges without copying the KG."""

    def __init__(
        self,
        edge_path: Path,
        node_path: Path,
        target_predicates: set[str],
        holdout_pairs: set[Pair],
    ):
        self.edge_path = edge_path
        self.node_path = node_path
        self.target_predicates = target_predicates
        self.holdout_pairs = holdout_pairs

    def _raw_edges(self) -> Iterator[dict[str, Any]]:
        with self.edge_path.open("rb") as stream:
            for line in stream:
                edge = orjson.loads(line)
                if edge_is_visible(edge, self.target_predicates, self.holdout_pairs):
                    yield edge

    def iter_edge_triples(self):
        for edge in self._raw_edges():
            yield edge["subject"], edge["object"], edge["predicate"]

    def iter_edges(self):
        from gandalf.normalize import normalize_edge
        from gandalf.sources.base import validate_normalized_edge

        for raw_edge in self._raw_edges():
            edge = normalize_edge(raw_edge)
            validate_normalized_edge(edge)
            yield edge

    def iter_nodes(self):
        from gandalf.normalize import normalize_node
        from gandalf.sources.base import validate_normalized_node

        with self.node_path.open("rb") as stream:
            for line in stream:
                node = normalize_node(orjson.loads(line))
                if not node.get("id"):
                    continue
                validate_normalized_node(node)
                yield node
