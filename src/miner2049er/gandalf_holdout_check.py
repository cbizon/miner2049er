"""Check over TRAPI that a built Gandalf store hides every held-out label.

Samples feedback and final pairs from the sealed labels and requires that
Gandalf returns no target-predicate edge for any of them. Training pairs are
sampled as a positive control: they must be found, so the check cannot pass
because of an ID or predicate mismatch. Only counts are printed, never pairs.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import httpx

from miner2049er.benchmark_config import DEFAULT_BENCHMARK_CONFIG, load_benchmark_config
from miner2049er.partitioning import Pair, load_label_pairs


def pair_query(pair: Pair, predicates: list[str]) -> dict[str, Any]:
    subject, object_ = pair
    return {
        "message": {
            "query_graph": {
                "nodes": {"n0": {"ids": [subject]}, "n1": {"ids": [object_]}},
                "edges": {"e0": {"subject": "n0", "object": "n1", "predicates": predicates}},
            }
        },
        "parameters": {"subclass": False},
    }


def sample_pairs(pairs: set[Pair], size: int, seed: str) -> list[Pair]:
    if not pairs:
        raise ValueError("Cannot sample from an empty label set")
    ordered = sorted(pairs)
    return random.Random(seed).sample(ordered, min(size, len(ordered)))


def count_found(
    client: httpx.Client, gandalf_url: str, pairs: list[Pair], predicates: list[str]
) -> int:
    found = 0
    for pair in pairs:
        response = client.post(f"{gandalf_url.rstrip('/')}/query", json=pair_query(pair, predicates))
        if not response.is_success:
            raise RuntimeError(f"Gandalf returned HTTP {response.status_code}: {response.text[:500]}")
        if response.json()["message"].get("results"):
            found += 1
    return found


def check_holdout(
    *,
    gandalf_url: str,
    holdout: dict[str, set[Pair]],
    training: set[Pair],
    predicates: list[str],
    sample_size: int,
    seed: str,
    timeout_seconds: float = 120,
) -> dict[str, Any]:
    summary: dict[str, Any] = {"predicates": predicates}
    with httpx.Client(timeout=timeout_seconds) as client:
        for name, pairs in holdout.items():
            sample = sample_pairs(pairs, sample_size, f"{seed}:{name}")
            summary[name] = {
                "sampled": len(sample),
                "found": count_found(client, gandalf_url, sample, predicates),
            }
        sample = sample_pairs(training, sample_size, f"{seed}:training")
        summary["training"] = {
            "sampled": len(sample),
            "found": count_found(client, gandalf_url, sample, predicates),
        }
    leaked = {name: summary[name]["found"] for name in holdout if summary[name]["found"]}
    if leaked:
        raise AssertionError(f"Held-out pairs visible in Gandalf: {leaked}; {summary}")
    if summary["training"]["found"] != summary["training"]["sampled"]:
        raise AssertionError(
            f"Training pairs missing from Gandalf, so absence proves nothing: {summary}"
        )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gandalf-url", required=True)
    parser.add_argument("--sealed-manifest", type=Path, required=True)
    parser.add_argument("--training-labels", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_BENCHMARK_CONFIG)
    parser.add_argument("--sample-size", type=int, default=250)
    parser.add_argument("--seed", default="gandalf-holdout-check")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_benchmark_config(args.config)
    sealed = json.loads(args.sealed_manifest.read_text(encoding="utf-8"))
    sealed_dir = args.sealed_manifest.parent
    summary = check_holdout(
        gandalf_url=args.gandalf_url,
        holdout={
            "feedback": load_label_pairs(sealed_dir / sealed["feedback_labels"]),
            "final": load_label_pairs(sealed_dir / sealed["final_labels"]),
        },
        training=load_label_pairs(args.training_labels),
        predicates=list(config.target_predicates),
        sample_size=args.sample_size,
        seed=args.seed,
    )
    print(json.dumps(summary, indent=2))
