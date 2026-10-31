"""Candidate documents for grouping corrections and independent genetic controls."""

from copy import deepcopy
import json

from miner2049er.biolink_semantics import predicate_expansion_record
from miner2049er.schema_validation import validate_document

from candidates import (
    CATALOG, HERE, NODES, add, build, constraint, direct, edge, effect,
    full_control, match, node, trapi,
)
from variants import derive, genetic


ROLES = ["infores:semmeddb", "infores:faers", "infores:multiomics-clinicaltrials"]
TARGET_ARTIFACT = "r0004-curated-causal-target-v1"


def transfer(key, *, signed=None, minimum=1, per_parent=False, direct_arm=True,
             relationship=False, full=False):
    NODES["parent"] = node("parent", "Drug", "Different drug with corroborated indication evidence")
    indication = edge(
        "indication", "parent", "disease", "treats_or_applied_or_studied_to_treat",
        "The parent drug has treatment-oriented evidence whose pair-level primary-source "
        "union includes SemMedDB literature, FAERS applied-use, and multiomics clinical trials",
    )
    if not full:
        indication["excluded_predicates"] = predicate_expansion_record(
            ["biolink:treats"]
        )["expanded_predicates"]
        indication["exclusion_rationale"] = (
            "Exclude every target treatment predicate so parent indication support "
            "does not directly reuse a visible target label."
        )
        indication["explanation"] += (
            " Exclude treats, ameliorates_condition, and preventative_for_condition; "
            "the remaining six descendants represent application, study, trial, model, "
            "or unspecialized treatment-oriented evidence."
        )
    edges = [
        indication,
        effect("parent_target", "parent", "gene", signed=bool(signed), curated=True, full=full),
        effect("candidate_target", "chemical", "gene", signed=bool(signed), curated=True, full=full),
    ]
    if direct_arm:
        edges.append(direct(full=full))
    if relationship:
        edges.append(edge(
            "derivation", "chemical", "parent", "derives_from",
            "The candidate drug derives from the supported parent, including the "
            "is_metabolite_of descendant, in the stored candidate-to-parent direction",
        ))
    grouping = (
        f"At least {minimum} distinct shared target genes must occur with one and the same "
        "supported parent. Genes from different parents cannot meet this minimum."
        if per_parent else
        f"At least {minimum} distinct shared target genes must occur across all supported "
        "parents pooled for this candidate and disease; different genes may use different parents."
    )
    constraints = [
        constraint("distinct-drugs", "The candidate and supported parent must be different canonical drug nodes."),
        constraint("roles", "Deduplicate primary-source identifiers over all qualifying parent-disease edges and require all three named sources.", kind="source"),
        constraint("target-grouping", grouping, kind="cardinality"),
    ]
    conditions = ["chemical<>parent"]
    if signed:
        relation = "=" if signed == "same" else "<>"
        conditions.append(
            f"candidate_target.object_direction_qualifier{relation}"
            "parent_target.object_direction_qualifier"
        )
        constraints.append(constraint(
            "target-directions",
            "Both drug effects must have explicit activity or activity_or_abundance "
            f"qualifiers and {signed} increased/decreased directions on the shared gene.",
            kind="property",
        ))
    support_type = (
        "MINER_R0001_TREATMENT_SOURCE_SUPPORT" if full
        else "MINER_R0001_NONTARGET_TREATMENT_SOURCE_SUPPORT"
    )
    support_artifact = (
        "r0001-treatment-source-support-v1" if full
        else "r0001-nontarget-treatment-source-support-v1"
    )
    prefix = (
        f"MATCH (parent:Drug)-[cohort:{support_type}]->(disease:Disease) "
        f"WHERE cohort.artifact_id='{support_artifact}' "
        f"AND all(source IN {json.dumps(ROLES)} WHERE source IN cohort.primary_sources) "
        "MATCH (parent)-[parent_access:MINER_R0004_CURATED_TARGET]->(gene:GeneOrGeneProduct)"
        f" WHERE parent_access.artifact_id='{TARGET_ARTIFACT}' "
        "MATCH (chemical:Drug)-[candidate_access:MINER_R0004_CURATED_TARGET]->(gene)"
        f" WHERE candidate_access.artifact_id='{TARGET_ARTIFACT}' "
        "WITH DISTINCT chemical,parent,gene,disease "
    )
    features = [
        {
            "name": "parent indication primary-source union",
            "definition": "Distinct primary knowledge sources across the stated indication predicate closure for one parent-disease pair.",
            "inputs": ["Original parent-disease treatment-oriented predicates and primary_knowledge_sources arrays"],
            "construction": "Group by canonical parent and disease, union and deduplicate source identifiers. Missing arrays contribute no identifiers. The stored access path contains pairs with at least two sources; this rule requires all three named sources and rematches raw edges.",
            "formula": "Require SemMedDB, FAERS, and multiomics clinical trials in the deduplicated union.",
            "interpretation": "Complementary resource coverage is not proof that evidence is statistically independent.",
            "neo4j_artifact_id": support_artifact,
        },
        {
            "name": "complete curated causal target access",
            "definition": "Curated causes-qualified drug-target pairs over the complete affects closure.",
            "inputs": ["Original causal affects-descendant edges from ChEMBL, Guide to Pharmacology, and DrugCentral"],
            "construction": "Group qualifying raw edges by drug and gene, counting distinct relationship identities. Retain one compact edge per endpoint pair. Rematch every raw target predicate, qualifier, and source required here, on both drugs.",
            "formula": "One access relationship iff at least one qualifying raw curated causal effect exists.",
            "interpretation": "This only accelerates joins; missing edges mean no qualifying curated evidence. It adds no predictive threshold.",
            "neo4j_artifact_id": TARGET_ARTIFACT,
        },
        {
            "name": "shared target grouping",
            "definition": grouping,
            "inputs": ["Canonical shared genes on all qualifying parent-candidate-disease paths"],
            "construction": "Deduplicate genes before the minimum test within the explicitly stated group. Deduplicate final candidate-disease pairs. support_count reports the union of genes from retained groups.",
            "formula": f"Require distinct gene count >= {minimum} " + ("per parent." if per_parent else "after pooling parents."),
            "interpretation": "Distinct genes can be functionally related; target multiplicity alone is not independent biological evidence.",
            "neo4j_artifact_id": None,
        },
    ]
    result = add(
        key, "shared-curated-target-pharmacologic-neighbor-transfer",
        "Pharmacologic Neighbor " + key.removeprefix("r4-transfer-").replace("-", " ").title(),
        "Explicit parent grouping and matched target pharmacology may distinguish transferable "
        "indications from pooled target-neighborhood similarity.",
        edges, conditions=conditions, constraints=constraints, prefix=prefix,
        features=features, score="medium",
        limitation="Shared molecular action does not guarantee shared exposure, dose, efficacy, or clinical context.",
    )
    # Raw source union is rechecked so materialization cannot stand in for rule semantics.
    body = prefix + " ".join(match(e) for e in edges)
    body += " AND " + " AND ".join("(" + x + ")" for x in conditions)
    body += (
        " WITH DISTINCT chemical,parent,gene,disease CALL { WITH parent,disease "
        "MATCH (parent)-[role_edge:{{relationship_types:indication}}]->(disease) "
        "WHERE role_edge.predicate IN {{predicates:indication}} "
        "UNWIND coalesce(role_edge.primary_knowledge_sources,[]) AS source "
        "RETURN collect(DISTINCT source) AS raw_sources } "
        f"WITH chemical,parent,gene,disease WHERE all(source IN {json.dumps(ROLES)} "
        "WHERE source IN raw_sources)"
    )
    if per_parent:
        body += (
            " WITH chemical,parent,disease,collect(DISTINCT gene.id) AS shared_genes"
            f" WHERE size(shared_genes)>={minimum} UNWIND shared_genes AS retained_gene"
            " RETURN chemical.id AS subject_id,disease.id AS object_id,"
            "count(DISTINCT retained_gene) AS support_count"
        )
    else:
        body += (
            " WITH chemical,disease,collect(DISTINCT gene.id) AS shared_genes"
            f" WHERE size(shared_genes)>={minimum}"
            " RETURN chemical.id AS subject_id,disease.id AS object_id,"
            "size(shared_genes) AS support_count"
        )
    result["execution"]["cypher_template"] = body
    result["execution"]["trapi"] = trapi(edges, result["graph_pattern"]["nodes"], constraints)
    result["execution"]["trapi"]["limitations"] += "; source unions and complete target grouping must be computed across all results"
    if full:
        result["parent_rule_id"] = key.removesuffix("-full-closure")
    validate_document(result, "rule-candidate.schema.json")
    return result


