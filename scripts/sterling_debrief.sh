#!/usr/bin/env bash
# Print the morning digest for the nightly run (or a named run) from Sterling.
#   scripts/sterling_debrief.sh [--run-id RUN] [--check]
set -euo pipefail

# Scheduled and non-interactive shells often lack these on PATH. kubectl lives
# in /usr/local/bin, and Sterling's OIDC login runs `kubectl oidc-login`,
# which needs kubectl-oidc_login from /opt/homebrew/bin.
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"

namespace="${MINER_NAMESPACE:-bizon}"
run_id=""
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) run_id="$2"; shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done

if [[ -z "$run_id" ]]; then
  run_id="$(kubectl -n "$namespace" get configmap miner-nightly -o jsonpath='{.data.run_id}')"
fi

kubectl -n "$namespace" exec deploy/miner-dashboard -c dashboard -- \
  env PYTHONWARNINGS=ignore miner-debrief --run-id "$run_id" ${args[@]+"${args[@]}"}
