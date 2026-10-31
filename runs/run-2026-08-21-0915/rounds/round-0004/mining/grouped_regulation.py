"""Reformulate an unrecorded query; retain its failed formulation in the log."""

import json

from miner2049er.schema_validation import validate_document

from probe import RUN, log_event
from work import ACTIVE


QUERY = """
MATCH (chemical:Drug)-[direct:{{relationship_types:direct}}]->(disease:Disease)
WHERE direct.predicate IN {{predicates:direct}}
WITH chemical,collect(DISTINCT disease) AS diseases
CALL (chemical,diseases) {
  MATCH (chemical)-[target:{{relationship_types:target}}]->(regulator:GeneOrGeneProduct)
  WHERE target.predicate IN {{predicates:target}}
    AND target.qualified_predicate='biolink:causes'
    AND target.object_direction_qualifier IN ['increased','decreased']
    AND target.object_aspect_qualifier IN ['activity','activity_or_abundance']
  WITH DISTINCT regulator,target.object_direction_qualifier AS drug_direction,diseases
  MATCH (regulator)-[bridge:{{relationship_types:bridge}}]->(gene:GeneOrGeneProduct)
  WHERE bridge.predicate IN {{predicates:bridge}}
    AND bridge.qualified_predicate='biolink:causes'
    AND bridge.object_direction_qualifier IN ['increased','decreased']
    AND bridge.object_aspect_qualifier IN ['activity','activity_or_abundance']
    AND regulator<>gene
    AND drug_direction<>bridge.object_direction_qualifier
  WITH DISTINCT gene,diseases
  MATCH (gene)-[causal:{{relationship_types:causal}}]->(disease:Disease)
  WHERE causal.predicate IN {{predicates:causal}} AND disease IN diseases
  RETURN disease,count(DISTINCT gene) AS support_count
}
RETURN chemical.id AS subject_id,disease.id AS object_id,support_count
""".strip()


def main():
    recorded = {json.loads(line)["rule_id"] for line in (RUN / "rules.jsonl").read_text().splitlines()}
    for suffix in ("", "-full-closure"):
        key = "r4-regulatory-net-decrease-no-curation" + suffix
        if key in recorded:
            raise RuntimeError("Never replace a recorded query: " + key)
        path = ACTIVE / (key + ".json")
        candidate = json.loads(path.read_text())
        original = candidate["execution"]["cypher_template"]
        if original == QUERY:
            continue
        candidate["execution"]["cypher_template"] = QUERY
        validate_document(candidate, "rule-candidate.schema.json")
        path.write_text(json.dumps(candidate, indent=2) + "\n")
        log_event("observation", "Group direct disease neighborhoods before the all-source regulation join: " + key, {
            "source": "Previously timed-out unrecorded candidate and source-cardinality profile in research event 332.",
            "finding": "The original flat four-edge join is replaced by a per-drug subquery. Direct diseases, target direction pairs, and downstream genes are deduplicated before the next expansion.",
            "implication": "No node, source, predicate, sign, support threshold, or output definition changes. This is an unmaterialized execution reformulation, not a biological refinement.",
            "next_action": "Run the complete bounded query and a bounded raw-equivalence comparison; keep the old timeout as an execution failure.",
            "candidate_id": key,
            "prior_cypher_template": original,
            "replacement_cypher_template": QUERY,
        })


if __name__ == "__main__":
    main()
