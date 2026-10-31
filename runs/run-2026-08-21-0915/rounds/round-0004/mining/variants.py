"""Generate biologically specified structural variants, not ledger records."""

from copy import deepcopy
import json

from miner2049er.schema_validation import validate_document

from candidates import (
    CATALOG, HERE, NODES, add, build, constraint, edge, effect, full_control,
    match, node, trapi,
)


def derive(base_id, key, title, hypothesis, *, edges=None, conditions=None,
           constraints=None, tail=None, features=None, support="gene"):
    base = CATALOG[base_id]
    result = deepcopy(base)
    result.update(rule_id=key, parent_rule_id=base_id, name=title, hypothesis=hypothesis, status="candidate")
    edges = deepcopy(edges if edges is not None else base["graph_pattern"]["edges"])
    constraints = deepcopy(constraints or [])
    nodes = [deepcopy(n) for k, n in NODES.items() if any(k in (e["subject"], e["object"]) for e in edges)]
    result["graph_pattern"] = {"nodes": nodes, "edges": edges, "constraints": constraints}
    source_query = base["execution"]["cypher_template"]
    marker = "/* END CURATED ACCESS PATH */"
    prefix = source_query.split(marker, 1)[0] + marker + " " if marker in source_query else ""
    query = prefix + " ".join(match(e) for e in edges)
    if conditions:
        query += " AND " + " AND ".join("(" + c + ")" for c in conditions)
    query += tail or (
        " RETURN chemical.id AS subject_id,disease.id AS object_id,"
        f"count(DISTINCT {support}) AS support_count"
    )
    result["execution"]["cypher_template"] = query
    result["execution"]["trapi"] = trapi(edges, nodes, constraints)
    result["derived_features"].extend(features or [])
    result["plain_language_rule"] = (
        "Predict treatment when " + "; ".join(e["explanation"] for e in edges)
        + " " + " ".join(c["explanation"] for c in constraints)
    )
    result["mechanism"]["rationale"] = hypothesis + " Association does not establish a corrective clinical mechanism."
    validate_document(result, "rule-candidate.schema.json")
    CATALOG[key] = result
    return result


def genetic(key="genetic", subject="gene"):
    return edge(key, subject, "disease", "gene_associated_with_condition",
                "The " + subject + " has independent genetic association evidence for the same disease",
                sources=["infores:geneticskp"])


