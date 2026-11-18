"""Merge table for graph 1.0.2.2 from Babel's ChemicalParent conflation (NCATSTranslator/Babel#1214).

The PR has not run in a Babel build, so there is no ChemicalParent.txt to apply. This script runs the PR's own
code on the graph's chemical nodes:

- each node's own InChIKey is its Babel 2025sep1 clique key (graph built on 2025sep1), not the keys of other
  cliques merged into it by drug-chemical conflation;
- salts and hydrates are resolved from UniChem InChIs with the PR's component split and reviewed component list;
- nodes are grouped by parent key and each group is ordered with the PR's order_group(); the first node is kept
  and the others are merged into it.

Run it in the PR branch's environment, from the miner2049er repository root:

    uv run --project data/upstream/babel-pr1214 python scripts/graph_1_0_2_2/parent_conflation.py \
        --babel-repo data/upstream/babel-pr1214 \
        --own-keys data/upstream/babel-2025sep1/graph-node-inchikeys.parquet \
        --unichem data/upstream/unichem/structure-graph-keys.tsv \
        --nodes data/identity/nodes-1.0.2.1.jsonl --nodes data/identity/nodes-1.0.2.1-extra.jsonl \
        --work-dir data/upstream/parent-conflation \
        --information-content data/upstream/parent-conflation/information-content.tsv \
        --output config/graph-1.0.2.2-parent-merges.tsv
"""

import argparse
import csv
import gzip
import json
import os
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--babel-repo", type=Path, required=True)
    parser.add_argument("--own-keys", type=Path, required=True)
    parser.add_argument("--unichem", type=Path, required=True)
    parser.add_argument("--nodes", type=Path, action="append", required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--information-content", type=Path,
                        help="TSV of node id and information_content, used to order group members")
    parser.add_argument("--processes", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    return parser.parse_args()


def main():
    args = parse_args()
    babel_repo = args.babel_repo.resolve()
    sys.path.insert(0, str(babel_repo))
    import duckdb
    import orjson
    from src.createcompendia import chemicalparent, inchi_components
    from src.createcompendia.drugchemical import chemical_conflation_prefix_sort_order

    args.work_dir.mkdir(parents=True, exist_ok=True)

    own = dict(
        duckdb.sql(
            f"select clique_leader, curie from read_parquet('{args.own_keys}') where conflation = 'None'"
        ).fetchall()
    )
    own_keys = {curie.split(":", 1)[1] for curie in own.values()}

    # UniChem rows for the nodes' own keys only, gzipped with the header the PR's reader checks.
    unichem_gz = args.work_dir / "structure-own-keys.tsv.gz"
    kept = 0
    with open(args.unichem) as inf, gzip.open(unichem_gz, "wt") as outf:
        header = inf.readline()
        if header != "UCI\tSTANDARDINCHI\tSTANDARDINCHIKEY\n":
            raise ValueError(f"{args.unichem}: unexpected header {header!r}")
        outf.write(header)
        for line in inf:
            if line.rstrip("\n").split("\t")[2] in own_keys:
                outf.write(line)
                kept += 1
    # GtoPdb's current ligands.tsv has no InChI column, which the PR's reader needs; an empty file with the
    # expected header stands in. GtoPdb-only keys therefore keep their own keys (counted below).
    gtopdb_stub = args.work_dir / "gtopdb-ligands-stub.tsv"
    gtopdb_stub.write_text('"InChIKey"\t"InChI"\n')

    components_tsv = args.work_dir / "inchi-components.tsv"
    component_counts = inchi_components.write_inchi_components(
        unichem_gz, gtopdb_stub, components_tsv, args.processes
    )
    salt_parents_tsv = args.work_dir / "salt-parents.tsv"
    salt_counts = inchi_components.write_salt_parents(
        components_tsv, babel_repo / "input_data" / "chemical_parent_components.tsv", salt_parents_tsv
    )
    salt_parents, conflicting = chemicalparent.load_salt_parents(salt_parents_tsv)

    info = {}
    names = {}
    for path in args.nodes:
        with open(path, "rb") as inf:
            for line in inf:
                node = orjson.loads(line)
                if node["id"] in own:
                    info[node["id"]] = (node.get("information_content"), len(node.get("eq") or []) or 1)
                    names[node["id"]] = node.get("name") or ""
    if args.information_content:
        with open(args.information_content) as inf:
            for row in csv.reader(inf, delimiter="\t"):
                if row[0] in info and row[1]:
                    info[row[0]] = (float(row[1]), info[row[0]][1])
    missing = set(own) - set(info)
    if missing:
        raise ValueError(f"{len(missing)} nodes with own keys are missing from the node export: {sorted(missing)[:5]}")

    groups, group_counts = chemicalparent.group_cliques_by_parent_key(
        ((leader, [curie]) for leader, curie in sorted(own.items())), salt_parents
    )
    with open(babel_repo / "config.yaml") as inf:
        biolink_version = next(
            line.split(":", 1)[1].strip().strip('"') for line in inf if line.startswith("biolink_version:")
        )
    prefix_order = chemical_conflation_prefix_sort_order(biolink_version)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with open(args.output, "w", newline="") as outf:
        writer = csv.writer(outf, delimiter="\t", lineterminator="\n")
        writer.writerow(["status", "replaced_id", "replaced_name", "replaced_inchikey", "replacement_id",
                         "replacement_name", "replacement_inchikey", "parent_key", "reason"])
        for parent in sorted(groups):
            members = groups[parent]
            via_salt = {leader: through for leader, _, through in members}
            ordered = chemicalparent.order_group(members, info, prefix_order)
            leader = ordered[0]
            for other in ordered[1:]:
                reason = "salt or hydrate of the parent" if via_salt[other] else "charge state of the parent"
                writer.writerow(["replace", other, names[other], own[other].split(":", 1)[1], leader, names[leader],
                                 own[leader].split(":", 1)[1], parent, reason])
                rows += 1

    summary = {
        "nodes_with_own_inchikey": len(own),
        "unichem_rows_for_own_keys": kept,
        "inchi_components": component_counts,
        "salt_parents": salt_counts,
        "salt_parent_keys_conflicting": len(conflicting),
        "grouping": group_counts,
        "merge_rows": rows,
        "biolink_version": biolink_version,
    }
    (args.work_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
