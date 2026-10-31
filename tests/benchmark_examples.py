from miner2049er.biolink_semantics import (
    BIOLINK_VERSION,
    FULL_EXPANSION,
    predicate_expansion_record,
)


def neo4j_artifact(
    run_id: str = "test-run",
    round_id: str = "round-0001",
    artifact_id: str = "disease-associated-gene-count",
) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "round_id": round_id,
        "artifact_id": artifact_id,
        "name": "Disease-associated gene count",
        "artifact_kind": "node_property",
        "description": (
            "The number of distinct genes associated with each disease after "
            "identifier and edge deduplication."
        ),
        "target": {
            "node_labels": ["Disease"],
            "relationship_types": [],
            "property_name": "_miner_associated_gene_count",
            "value_type": "integer",
            "unit": "genes",
            "scope": "Every Disease node with at least one qualifying association.",
        },
        "semantics": {
            "definition": (
                "Count of distinct Gene nodes connected to a disease by a "
                "configured gene-disease association predicate."
            ),
            "inputs": [
                "Disease nodes",
                "Gene nodes",
                "gene-disease association relationships",
            ],
            "formula": "count(DISTINCT gene.id)",
            "aggregation": "One integer count per normalized disease node.",
            "deduplication": (
                "Gene identifiers are deduplicated within each disease before counting."
            ),
            "missing_value_policy": (
                "Diseases without a qualifying relationship retain no property."
            ),
            "interpretation": (
                "Lower values identify diseases whose genetic association "
                "neighborhood is comparatively focused."
            ),
        },
        "execution": {
            "create_cypher": (
                "MATCH (d:Disease)-[]-(g:Gene) WITH d, count(DISTINCT g.id) AS n "
                "SET d._miner_associated_gene_count = n"
            ),
            "verification_cypher": (
                "MATCH (d:Disease) RETURN count(d._miner_associated_gene_count) "
                "AS populated, min(d._miner_associated_gene_count) AS minimum"
            ),
            "cleanup_cypher": (
                "MATCH (d:Disease) REMOVE d._miner_associated_gene_count"
            ),
        },
        "observed": {
            "measured_at": "2026-08-18T12:00:00Z",
            "nodes_created": 0,
            "relationships_created": 0,
            "nodes_updated": 120,
            "relationships_updated": 0,
            "values_populated": 120,
            "values_missing": 30,
            "distinct_values": 42,
            "minimum": 1,
            "maximum": 860,
            "mean": 73.5,
            "quantiles": {"p50": 18, "p90": 211, "p99": 740},
        },
        "dependencies": [],
        "supersedes_artifact_id": None,
        "limitations": [
            "The value depends on the configured predicate closure and source graph."
        ],
    }


def benchmark_rule(
    run_id: str = "test-run",
    round_id: str = "round-0001",
    rule_id: str = "test-rule",
) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "round_id": round_id,
        "rule_id": rule_id,
        "family_id": "test-family",
        "parent_rule_id": None,
        "name": "Test treatment rule",
        "status": "candidate",
        "plain_language_rule": (
            "A candidate chemical is connected to a disease through test evidence."
        ),
        "hypothesis": "The test graph pattern predicts treatment relationships.",
        "variant_parameters": {},
        "graph_pattern": {
            "nodes": [
                {
                    "id": "chemical",
                    "role": "candidate treatment",
                    "categories": ["biolink:ChemicalEntity"],
                    "explanation": "The predicted treatment.",
                },
                {
                    "id": "disease",
                    "role": "target disease",
                    "categories": ["biolink:Disease"],
                    "explanation": "The predicted disease.",
                },
            ],
            "edges": [
                {
                    "id": "evidence",
                    "subject": "chemical",
                    "object": "disease",
                    "predicates": ["biolink:related_to"],
                    "predicate_expansion": predicate_expansion_record(
                        ["biolink:related_to"]
                    ),
                    "direction": "forward",
                    "explanation": "The test evidence relationship.",
                }
            ],
            "constraints": [],
        },
        "derived_features": [],
        "mechanism": {
            "score": "low",
            "rationale": "This fixture tests benchmark workflow behavior.",
        },
        "uses_treatment_edges": True,
        "execution": {
            "cypher": (
                "MATCH (subject)-[]->(object) "
                "RETURN subject.id AS subject_id, object.id AS object_id"
            ),
            "predicate_expansion": {
                "semantics": FULL_EXPANSION,
                "biolink_version": BIOLINK_VERSION,
                "implementation": (
                    "The rule query uses every expanded predicate recorded on "
                    "each graph-pattern edge."
                ),
            },
            "trapi": {
                "expressibility": "full",
                "query": {},
                "limitations": "",
            },
        },
        "limitations": ["This is a test fixture."],
    }
