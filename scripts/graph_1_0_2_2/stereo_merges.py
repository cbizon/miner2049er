"""Stereo merge table for graph 1.0.2.2: the unambiguous stereo-unspecified nodes 1.0.2.1 didn't merge.

A node whose own Babel 2025sep1 InChIKey is stereo-unspecified (second block ``UHFFFAOYSA``) is merged into the
graph's one specified stereoisomer of the same skeleton when:

- exactly one specified stereo layer exists for the skeleton across the graph (if it has several charge states,
  the neutral one is the target);
- the two names are the same after lowercasing and removing punctuation, and longer than five characters;
- neither name carries a stereo marker ((+), (-), (R)-, D-, L-, cis-, ...). A marked name says the node is one
  particular isomer, often of a racemic drug, so merging would be wrong.

Different names are usually a racemic drug and its single-enantiomer drug (citalopram, escitalopram) and are left
alone. A node the parent conflation already merges is left to that merge, so a node never has two targets; the
parent group's leader can still be stereo-merged, and its members follow it.

    uv run python scripts/graph_1_0_2_2/stereo_merges.py \
        --own-keys data/upstream/babel-2025sep1/graph-node-inchikeys.parquet \
        --nodes data/identity/nodes-1.0.2.1.jsonl --nodes data/identity/nodes-1.0.2.1-extra.jsonl \
        --parent-merges config/graph-1.0.2.2-parent-merges.tsv \
        --output config/graph-1.0.2.2-stereo-merges.tsv
"""

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import orjson

UNSPECIFIED = "UHFFFAOYSA"
STEREO_MARKER = re.compile(
    r"\([+\-±]\)|\(\+/-\)|\((r|s|rs|e|z)\)-|^(d|l|dl|r|s)-|\b(cis|trans)-|, \([+-]\)-?$", re.IGNORECASE
)
REASON = "stereo-unspecified node with one specified stereoisomer of the same name"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--own-keys", type=Path, required=True)
    parser.add_argument("--nodes", type=Path, action="append", required=True)
    parser.add_argument("--parent-merges", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def main() -> None:
    args = parse_args()
    own = dict(duckdb.sql(
        f"select clique_leader, split_part(curie, ':', 2) from read_parquet('{args.own_keys}') "
        "where conflation = 'None'"
    ).fetchall())
    names: dict[str, str] = {}
    for path in args.nodes:
        with open(path, "rb") as handle:
            for line in handle:
                node = orjson.loads(line)
                if node["id"] in own:
                    names[node["id"]] = node.get("name") or ""
    with open(args.parent_merges, newline="") as handle:
        parent_replaced = {row["replaced_id"] for row in csv.DictReader(handle, delimiter="\t")}

    by_skeleton: dict[str, list[str]] = defaultdict(list)
    for node, key in own.items():
        by_skeleton[key[:14]].append(node)
    counts: Counter = Counter()
    rows = []
    for node, key in own.items():
        if key[15:25] != UNSPECIFIED:
            continue
        specified = [other for other in by_skeleton[key[:14]] if own[other][15:25] != UNSPECIFIED]
        if not specified:
            counts["no specified stereoisomer"] += 1
            continue
        if len({own[other][15:25] for other in specified}) != 1:
            counts["several specified stereoisomers"] += 1
            continue
        neutral = [other for other in specified if own[other].endswith("-N")]
        targets = neutral if len(neutral) == 1 else (specified if len(specified) == 1 else [])
        if len(targets) != 1:
            counts["one stereoisomer, several nodes, no single neutral one"] += 1
            continue
        target = targets[0]
        if STEREO_MARKER.search(names[node].strip()) or STEREO_MARKER.search(names[target].strip()):
            counts["a name carries a stereo marker"] += 1
            continue
        if normalize(names[node]) != normalize(names[target]) or len(normalize(names[node]).replace(" ", "")) <= 5:
            counts["names differ"] += 1
            continue
        if node in parent_replaced:
            counts["already merged by the parent conflation"] += 1
            continue
        counts["merge"] += 1
        rows.append(["replace", node, names[node], key, target, names[target], own[target], REASON])

    with open(args.output, "w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["status", "replaced_id", "replaced_name", "replaced_inchikey", "replacement_id",
                         "replacement_name", "replacement_inchikey", "reason"])
        writer.writerows(sorted(rows, key=lambda row: (row[2].lower(), row[1])))
    for reason, count in counts.most_common():
        print(f"{count:8d} {reason}")


if __name__ == "__main__":
    main()
