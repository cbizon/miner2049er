from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = Path("/Users/bizon/Projects/ROBOKOP/ORION")
DEFAULT_GRAPH_VERSION = "1.0.2"


def source_dir() -> Path:
    return Path(os.environ.get("SOURCE_DIR", DEFAULT_SOURCE_DIR))


def graph_version() -> str:
    return os.environ.get("GRAPH_VERSION", DEFAULT_GRAPH_VERSION)


def nodes_path() -> Path:
    return source_dir() / "nodes.jsonl"


def edges_path() -> Path:
    return source_dir() / "edges.jsonl"


def metadata_path() -> Path:
    return source_dir() / "graph-metadata.json"


def gandalf_path() -> Path:
    return ROOT / "data" / "gandalf" / graph_version()


def neo4j_import_path() -> Path:
    return ROOT / "data" / "neo4j" / "import" / graph_version()

