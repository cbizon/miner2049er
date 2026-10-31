#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

graph="${GANDALF_GRAPH_PATH:-$ROOT/data/gandalf/$GRAPH_VERSION}"
log_file="$ROOT/logs/gandalf-server.log"
service_label="io.renci.miner2049er.gandalf"
service_target="gui/$(id -u)/$service_label"

if [[ ! -d "$graph" ]]; then
  echo "Missing Gandalf graph: $graph" >&2
  exit 1
fi

"$ROOT/scripts/fetch_biolink.sh"

mkdir -p "$ROOT/.run" "$ROOT/logs"
rm -f "$ROOT/.run/gandalf.pid"

if curl --fail --silent "$GANDALF_URL/metadata" >/dev/null 2>&1; then
  echo "Gandalf is already responding at $GANDALF_URL"
  exit 0
fi

if launchctl print "$service_target" >/dev/null 2>&1; then
  launchctl remove "$service_label"
fi

: >"$log_file"
launchctl submit \
  -l "$service_label" \
  -o "$log_file" \
  -e "$log_file" \
  -- /usr/bin/env -i \
  HOME="$HOME" \
  PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
  PYTHONUNBUFFERED=1 \
  GANDALF_GRAPH_PATH="$graph" \
  GANDALF_GRAPH_FORMAT=mmap \
  GANDALF_LOAD_MMAPS_INTO_MEMORY=false \
  GANDALF_OTEL_ENABLED=false \
  GANDALF_WORKERS=1 \
  "$ROOT/.venv/bin/uvicorn" miner2049er.gandalf_server:APP \
  --host 127.0.0.1 \
  --port 6429

for _ in {1..60}; do
  if curl --fail --silent "$GANDALF_URL/metadata" >/dev/null 2>&1; then
    echo "Started Gandalf launch service $service_label; log: $log_file"
    exit 0
  fi
  sleep 1
done

echo "Gandalf did not become ready within 60 seconds" >&2
tail -n 50 "$log_file" >&2
launchctl remove "$service_label" >/dev/null 2>&1 || true
exit 1