def generated():
    build()
    original = set(CATALOG)
    distinct = constraint("distinct-genes", "The upstream regulator and downstream disease gene must be distinct.")
    opposite = constraint("opposite-signs", "Drug action and downstream regulation have opposite signs, yielding net decrease.")
    net_conditions = ["regulator<>gene", "target.object_direction_qualifier<>bridge.object_direction_qualifier"]
    for label, condition, explanation in [
        (
            "majority", "size(lower_genes)>size(higher_genes)",
            "The number of distinct disease genes receiving any net-decreasing path must exceed the number receiving any net-increasing path.",
        ),
        (
            "unopposed", "size(lower_genes)>0 AND size(higher_genes)=0",
            "At least one disease gene must receive a net-decreasing path and no disease gene may receive a net-increasing path.",
        ),
    ]:
        derive(
            "r4-regulatory-unsigned", "r4-regulatory-net-decrease-" + label,
            "Net Decrease With " + label.title() + " Gene Votes",
            "Gene-level direction consistency may distinguish corrective intervention from generic signed network proximity.",
            conditions=["regulator<>gene"],
            constraints=[distinct, constraint("gene-votes", explanation, kind="cardinality")],
            tail=(
                " WITH chemical,disease,"
                "collect(DISTINCT CASE WHEN target.object_direction_qualifier<>bridge.object_direction_qualifier THEN gene.id END) AS lower_genes,"
                "collect(DISTINCT CASE WHEN target.object_direction_qualifier=bridge.object_direction_qualifier THEN gene.id END) AS higher_genes"
                " WHERE " + condition
                + " RETURN chemical.id AS subject_id,disease.id AS object_id,size(lower_genes) AS support_count"
            ),
            features=[{
                "name": "distinct downstream gene direction balance",
                "definition": "Two signed causal activity edges compose to net decrease when their signs differ and to net increase when their signs agree.",
                "inputs": ["Every qualifying signed drug-regulator-gene path in the stated graph pattern"],
                "construction": (
                    "Group all paths by drug and disease. Independently collect distinct canonical downstream gene IDs "
                    "for opposite-sign and same-sign paths. Ignore null CASE values. A gene with both path signs "
                    "belongs to both sets, so parallel edges and regulators cannot inflate its vote."
                ),
                "formula": "L=count(distinct net-decreased genes); H=count(distinct net-increased genes); " + condition,
                "interpretation": explanation + " Sign consistency does not identify whether disease causation reflects gain or loss of normal gene function.",
                "neo4j_artifact_id": None,
            }],
        )
    base = CATALOG["r4-regulatory-net-decrease"]
    for label, aspect, sources in [
        ("ctd-activity", ["activity", "activity_or_abundance"], ["infores:ctd"]),
        ("ctd-expression", ["expression"], ["infores:ctd"]),
        ("expression", ["expression"], None),
    ]:
        edges = deepcopy(base["graph_pattern"]["edges"])
        bridge = effect("bridge", "regulator", "gene", signed=True, aspect=aspect)
        if sources:
            bridge["source_constraints"] = sources
            bridge["explanation"] += " A primary source must be infores:ctd."
        edges[2] = bridge
        derive(
            base["rule_id"], "r4-regulatory-net-decrease-" + label,
            "Signed Regulatory Bridge With " + label.replace("-", " ").title(),
            "Curated expression regulation and activity regulation are different biological evidence channels and should be tested separately.",
            edges=edges, conditions=net_conditions, constraints=[distinct, opposite],
        )
    source_disjoint = (
        "size(coalesce(bridge.primary_knowledge_sources,[]))>0 "
        "AND size(coalesce(causal.primary_knowledge_sources,[]))>0 "
        "AND none(source IN bridge.primary_knowledge_sources WHERE source IN causal.primary_knowledge_sources)"
    )
    derive(
        base["rule_id"], "r4-regulatory-net-decrease-source-disjoint",
        "Regulatory And Causal Arms With Disjoint Primary Sources",
        "Separating the regulatory and disease-causal evidence sources may reduce a shared text-extraction explanation.",
        conditions=net_conditions + [source_disjoint],
        constraints=[distinct, opposite, constraint(
            "source-disjoint", "The regulatory and gene-disease causal edges each need nonempty primary-source arrays, with no primary source shared between them.",
            kind="source",
        )],
    )
    for label, both in [("genetic-disease", False), ("genetic-corroboration", True)]:
        edges = deepcopy(base["graph_pattern"]["edges"])
        if not both:
            edges = [e for e in edges if e["id"] != "causal"]
        edges.append(genetic())
        derive(
            base["rule_id"], "r4-regulatory-net-decrease-" + label,
            "Signed Regulatory Intervention With " + label.replace("-", " ").title(),
            "A distinct genetic disease arm tests whether the downstream gene is independently implicated beyond text-derived causal assertions.",
            edges=edges, conditions=net_conditions, constraints=[distinct, opposite],
        )
    physical_base = CATALOG["r4-regulatory-net-decrease-physical-corroboration"]
    derive(
        physical_base["rule_id"], "r4-regulatory-net-decrease-independent-physical",
        "Signed Regulation With Source-Independent Physical Interaction",
        "A physical interaction from a separate primary source may corroborate the same regulatory bridge.",
        conditions=net_conditions + [
            "size(coalesce(physical.primary_knowledge_sources,[]))>0",
            "size(coalesce(bridge.primary_knowledge_sources,[]))>0",
            "none(source IN physical.primary_knowledge_sources WHERE source IN bridge.primary_knowledge_sources)",
        ],
        constraints=[distinct, opposite, constraint(
            "physical-source", "The physical and regulatory bridge edges require nonempty, disjoint primary-source arrays.",
            kind="source",
        )],
    )

    NODES["member"] = node("member", "GeneOrGeneProduct", "Gene counted in the complete family-membership neighborhood")
    for leg in ("genetic", "causal"):
        base_id = "r4-family-" + leg + "-direct"
        base = CATALOG[base_id]
        member_edge = edge(
            "member_count", "member", "family", "member_of",
            "Every distinct gene in the complete PANTHER family is counted",
            sources=["infores:panther"],
        )
        result = derive(
            base_id, base_id + "-small-family", "Specific PANTHER Family " + leg.title() + " Bridge",
            "Excluding the largest evolutionary families may suppress generic family similarity while retaining the independently observed drug and disease arms.",
            conditions=["regulator<>gene"],
            constraints=[distinct, constraint(
                "family-size", "The family must contain at most fourteen distinct GeneOrGeneProduct nodes through PANTHER member-of edges. Fourteen is the observed 90th percentile across all graph PANTHER families.",
                kind="degree",
            )],
            support="family",
            features=[{
                "name": "complete PANTHER family member degree",
                "definition": "The number of distinct canonical GeneOrGeneProduct members of a family through member_of edges with PANTHER primary provenance.",
                "inputs": ["All original gene-to-family member_of edges with infores:panther primary-source support"],
                "construction": "For each candidate family, count distinct endpoint gene nodes across its entire incoming qualifying membership neighborhood, not only drug targets or disease genes.",
                "formula": "family_degree=count(distinct qualifying member genes); require family_degree<=14",
                "interpretation": "The fixed all-family 90th-percentile bound penalizes large families. It does not imply functional equivalence or shared tissue context.",
                "neo4j_artifact_id": None,
            }],
        )
        query = result["execution"]["cypher_template"]
        query, ending = query.rsplit(" RETURN ", 1)
        query += (
            " WITH DISTINCT chemical,disease,family CALL { WITH family "
            + match(member_edge)
            + " RETURN count(DISTINCT member) AS family_degree }"
            + " WITH chemical,disease,family,family_degree WHERE family_degree<=14 RETURN " + ending
        )
        result["execution"]["cypher_template"] = query
        result["graph_pattern"]["edges"].append(member_edge)
        result["graph_pattern"]["nodes"].append(deepcopy(NODES["member"]))
        result["plain_language_rule"] += " " + member_edge["explanation"]
        result["execution"]["trapi"] = trapi(
            result["graph_pattern"]["edges"], result["graph_pattern"]["nodes"],
            result["graph_pattern"]["constraints"],
        )
        result["execution"]["trapi"]["limitations"] += (
            "; member_count denotes a complete neighborhood count, not one existential TRAPI match"
        )
    base_id = "r4-family-genetic-direct"
    for label, extra in [
        ("target-genetics", genetic("target_genetics", "regulator")),
        ("physical", edge("physical", "regulator", "gene", "physically_interacts_with",
                          "The two family-related genes also physically interact", either=True)),
    ]:
        derive(
            base_id, base_id + "-" + label, "Evolutionary Family With " + label.replace("-", " ").title(),
            "An additional gene-specific arm tests whether family similarity alone explains the candidate.",
            edges=deepcopy(CATALOG[base_id]["graph_pattern"]["edges"]) + [extra],
            conditions=["regulator<>gene"], constraints=[distinct], support="family",
        )

    base_id = "r4-process-curated-target-direct"
    for label, extra in [
        ("target-genetics", genetic()),
        ("target-causality", edge("causal", "gene", "disease", "contributes_to",
                                 "The curated target also causes or contributes to the same disease")),
        ("dual-unsigned", effect("perturbation", "chemical", "process")),
    ]:
        derive(
            base_id, base_id + "-" + label, "Genetic Process With " + label.replace("-", " ").title(),
            "An added target-specific or direct process arm tests convergence beyond membership in a genetically associated process.",
            edges=deepcopy(CATALOG[base_id]["graph_pattern"]["edges"]) + [extra],
            support="process",
        )
    for direction in ("decreased", "increased"):
        for direct in (False, True):
            base_id = "r4-process-" + direction + ("-direct" if direct else "")
            edges = deepcopy(CATALOG[base_id]["graph_pattern"]["edges"])
            replacement = edge(
                "perturbation", "chemical", "process", "affects",
                "The drug causally changes the biological process in the " + direction
                + " direction; no object-aspect qualifier is required because the endpoint is itself a biological process",
                exact=True,
                qualifiers={"qualified_predicate": "biolink:causes", "object_direction_qualifier": direction},
            )
            edges = [replacement if e["id"] == "perturbation" else e for e in edges]
            derive(
                base_id, base_id + "-direction-only",
                "Genetically Associated Process " + direction.title() + " Without An Aspect Requirement",
                "Recorded CTD process effects have explicit causal direction but lack object-aspect values; this formulation tests that evidence directly.",
                edges=edges, support="process",
            )
    base_id = "r4-process-dual-perturbation-direct"
    edges = deepcopy(CATALOG[base_id]["graph_pattern"]["edges"])
    replacement = next(
        deepcopy(e) for e in CATALOG["r4-process-decreased-direct-direction-only"]["graph_pattern"]["edges"]
        if e["id"] == "perturbation"
    )
    edges = [replacement if e["id"] == "perturbation" else e for e in edges]
    derive(
        base_id, base_id + "-direction-only",
        "Direct And Target-Mediated Process Convergence With Recorded Process Direction",
        "A curated decreased target within the genetically associated process converges with a separately recorded decreased drug-process effect.",
        edges=edges, support="process",
    )
    derive(
        base_id, "r4-process-dual-perturbation-direction-only",
        "Target And Direct Process Convergence Without Direct Drug-Disease Evidence",
        "Removing the direct drug-disease arm tests whether the two process intervention arms generalize without that associative anchor.",
        edges=[e for e in edges if e["id"] != "direct"], support="process",
    )
    for label, both in [("genetic", False), ("causal-genetic", True)]:
        base_id = "r4-production-decreased-causal-loop" if both else "r4-production-decreased"
        derive(
            base_id, "r4-production-decreased-" + label,
            "Disease-Produced Molecule With " + label.replace("-", " ").title() + " Evidence",
            "Independent genetic support tests whether a disease-produced molecule is implicated beyond being a textual biomarker or consequence.",
            edges=deepcopy(CATALOG[base_id]["graph_pattern"]["edges"]) + [genetic()],
        )
    for key in list(set(CATALOG) - original):
        value = CATALOG[key]
        if any(e.get("excluded_predicates") for e in value["graph_pattern"]["edges"]):
            full_control(value)
    return {key: value for key, value in CATALOG.items() if key not in original}


def main():
    output = HERE / "active-candidates"
    output.mkdir(exist_ok=True)
    values = generated()
    for key, value in values.items():
        validate_document(value, "rule-candidate.schema.json")
        path = output / (key + ".json")
        if path.exists():
            if json.loads(path.read_text()) != value:
                raise RuntimeError("Refusing to change existing candidate " + key)
            continue
        path.write_text(json.dumps(value, indent=2) + "\n")
    print("Generated", len(values), "validated structural and aggregation candidate documents.")


if __name__ == "__main__":
    main()
