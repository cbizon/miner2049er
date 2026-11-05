from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pytest

from miner2049er.graph_derivation import derive_graph, load_replacements
from miner2049er.source_files import open_source

HEADER = "status\tunspecified_id\treplacement_id\n"


def _jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


def _read(path: Path) -> list[dict]:
    with open_source(path) as stream:
        return [json.loads(line) for line in stream]


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    _jsonl(
        source / "nodes.jsonl",
        [
            {"id": "PUBCHEM.COMPOUND:1", "name": "drug"},
            {"id": "CHEBI:1", "name": "Drug", "equivalent_identifiers": ["CHEBI:1"]},
            {"id": "MONDO:1", "name": "disease"},
            {"id": "MONDO:2", "name": "other disease"},
        ],
    )
    trial = {"predicate": "biolink:in_clinical_trials_for", "object": "MONDO:1"}
    _jsonl(
        source / "edges.jsonl",
        [
            {"id": "e1", "subject": "PUBCHEM.COMPOUND:1", **trial},
            {"id": "e2", "subject": "CHEBI:1", **trial},
            {"id": "e3", "subject": "PUBCHEM.COMPOUND:1", "predicate": "biolink:treats",
             "object": "MONDO:2"},
            {"id": "e4", "subject": "PUBCHEM.COMPOUND:1", "predicate": "biolink:related_to",
             "object": "CHEBI:1"},
            {"id": "e5", "subject": "MONDO:1", "predicate": "biolink:related_to",
             "object": "MONDO:2"},
        ],
    )
    (source / "graph-metadata.json").write_text(json.dumps({"version": "1.0.2"}))
    return source


def _table(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "replacements.tsv"
    path.write_text(HEADER + rows)
    return path


def test_derive_graph_merges_replaced_nodes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SOURCE_COMPRESSION", "none")
    table = _table(
        tmp_path, "replace\tPUBCHEM.COMPOUND:1\tCHEBI:1\nambiguous\tMONDO:2\tMONDO:1\n"
    )
    output = tmp_path / "derived"

    manifest = derive_graph(
        source_dir=_source(tmp_path),
        replacements_path=table,
        output_dir=output,
        graph_version="1.0.2.1",
    )

    nodes = {node["id"]: node for node in _read(output / "nodes.jsonl")}
    assert set(nodes) == {"CHEBI:1", "MONDO:1", "MONDO:2"}
    assert nodes["CHEBI:1"]["equivalent_identifiers"] == ["CHEBI:1", "PUBCHEM.COMPOUND:1"]
    edges = _read(output / "edges.jsonl")
    # Rewritten e1 is identical to e2, so the later copy is dropped; e4 becomes a self-loop.
    assert [edge["id"] for edge in edges] == ["e1", "e3", "e5"]
    assert [edge["subject"] for edge in edges[:2]] == ["CHEBI:1", "CHEBI:1"]
    assert manifest["counts"]["edges_dropped_duplicate"] == 1
    assert manifest["counts"]["edges_dropped_self_loop"] == 1
    assert manifest["counts"]["edges_rewritten"] == 3
    metadata = json.loads((output / "graph-metadata.json").read_text())
    assert metadata["version"] == "1.0.2.1"
    assert metadata["derivation"]["derived_from"] == "1.0.2"
    assert (output / "derivation-manifest.json").is_file()


def test_derive_graph_writes_zstd_when_source_is_compressed(tmp_path: Path, monkeypatch):
    source = _source(tmp_path)
    monkeypatch.setenv("SOURCE_COMPRESSION", "zstd")
    for kind in ("nodes", "edges"):
        plain = source / f"{kind}.jsonl"
        with pa.output_stream(str(source / f"{kind}.jsonl.zst"), compression="zstd") as out:
            out.write(plain.read_bytes())
        plain.unlink()
    output = tmp_path / "derived"

    derive_graph(
        source_dir=source,
        replacements_path=_table(tmp_path, "replace\tPUBCHEM.COMPOUND:1\tCHEBI:1\n"),
        output_dir=output,
        graph_version="1.0.2.1",
    )

    assert len(_read(output / "edges.jsonl.zst")) == 3


def test_derive_graph_fails_when_a_replacement_node_is_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SOURCE_COMPRESSION", "none")
    output = tmp_path / "derived"

    with pytest.raises(ValueError, match="absent from the graph"):
        derive_graph(
            source_dir=_source(tmp_path),
            replacements_path=_table(tmp_path, "replace\tPUBCHEM.COMPOUND:1\tCHEBI:9\n"),
            output_dir=output,
            graph_version="1.0.2.1",
        )
    assert not (output / "derivation-manifest.json").exists()


def test_load_replacements_rejects_chains(tmp_path: Path):
    table = _table(tmp_path, "replace\tA:1\tB:1\nreplace\tB:1\tC:1\n")
    with pytest.raises(ValueError, match="themselves replaced"):
        load_replacements(table)
