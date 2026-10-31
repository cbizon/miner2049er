#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_free_gib 30

output="$ROOT/data/neo4j/import/$GRAPH_VERSION"
mkdir -p "$output" "$ROOT/logs"

uv run miner-export-neo4j \
  --nodes "$SOURCE_DIR/nodes.jsonl" \
  --edges "$SOURCE_DIR/edges.jsonl" \
  --output "$output" \
  2>&1 | tee "$ROOT/logs/neo4j-export-${GRAPH_VERSION}.log"

