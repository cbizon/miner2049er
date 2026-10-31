#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

service_label="io.renci.miner2049er.gandalf"
service_target="gui/$(id -u)/$service_label"

if ! launchctl print "$service_target" >/dev/null 2>&1; then
  echo "Gandalf is not running"
  exit 0
fi

launchctl remove "$service_label"
rm -f "$ROOT/.run/gandalf.pid"
echo "Stopped Gandalf launch service $service_label"
