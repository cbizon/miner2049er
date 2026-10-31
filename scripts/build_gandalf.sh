#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_free_gib 35
"$ROOT/scripts/fetch_biolink.sh"

output="$ROOT/data/gandalf/$GRAPH_VERSION"
tmp_root="$ROOT/data/tmp/gandalf"
mkdir -p "$tmp_root" "$ROOT/logs"

if [[ -e "$output" ]]; then
  echo "Gandalf output already exists: $output" >&2
  exit 1
fi

export TMPDIR="$tmp_root"
uv run miner-build-gandalf \
  --nodes "$SOURCE_DIR/nodes.jsonl" \
  --edges "$SOURCE_DIR/edges.jsonl" \
  --output "$output" \
  2>&1 | tee "$ROOT/logs/gandalf-build-${GRAPH_VERSION}.log"

find "$tmp_root" -mindepth 1 -maxdepth 1 -type d -name 'gandalf_build_*' -exec rm -rf {} +
