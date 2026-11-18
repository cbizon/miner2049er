"""Study-removal table for graph 1.0.2.2: drop a trial from the extra subjects the clinical-trials KP gave it.

For a trial that lists exactly one intervention, and whose intervention doesn't name a combination, the KP
should assert one subject. When it asserts several, and after the 1.0.2.2 node merges exactly one of them has a
DrugBank or DrugCentral identifier, that one is kept and the trial is removed from the other subjects' edges.
Trials where none or several subjects have such an identifier are left alone in the graph; their subjects are
written to --unresolved-output so the holdout split can keep them together.

Inputs: the KP's edges exported from the loaded graph (export_ct_edges.py), ClinicalTrials.gov interventions
fetched for every trial, and the 1.0.2.2 merge tables. DrugBank and DrugCentral identifiers come from NodeNorm
(conflation off) and are cached in --drug-ids.

    uv run python scripts/graph_1_0_2_2/ct_study_removals.py \
        --ct-edges data/identity/ct-edges-all-1.0.2.1.jsonl \
        --interventions data/identity/ctgov-interventions.json \
        --replacements config/graph-1.0.2.2-stereo-merges.tsv \
        --replacements config/graph-1.0.2.2-parent-merges.tsv \
        --drug-ids data/upstream/ct-rule/nodenorm-drug-ids.json \
        --output config/graph-1.0.2.2-ct-study-removals.tsv.gz \
        --report data/upstream/ct-rule/report.json \
        --unresolved-output config/graph-1.0.2.2-ct-unresolved-sets.tsv
"""

import argparse
import gzip
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import httpx
import orjson

from miner2049er.graph_derivation import load_replacements

NODENORM = "https://nodenormalization-sri.renci.org/get_normalized_nodes"
COMBINATION = re.compile(r" / | \+ | & | and | with | plus |(?<=[a-z]{3})/(?=[a-z]{3})|, (?=[a-z])", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ct-edges", type=Path, required=True)
    parser.add_argument("--interventions", type=Path, required=True)
    parser.add_argument("--replacements", type=Path, action="append", required=True)
    parser.add_argument("--drug-ids", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--unresolved-output", type=Path, required=True,
                        help="TSV of the unresolved trials and their subjects, for holdout grouping")
    return parser.parse_args()


def drug_ids(nodes: list[str], cache: Path) -> dict[str, list[str]]:
    """DrugBank and DrugCentral identifiers in each node's own NodeNorm clique, cached on disk."""
    known = json.loads(cache.read_text()) if cache.exists() else {}
    todo = [node for node in nodes if node not in known]
    with httpx.Client(timeout=120) as client:
        for start in range(0, len(todo), 500):
            response = client.post(NODENORM, json={"curies": todo[start:start + 500], "conflate": False,
                                                   "drug_chemical_conflate": False})
            response.raise_for_status()
            for node, record in response.json().items():
                identifiers = [e["identifier"] for e in (record or {}).get("equivalent_identifiers", [])]
                known[node] = [i for i in identifiers if i.startswith(("DRUGBANK:", "DrugCentral:"))]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(known))
    return known


def is_combination(intervention: dict) -> bool:
    names = [intervention["name"], *intervention.get("other", [])]
    return intervention.get("type") == "COMBINATION_PRODUCT" or any(COMBINATION.search(n or "") for n in names)


def main() -> None:
    args = parse_args()
    replacements = load_replacements(args.replacements)
    interventions = json.loads(args.interventions.read_text())

    # trial -> merged subject -> edge ids carrying that trial
    trial_edges: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    members: dict[str, set[str]] = defaultdict(set)
    with open(args.ct_edges, "rb") as handle:
        for line in handle:
            edge = orjson.loads(line)
            subject = replacements.get(edge["s"], edge["s"])
            members[subject].add(edge["s"])
            for nct, _ in edge["trials"]:
                trial_edges[nct][subject].add(edge["id"])

    ids = drug_ids(sorted({node for group in members.values() for node in group}), args.drug_ids)
    has_drug_id = {subject: any(ids.get(node) for node in group) for subject, group in members.items()}

    counts: Counter = Counter()
    removals: list[tuple[str, str]] = []
    unresolved: list[tuple[str, str, list[str]]] = []
    for nct, subjects in trial_edges.items():
        listed = interventions.get(nct)
        if listed is None or len(listed) != 1:
            continue
        counts["single_intervention_trials"] += 1
        if len(subjects) < 2:
            continue
        if is_combination(listed[0]):
            counts["several_subjects_combination_intervention"] += 1
            continue
        counts["several_subjects"] += 1
        with_id = [s for s in subjects if has_drug_id[s]]
        if len(with_id) != 1:
            outcome = "unresolved_none_with_id" if not with_id else "unresolved_several_with_id"
            counts[outcome] += 1
            unresolved.append((nct, outcome, sorted(subjects)))
            continue
        counts["resolved"] += 1
        for subject, edge_ids in subjects.items():
            if subject != with_id[0]:
                counts["subjects_removed"] += 1
                removals.extend((edge_id, f"CLINICALTRIALS:{nct}") for edge_id in edge_ids)
    counts["edge_trial_removals"] = len(removals)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 so the same removals give a byte-identical file.
    with io.TextIOWrapper(gzip.GzipFile(args.output, "wb", mtime=0), encoding="utf-8") as out:
        out.write("edge_id\tstudy_id\n")
        for edge_id, study_id in sorted(removals):
            out.write(f"{edge_id}\t{study_id}\n")
    with open(args.unresolved_output, "w", encoding="utf-8") as out:
        out.write("nct_id\toutcome\tsubject_ids\n")
        for nct, outcome, subjects in sorted(unresolved):
            out.write(f"{nct}\t{outcome}\t{','.join(subjects)}\n")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(dict(sorted(counts.items())), indent=2) + "\n")
    print(json.dumps(dict(sorted(counts.items())), indent=2))


if __name__ == "__main__":
    main()
