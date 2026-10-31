#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

set -a
source "$ROOT/config/source.env"
if [[ -f "$ROOT/.env" ]]; then
  source "$ROOT/.env"
fi
set +a

export SOURCE_DIR GRAPH_VERSION
export NEO4J_USER="${NEO4J_USER:-neo4j}"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-translator-local}"
export NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
export GANDALF_URL="${GANDALF_URL:-http://localhost:6429}"
export SCORER_URL="${SCORER_URL:-http://127.0.0.1:6430}"

require_free_gib() {
  local required_gib="$1"
  local available_kib
  available_kib="$(df -Pk "$ROOT" | awk 'NR == 2 {print $4}')"
  local required_kib=$((required_gib * 1024 * 1024))
  if (( available_kib < required_kib )); then
    echo "Insufficient free disk: need ${required_gib} GiB, have $((available_kib / 1024 / 1024)) GiB" >&2
    exit 1
  fi
}
