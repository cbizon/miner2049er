"""Profile and explicitly create a complete run-owned regulatory context cache."""

import argparse
from datetime import datetime, timezone
import json
import os
import shutil
import time

from neo4j import GraphDatabase, Query, READ_ACCESS, WRITE_ACCESS

from miner2049er.biolink_semantics import neo4j_relationship_type, predicate_expansion_record
from miner2049er.schema_validation import validate_document

from audit import records
from probe import REQUIRED, RUN, log_event


ARTIFACT = "r0004-signed-regulator-causal-context-v1"
RELATIONSHIP = "MINER_R0004_SIGNED_CAUSAL_CONTEXT"
RUN_ID = "run-2026-08-21-0915"
ROUND_ID = "round-0004"
MAX_SUPPORTS = 5_000_000
MAX_CONTEXTS = 1_000_000
RESERVE = 5 * 1024**3
CUTOFF = datetime.fromisoformat("2026-09-15T15:22:23-04:00")


def closure(predicate):
    predicates = predicate_expansion_record([predicate])["expanded_predicates"]
    return "|".join(sorted(neo4j_relationship_type(p) for p in predicates)), json.dumps(predicates)


EFFECT_TYPES, EFFECT_PREDICATES = closure("biolink:affects")
CAUSAL_TYPES, CAUSAL_PREDICATES = closure("biolink:contributes_to")
CAUSAL_LEG = (
    f"MATCH (gene:GeneOrGeneProduct)-[causal:{CAUSAL_TYPES}]->(disease:Disease) "
    f"WHERE causal.predicate IN {CAUSAL_PREDICATES} "
)
REGULATORY_LEG = (
    f"MATCH (regulator:GeneOrGeneProduct)-[bridge:{EFFECT_TYPES}]->(gene:GeneOrGeneProduct) "
    f"WHERE bridge.predicate IN {EFFECT_PREDICATES} "
    "AND bridge.qualified_predicate='biolink:causes' "
    "AND bridge.object_direction_qualifier IN ['increased','decreased'] "
    "AND bridge.object_aspect_qualifier IN ['activity','activity_or_abundance'] "
    "AND regulator<>gene "
)
NEIGHBORHOODS = (
    CAUSAL_LEG + "WITH gene,collect(DISTINCT disease) AS diseases "
    + REGULATORY_LEG
)
INCIDENCE_QUERY = (
    NEIGHBORHOODS
    + "WITH gene,size(diseases) AS disease_degree,"
    "count(DISTINCT [regulator,bridge.object_direction_qualifier]) AS signed_regulator_degree "
    "RETURN count(gene) AS downstream_genes,"
    "sum(disease_degree*signed_regulator_degree) AS support_incidences,"
    "max(disease_degree) AS maximum_disease_degree,"
    "max(signed_regulator_degree) AS maximum_signed_regulator_degree"
)
GROUPED = (
    NEIGHBORHOODS
    + "WITH DISTINCT regulator,gene,diseases,bridge.object_direction_qualifier AS direction "
    "UNWIND diseases AS disease "
    "WITH regulator,disease,"
    "collect(DISTINCT CASE WHEN direction='increased' THEN elementId(gene) END) AS increased_gene_element_ids,"
    "collect(DISTINCT CASE WHEN direction='decreased' THEN elementId(gene) END) AS decreased_gene_element_ids "
)
SIZES_QUERY = (
    GROUPED
    + "WITH regulator,disease,size(increased_gene_element_ids)+size(decreased_gene_element_ids) AS support_count "
    "RETURN count(*) AS contexts,count(DISTINCT regulator) AS regulators,"
    "count(DISTINCT disease) AS diseases,sum(support_count) AS support_incidences,"
    "min(support_count) AS minimum,max(support_count) AS maximum,avg(support_count) AS mean"
)
OWNER = f"artifact_id:'{ARTIFACT}',run_id:'{RUN_ID}'"
CREATE_QUERY = (
    GROUPED
    + "CALL (regulator,disease,increased_gene_element_ids,decreased_gene_element_ids) { "
    + f"MERGE (regulator)-[context:{RELATIONSHIP} {{{OWNER}}}]->(disease) "
    + f"SET context.round_id='{ROUND_ID}',"
    "context.increased_gene_element_ids=increased_gene_element_ids,"
    "context.decreased_gene_element_ids=decreased_gene_element_ids,"
    "context.support_count=size(increased_gene_element_ids)+size(decreased_gene_element_ids) "
    "RETURN count(context) AS created_contexts "
    "} IN TRANSACTIONS OF 1000 ROWS RETURN sum(created_contexts) AS relationships"
)
OWNED_MATCH = (
    f"MATCH (regulator:GeneOrGeneProduct)-[context:{RELATIONSHIP}]->(disease:Disease) "
    f"WHERE context.artifact_id='{ARTIFACT}' AND context.run_id='{RUN_ID}' "
)
VERIFY_QUERY = (
    OWNED_MATCH
    + "RETURN count(context) AS relationships,count(DISTINCT regulator) AS regulators,"
    "count(DISTINCT disease) AS diseases,count(context.support_count) AS values_populated,"
    "count(CASE WHEN context.support_count IS NULL THEN 1 END) AS values_missing,"
    "count(DISTINCT context.support_count) AS distinct_values,"
    "min(context.support_count) AS minimum,max(context.support_count) AS maximum,"
    "avg(context.support_count) AS mean,"
    "percentileCont(context.support_count,0.25) AS p25,"
    "percentileCont(context.support_count,0.5) AS p50,"
    "percentileCont(context.support_count,0.75) AS p75,"
    "percentileCont(context.support_count,0.9) AS p90,"
    "percentileCont(context.support_count,0.95) AS p95,"
    "sum(context.support_count) AS support_incidences,"
    "count(CASE WHEN context.increased_gene_element_ids IS NULL "
    "OR context.decreased_gene_element_ids IS NULL THEN 1 END) AS missing_member_lists,"
    "count(CASE WHEN context.support_count<>"
    "size(context.increased_gene_element_ids)+size(context.decreased_gene_element_ids) "
    "THEN 1 END) AS inconsistent_counts"
)
CLEANUP_QUERY = (
    f"MATCH ()-[context:{RELATIONSHIP}]->() WHERE context.artifact_id='{ARTIFACT}' "
    f"AND context.run_id='{RUN_ID}' AND context.round_id='{ROUND_ID}' "
    "CALL (context) { DELETE context } IN TRANSACTIONS OF 1000 ROWS"
)