def main():
    build()
    original = set(CATALOG)
    for sign in ("unsigned", "net-increase-control"):
        base_id = "r4-regulatory-" + sign
        for both in (False, True):
            edges = deepcopy(CATALOG[base_id]["graph_pattern"]["edges"])
            if not both:
                edges = [e for e in edges if e["id"] != "causal"]
            edges.append(genetic())
            conditions = ["regulator<>gene"]
            constraints = [constraint("distinct-genes", "The regulator and disease-associated gene must be distinct.")]
            if sign != "unsigned":
                conditions.append("target.object_direction_qualifier=bridge.object_direction_qualifier")
                constraints.append(constraint("net-increase", "Equal signs on the two causal activity effects imply net increase."))
            rule = derive(
                base_id, base_id + ("-genetic-corroboration" if both else "-genetic-disease"),
                "Genetic Regulatory " + sign.replace("-", " ").title() + (" With Causal Corroboration" if both else ""),
                "Matched unsigned and opposite-sign controls test whether genetic association, "
                "rather than corrective regulatory polarity, explains predictive enrichment.",
                edges=edges, conditions=conditions, constraints=constraints,
            )
            full_control(rule)
    settings = [
        ("pooled-one-direct", {}),
        ("same-sign-direct", {"signed": "same"}),
        ("opposite-sign-direct", {"signed": "opposite"}),
        ("pooled-two-direct", {"minimum": 2}),
        ("same-parent-two-direct", {"minimum": 2, "per_parent": True}),
        ("same-parent-two-same-sign-direct", {"minimum": 2, "per_parent": True, "signed": "same"}),
        ("pooled-one-no-direct", {"direct_arm": False}),
        ("same-sign-no-direct", {"direct_arm": False, "signed": "same"}),
        ("derived-parent-direct", {"relationship": True}),
    ]
    for name, kwargs in settings:
        transfer("r4-transfer-" + name, **kwargs)
        transfer("r4-transfer-" + name + "-full-closure", full=True, **kwargs)
    output = HERE / "active-candidates"
    for key in sorted(set(CATALOG) - original):
        document = CATALOG[key]
        path = output / (key + ".json")
        validate_document(document, "rule-candidate.schema.json")
        if path.exists():
            if json.loads(path.read_text()) != document:
                raise RuntimeError("Refusing to change an existing candidate: " + key)
        else:
            path.write_text(json.dumps(document, indent=2) + "\n")
    print("Prepared", len(set(CATALOG) - original), "candidate documents; no ledgers modified.")


if __name__ == "__main__":
    main()
