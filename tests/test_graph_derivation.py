from __future__ import annotations

import gzip
import json
from pathlib import Path

import pyarrow as pa
import pytest

from miner2049er.graph_derivation import TMKP, derive_graph, load_replacements
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
        replacements_paths=[table],
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
        replacements_paths=[_table(tmp_path, "replace\tPUBCHEM.COMPOUND:1\tCHEBI:1\n")],
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
            replacements_paths=[_table(tmp_path, "replace\tPUBCHEM.COMPOUND:1\tCHEBI:9\n")],
            output_dir=output,
            graph_version="1.0.2.1",
        )
    assert not (output / "derivation-manifest.json").exists()


def test_load_replacements_rejects_chains(tmp_path: Path):
    table = _table(tmp_path, "replace\tA:1\tB:1\nreplace\tB:1\tC:1\n")
    with pytest.raises(ValueError, match="themselves replaced"):
        load_replacements(table)


def test_load_replacements_follows_chains_across_tables(tmp_path: Path):
    stereo = tmp_path / "stereo.tsv"
    stereo.write_text(HEADER + "replace\tB:1\tC:1\n")
    parent = tmp_path / "parent.tsv"
    parent.write_text("status\treplaced_id\treplacement_id\nreplace\tA:1\tB:1\n")
    assert load_replacements([stereo, parent]) == {"A:1": "C:1", "B:1": "C:1"}


def test_load_replacements_rejects_conflicts_across_tables(tmp_path: Path):
    first = tmp_path / "first.tsv"
    first.write_text(HEADER + "replace\tA:1\tB:1\n")
    second = tmp_path / "second.tsv"
    second.write_text("status\treplaced_id\treplacement_id\nreplace\tA:1\tC:1\n")
    with pytest.raises(ValueError, match="two replacements"):
        load_replacements([first, second])


TMKP_SOURCE = [{"resource_id": TMKP, "resource_role": "primary_knowledge_source"}]


def _study(*sentences: str) -> dict:
    return {"s1": {"id": "s1", "category": ["biolink:Study"], "has_study_results": [
        {"id": sentence, "category": ["biolink:TextMiningStudyResult"], "xref": [f"PMID:{sentence[-1]}"]}
        for sentence in sentences]}}


def _gz(path: Path, lines: list[str]) -> None:
    with gzip.open(path, "wt") as handle:
        handle.write("".join(line + "\n" for line in lines))


def _tmkp_row(subject, predicate, obj, direction, edge_id, association, sentences, attributes="[]"):
    row = [subject, predicate, obj] + [""] * 6 + [direction] + [""] * 3
    row += [edge_id, association, "0.9", "|".join(sentences), "|".join(f"PMID:{s[-1]}" for s in sentences), attributes]
    return "\t".join(row)


def _cleanup_dir(tmp_path: Path) -> Path:
    cleanup = tmp_path / "tmkp"
    cleanup.mkdir()
    gene = "biolink:ChemicalToGeneAssociation"
    _gz(cleanup / "edges.tsv.gz", [
        _tmkp_row("RAW:drug", "biolink:affects", "RAW:gene", "increased", "t1", gene, ["tmkp:a1", "tmkp:a2"]),
        _tmkp_row("RAW:drug", "biolink:affects", "RAW:gene2", "decreased", "t2", gene, ["tmkp:b1"]),
        _tmkp_row("RAW:drug", "biolink:treats_or_applied_or_studied_to_treat", "MONDO:1", "", "t3",
                  "biolink:ChemicalToDiseaseOrPhenotypicFeatureAssociation", ["tmkp:c1"]),
    ])
    _gz(cleanup / "tmkp_treats_jev_v3_dropped_edges.txt.gz", ["t3"])
    _gz(cleanup / "tmkp_chem_gene_dropped_edges.txt.gz", ["t2\tdecreased"])
    _gz(cleanup / "tmkp_chem_gene_pruned_sentences.txt.gz", ["t1\tincreased\ttmkp:a2"])
    result = {"attribute_type_id": "biolink:has_supporting_study_result", "value": "tmkp:r1", "attributes": [
        {"attribute_type_id": "biolink:supporting_text", "value": "Drug raises gene."},
        {"attribute_type_id": "biolink:publications", "value": "PMID:7"},
        {"attribute_type_id": "biolink:subject_location_in_text", "value": "0|4"}]}
    repair = _tmkp_row("RAW:drug", "biolink:affects", "RAW:gene", "increased", "tmkp-repair:r", gene,
                       ["tmkp:r1"], json.dumps([result]))
    _gz(cleanup / "tmkp_chem_gene_repaired_edges.tsv.gz", [repair])
    for family in ("gene_gene", "chem_disease"):
        _gz(cleanup / f"tmkp_{family}_dropped_edges.txt.gz", [])
        _gz(cleanup / f"tmkp_{family}_pruned_sentences.txt.gz", [])
        _gz(cleanup / f"tmkp_{family}_repaired_edges.tsv.gz", [])
    _gz(cleanup / "tmkp_chem_gene_pruned_sentences.txt.gz", ["t1\tincreased\ttmkp:a2"])
    return cleanup


