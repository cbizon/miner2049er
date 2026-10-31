#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

uv run miner-validate \
  --edge-file "$SOURCE_DIR/edges.jsonl" \
  --gandalf-url "$GANDALF_URL" \
  --neo4j-uri "$NEO4J_URI" \
  --neo4j-password "$NEO4J_PASSWORD"

