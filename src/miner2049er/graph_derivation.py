"""Derive a graph version from a Translator KG release by merging nodes and editing edges.

Translator 1.0.2 carries some drugs several times (a stereo-unspecified node and its stereoisomer, a salt and its
parent, charge states of one molecule) with nothing linking them, and some of its edges are known to be wrong.
Until the upstream fixes land, a derived graph patches them. The derivation streams the release once:

- **Node merges.** One or more replacement tables map a node to the node it is merged into. Replaced nodes are
  dropped; each replacement node lists the ids it absorbed in equivalent_identifiers. Edges are rewritten through
  the tables; an edge whose rewrite makes it identical (apart from its id) to an edge already written is dropped,
  and so is an edge the rewrite turns into a self-loop.
- **TMKP cleanup** (RobokopU24/ORION#455). Text-mining sentences judged not to support their edge are removed:
  every sentence of a dropped TMKP edge, and pruned sentences of kept ones. An edge left with no sentences is
  dropped; a pruned edge keeps the rest and its publications are rebuilt from them. Repaired edges (sentences
  regrouped under the right concepts) are merged into an existing TMKP edge with the same subject, predicate,
  object and qualifiers, or appended.
- **Study removals.** Listed (edge id, study id) pairs are removed from edges' supporting studies, and an edge
  left with no studies is dropped. Used to drop a clinical trial from the extra subjects a single-intervention
  trial was grounded to.

Unchanged lines are copied byte for byte. The result is a source directory the rest of the pipeline reads like a
fetched release, with graph-metadata.json carrying the new version and derivation-manifest.json recording what
changed.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import orjson
import pyarrow as pa

from miner2049er.settings import source_file
from miner2049er.source_files import open_source

TMKP = "infores:text-mining-provider-targeted"
TMKP_TREATS_PREDICATES = frozenset({"biolink:treats", "biolink:treats_or_applied_or_studied_to_treat"})
TMKP_FAMILIES = {
    "biolink:ChemicalToGeneAssociation": "chem_gene",
    "biolink:GeneRegulatoryRelationship": "gene_gene",
    "biolink:ChemicalToDiseaseOrPhenotypicFeatureAssociation": "chem_disease",
}
TMKP_TREATS_DROPPED = "tmkp_treats_jev_v3_dropped_edges.txt.gz"
TMKP_EDGES = "edges.tsv.gz"
# Columns of TMKP's edges.tsv (no header), as RobokopU24/ORION's loadTMKP.TMKPEDGE.
TMKP_QUALIFIER_COLUMNS = {
    3: "qualified_predicate",
    4: "subject_aspect_qualifier",
    5: "subject_direction_qualifier",
    6: "subject_part_qualifier",
    7: "subject_form_or_variant_qualifier",
    8: "object_aspect_qualifier",
    9: "object_direction_qualifier",
    10: "object_part_qualifier",
    11: "object_form_or_variant_qualifier",
    12: "anatomical_context_qualifier",
}
TMKP_ID, TMKP_ASSOCIATION, TMKP_SCORE, TMKP_SENTENCES, TMKP_PUBLICATIONS, TMKP_ATTRIBUTES = 13, 14, 15, 16, 17, 18
MERGE_KEY_FIELDS = ("subject", "predicate", "object", *TMKP_QUALIFIER_COLUMNS.values())


def _output_stream(path: Path, final_name: str):
    """Write zstd when the final file is .zst, as the readers expect."""
    return pa.output_stream(
        str(path), compression="zstd" if final_name.endswith(".zst") else None
    )


def _read_table(path: Path) -> dict[str, str]:
    """Map replaced node id -> replacement node id from one table's status=replace rows.

    The replaced id is in ``replaced_id`` (or ``unspecified_id``, the 1.0.2.1 stereo table's name for it).
    """
    replacements: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        old_column = "replaced_id" if "replaced_id" in (reader.fieldnames or []) else "unspecified_id"
        for row in reader:
            if row["status"] != "replace":
                continue
            old, new = row[old_column], row["replacement_id"]
            if not old or not new or old == new:
                raise ValueError(f"Bad replacement row in {path.name}: {old!r} -> {new!r}")
            if old in replacements and replacements[old] != new:
                raise ValueError(f"{old} has two replacements in {path.name}")
            replacements[old] = new
    chained = set(replacements) & set(replacements.values())
    if chained:
        raise ValueError(f"Replacement targets are themselves replaced: {sorted(chained)}")
    if not replacements:
        raise ValueError(f"No status=replace rows in {path}")
    return replacements


def load_replacements(paths: Path | Sequence[Path]) -> dict[str, str]:
    """Combine replacement tables into one map, resolving merges that chain across tables.

    Within a table a target may not itself be replaced. Across tables (a salt merged into a stereo-unspecified
    node that another table merges into its stereoisomer) the chain is followed to its end; a node with two
    different final targets, or a cycle, fails.
    """
    if isinstance(paths, Path):
        paths = [paths]
    combined: dict[str, str] = {}
    for path in paths:
        for old, new in _read_table(path).items():
            if old in combined and combined[old] != new:
                raise ValueError(f"{old} has two replacements: {combined[old]} and {new}")
            combined[old] = new
    resolved: dict[str, str] = {}
    for old, first in combined.items():
        seen = [old]
        target = first
        while target in combined:
            if target in seen:
                raise ValueError(f"Replacement cycle: {' -> '.join(seen + [target])}")
            seen.append(target)
            target = combined[target]
        resolved[old] = target
    return resolved


def _edge_key(edge: dict[str, Any]) -> bytes:
    content = {key: value for key, value in edge.items() if key != "id"}
    return hashlib.blake2b(
        orjson.dumps(content, option=orjson.OPT_SORT_KEYS), digest_size=16
    ).digest()


def _merge_key(edge: dict[str, Any]) -> tuple:
    return tuple(
        tuple(value) if isinstance(value := edge.get(field), list) else value for field in MERGE_KEY_FIELDS
    )


def _removal_key(sentence: str, predicate: str, direction: str, subject: str, obj: str) -> bytes:
    predicate_class = "treats" if predicate in TMKP_TREATS_PREDICATES else predicate
    return hashlib.blake2b(
        f"{sentence}\t{predicate_class}\t{direction}\t{subject}\t{obj}".encode(), digest_size=16
    ).digest()


def _gzip_rows(path: Path) -> Iterable[list[str]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield line.rstrip("\n").split("\t")


def load_tmkp_removals(cleanup_dir: Path) -> tuple[set[bytes], Counter]:
    """Keys of TMKP sentences to remove: all sentences of dropped edges, and pruned sentences of kept ones.

    A key is (sentence id, predicate class, object direction, raw subject, raw object), so a sentence is removed
    only from the edge it was judged against. TMKP edge ids ignore direction, and a treats and a contributes_to
    edge can share one, so the lists are matched as ORION#455 matches them: treats by id and predicate, the other
    families by (id, direction).
    """
    treats_dropped = {row[0] for row in _gzip_rows(cleanup_dir / TMKP_TREATS_DROPPED)}
    dropped = {
        family: {(row[0], row[1] if len(row) > 1 else "") for row in _gzip_rows(
            cleanup_dir / f"tmkp_{family}_dropped_edges.txt.gz")}
        for family in TMKP_FAMILIES.values()
    }
    pruned = {
        family: {(row[0], row[1], row[2]) for row in _gzip_rows(cleanup_dir / f"tmkp_{family}_pruned_sentences.txt.gz")}
        for family in TMKP_FAMILIES.values()
    }
    removals: set[bytes] = set()
    counts: Counter = Counter()
    for row in _gzip_rows(cleanup_dir / TMKP_EDGES):
        subject, predicate, obj, direction = row[0], row[1], row[2], row[9]
        edge_id, sentences = row[TMKP_ID], row[TMKP_SENTENCES].split("|")
        if predicate in TMKP_TREATS_PREDICATES:
            if edge_id in treats_dropped:
                removals.update(_removal_key(s, predicate, direction, subject, obj) for s in sentences)
                counts["tmkp_source_edges_dropped"] += 1
            continue
        family = TMKP_FAMILIES.get(row[TMKP_ASSOCIATION])
        if family is None:
            continue
        if (edge_id, direction) in dropped[family]:
            removals.update(_removal_key(s, predicate, direction, subject, obj) for s in sentences)
            counts["tmkp_source_edges_dropped"] += 1
            continue
        for sentence in sentences:
            if (edge_id, direction, sentence) in pruned[family]:
                removals.add(_removal_key(sentence, predicate, direction, subject, obj))
                counts["tmkp_source_sentences_pruned"] += 1
    expected_drops = len(treats_dropped) + sum(len(v) for v in dropped.values())
    if counts["tmkp_source_edges_dropped"] != expected_drops:
        raise ValueError(
            f"TMKP drop lists name {expected_drops} edges but {counts['tmkp_source_edges_dropped']} matched "
            f"{TMKP_EDGES}; the lists and the edge file are from different releases"
        )
    return removals, counts


def _study_result(attribute: dict[str, Any]) -> dict[str, Any]:
    """A TextMiningStudyResult record, in the release's layout, from a has_supporting_study_result attribute."""
    fields = {item["attribute_type_id"].removeprefix("biolink:"): item["value"]
              for item in attribute.get("attributes", [])}
    result: dict[str, Any] = {"category": ["biolink:TextMiningStudyResult"], "id": attribute["value"]}
    if "supporting_text" in fields:
        result["supporting_text"] = [fields["supporting_text"]]
    if "publications" in fields:
        result["xref"] = [fields["publications"]]
    if "supporting_text_located_in" in fields:
        result["supporting_text_section_type"] = fields["supporting_text_located_in"]
    if "extraction_confidence_score" in fields:
        result["extraction_confidence_score"] = fields["extraction_confidence_score"]
    if "supporting_document_year" in fields:
        result["supporting_document_year"] = fields["supporting_document_year"]
    for location in ("subject_location_in_text", "object_location_in_text"):
        if location in fields:
            result[location] = [int(part) for part in str(fields[location]).split("|")]
    return result


def load_tmkp_repairs(cleanup_dir: Path) -> list[dict[str, Any]]:
    """Repaired TMKP edges, in the release's edge layout, with raw (unnormalized) subject and object."""
    edges = []
    for family in TMKP_FAMILIES.values():
        for row in _gzip_rows(cleanup_dir / f"tmkp_{family}_repaired_edges.tsv.gz"):
            attributes = json.loads(row[TMKP_ATTRIBUTES])
            results = [_study_result(a) for a in attributes
                       if a["attribute_type_id"] == "biolink:has_supporting_study_result"]
            if {r["id"] for r in results} != set(row[TMKP_SENTENCES].split("|")):
                raise ValueError(f"Repaired TMKP edge {row[TMKP_ID]}: sentence ids and study results disagree")
            edge: dict[str, Any] = {
                "id": row[TMKP_ID],
                "category": [row[TMKP_ASSOCIATION]],
                "subject": row[0],
                "predicate": row[1],
                "object": row[2],
                "original_subject": row[0],
                "original_object": row[2],
                "sources": [{"resource_id": TMKP, "resource_role": "primary_knowledge_source",
                             "upstream_resource_ids": ["infores:pubmed"]}],
                "knowledge_level": "not_provided",
                "agent_type": "text_mining_agent",
                "has_confidence_score": float(row[TMKP_SCORE]),
                "publications": sorted(set(row[TMKP_PUBLICATIONS].split("|"))),
                "has_supporting_studies": {row[TMKP_ID]: {
                    "category": ["biolink:Study"], "id": row[TMKP_ID], "has_study_results": results}},
            }
            for column, field in TMKP_QUALIFIER_COLUMNS.items():
                if row[column]:
                    edge[field] = [row[column]] if field == "anatomical_context_qualifier" else row[column]
            edges.append(edge)
    return edges


def load_study_removals(path: Path) -> dict[str, set[str]]:
    """Map edge id -> study ids to remove, from a TSV with edge_id and study_id columns."""
    removals: dict[str, set[str]] = defaultdict(set)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            removals[row["edge_id"]].add(row["study_id"])
    if not removals:
        raise ValueError(f"No study removals in {path}")
    return dict(removals)


def _is_tmkp(edge: dict[str, Any]) -> bool:
    return any(source.get("resource_id") == TMKP and source.get("resource_role") == "primary_knowledge_source"
               for source in edge.get("sources") or [])


def _tmkp_publications(studies: dict[str, Any]) -> list[str]:
    return sorted({xref for study in studies.values() for result in study.get("has_study_results") or []
                   for xref in result.get("xref") or []})


def clean_tmkp_edge(edge: dict[str, Any], removals: set[bytes], counts: Counter) -> dict[str, Any] | None:
    """Remove judged-out sentences from one TMKP edge; None if none remain. Returns the edge unchanged otherwise."""
    direction = edge.get("object_direction_qualifier") or ""
    subject = edge.get("original_subject") or edge["subject"]
    obj = edge.get("original_object") or edge["object"]
    studies = edge.get("has_supporting_studies") or {}
    kept_studies: dict[str, Any] = {}
    removed = 0
    for study_id, study in studies.items():
        results = study.get("has_study_results") or []
        kept = [r for r in results
                if _removal_key(r["id"], edge["predicate"], direction, subject, obj) not in removals]
        removed += len(results) - len(kept)
        if kept:
            kept_studies[study_id] = {**study, "has_study_results": kept}
    if not removed:
        return edge
    if not kept_studies:
        counts["tmkp_edges_dropped"] += 1
        return None
    counts["tmkp_edges_pruned"] += 1
    counts["tmkp_sentences_pruned"] += removed
    return {**edge, "has_supporting_studies": kept_studies, "publications": _tmkp_publications(kept_studies)}


def _merge_repair(edge: dict[str, Any], repair: dict[str, Any]) -> dict[str, Any]:
    studies = {**(edge.get("has_supporting_studies") or {}), **repair["has_supporting_studies"]}
    return {**edge, "has_supporting_studies": studies, "publications": _tmkp_publications(studies)}


def derive_nodes(
    source: Path,
    output: Path,
    replacements: dict[str, str],
    final_name: str,
    wanted_identifiers: set[str] | None = None,
) -> tuple[Counter, dict[str, set[str]]]:
    """Write merged nodes; also return identifier -> node ids for ``wanted_identifiers`` (before merging)."""
    absorbed: dict[str, list[str]] = {}
    for old, new in replacements.items():
        absorbed.setdefault(new, []).append(old)
    wanted = wanted_identifiers or set()
    found: dict[str, set[str]] = defaultdict(set)
    counts: Counter = Counter()
    seen_old: set[str] = set()
    seen_new: set[str] = set()
    with open_source(source) as lines, _output_stream(output, final_name) as out:
        for line in lines:
            node = orjson.loads(line)
            node_id = node["id"]
            counts["nodes_read"] += 1
            if wanted:
                for identifier in {node_id, *(node.get("equivalent_identifiers") or [])} & wanted:
                    found[identifier].add(node_id)
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
    return counts, found


def derive_edges(
    source: Path,
    output: Path,
    replacements: dict[str, str],
    final_name: str,
    tmkp_removals: set[bytes] | None = None,
    tmkp_repairs: list[dict[str, Any]] | None = None,
    study_removals: dict[str, set[str]] | None = None,
) -> Counter:
    """Write edges: rewrite through replacements, clean TMKP edges, remove studies, merge or append repairs.

    ``tmkp_repairs`` must already have graph node ids as subject and object.
    """
    removals = tmkp_removals or set()
    study_removals = study_removals or {}
    pending: dict[tuple, dict[str, Any]] = {}
    counts: Counter = Counter()
    for repair in tmkp_repairs or []:
        repair = {**repair, "subject": replacements.get(repair["subject"], repair["subject"]),
                  "object": replacements.get(repair["object"], repair["object"])}
        if repair["subject"] == repair["object"]:
            counts["tmkp_repairs_dropped_self_loop"] += 1
            continue
        key = _merge_key(repair)
        pending[key] = _merge_repair(pending[key], repair) if key in pending else repair
    # Duplicates can only arise on edges touching a replacement node, so only those edges' keys are kept in memory.
    targets = set(replacements.values())
    seen: set[bytes] = set()
    matched_studies: Counter = Counter()

    def write(edge: dict[str, Any], raw: bytes | None, out) -> None:
        if edge["subject"] in targets or edge["object"] in targets:
            key = _edge_key(edge)
            if key in seen:
                counts["edges_dropped_duplicate"] += 1
                return
            seen.add(key)
        out.write(raw if raw is not None else orjson.dumps(edge) + b"\n")
        counts["edges_written"] += 1

    with open_source(source) as lines, _output_stream(output, final_name) as out:
        for line in lines:
            edge = orjson.loads(line)
            counts["edges_read"] += 1
            changed = False
            subject = replacements.get(edge["subject"], edge["subject"])
            obj = replacements.get(edge["object"], edge["object"])
            if subject != edge["subject"] or obj != edge["object"]:
                counts["edges_rewritten"] += 1
                if subject == obj:
                    counts["edges_dropped_self_loop"] += 1
                    continue
                edge["subject"], edge["object"] = subject, obj
                changed = True
            if edge.get("id") in study_removals:
                remove = study_removals[edge["id"]]
                studies = edge.get("has_supporting_studies") or {}
                matched_studies[edge["id"]] = len(remove & set(studies))
                kept = {k: v for k, v in studies.items() if k not in remove}
                if len(kept) < len(studies):
                    counts["study_removal_edges_edited"] += 1
                    if not kept:
                        counts["study_removal_edges_dropped"] += 1
                        continue
                    edge["has_supporting_studies"] = kept
                    changed = True
            if (removals or pending) and _is_tmkp(edge):
                cleaned = clean_tmkp_edge(edge, removals, counts)
                if cleaned is None:
                    continue
                if cleaned is not edge:
                    edge, changed = cleaned, True
                key = _merge_key(edge)
                if key in pending:
                    edge, changed = _merge_repair(edge, pending.pop(key)), True
                    counts["tmkp_repairs_merged"] += 1
            write(edge, None if changed else (line if line.endswith(b"\n") else line + b"\n"), out)
        for repair in pending.values():
            counts["tmkp_repairs_appended"] += 1
            write(repair, None, out)
    unmatched = [edge_id for edge_id in study_removals if not matched_studies.get(edge_id)]
    if unmatched:
        raise ValueError(f"Study removals name {len(unmatched)} edges or studies absent from the graph: {unmatched[:10]}")
    return counts


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derive_graph(
    *,
    source_dir: Path,
    replacements_paths: Sequence[Path],
    output_dir: Path,
    graph_version: str,
    tmkp_cleanup_dir: Path | None = None,
    study_removals_path: Path | None = None,
) -> dict[str, Any]:
    replacements = load_replacements(replacements_paths)
    metadata = json.loads((source_dir / "graph-metadata.json").read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    inputs: dict[str, Any] = {
        "replacements": [{"path": p.name, "sha256": _sha256(p)} for p in replacements_paths],
        "replacement_count": len(replacements),
    }
    tmkp_removals: set[bytes] = set()
    repairs: list[dict[str, Any]] = []
    if tmkp_cleanup_dir is not None:
        tmkp_removals, tmkp_counts = load_tmkp_removals(tmkp_cleanup_dir)
        counts.update(tmkp_counts)
        repairs = load_tmkp_repairs(tmkp_cleanup_dir)
        inputs["tmkp_cleanup"] = {p.name: _sha256(p) for p in sorted(tmkp_cleanup_dir.glob("*.gz"))}
    study_removals = load_study_removals(study_removals_path) if study_removals_path else {}
    if study_removals_path:
        inputs["study_removals"] = {"path": study_removals_path.name, "sha256": _sha256(study_removals_path)}

    wanted = {curie for repair in repairs for curie in (repair["subject"], repair["object"])}
    node_target = source_file(output_dir, "nodes")
    node_partial = node_target.with_name(node_target.name + ".partial")
    node_counts, found = derive_nodes(
        source_file(source_dir, "nodes"), node_partial, replacements, node_target.name, wanted
    )
    counts.update(node_counts)
    def graph_node(curie: str) -> str | None:
        """The node an identifier belongs to: the node with that id, else the one node listing it."""
        nodes = found.get(curie, set())
        if curie in nodes:
            return curie
        if len(nodes) > 1:
            counts["tmkp_repair_identifiers_ambiguous"] += 1
        return next(iter(nodes)) if len(nodes) == 1 else None

    mapped = []
    for repair in repairs:
        subject, obj = graph_node(repair["subject"]), graph_node(repair["object"])
        if subject is None or obj is None:
            counts["tmkp_repairs_unmapped"] += 1
            continue
        mapped.append({**repair, "subject": subject, "object": obj})
    counts["tmkp_repairs_read"] = len(repairs)

    edge_target = source_file(output_dir, "edges")
    edge_partial = edge_target.with_name(edge_target.name + ".partial")
    counts.update(derive_edges(
        source_file(source_dir, "edges"), edge_partial, replacements, edge_target.name,
        tmkp_removals, mapped, study_removals,
    ))
    node_partial.replace(node_target)
    edge_partial.replace(edge_target)
    manifest = {
        "graph_version": graph_version,
        "derived_from": metadata.get("version"),
        "inputs": inputs,
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
        description="Derive a graph version by merging nodes and editing edges"
    )
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--replacements", type=Path, action="append", required=True,
                        help="replacement table; repeat for several")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--graph-version", required=True)
    parser.add_argument("--tmkp-cleanup-dir", type=Path,
                        help="TMKP edges.tsv.gz and the ORION#455 cleanup lists")
    parser.add_argument("--study-removals", type=Path, help="TSV of edge_id, study_id to remove")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = derive_graph(
        source_dir=args.source_dir,
        replacements_paths=args.replacements,
        output_dir=args.output_dir,
        graph_version=args.graph_version,
        tmkp_cleanup_dir=args.tmkp_cleanup_dir,
        study_removals_path=args.study_removals,
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
