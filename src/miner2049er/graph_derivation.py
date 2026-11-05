"""Derive a graph version from a Translator KG release by merging nodes.

Translator 1.0.2 carries some drugs twice: a stereo-unspecified node (often
from the clinical-trials ingest) and the drug's specified stereoisomer, with
nothing linking them. A replacement table maps each unspecified node to the one
specified node it stands for. The derivation streams the release once:

- nodes: replaced nodes are dropped; each replacement node lists the ids it
  absorbed in equivalent_identifiers;
- edges: subject and object are rewritten through the table; an edge whose
  rewrite makes it identical (apart from its id) to an edge already written is
  dropped, and so is an edge the rewrite turns into a self-loop.

Unchanged lines are copied byte for byte. The result is a source directory the
rest of the pipeline reads like a fetched release, with graph-metadata.json
carrying the new version and derivation-manifest.json recording what changed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import orjson
import pyarrow as pa

from miner2049er.settings import source_file
from miner2049er.source_files import open_source


def _output_stream(path: Path, final_name: str):
    """Write zstd when the final file is .zst, as the readers expect."""
    return pa.output_stream(
        str(path), compression="zstd" if final_name.endswith(".zst") else None
    )


def load_replacements(path: Path) -> dict[str, str]:
    """Map replaced node id -> replacement node id from rows with status=replace."""
    replacements: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["status"] != "replace":
                continue
            old, new = row["unspecified_id"], row["replacement_id"]
            if not old or not new or old == new:
                raise ValueError(f"Bad replacement row: {old!r} -> {new!r}")
            if old in replacements and replacements[old] != new:
                raise ValueError(f"{old} has two replacements")
            replacements[old] = new
    chained = set(replacements) & set(replacements.values())
    if chained:
        raise ValueError(f"Replacement targets are themselves replaced: {sorted(chained)}")
    if not replacements:
        raise ValueError(f"No status=replace rows in {path}")
    return replacements


def _edge_key(edge: dict[str, Any]) -> bytes:
    content = {key: value for key, value in edge.items() if key != "id"}
    return hashlib.blake2b(
        orjson.dumps(content, option=orjson.OPT_SORT_KEYS), digest_size=16
    ).digest()


def derive_nodes(
    source: Path, output: Path, replacements: dict[str, str], final_name: str
) -> Counter:
    absorbed: dict[str, list[str]] = {}
    for old, new in replacements.items():
        absorbed.setdefault(new, []).append(old)
    counts: Counter = Counter()
    seen_old: set[str] = set()
    seen_new: set[str] = set()
    with open_source(source) as lines, _output_stream(output, final_name) as out:
        for line in lines:
            node = orjson.loads(line)
            node_id = node["id"]
            counts["nodes_read"] += 1
            if node_id in replacements:
                seen_old.add(node_id)
                counts["nodes_dropped"] += 1
                continue
            if node_id in absorbed:
                seen_new.add(node_id)
                identifiers = list(node.get("equivalent_identifiers") or [node_id])
                identifiers += [old for old in sorted(absorbed[node_id]) if old not in identifiers]
                node["equivalent_identifiers"] = identifiers
                out.write(orjson.dumps(node) + b"\n")
                counts["nodes_extended"] += 1
            else:
                out.write(line if line.endswith(b"\n") else line + b"\n")
            counts["nodes_written"] += 1
    missing_old = set(replacements) - seen_old
    missing_new = set(absorbed) - seen_new
    if missing_old or missing_new:
        raise ValueError(
            f"Replacement table names nodes absent from the graph: "
            f"replaced {sorted(missing_old)[:10]} ({len(missing_old)}), "
            f"replacements {sorted(missing_new)[:10]} ({len(missing_new)})"
        )
    return counts


def derive_edges(
    source: Path, output: Path, replacements: dict[str, str], final_name: str
) -> Counter:
    # Duplicates can only arise on edges touching a replacement node, so only
    # those edges' keys are kept in memory.
    targets = set(replacements.values())
    seen: set[bytes] = set()
    counts: Counter = Counter()
    with open_source(source) as lines, _output_stream(output, final_name) as out:
        for line in lines:
            edge = orjson.loads(line)
            counts["edges_read"] += 1
            subject = replacements.get(edge["subject"], edge["subject"])
            obj = replacements.get(edge["object"], edge["object"])
            rewritten = subject != edge["subject"] or obj != edge["object"]
            if rewritten:
                counts["edges_rewritten"] += 1
                if subject == obj:
                    counts["edges_dropped_self_loop"] += 1
                    continue
                edge["subject"], edge["object"] = subject, obj
            if subject in targets or obj in targets:
                key = _edge_key(edge)
                if key in seen:
                    counts["edges_dropped_duplicate"] += 1
                    continue
                seen.add(key)
            if rewritten:
                out.write(orjson.dumps(edge) + b"\n")
            else:
                out.write(line if line.endswith(b"\n") else line + b"\n")
            counts["edges_written"] += 1
    return counts


def derive_graph(
    *,
    source_dir: Path,
    replacements_path: Path,
    output_dir: Path,
    graph_version: str,
) -> dict[str, Any]:
    replacements = load_replacements(replacements_path)
    metadata = json.loads((source_dir / "graph-metadata.json").read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    for kind, derive in (("nodes", derive_nodes), ("edges", derive_edges)):
        target = source_file(output_dir, kind)
        partial = target.with_name(target.name + ".partial")
        counts.update(derive(source_file(source_dir, kind), partial, replacements, target.name))
        partial.replace(target)
    manifest = {
        "graph_version": graph_version,
        "derived_from": metadata.get("version"),
        "replacements": {
            "path": replacements_path.name,
            "sha256": hashlib.sha256(replacements_path.read_bytes()).hexdigest(),
            "count": len(replacements),
        },
        "counts": dict(sorted(counts.items())),
    }
    derived_metadata = {**metadata, "version": graph_version, "derivation": manifest}
    (output_dir / "graph-metadata.json").write_text(
        json.dumps(derived_metadata, indent=2) + "\n", encoding="utf-8"
    )
    # Written last: its presence means the derivation finished.
    (output_dir / "derivation-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Derive a graph version by merging nodes through a replacement table"
    )
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--replacements", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--graph-version", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = derive_graph(
        source_dir=args.source_dir,
        replacements_path=args.replacements,
        output_dir=args.output_dir,
        graph_version=args.graph_version,
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