def execute(driver, query, purpose, formulation, timeout, write=False):
    start = time.monotonic()
    try:
        with driver.session(database="neo4j", default_access_mode=WRITE_ACCESS if write else READ_ACCESS) as session:
            result = session.run(Query(
                query, timeout=timeout, metadata={"run_id": RUN_ID, "artifact_id": ARTIFACT}
            ))
            rows = [{"plan": result.consume().plan}] if query.startswith("EXPLAIN ") else [row.data() for row in result]
        log_event("query", purpose, {
            "purpose": purpose, "query_language": "cypher", "query_text": query,
            "outcome": "completed", "result_summary": json.dumps(rows),
            "runtime_seconds": time.monotonic() - start, "artifact_id": ARTIFACT,
            "formulation": formulation,
            "next_action": "Respect the complete-representation resource bounds and document any persistent addition before use.",
        })
        print(formulation, json.dumps(rows), flush=True)
        return rows
    except Exception as error:
        log_event("failure", purpose + " did not complete.", {
            "stage": "regulatory context " + formulation, "error": str(error),
            "diagnosis": "This formulation has not completed; no biological conclusion follows.",
            "next_action": "Check for any owned persistent relationships after a failed write; never rerun creation blindly.",
            "hypothesis_status": "blocked", "artifact_id": ARTIFACT,
            "query_text": query, "runtime_seconds": time.monotonic() - start,
        })
        raise


def resource_estimate(sizes):
    if not sizes["contexts"] or not sizes["support_incidences"]:
        raise RuntimeError("There is no nonempty regulatory context to materialize")
    estimate = sizes["support_incidences"] * 128 + sizes["contexts"] * 1024
    free = shutil.disk_usage(RUN).free
    if sizes["support_incidences"] > MAX_SUPPORTS or sizes["contexts"] > MAX_CONTEXTS:
        raise RuntimeError("Complete representation exceeds the predeclared incidence/context abort limits")
    if free - 3 * estimate < RESERVE:
        raise RuntimeError("Conservative structure-plus-transaction estimate would breach the disk reserve")
    return {"free_bytes": free, "estimated_structure_bytes": estimate, "reserved_transaction_factor": 3}


