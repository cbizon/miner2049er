#!/usr/bin/env bash
# Set tonight's instruction for the nightly round from a file.
#   scripts/sterling_set_instruction.sh instruction.md
# Stamps it with today's New York date; a night whose stamp doesn't match runs
# the standing fallback instead (see deploy/sterling/nightly.yaml).
set -euo pipefail

namespace="${MINER_NAMESPACE:-bizon}"
instruction_file="$1"
[[ -s "$instruction_file" ]] || { echo "Empty or missing: $instruction_file" >&2; exit 1; }
today="$(TZ=America/New_York date +%F)"

patch="$(python3 -c '
import json, sys
print(json.dumps({"data": {"instruction.md": open(sys.argv[1]).read(), "instruction_for": sys.argv[2]}}))
' "$instruction_file" "$today")"
kubectl -n "$namespace" patch configmap miner-nightly --type merge -p "$patch" >/dev/null
echo "Tonight's instruction set for $today:"
kubectl -n "$namespace" get configmap miner-nightly -o jsonpath='{.data.instruction\.md}'
