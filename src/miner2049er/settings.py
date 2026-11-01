from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = Path("/Users/bizon/Projects/ROBOKOP/ORION")
DEFAULT_GRAPH_VERSION = "1.0.2"
# "none" reads nodes.jsonl/edges.jsonl; "zstd" reads nodes.jsonl.zst/edges.jsonl.zst
# as written by miner-fetch-source, so the 28 GB source never sits uncompressed.
SOURCE_COMPRESSIONS = {"none": "", "zstd": ".zst"}


def source_dir() -> Path:
    return Path(os.environ.get("SOURCE_DIR", DEFAULT_SOURCE_DIR))


def graph_version() -> str:
    return os.environ.get("GRAPH_VERSION", DEFAULT_GRAPH_VERSION)


def source_compression() -> str:
    compression = os.environ.get("SOURCE_COMPRESSION", "none")
    if compression not in SOURCE_COMPRESSIONS:
        raise ValueError(
            f"SOURCE_COMPRESSION must be one of {sorted(SOURCE_COMPRESSIONS)}, "
            f"not {compression!r}"
        )
    return compression


def source_file(directory: Path, kind: str) -> Path:
    """Path of the nodes or edges JSONL in a source directory."""
    if kind not in {"nodes", "edges"}:
        raise ValueError(f"Unknown source file kind: {kind}")
    return directory / f"{kind}.jsonl{SOURCE_COMPRESSIONS[source_compression()]}"


def nodes_path() -> Path:
    return source_file(source_dir(), "nodes")


def edges_path() -> Path:
    return source_file(source_dir(), "edges")


def metadata_path() -> Path:
    return source_dir() / "graph-metadata.json"


def gandalf_path() -> Path:
    return ROOT / "data" / "gandalf" / graph_version()


def neo4j_import_path() -> Path:
    return ROOT / "data" / "neo4j" / "import" / graph_version()

