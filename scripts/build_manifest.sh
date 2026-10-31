#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

mkdir -p "$ROOT/manifest"
uv run miner-build-manifest \
  --output "$ROOT/manifest/translator-${GRAPH_VERSION}.json"

