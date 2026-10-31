"""Record matched structural-arm removals through the official serial workflow."""

import argparse
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import subprocess

from miner2049er.schema_validation import validate_document

from audit import records
from candidates import match, trapi
from probe import RUN, log_event


KEY = "r4-curated-inhibited-genetic-target-direct"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", default="120")
    parser.add_argument("--stop-at")
    args = parser.parse_args()
    if args.stop_at and datetime.now().astimezone() >= datetime.fromisoformat(args.stop_at):
        return
    recorded = {rule["rule_id"] for rule in records(RUN / "rules.jsonl")}
    if {KEY, KEY + "-full-closure"} <= recorded:
        for event in records(RUN / "research-log.jsonl"):
            if event["details"].get("candidate_id") == KEY and event["summary"].startswith(
                "Visible-label exclusion and feedback duplicate preflight:"
            ) and json.loads(event["details"]["result_summary"])["identical_already_scored_rules"]:
                print("Both structural-removal controls recorded; feedback identity already verified.")
                return
    here = Path(__file__).resolve().parent
    active = here / "active-candidates"
    for suffix in ("", "-full-closure"):
        key = KEY + suffix
        source = active / ("r4-family-genetic-direct-target-genetics" + suffix + ".json")
        candidate = deepcopy(json.loads(source.read_text()))
        candidate.update({
            "rule_id": key,
            "family_id": "curated-genetic-target-structural-ablation",
            "parent_rule_id": KEY if suffix else "genetic-convergence-curated-decreased",
            "name": "Curated Inhibited Genetic Target With Direct Evidence" + (
                " Full Descendant Control" if suffix else ""
            ),
            "hypothesis": (
                "Removing the family or process arm while retaining curated inhibition, "
                "exact-target genetic provenance, and direct disease evidence measures "
                "whether the added structure improves beyond the genetic target alone."
            ),
        })
        edges = [edge for edge in candidate["graph_pattern"]["edges"]
                 if edge["id"] in ("direct", "target", "target_genetics")]
        used = {edge[endpoint] for edge in edges for endpoint in ("subject", "object")}
        nodes = [node for node in candidate["graph_pattern"]["nodes"] if node["id"] in used]
        candidate["graph_pattern"] = {"nodes": nodes, "edges": edges, "constraints": []}
        candidate["plain_language_rule"] = "Predict treatment when " + "; ".join(
            edge["explanation"] for edge in edges
        ) + ". No gene-family, related-gene, process, physical-interaction, or target-count requirement is imposed."
        candidate["mechanism"] = {
            "score": "medium",
            "rationale": "Curated inhibition and genetic association are complementary evidence, but the graph lacks the genetic risk direction needed to establish therapeutic correction.",
        }
        prefix = candidate["execution"]["cypher_template"].split(
            "/* END CURATED ACCESS PATH */", 1
        )[0] + "/* END CURATED ACCESS PATH */ "
        candidate["execution"]["cypher_template"] = prefix + " ".join(match(edge) for edge in edges) + (
            " RETURN chemical.id AS subject_id,disease.id AS object_id,"
            "count(DISTINCT regulator) AS support_count"
        )
        candidate["execution"]["trapi"] = trapi(edges, nodes, [])
        validate_document(candidate, "rule-candidate.schema.json")
        path = active / (key + ".json")
        if path.exists():
            if json.loads(path.read_text()) != candidate:
                raise RuntimeError("Refusing to replace an existing component-removal candidate")
        else:
            path.write_text(json.dumps(candidate, indent=2) + "\n")
            log_event("hypothesis", "Remove structural corroboration from the same inhibited genetic target: " + key, {
                "mechanism_family": "curated genetic target structural ablation",
                "rationale": candidate["hypothesis"],
                "proposed_test": "Compare exact target genetics alone with the family-related genetic gene and genetically associated process additions.",
                "variables_to_explore": ["presence of family arm", "presence of process arm", "full versus filtered predicate closure"],
                "success_criterion": "An added structural arm should improve precision with useful hit retention rather than only reduce the prediction set.",
                "next_action": "Profile and record both baseline closures, and suppress feedback if the complete eligible set duplicates earlier work.",
            })
    for mode in ("profile", "record"):
        command = [
            "uv", "run", "python", str(here / "work.py"), mode,
            "--family", "^curated-genetic-target-structural-ablation$",
            "--include-full", "--timeout-seconds", args.timeout_seconds,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        print(result.stdout, flush=True)
        if result.returncode:
            raise RuntimeError(result.stderr[-8000:])
    # Use the same official-submit preflight as the main queue; never bypass its duplicate ledger.
    from work import feedback_after_record
    feedback_after_record(KEY, 60)


if __name__ == "__main__":
    main()
