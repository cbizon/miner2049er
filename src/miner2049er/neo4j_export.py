from __future__ import annotations

import argparse
import json
import math
import re
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import orjson
import pyarrow as pa
import pyarrow.parquet as pq

from miner2049er.graph_filter import edge_is_visible, load_holdout_pairs
from miner2049er.settings import edges_path, neo4j_import_path, nodes_path

BATCH_SIZE = 50_000
TOKEN_PATTERN = re.compile(r"[^A-Za-z0-9_]")

NODE_LIST_FIELDS = (
    "category",
    "equivalent_identifiers",
    "xref",
    "synonym",
    "in_taxon",
)
NODE_STRING_FIELDS = (
    "name",
    "description",
    "full_name",
    "symbol",
    "taxon",
    "in_taxon_label",
    "inheritance",
    "chembl_availability_type",
    "chembl_black_box_warning",
    "chembl_natural_product",
    "chembl_prodrug",
)
EDGE_LIST_FIELDS = (
    "category",
    "publications",
    "FDA_regulatory_approvals",
    "has_evidence",
    "has_evidence_of_type",
)
EDGE_STRING_FIELDS = (
    "knowledge_level",
    "agent_type",
    "allelic_requirement",
    "clinical_approval_status",
    "description",
    "gene2phenotype_confidence_category",
    "object_feature_name",
    "original_object",
    "original_predicate",
    "original_subject",
    "subject_feature_name",
    "supporting_text",
    "update_date",
)
EDGE_FLOAT_FIELDS = (
    "adjusted_p_value",
    "dgidb_evidence_score",
    "dgidb_interaction_score",
    "diseases_confidence_score",
    "has_affinity",
    "has_confidence_score",
    "has_percentage",
    "has_quotient",
    "p_value",
)
EDGE_INT_FIELDS = (
    "evidence_count",
    "has_count",
    "has_supporting_studies",
    "has_total",
    "max_research_phase",
    "number_of_cases",
)
QUALIFIER_FIELDS = (
    "anatomical_context_qualifier",
    "causal_mechanism_qualifier",
    "disease_context_qualifier",
    "frequency_qualifier",
    "object_aspect_qualifier",
    "object_direction_qualifier",
    "object_form_or_variant_qualifier",
    "onset_qualifier",
    "qualified_predicate",
    "qualifier",
    "sex_qualifier",
    "species_context_qualifier",
    "stage_qualifier",
    "subject_form_or_variant_qualifier",
)


def sanitize_token(value: str, *, uppercase: bool = False) -> str:
    value = value.split(":", 1)[-1]
    value = TOKEN_PATTERN.sub("_", value).strip("_")
    if not value:
        value = "UNKNOWN"
    if value[0].isdigit():
        value = f"_{value}"
    return value.upper() if uppercase else value


def compact_json(value: Any) -> str:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")


def as_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return compact_json(value)
    return str(value)


def as_string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    values = value if isinstance(value, list) else [value]
    return [as_string(item) or "" for item in values]


def as_float(value: Any) -> float | None:
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def as_int(value: Any) -> int | None:
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def flatten_sources(sources: Any) -> tuple[list[str], list[str], list[str], str]:
    primary: list[str] = []
    aggregators: list[str] = []
    upstream: list[str] = []
    source_records = sources if isinstance(sources, list) else []

    for source in source_records:
        if not isinstance(source, dict):
            continue
        resource_id = source.get("resource_id") or source.get("id")
        role = source.get("resource_role")
        if resource_id and role == "primary_knowledge_source":
            primary.append(str(resource_id))
        elif resource_id and role == "aggregator_knowledge_source":
            aggregators.append(str(resource_id))
        upstream.extend(str(value) for value in source.get("upstream_resource_ids", []))

    return (
        sorted(set(primary)),
        sorted(set(aggregators)),
        sorted(set(upstream)),
        compact_json(source_records),
    )


