"""Drug holdout groups for graph 1.0.2.2, from the decisions in docs/identity-review-log.md.

Nodes in one group are related but distinct drugs (stereoisomers, salts and parents that stay separate, same-name
records without structures, dose forms, combinations). A treats pair's split unit is (subject's group, object), so
all of a group's pairs for one disease land in the same partition.

Grouped, per the log: A1-A5 and A6b pairs, the stereo-marked-name pairs (except Oshadi D / Oshadi R), the B1-B4
Babel lists (B5, the B6 chemical records and D Vitamin / VITAMIN D are in the B1 list), the eight
and combination-vs-ingredient pairs. Not grouped: A6a (different compounds sharing trials), B6 gene pairs, the B4 wrong matches, and group C, which
has not been decided. Subjects of single-intervention trials the CTKP rule couldn't resolve are not grouped as a
set: many of those trials list one intervention ("chemotherapy", an HIV regimen) that the KP grounded to every drug
of the regimen, so their subjects chain unrelated drugs together. Their identity-related pairs are grouped through
the A and B decisions above, as the log says.

Node ids are mapped through the 1.0.2.2 merge tables, so merged nodes don't appear and a pair the merges collapse
adds nothing.

    uv run python scripts/graph_1_0_2_2/holdout_groups.py \
        --review-dir data/identity/review-2026-11-09 \
        --replacements config/graph-1.0.2.1-replacements.tsv \
        --replacements config/graph-1.0.2.2-stereo-merges.tsv \
        --replacements config/graph-1.0.2.2-parent-merges.tsv \
        --output config/graph-1.0.2.2-holdout-groups.tsv
"""

import argparse
import csv
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path

from miner2049er.graph_derivation import load_replacements

PAIR_FILES = {
    "a1-protonation-pairs.tsv": ("keep_id", "other_id", "A1 charge forms"),
    "a2-stereo-pairs.tsv": ("id_a", "id_b", "A2 stereoisomers, same name"),
    "a3-stereo-pairs.tsv": ("id_a", "id_b", "A3 stereoisomers, different names"),
    "stereo-marked-names.tsv": ("id_a", "id_b", "AB stereo-marked names"),
    "a4-same-name-different-structure.tsv": ("id_a", "id_b", "A4 same name, different structure"),
    "a5-salt-name-different-structure.tsv": ("id_a", "id_b", "A5 salt name, different structure"),
    "a6b-identity-links.tsv": ("id_a", "id_b", "A6b identity links"),
    "babel-b3-dose-form-not-conflated.tsv": ("base_id", "product_id", "B3 ingredient and dose form"),
}
GROUP_FILES = {
    "babel-b1-same-name-no-structure.tsv": "B1 same name, no structure",
    "babel-b2-salt-name-no-structure.tsv": "B2 salt name, no structure",
    "babel-b4-same-combination.tsv": "B4 same combination",
}
NOT_GROUPED_NAMES = {frozenset({"Oshadi D", "Oshadi R"})}
# B4 combination-vs-ingredient matches the log rejects (CHOP protocol / CHOP regimen is in the B4 list instead).
COMBINATION_REJECTED = {"UMLS:C1456094", "UMLS:C0376547", "UMLS:C3537046", "UMLS:C0055598"}
COMBINATION_REASON = "combination product containing the single drug"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--replacements", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def rows(path: Path) -> Iterable[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle, delimiter="\t")


def links(review: Path) -> Iterable[tuple[str, str, str]]:
    """(node, node, reason) for every pair the log groups."""
    for name, (left, right, reason) in PAIR_FILES.items():
        for row in rows(review / name):
            names = frozenset({row.get("name_a"), row.get("name_b")})
            if names in NOT_GROUPED_NAMES:
                continue
            yield row[left], row[right], reason
    for name, reason in GROUP_FILES.items():
        members: dict[str, list[str]] = defaultdict(list)
        for row in rows(review / name):
            members[row["group"]].append(row["node_id"])
        for nodes in members.values():
            yield from ((nodes[0], other, reason) for other in nodes[1:])
    for row in rows(review / "drug-pairs-classified.tsv"):
        if row["reason"] == COMBINATION_REASON and not {row["node_a"], row["node_b"]} & COMBINATION_REJECTED:
            yield row["node_a"], row["node_b"], "B4 combination and ingredient"


def main() -> None:
    args = parse_args()
    replacements = load_replacements(args.replacements)
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    reasons: dict[str, set[str]] = defaultdict(set)
    counts: Counter = Counter()
    for left, right, reason in links(args.review_dir):
        left, right = replacements.get(left, left), replacements.get(right, right)
        if left == right:
            counts["pairs collapsed by merges"] += 1
            continue
        counts[reason] += 1
        reasons[left].add(reason)
        reasons[right].add(reason)
        parent[find(left)] = find(right)

    groups: dict[str, list[str]] = defaultdict(list)
    for node in parent:
        groups[find(node)].append(node)
    groups = {min(nodes): sorted(nodes) for nodes in groups.values() if len(nodes) > 1}
    with open(args.output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["node_id", "group_id", "reasons"])
        for group_id in sorted(groups):
            for node in groups[group_id]:
                writer.writerow([node, group_id, "; ".join(sorted(reasons[node]))])
    sizes = Counter(len(nodes) for nodes in groups.values())
    print(f"groups {len(groups)}, nodes {sum(len(n) for n in groups.values())}")
    print("largest groups:", sorted((len(n) for n in groups.values()), reverse=True)[:10])
    print("size distribution:", dict(sorted(sizes.items())[:10]))
    for reason, count in counts.most_common():
        print(f"{count:8d} {reason}")


if __name__ == "__main__":
    main()