def artifact_document(observed):
    document = {
        "schema_version": "1.0", "run_id": RUN_ID, "round_id": ROUND_ID,
        "artifact_id": ARTIFACT, "name": "Complete signed regulator-to-causal-disease contexts",
        "artifact_kind": "derived_relationship",
        "description": (
            f"One relationship per regulator-disease pair with a signed activity path through a distinct causal gene. "
            f"The verified representation has {observed['relationships']} relationships, "
            f"{observed['regulators']} regulators, and {observed['diseases']} diseases."
        ),
        "target": {
            "node_labels": ["GeneOrGeneProduct", "Disease"], "relationship_types": [RELATIONSHIP],
            "property_name": "support_count", "value_type": "integer",
            "unit": "distinct downstream gene-node and regulatory-direction incidences",
            "scope": "Every regulator-disease endpoint pair supported by the complete declared two-edge subpath in the fixed graph.",
        },
        "semantics": {
            "definition": (
                "A regulator has a causes-qualified affects-descendant edge to a distinct downstream gene, "
                "with increased or decreased direction and activity or activity_or_abundance aspect; "
                "the downstream gene causes or contributes to the disease. support_count sums distinct "
                "downstream gene nodes separately by regulatory direction. increased_gene_element_ids and "
                "decreased_gene_element_ids store the corresponding unordered, deduplicated Neo4j node element identifiers. "
                "Ownership fields are artifact_id, run_id, and round_id."
            ),
            "inputs": [
                "Raw GeneOrGeneProduct-to-GeneOrGeneProduct effects under the complete Biolink 4.3.2 affects closure: " + EFFECT_PREDICATES,
                "Raw qualified_predicate, object_direction_qualifier, and object_aspect_qualifier values",
                "Raw downstream-gene-to-Disease predicates under the complete contributes_to closure: " + CAUSAL_PREDICATES,
                "Original endpoint-node identity; no external mapping or held-out label data",
            ],
            "formula": "support_count = number of distinct increased downstream gene nodes + number of distinct decreased downstream gene nodes, grouped by regulator and disease.",
            "aggregation": (
                "First deduplicate disease neighbors per downstream gene. Then deduplicate regulator and direction "
                "per downstream gene before expanding diseases. Group by regulator and disease and collect gene-node "
                "element identifiers separately for each sign. Store every nonempty context; the resource ceilings "
                "abort creation of the whole representation rather than truncate it. Write in transactions of "
                "one thousand context rows to bound transaction memory, without filtering or ranking any support. "
                "A partially completed write is not usable until verified as complete against the raw preflight."
            ),
            "deduplication": "Parallel source edges do not multiply node-direction support. A gene with both signs contributes once to each list and twice to support_count. List order is immaterial.",
            "missing_value_policy": "Missing or unsupported causal, direction, or aspect qualifiers do not qualify. An absent direction-specific neighborhood is an empty list. Pairs with no qualifying paths have no relationship. Node element identifiers are supplied by Neo4j for every source node.",
            "interpretation": (
                "This is a complete computational access path, not new evidence of treatment or a biological score. "
                "Dependent rules must rematch every original edge using their own exact expanded predicate sets, "
                "qualifiers, and sources. The broader stored affects closure cannot supply evidence that the rule excludes."
            ),
        },
        "execution": {"create_cypher": CREATE_QUERY, "verification_cypher": VERIFY_QUERY, "cleanup_cypher": CLEANUP_QUERY},
        "observed": {
            "measured_at": datetime.now(timezone.utc).isoformat(), "nodes_created": 0,
            "relationships_created": observed["relationships"], "nodes_updated": 0,
            "relationships_updated": 0,
            **{key: observed[key] for key in ("values_populated", "values_missing", "distinct_values", "minimum", "maximum", "mean")},
            "quantiles": {key: observed[key] for key in ("p25", "p50", "p75", "p90", "p95")},
        },
        "dependencies": [], "supersedes_artifact_id": None,
        "limitations": [
            "Regulatory signs and gene-disease causation do not establish the clinical risk direction or a corrective treatment mechanism.",
            "The full affects closure includes ameliorates_condition; exact raw predicate rematching is mandatory for treatment-free rules.",
            "Node element identifiers are local to this Neo4j instance and require rebuilding after graph reload or identity changes.",
            "The cache is fixed to the current graph and has no automatic refresh policy.",
        ],
    }
    validate_document(document, "neo4j-artifact.schema.json")
    return document


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["profile", "create", "verify"])
    parser.add_argument("--timeout-seconds", type=float, default=180)
    args = parser.parse_args()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing service variables: " + ", ".join(missing))
    manifest = json.loads((RUN / "run.json").read_text())
    if manifest["run_id"] != RUN_ID or manifest["current_round_id"] != ROUND_ID:
        raise RuntimeError("This artifact belongs only to the active fourth round")
    if shutil.disk_usage(RUN).free < RESERVE:
        raise RuntimeError("Disk reserve breached")
    with GraphDatabase.driver(
        os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        max_transaction_retry_time=0, connection_timeout=15,
    ) as driver:
        if args.mode != "verify" and datetime.now().astimezone() >= CUTOFF:
            raise RuntimeError("New-work cutoff reached; do not launch context construction")
        if args.mode == "profile":
            execute(driver, REGULATORY_LEG + "RETURN bridge.predicate AS predicate,"
                    "bridge.primary_knowledge_sources AS sources,count(bridge) AS edges,"
                    "count(DISTINCT regulator) AS regulators,count(DISTINCT gene) AS genes",
                    "Profile the signed regulatory leg for complete context construction.", "regulatory-source-leg", args.timeout_seconds)
            execute(driver, CAUSAL_LEG + "RETURN causal.predicate AS predicate,"
                    "causal.primary_knowledge_sources AS sources,count(causal) AS edges,"
                    "count(DISTINCT gene) AS genes,count(DISTINCT disease) AS diseases",
                    "Profile the causal disease leg for complete context construction.", "causal-source-leg", args.timeout_seconds)
            incidence = execute(driver, INCIDENCE_QUERY, "Bound total distinct gene-direction context incidences before expansion.",
                                "context-incidence-bound", args.timeout_seconds)[0]
            if incidence["support_incidences"] > MAX_SUPPORTS:
                raise RuntimeError("Complete context incidence count exceeds the predeclared abort limit")
            execute(driver, "EXPLAIN " + SIZES_QUERY, "Inspect the complete context aggregation plan before execution.",
                    "complete-context-size-explain", 30)
            sample_prefix = (
                "CALL () { " + CAUSAL_LEG
                + "RETURN DISTINCT gene ORDER BY gene.id,elementId(gene) LIMIT 20 } "
            )
            execute(driver, sample_prefix + SIZES_QUERY,
                    "Test complete neighborhood aggregation for twenty graph-selected downstream genes.",
                    "bounded-context-size-profile", args.timeout_seconds)
            sizes = execute(driver, SIZES_QUERY, "Measure the complete preaggregated regulatory context size.",
                            "complete-context-size-profile", args.timeout_seconds)[0]
            if sizes["support_incidences"] != incidence["support_incidences"]:
                raise RuntimeError("Preaggregated size and independently counted support incidences disagree")
            print("RESOURCE_ESTIMATE", json.dumps(resource_estimate(sizes)), flush=True)
            return
        if args.mode == "create":
            if any(a["artifact_id"] == ARTIFACT for a in records(RUN / "neo4j-artifacts.jsonl")):
                raise RuntimeError("This artifact is already recorded; never replace it")
            profiles = [
                e for e in records(RUN / "research-log.jsonl")
                if e["details"].get("artifact_id") == ARTIFACT
                and e["details"].get("formulation") == "complete-context-size-profile"
                and e["details"].get("query_text") == SIZES_QUERY
                and e["details"].get("outcome") == "completed"
            ]
            if not profiles:
                raise RuntimeError("A completed exact source-size preflight is required before creation")
            sizes = json.loads(profiles[-1]["details"]["result_summary"])[0]
            print("RESOURCE_ESTIMATE", json.dumps(resource_estimate(sizes)), flush=True)
            existing = execute(driver, OWNED_MATCH + "RETURN count(context) AS relationships",
                               "Check that the new context ownership namespace is empty.", "precreation-ownership-check", 30)[0]
            if existing["relationships"]:
                raise RuntimeError("Owned relationships already exist; investigate before any creation retry")
            execute(driver, "EXPLAIN " + CREATE_QUERY,
                    "Inspect bounded-transaction context creation before the first write.",
                    "context-batched-creation-explain", 30)
            created = execute(driver, CREATE_QUERY, "Create the complete signed regulatory context access path.",
                              "context-creation", args.timeout_seconds, write=True)[0]
        observed = execute(driver, VERIFY_QUERY, "Verify the run-owned signed regulatory context representation.",
                           "context-verification", args.timeout_seconds)[0]
        if observed["values_missing"] or observed["missing_member_lists"] or observed["inconsistent_counts"]:
            raise RuntimeError("Context properties failed verification; do not use the new structure")
        if args.mode == "create":
            comparisons = {
                "relationships": sizes["contexts"],
                "regulators": sizes["regulators"],
                "diseases": sizes["diseases"],
                "support_incidences": sizes["support_incidences"],
                "minimum": sizes["minimum"],
                "maximum": sizes["maximum"],
            }
            if created["relationships"] != sizes["contexts"] or any(
                observed[key] != value for key, value in comparisons.items()
            ):
                raise RuntimeError("Created and verified contexts disagree with the complete raw preflight")
        document = artifact_document(observed)
        print("VERIFIED_ARTIFACT_DOCUMENT", json.dumps(document, sort_keys=True), flush=True)
        print("Append this verified document to the artifact inventory immediately before any dependent rule uses it.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log_event("failure", "Regulatory-context operation stopped without advancing dependent rules.", {
            "stage": "bounded context materialization workflow", "error": str(error),
            "diagnosis": "A resource guard, query, or verification check did not pass. This is not evidence against the biological hypothesis.",
            "next_action": "Inspect recorded queries and verify the owned namespace after any write attempt; record or clean up persistent state before resuming other work.",
            "hypothesis_status": "blocked", "artifact_id": ARTIFACT,
        })
        raise