def node_schema() -> pa.Schema:
    fields = [
        pa.field("id:ID(Entity)", pa.string(), nullable=False),
        # Neo4j's Parquet importer expects multiple labels in a delimiter-encoded
        # scalar. A Parquet list is interpreted as one literal composite label.
        pa.field(":LABEL", pa.string(), nullable=False),
        pa.field("categories", pa.list_(pa.string())),
        pa.field("equivalent_identifiers", pa.list_(pa.string())),
        pa.field("xref", pa.list_(pa.string())),
        pa.field("synonym", pa.list_(pa.string())),
        pa.field("in_taxon", pa.list_(pa.string())),
    ]
    fields.extend(pa.field(name, pa.string()) for name in NODE_STRING_FIELDS)
    fields.append(pa.field("information_content", pa.float64()))
    fields.append(pa.field("raw_json", pa.string(), nullable=False))
    return pa.schema(fields)


def edge_schema() -> pa.Schema:
    fields = [
        pa.field(":START_ID(Entity)", pa.string(), nullable=False),
        pa.field(":END_ID(Entity)", pa.string(), nullable=False),
        pa.field(":TYPE", pa.string(), nullable=False),
        pa.field("edge_id", pa.string()),
        pa.field("predicate", pa.string(), nullable=False),
        pa.field("association_categories", pa.list_(pa.string())),
        pa.field("publications", pa.list_(pa.string())),
        pa.field("FDA_regulatory_approvals", pa.list_(pa.string())),
        pa.field("has_evidence", pa.list_(pa.string())),
        pa.field("has_evidence_of_type", pa.list_(pa.string())),
        pa.field("primary_knowledge_sources", pa.list_(pa.string())),
        pa.field("aggregator_knowledge_sources", pa.list_(pa.string())),
        pa.field("upstream_resource_ids", pa.list_(pa.string())),
        pa.field("sources_json", pa.string(), nullable=False),
    ]
    fields.extend(pa.field(name, pa.string()) for name in EDGE_STRING_FIELDS)
    fields.extend(pa.field(name, pa.float64()) for name in EDGE_FLOAT_FIELDS)
    fields.extend(pa.field(name, pa.int64()) for name in EDGE_INT_FIELDS)
    fields.append(pa.field("negated", pa.bool_()))
    fields.extend(pa.field(name, pa.string()) for name in QUALIFIER_FIELDS)
    fields.append(pa.field("raw_json", pa.string(), nullable=False))
    return pa.schema(fields)


def transform_node(node: dict[str, Any]) -> dict[str, Any]:
    categories = as_string_list(node.get("category")) or []
    labels = ["Entity", *(sanitize_token(category) for category in categories)]
    record: dict[str, Any] = {
        "id:ID(Entity)": node["id"],
        ":LABEL": ";".join(dict.fromkeys(labels)),
        "categories": categories,
        "raw_json": compact_json(node),
        "information_content": as_float(node.get("information_content")),
    }
    for field in NODE_LIST_FIELDS:
        if field != "category":
            record[field] = as_string_list(node.get(field))
    for field in NODE_STRING_FIELDS:
        record[field] = as_string(node.get(field))
    return record


def transform_edge(edge: dict[str, Any]) -> dict[str, Any]:
    predicate = edge["predicate"]
    primary, aggregators, upstream, sources_json = flatten_sources(edge.get("sources"))
    record: dict[str, Any] = {
        ":START_ID(Entity)": edge["subject"],
        ":END_ID(Entity)": edge["object"],
        ":TYPE": sanitize_token(predicate, uppercase=True),
        "edge_id": as_string(edge.get("id")),
        "predicate": predicate,
        "association_categories": as_string_list(edge.get("category")),
        "primary_knowledge_sources": primary,
        "aggregator_knowledge_sources": aggregators,
        "upstream_resource_ids": upstream,
        "sources_json": sources_json,
        "negated": as_bool(edge.get("negated")),
        "raw_json": compact_json(edge),
    }
    for field in EDGE_LIST_FIELDS:
        target = "association_categories" if field == "category" else field
        record[target] = as_string_list(edge.get(field))
    for field in EDGE_STRING_FIELDS:
        record[field] = as_string(edge.get(field))
    for field in EDGE_FLOAT_FIELDS:
        record[field] = as_float(edge.get(field))
    for field in EDGE_INT_FIELDS:
        record[field] = as_int(edge.get(field))
    for field in QUALIFIER_FIELDS:
        record[field] = as_string(edge.get(field))
    return record


