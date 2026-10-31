from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from miner2049er.gandalf_runtime import BIOLINK_VERSION
from miner2049er.settings import edges_path, graph_version, metadata_path, nodes_path

GANDALF_COMMIT = "82a1fb2e1bcaac6aaa899f3ff4864fc4501c7879"
NEO4J_IMAGE = "neo4j@sha256:d9dd3dc7d1c78fa959191ff02dbdcbefadceaf83eee23428fb92a58cac8ad3fe"
# Must match scripts/fetch_biolink.sh for BIOLINK_VERSION.
BIOLINK_SCHEMA_SHA256 = "376e4f455877c0bf7f39231e1163bbda8455516609f66300e8ba37fb373ea71b"
BIOLINK_ATTRIBUTES_SHA256 = (
    "ca7c400df55a728a3a96a8c1b8ae435540752fc18b3d300a8b47253346f80d80"
)
BIOLINK_PREDICATE_MAP_SHA256 = (
    "b532220b1d33f0e51794566fa33a736905b5a41ed1fe38839f9e949cb58c796c"
)


def sha256_file(path: Path, chunk_size: int = 16 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, include_hash: bool) -> dict:
    stat = path.stat()
    record = {
        "path": str(path.resolve()),
        "bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
    }
    if include_hash:
        record["sha256"] = sha256_file(path)
    return record


def build_manifest(include_hashes: bool = True) -> dict:
    metadata_file = metadata_path()
    with metadata_file.open(encoding="utf-8") as stream:
        metadata = json.load(stream)

    version = graph_version()
    actual_version = metadata.get("version")
    if actual_version != version:
        raise ValueError(f"Expected graph version {version}, found {actual_version}")

    return {
        "created_at": datetime.now(UTC).isoformat(),
        "graph": {
            "id": metadata.get("@id"),
            "version": actual_version,
            "date_created": metadata.get("dateCreated"),
            "node_count": metadata["schema"]["nodes_summary"]["total_count"],
            "edge_count": metadata["schema"]["edges_summary"]["total_count"],
        },
        "source_files": {
            "nodes": file_record(nodes_path(), include_hashes),
            "edges": file_record(edges_path(), include_hashes),
            "metadata": file_record(metadata_file, include_hashes),
        },
        "tools": {
            "gandalf_commit": GANDALF_COMMIT,
            "neo4j_image": NEO4J_IMAGE,
            "biolink_model": {
                "version": BIOLINK_VERSION,
                "schema_sha256": BIOLINK_SCHEMA_SHA256,
                "attributes_sha256": BIOLINK_ATTRIBUTES_SHA256,
                "predicate_map_sha256": BIOLINK_PREDICATE_MAP_SHA256,
            },
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record the exact Translator source snapshot")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--skip-hashes",
        action="store_true",
        help="Record paths, sizes, and timestamps without hashing large files",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(include_hashes=not args.skip_hashes)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
