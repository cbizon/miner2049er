#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

deadline=$((SECONDS + 300))
until docker exec miner2049er-neo4j cypher-shell \
  -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; do
  if (( SECONDS >= deadline )); then
    echo "Neo4j did not become ready within 300 seconds" >&2
    exit 1
  fi
  sleep 3
done

docker exec -i miner2049er-neo4j cypher-shell \
  -u neo4j -p "$NEO4J_PASSWORD" <"$ROOT/cypher/indexes.cypher"

docker exec miner2049er-neo4j cypher-shell \
  -u neo4j -p "$NEO4J_PASSWORD" \
  "CALL db.awaitIndexes(1800)"

docker exec miner2049er-neo4j cypher-shell \
  -u neo4j -p "$NEO4J_PASSWORD" \
  "SHOW INDEXES YIELD name, state, populationPercent RETURN name, state, populationPercent"
