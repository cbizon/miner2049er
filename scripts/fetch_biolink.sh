#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

version="4.3.2"
target_dir="$ROOT/data/reference/biolink/$version"
schema="$target_dir/biolink-model.yaml"
predicate_map="$target_dir/predicate_mapping.yaml"
schema_sha="d8ea043537d345a6c0a3a6f1052bf0c381307c3a3d4cc4c878c7d362fe7870d7"
predicate_sha="b532220b1d33f0e51794566fa33a736905b5a41ed1fe38839f9e949cb58c796c"

verify() {
  local path="$1"
  local expected="$2"
  [[ -f "$path" ]] && [[ "$(shasum -a 256 "$path" | awk '{print $1}')" == "$expected" ]]
}

download() {
  local url="$1"
  local path="$2"
  local expected="$3"
  local partial="${path}.partial"

  curl --fail --location --silent --show-error --output "$partial" "$url"
  local actual
  actual="$(shasum -a 256 "$partial" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    rm -f "$partial"
    echo "Checksum mismatch for $url: expected $expected, found $actual" >&2
    exit 1
  fi
  mv "$partial" "$path"
}

mkdir -p "$target_dir"

if ! verify "$schema" "$schema_sha"; then
  download \
    "https://raw.githubusercontent.com/biolink/biolink-model/refs/tags/v${version}/biolink-model.yaml" \
    "$schema" \
    "$schema_sha"
fi

if ! verify "$predicate_map" "$predicate_sha"; then
  download \
    "https://raw.githubusercontent.com/biolink/biolink-model/refs/tags/v${version}/predicate_mapping.yaml" \
    "$predicate_map" \
    "$predicate_sha"
fi

echo "Biolink Model $version reference files verified"
