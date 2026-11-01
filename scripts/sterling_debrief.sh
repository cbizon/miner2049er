#!/usr/bin/env bash
# Print the morning digest for the nightly run (or a named run) from Sterling.
#   scripts/sterling_debrief.sh [--run-id RUN] [--check]
set -euo pipefail

namespace="${MINER_NAMESPACE:-bizon}"
run_id="$(kubectl -n "$namespace" get configmap miner-nightly -o jsonpath='{.data.run_id}')"
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) run_id="$2"; shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done

kubectl -n "$namespace" exec deploy/miner-dashboard -c dashboard -- \
  env PYTHONWARNINGS=ignore miner-debrief --run-id "$run_id" ${args[@]+"${args[@]}"}