def batches(
    path: Path,
    transform,
    batch_size: int,
    include_record=lambda _record: True,
) -> Iterable[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    with path.open("rb") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                record = orjson.loads(line)
                if not include_record(record):
                    continue
                batch.append(transform(record))
            except Exception as error:
                raise ValueError(f"Failed parsing {path}:{line_number}") from error
            if len(batch) >= batch_size:
                yield batch
                batch = []
    if batch:
        yield batch


def export_file(
    source: Path,
    output: Path,
    schema: pa.Schema,
    transform,
    batch_size: int,
    include_record=lambda _record: True,
) -> tuple[int, float]:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".partial")
    if temporary.exists():
        temporary.unlink()

    count = 0
    started = time.monotonic()
    with pq.ParquetWriter(
        temporary,
        schema,
        compression="zstd",
        compression_level=3,
        use_dictionary=True,
        write_statistics=True,
    ) as writer:
        for records in batches(source, transform, batch_size, include_record):
            writer.write_table(pa.Table.from_pylist(records, schema=schema))
            count += len(records)
            if count % 1_000_000 == 0:
                elapsed = time.monotonic() - started
                print(f"{source.name}: {count:,} rows in {elapsed / 60:.1f} minutes", flush=True)

    temporary.replace(output)
    return count, time.monotonic() - started


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export KGX JSONL to Neo4j Parquet")
    parser.add_argument("--nodes", type=Path, default=nodes_path())
    parser.add_argument("--edges", type=Path, default=edges_path())
    parser.add_argument("--output", type=Path, default=neo4j_import_path())
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--exclude-labels",
        type=Path,
        action="append",
        default=[],
        help="JSONL label files whose target pairs must be omitted from the edge export",
    )
    parser.add_argument(
        "--target-predicate",
        action="append",
        default=[],
        help="Target predicate to filter; repeat for the complete target closure",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    nodes_output = args.output / "nodes.parquet"
    edges_output = args.output / "edges.parquet"
    report_output = args.output / "export-report.json"

    existing = [path for path in (nodes_output, edges_output) if path.exists()]
    if existing and not args.overwrite:
        paths = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output exists: {paths}; pass --overwrite to rebuild")

    node_count, node_seconds = export_file(
        args.nodes,
        nodes_output,
        node_schema(),
        transform_node,
        args.batch_size,
    )
    holdout_pairs = load_holdout_pairs(args.exclude_labels)
    target_predicates = set(args.target_predicate)
    if holdout_pairs and not target_predicates:
        raise ValueError("--target-predicate is required when --exclude-labels is used")
    edge_filter = (
        lambda edge: edge_is_visible(edge, target_predicates, holdout_pairs)
    )
    edge_count, edge_seconds = export_file(
        args.edges,
        edges_output,
        edge_schema(),
        transform_edge,
        args.batch_size,
        edge_filter,
    )

    report = {
        "nodes": {
            "count": node_count,
            "seconds": node_seconds,
            "path": str(nodes_output),
            "bytes": nodes_output.stat().st_size,
        },
        "edges": {
            "count": edge_count,
            "seconds": edge_seconds,
            "path": str(edges_output),
            "bytes": edges_output.stat().st_size,
            "heldout_target_pairs": len(holdout_pairs),
        },
        "relationship_types": sorted(
            {
                sanitize_token(predicate, uppercase=True)
                for predicate in _predicates_from_parquet(edges_output)
            }
        ),
    }
    report_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


def _predicates_from_parquet(path: Path) -> set[str]:
    predicates: set[str] = set()
    parquet_file = pq.ParquetFile(path)
    for batch in parquet_file.iter_batches(columns=["predicate"], batch_size=250_000):
        predicates.update(value for value in batch.column(0).to_pylist() if value)
    return predicates
