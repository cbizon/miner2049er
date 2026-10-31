#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_free_gib 25

import_dir="${NEO4J_IMPORT_DIR:-$ROOT/data/neo4j/import/$GRAPH_VERSION}"
data_dir="${NEO4J_DATA_DIR:-$ROOT/data/neo4j/data}"
report_dir="$ROOT/logs/neo4j"

for file in nodes.parquet edges.parquet; do
  if [[ ! -f "$import_dir/$file" ]]; then
    echo "Missing Neo4j import file: $import_dir/$file" >&2
    exit 1
  fi
done

mkdir -p "$data_dir" "$report_dir"
if [[ -n "$(find "$data_dir" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "Neo4j data directory is not empty: $data_dir" >&2
  echo "Refusing to overwrite it automatically." >&2
  exit 1
fi

docker run --rm \
  --env NEO4J_server_memory_heap_initial__size=3G \
  --env NEO4J_server_memory_heap_max__size=3G \
  --volume "$data_dir:/data" \
  --volume "$import_dir:/import:ro" \
  --volume "$report_dir:/logs" \
  neo4j@sha256:d9dd3dc7d1c78fa959191ff02dbdcbefadceaf83eee23428fb92a58cac8ad3fe \
  neo4j-admin database import full \
  --input-type=parquet \
  --nodes=/import/nodes.parquet \
  --relationships=/import/edges.parquet \
  --id-type=string \
  --max-off-heap-memory=3G \
  --threads=4 \
  --strict=true \
  --bad-tolerance=0 \
  --report-file=/logs/import.report \
  neo4j
