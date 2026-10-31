#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

echo "Source: $SOURCE_DIR ($GRAPH_VERSION)"
echo "Disk:"
df -h "$ROOT"

echo
echo "Artifacts:"
du -sh "$ROOT/data/gandalf/$GRAPH_VERSION" 2>/dev/null || true
du -sh "$ROOT/data/neo4j/import/$GRAPH_VERSION" 2>/dev/null || true
du -sh "$ROOT/data/neo4j/data" 2>/dev/null || true

echo
echo "Gandalf:"
service_target="gui/$(id -u)/io.renci.miner2049er.gandalf"
if launchctl print "$service_target" >/dev/null 2>&1; then
  launchctl print "$service_target" | awk '
    $1 == "state" && !seen_state {print; seen_state = 1}
    $1 == "pid" {print}
  '
else
  echo "launch service is not registered"
fi
if curl --fail --silent "$GANDALF_URL/metadata" >/dev/null; then
  echo "TRAPI endpoint: ready ($GANDALF_URL)"
else
  echo "TRAPI endpoint: unavailable ($GANDALF_URL)"
fi

echo
echo "Neo4j:"
docker compose ps neo4j
