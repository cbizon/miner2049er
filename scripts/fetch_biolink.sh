#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

# The runtime pin is 4.4.4; 4.3.2 is kept so runs recorded under it still validate.
version="${1:-4.4.4}"
target_dir="$ROOT/data/reference/biolink/$version"
predicate_sha="b532220b1d33f0e51794566fa33a736905b5a41ed1fe38839f9e949cb58c796c"
case "$version" in
  4.3.2)
    files=(biolink-model.yaml predicate_mapping.yaml)
    shas=(d8ea043537d345a6c0a3a6f1052bf0c381307c3a3d4cc4c878c7d362fe7870d7 "$predicate_sha")
    ;;
  4.4.4)
    files=(biolink-model.yaml attributes.yaml predicate_mapping.yaml)
    shas=(
      376e4f455877c0bf7f39231e1163bbda8455516609f66300e8ba37fb373ea71b
      ca7c400df55a728a3a96a8c1b8ae435540752fc18b3d300a8b47253346f80d80
      "$predicate_sha"
    )
    ;;
  *)
    echo "No pinned checksums for Biolink Model $version" >&2
    exit 1
    ;;
esac

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

for index in "${!files[@]}"; do
  file="${files[$index]}"
  if ! verify "$target_dir/$file" "${shas[$index]}"; then
    download \
      "https://raw.githubusercontent.com/biolink/biolink-model/refs/tags/v${version}/${file}" \
      "$target_dir/$file" \
      "${shas[$index]}"
  fi
done

echo "Biolink Model $version reference files verified"