def _tmkp_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    _jsonl(source / "nodes.jsonl", [
        {"id": "CHEBI:1", "equivalent_identifiers": ["CHEBI:1", "RAW:drug"]},
        {"id": "NCBIGene:1", "equivalent_identifiers": ["NCBIGene:1", "RAW:gene"]},
        {"id": "NCBIGene:2", "equivalent_identifiers": ["NCBIGene:2", "RAW:gene2"]},
        {"id": "MONDO:1"},
    ])
    common = {"subject": "CHEBI:1", "original_subject": "RAW:drug", "sources": TMKP_SOURCE}
    trial_studies = {"NCT1": {"id": "NCT1"}, "NCT2": {"id": "NCT2"}}
    _jsonl(source / "edges.jsonl", [
        {"id": "g1", **common, "predicate": "biolink:affects", "object": "NCBIGene:1", "original_object": "RAW:gene",
         "object_direction_qualifier": "increased", "has_supporting_studies": _study("tmkp:a1", "tmkp:a2")},
        {"id": "g2", **common, "predicate": "biolink:affects", "object": "NCBIGene:2", "original_object": "RAW:gene2",
         "object_direction_qualifier": "decreased", "has_supporting_studies": _study("tmkp:b1")},
        {"id": "g3", **common, "predicate": "biolink:treats_or_applied_or_studied_to_treat", "object": "MONDO:1",
         "original_object": "MONDO:1", "has_supporting_studies": _study("tmkp:c1")},
        {"id": "c1", "subject": "CHEBI:1", "predicate": "biolink:in_clinical_trials_for", "object": "MONDO:1",
         "has_supporting_studies": trial_studies},
        {"id": "c2", "subject": "NCBIGene:1", "predicate": "biolink:in_clinical_trials_for", "object": "MONDO:1",
         "has_supporting_studies": {"NCT1": {"id": "NCT1"}}},
    ])
    (source / "graph-metadata.json").write_text(json.dumps({"version": "1.0.2"}))
    return source


def test_derive_graph_applies_tmkp_cleanup_and_study_removals(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SOURCE_COMPRESSION", "none")
    removals = tmp_path / "removals.tsv"
    removals.write_text("edge_id\tstudy_id\nc1\tNCT2\nc2\tNCT1\n")
    output = tmp_path / "derived"

    manifest = derive_graph(
        source_dir=_tmkp_source(tmp_path),
        replacements_paths=[_table(tmp_path, "replace\tNCBIGene:2\tNCBIGene:1\n")],
        output_dir=output,
        graph_version="1.0.2.2",
        tmkp_cleanup_dir=_cleanup_dir(tmp_path),
        study_removals_path=removals,
    )

    edges = {edge["id"]: edge for edge in _read(output / "edges.jsonl")}
    # g2 lost its only sentence, g3 is a dropped treats edge, c2 lost its only trial.
    assert set(edges) == {"g1", "c1"}
    results = edges["g1"]["has_supporting_studies"]
    # g1 kept tmkp:a1, lost the pruned tmkp:a2, and absorbed the repaired edge with the same key.
    assert [r["id"] for r in results["s1"]["has_study_results"]] == ["tmkp:a1"]
    repaired = results["tmkp-repair:r"]["has_study_results"][0]
    assert repaired["supporting_text"] == ["Drug raises gene."]
    assert repaired["subject_location_in_text"] == [0, 4]
    assert edges["g1"]["publications"] == ["PMID:1", "PMID:7"]
    assert set(edges["c1"]["has_supporting_studies"]) == {"NCT1"}
    counts = manifest["counts"]
    assert counts["tmkp_edges_dropped"] == 2
    assert counts["tmkp_edges_pruned"] == 1
    assert counts["tmkp_repairs_merged"] == 1
    assert counts["study_removal_edges_dropped"] == 1


def test_derive_graph_appends_unmatched_repairs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SOURCE_COMPRESSION", "none")
    source = _tmkp_source(tmp_path)
    edges = [e for e in _read(source / "edges.jsonl") if e["id"] != "g1"]
    _jsonl(source / "edges.jsonl", edges)

    manifest = derive_graph(
        source_dir=source,
        replacements_paths=[_table(tmp_path, "replace\tNCBIGene:2\tNCBIGene:1\n")],
        output_dir=tmp_path / "derived",
        graph_version="1.0.2.2",
        tmkp_cleanup_dir=_cleanup_dir(tmp_path),
    )

    appended = [e for e in _read(tmp_path / "derived" / "edges.jsonl") if e["id"] == "tmkp-repair:r"]
    assert len(appended) == 1
    assert (appended[0]["subject"], appended[0]["object"]) == ("CHEBI:1", "NCBIGene:1")
    assert manifest["counts"]["tmkp_repairs_appended"] == 1


def test_study_removals_must_match_the_graph(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SOURCE_COMPRESSION", "none")
    removals = tmp_path / "removals.tsv"
    removals.write_text("edge_id\tstudy_id\nc1\tNCT9\n")
    with pytest.raises(ValueError, match="absent from the graph"):
        derive_graph(
            source_dir=_tmkp_source(tmp_path),
            replacements_paths=[_table(tmp_path, "replace\tNCBIGene:2\tNCBIGene:1\n")],
            output_dir=tmp_path / "derived",
            graph_version="1.0.2.2",
            study_removals_path=removals,
        )


def test_repairs_map_to_the_node_with_that_id_when_listed_twice(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SOURCE_COMPRESSION", "none")
    source = _tmkp_source(tmp_path)
    nodes = _read(source / "nodes.jsonl") + [{"id": "RAW:gene", "equivalent_identifiers": ["RAW:gene"]}]
    _jsonl(source / "nodes.jsonl", nodes)
    _jsonl(source / "edges.jsonl", [e for e in _read(source / "edges.jsonl") if e["id"] != "g1"])

    derive_graph(
        source_dir=source,
        replacements_paths=[_table(tmp_path, "replace\tNCBIGene:2\tNCBIGene:1\n")],
        output_dir=tmp_path / "derived",
        graph_version="1.0.2.2",
        tmkp_cleanup_dir=_cleanup_dir(tmp_path),
    )

    appended = [e for e in _read(tmp_path / "derived" / "edges.jsonl") if e["id"] == "tmkp-repair:r"]
    assert appended[0]["object"] == "RAW:gene"
