"""Generate self-contained candidate documents, never benchmark ledgers."""

import argparse
from copy import deepcopy
import itertools
import json
from pathlib import Path

from miner2049er.biolink_semantics import predicate_expansion_record
from miner2049er.schema_validation import validate_document


HERE = Path(__file__).resolve().parent
CURATED = ["infores:chembl", "infores:gtopdb", "infores:drugcentral"]
ACTIVITY = ["activity", "activity_or_abundance"]
CATALOG = {}


def literal(value):
    return json.dumps(value, separators=(",", ":"))


def node(key, category, description):
    return {
        "id": key, "role": description, "categories": ["biolink:" + category],
        "explanation": description + ".",
    }


NODES = {
    "chemical": node("chemical", "Drug", "Candidate drug"),
    "disease": node("disease", "Disease", "Disease predicted to be treated"),
    "regulator": node("regulator", "GeneOrGeneProduct", "Drug-engaged upstream gene or gene product"),
    "gene": node("gene", "GeneOrGeneProduct", "Disease-implicated gene or gene product"),
    "protein": node("protein", "Protein", "Protein physically engaged by the drug"),
    "organism": node("organism", "OrganismTaxon", "Organism asserted to cause the disease"),
    "process": node("process", "BiologicalProcess", "Biological process genetically associated with disease"),
    "family": node("family", "GeneFamily", "PANTHER family containing both distinct genes"),
}


def edge(key, subject, object_, predicate, description, *, exact=False, qualifiers=None,
         sources=None, either=False):
    predicate = "biolink:" + predicate
    closure = predicate_expansion_record([predicate])["expanded_predicates"]
    result = {
        "id": key, "subject": subject, "object": object_, "predicates": [predicate],
        "direction": "either" if either else "forward",
        "explanation": description + " The pinned descendant closure is " + ", ".join(closure) + ".",
    }
    if exact and len(closure) > 1:
        result["excluded_predicates"] = [p for p in closure if p != predicate]
        result["exclusion_rationale"] = (
            "This arm tests the exact stated relation; response, adverse, treatment, and "
            "other more-specific assertions would change its biological meaning."
        )
        result["explanation"] += (
            " All more-specific descendants are explicitly excluded, leaving only " + predicate + "."
        )
    if qualifiers:
        result["qualifiers"] = qualifiers
    if sources:
        result["source_constraints"] = sources
        result["explanation"] += (
            " At least one primary source must be " + ", ".join(sources) + "."
        )
    return result


def match(e):
    s, o, key = e["subject"], e["object"], e["id"]
    tail = "-" if e["direction"] == "either" else "->"
    text = (
        f"MATCH ({s}:{NODES[s]['categories'][0].split(':')[1]})"
        f"-[{key}:{{{{relationship_types:{key}}}}}]{tail}"
        f"({o}:{NODES[o]['categories'][0].split(':')[1]})"
        f" WHERE {key}.predicate IN {{{{predicates:{key}}}}}"
    )
    for qualifier, value in e.get("qualifiers", {}).items():
        text += f" AND {key}.{qualifier} " + (
            "IN " + literal(value) if isinstance(value, list) else "= " + literal(value)
        )
    if e.get("source_constraints"):
        text += (
            f" AND any(source IN {literal(e['source_constraints'])} "
            f"WHERE source IN coalesce({key}.primary_knowledge_sources,[]))"
        )
    return text


def constraint(key, description, expression=None, kind="other"):
    return {"id": key, "kind": kind, "expression": expression or description, "explanation": description}


def trapi(edges, nodes, constraints):
    query_edges = {}
    for e in edges:
        qe = {k: e[k] for k in ("subject", "object", "predicates")}
        if e.get("qualifiers"):
            values = {
                k: v if isinstance(v, list) else [v] for k, v in e["qualifiers"].items()
            }
            qe["qualifier_constraints"] = [
                {"qualifier_set": [
                    {"qualifier_type_id": "biolink:" + key, "qualifier_value": value}
                    for key, value in zip(values, choice)
                ]}
                for choice in itertools.product(*values.values())
            ]
        query_edges[e["id"]] = qe
    limitations = []
    for e in edges:
        if e.get("excluded_predicates"):
            limitations.append(
                e["id"] + ": discard exact predicates " + ", ".join(e["excluded_predicates"])
            )
        if e.get("source_constraints"):
            limitations.append(
                e["id"] + ": enforce primary-source membership in " + ", ".join(e["source_constraints"])
            )
        if e["direction"] == "either":
            limitations.append(e["id"] + ": union both stored edge orientations")
    limitations += [c["explanation"] for c in constraints]
    return {
        "expressibility": "partial" if limitations else "full",
        "query": {"message": {"query_graph": {
            "nodes": {n["id"]: {"categories": n["categories"]} for n in nodes},
            "edges": query_edges,
        }}},
        "limitations": "Outside TRAPI: " + "; ".join(limitations) if limitations else "",
    }


def add(key, family, title, hypothesis, edges, *, conditions=None, constraints=None,
        support="gene", prefix="", suffix="", features=None, score="medium", status="candidate",
        limitation=None):
    conditions, constraints = conditions or [], constraints or []
    nodes = [deepcopy(NODES[k]) for k in NODES if any(k in (e["subject"], e["object"]) for e in edges)]
    query = prefix + " ".join(match(e) for e in edges)
    if conditions:
        query += " AND " + " AND ".join("(" + c + ")" for c in conditions)
    query += suffix
    query += (
        f" RETURN chemical.id AS subject_id,disease.id AS object_id,"
        f"count(DISTINCT {support}) AS support_count"
    )
    text = "Predict treatment when " + "; ".join(e["explanation"] for e in edges)
    if constraints:
        text += " Additionally, " + " ".join(c["explanation"] for c in constraints)
    result = {
        "schema_version": "1.0", "rule_id": key, "family_id": family, "name": title,
        "status": status, "plain_language_rule": text, "hypothesis": hypothesis,
        "graph_pattern": {"nodes": nodes, "edges": edges, "constraints": constraints},
        "derived_features": features or [],
        "mechanism": {
            "score": score,
            "rationale": hypothesis + " The graph pattern is a hypothesis, not proof of clinical efficacy.",
        },
        "execution": {"cypher_template": query, "trapi": trapi(edges, nodes, constraints)},
        "limitations": [
            "Unknown predictions are unlabeled, not known negatives.",
            "Canonical graph identifiers are deduplicated; parallel evidence does not multiply gene support.",
            limitation or "Source assertions lack dose, exposure, clinical context, and experimental causal validation.",
        ],
    }
    validate_document(result, "rule-candidate.schema.json")
    CATALOG[key] = result
    return result


def effect(key, subject, object_, *, direction=None, signed=False, curated=False,
           full=False, aspect=ACTIVITY):
    qualifiers = {"qualified_predicate": "biolink:causes"}
    if direction:
        qualifiers["object_direction_qualifier"] = direction
    elif signed:
        qualifiers["object_direction_qualifier"] = ["increased", "decreased"]
    if direction or signed:
        qualifiers["object_aspect_qualifier"] = aspect
    return edge(
        key, subject, object_, "affects",
        subject.capitalize() + " causally affects " + object_ + (
            " in the " + direction + " direction for " + ", ".join(aspect) if direction
            else " with an explicit increased or decreased direction for " + ", ".join(aspect) if signed
            else " without requiring a direction"
        ),
        exact=not full, qualifiers=qualifiers, sources=CURATED if curated else None,
    )


def direct(full=False):
    return edge("direct", "chemical", "disease", "affects",
                "The candidate drug independently affects the same disease", exact=not full)


def causal():
    return edge("causal", "gene", "disease", "contributes_to",
                "The downstream gene causes or contributes to the disease")


def full_control(rule):
    """Otherwise-identical full-closure control for every explicitly filtered body arm."""
    result = deepcopy(rule)
    result["rule_id"] += "-full-closure"
    result["parent_rule_id"] = rule["rule_id"]
    result["name"] += " (Full Descendant Control)"
    result["status"] = "baseline"
    result["plain_language_rule"] = (
        "Use the same nodes, qualifiers, sources, and structural constraints as follows, "
        "but accept every pinned descendant on each body edge: "
        + rule["plain_language_rule"].split(" Additionally, ")[0]
    )
    for e in result["graph_pattern"]["edges"]:
        e.pop("excluded_predicates", None)
        e.pop("exclusion_rationale", None)
        e["explanation"] = e["explanation"].split(" All more-specific descendants")[0]
        e["explanation"] += " No predicate descendants are excluded in this control."
        if e.get("source_constraints") and "At least one primary source" not in e["explanation"]:
            e["explanation"] += " At least one primary source must be " + ", ".join(e["source_constraints"]) + "."
    result["plain_language_rule"] = (
        "Predict treatment when " + "; ".join(e["explanation"] for e in result["graph_pattern"]["edges"])
        + " " + " ".join(c["explanation"] for c in result["graph_pattern"]["constraints"])
    )
    result["execution"]["trapi"] = trapi(
        result["graph_pattern"]["edges"], result["graph_pattern"]["nodes"],
        result["graph_pattern"]["constraints"],
    )
    result["limitations"].append(
        "The full affects closure includes ameliorates_condition and is classified as treatment-using "
        "even if no such edge satisfies the other constraints in this graph."
    )
    validate_document(result, "rule-candidate.schema.json")
    CATALOG[result["rule_id"]] = result


def build():
    # New signed regulatory topology, not the earlier unsigned REGULATES bridge.
    family = "net-signed-regulatory-intervention"
    for key, drug_sign, bridge_sign, net in [
        ("inhibit-activator", "decreased", "increased", "decreasing"),
        ("activate-inhibitor", "increased", "decreased", "decreasing"),
        ("inhibit-inhibitor-control", "decreased", "decreased", "increasing"),
        ("activate-activator-control", "increased", "increased", "increasing"),
    ]:
        add(
            "r4-regulatory-" + key, family, key.replace("-", " ").title(),
            f"Two causal signed activity effects imply a net-{net} intervention on a disease-causal gene.",
            [direct(), effect("target", "chemical", "regulator", direction=drug_sign, curated=True),
             effect("bridge", "regulator", "gene", direction=bridge_sign), causal()],
            conditions=["regulator<>gene"],
            constraints=[constraint("distinct-genes", "The regulator and downstream disease gene must be different nodes.")],
            status="candidate" if net == "decreasing" else "rejected",
            limitation="Gene causes-or-contributes evidence does not establish that increased normal gene activity drives disease.",
        )
    for key, relation in [("net-decrease", "<>"), ("net-increase-control", "="), ("unsigned", None)]:
        conditions = ["regulator<>gene"]
        constraints = [constraint("distinct-genes", "The regulator and downstream disease gene must be different nodes.")]
        if relation:
            conditions.append(f"target.object_direction_qualifier {relation} bridge.object_direction_qualifier")
            constraints.append(constraint(
                "composed-sign",
                "The two signs must be opposite, giving net decrease." if relation == "<>"
                else "The two signs must agree, giving the net-increasing control.",
                kind="property",
            ))
        add(
            "r4-regulatory-" + key, family, "Signed Regulatory " + key.replace("-", " ").title(),
            "Composing two signed activity effects tests a regulatory intervention rather than unsigned network proximity.",
            [direct(), effect("target", "chemical", "regulator", signed=True, curated=True),
             effect("bridge", "regulator", "gene", signed=True), causal()],
            conditions=conditions, constraints=constraints,
            status="baseline" if relation is None else "candidate",
        )
    base = CATALOG["r4-regulatory-net-decrease"]
    for suffix, mode in [("no-direct", "direct"), ("no-curation", "curation"), ("physical-corroboration", "physical")]:
        es = deepcopy(base["graph_pattern"]["edges"])
        if mode == "direct":
            es = [e for e in es if e["id"] != "direct"]
        elif mode == "curation":
            es[1] = effect("target", "chemical", "regulator", signed=True)
        else:
            es.append(edge("physical", "regulator", "gene", "physically_interacts_with",
                           "A physical interaction independently connects the same two genes", either=True))
        add(
            "r4-regulatory-net-decrease-" + suffix, family, "Net Decrease " + suffix.replace("-", " ").title(),
            base["hypothesis"], es,
            conditions=["regulator<>gene", "target.object_direction_qualifier<>bridge.object_direction_qualifier"],
            constraints=deepcopy(base["graph_pattern"]["constraints"]),
        )

    family = "disease-produced-molecule-intervention"
    production = edge("production", "disease", "gene", "produces",
                      "The disease produces the molecular gene product")
    for direction in (None, "decreased", "increased"):
        for has_direct in (False, True):
            key = "r4-production-" + (direction or "unsigned") + ("-direct" if has_direct else "")
            add(
                key, family, "Disease Product " + (direction or "Unsigned").title(),
                "Curated pharmacologic action on a molecule produced by the disease may interrupt an overproduction mechanism.",
                ([direct()] if has_direct else [])
                + [production, effect("target", "chemical", "gene", direction=direction, curated=True)],
                status="rejected" if direction == "increased" else "candidate",
                limitation="Production may be a consequence or biomarker rather than a harmful driver; inhibition is not necessarily corrective.",
            )
    add(
        "r4-production-decreased-causal-loop", family, "Disease Product Causal Feedback Blockade",
        "A disease-produced molecule that also causes or contributes to that disease forms a candidate positive-feedback loop.",
        [production, effect("target", "chemical", "gene", direction="decreased", curated=True), causal()],
    )
    add(
        "r4-production-decreased-causal-loop-direct", family, "Direct Corroborated Product Feedback Blockade",
        "Independent direct drug-disease evidence may corroborate blockade of a disease-product causal feedback loop.",
        [direct(), production, effect("target", "chemical", "gene", direction="decreased", curated=True), causal()],
    )

    family = "genetically-associated-process-intervention"
    association = edge("association", "process", "disease", "genetic_association",
                       "The biological process has a forward genetic association to the disease",
                       sources=["infores:geneticskp"])
    for direction in (None, "decreased", "increased"):
        for has_direct in (False, True):
            add(
                "r4-process-" + (direction or "unsigned") + ("-direct" if has_direct else ""),
                family, "Genetically Implicated Process " + (direction or "Unsigned").title(),
                "Drug perturbation of a genetically disease-associated process supplies process-level evidence beyond a single target.",
                ([direct()] if has_direct else [])
                + [effect("perturbation", "chemical", "process", direction=direction), association],
                support="process",
                limitation="The genetic pathway association lacks a sign and may represent enrichment rather than a causal process effect.",
            )
    upstream = edge("upstream", "gene", "process", "acts_upstream_of_or_within",
                    "The pharmacologic target acts upstream of or within the genetically associated process")
    for has_direct in (False, True):
        add(
            "r4-process-curated-target" + ("-direct" if has_direct else ""),
            family, "Curated Target Within Genetically Implicated Process",
            "A curated drug target can intervene within a genetically implicated process without being a directly associated gene.",
            ([direct()] if has_direct else [])
            + [effect("target", "chemical", "gene", direction="decreased", curated=True), upstream, association],
            support="process",
        )
    add(
        "r4-process-dual-perturbation-direct", family, "Direct And Target-Mediated Process Convergence",
        "Independent drug-to-process and curated target-to-process arms corroborate a genetically implicated process.",
        [direct(), effect("perturbation", "chemical", "process", direction="decreased"),
         effect("target", "chemical", "gene", direction="decreased", curated=True), upstream, association],
        support="process",
    )

    family = "panther-family-disease-target-bridge"
    members = [
        edge("target_member", "regulator", "family", "member_of",
             "The drug target belongs to the PANTHER gene family", sources=["infores:panther"]),
        edge("disease_member", "gene", "family", "member_of",
             "The distinct disease-associated gene belongs to the same PANTHER family", sources=["infores:panther"]),
    ]
    for disease_leg in ("genetic", "causal"):
        ge = (edge("association", "gene", "disease", "gene_associated_with_condition",
                   "The family-related gene is genetically associated with the disease", sources=["infores:geneticskp"])
              if disease_leg == "genetic" else causal())
        for has_direct in (False, True):
            add(
                "r4-family-" + disease_leg + ("-direct" if has_direct else ""),
                family, "PANTHER Family " + disease_leg.title() + " Bridge",
                "A curated target in the same evolutionary gene family as a distinct disease gene may share disease-relevant function.",
                ([direct()] if has_direct else [])
                + [effect("target", "chemical", "regulator", direction="decreased", curated=True)]
                + deepcopy(members) + [ge],
                conditions=["regulator<>gene"],
                constraints=[constraint("distinct-genes", "The drug target and disease gene must be different nodes.")],
                support="family",
                limitation="Shared evolutionary family does not establish equivalent function, tissue expression, or regulatory direction.",
            )

    family = "enzyme-substrate-disease-context"
    substrate = edge("substrate", "gene", "chemical", "has_substrate",
                     "The disease-associated enzyme has the candidate drug as a substrate",
                     sources=["infores:chembl"])
    for disease_leg in ("genetic", "causal"):
        ge = (edge("association", "gene", "disease", "gene_associated_with_condition",
                   "The enzyme is genetically associated with the disease", sources=["infores:geneticskp"])
              if disease_leg == "genetic" else causal())
        for has_direct in (False, True):
            add(
                "r4-substrate-" + disease_leg + ("-direct" if has_direct else ""),
                family, "Enzyme Substrate " + disease_leg.title() + " Context",
                "A disease-linked enzyme substrate may provide metabolic intervention or replacement context.",
                ([direct()] if has_direct else []) + [substrate, ge],
                score="low",
                limitation="Metabolic processing can affect drug exposure without treating the enzyme-linked disease; this is an association diagnostic.",
            )

    family = "pathogen-directed-disease-intervention"
    infection = edge("infection", "organism", "disease", "causes",
                     "The organism is asserted to cause the disease")
    for direction in (None, "decreased", "increased"):
        pe = (effect("organism_effect", "chemical", "organism", direction=direction)
              if direction else edge("organism_effect", "chemical", "organism", "affects",
                                     "The drug affects the causal organism without a direction requirement", exact=True))
        add(
            "r4-pathogen-" + (direction or "unsigned"), family,
            "Causal Organism " + (direction or "Unsigned").title(),
            "Decreasing a disease-causing organism is compatible with anti-infective therapy, unlike unsigned association.",
            [pe, infection], support="organism",
            score="low" if direction is None else "medium",
        )
    add(
        "r4-pathogen-disruption", family, "Disruption Of A Causal Organism",
        "Disruption of a disease-causing organism may supply direct anti-infective action.",
        [edge("disruption", "chemical", "organism", "disrupts",
              "The drug disrupts the causal organism"), infection], support="organism",
    )
    product = edge("organism_product", "organism", "gene", "produces",
                   "The disease-causing organism produces the drug-targeted molecular product")
    for engagement in ("decreased", "physical"):
        target = (effect("target", "chemical", "gene", direction="decreased", curated=True)
                  if engagement == "decreased" else edge("target", "chemical", "gene", "directly_physically_interacts_with",
                                                        "The drug directly physically engages the organism-produced molecule"))
        for has_direct in (False, True):
            add(
                "r4-pathogen-product-" + engagement + ("-direct" if has_direct else ""),
                "pathogen-product-target-intervention", "Causal Organism Product " + engagement.title(),
                "Engagement of a molecule produced by a causal organism may interrupt infection through a molecular target.",
                ([direct()] if has_direct else []) + [target, product, infection],
                support="organism",
                limitation="An organism-produced molecule is not necessarily a virulence factor; host response and generic products may confound the path.",
            )

    # Explicit zero-capable diagnostic candidates preserve missing-leg hypotheses.
    add(
        "r4-protein-gene-identity", "protein-gene-identity-genetic-bridge",
        "Protein To Gene Identity Bridge",
        "An explicit protein-to-gene identity relation may connect pharmacologic protein targets to gene disease evidence.",
        [edge("target", "chemical", "protein", "directly_physically_interacts_with",
              "The drug directly physically engages the protein"),
         edge("identity", "protein", "gene", "gene_product_of", "The protein is a product of the gene"),
         edge("association", "gene", "disease", "gene_associated_with_condition",
              "The gene is genetically associated with disease")],
    )
    add(
        "r4-disease-expression-opposition", "explicit-disease-expression-reversal",
        "Opposing Disease And Drug Expression Effects",
        "Opposing signed effects of a disease and a drug on the same gene expression may support molecular reversal.",
        [effect("disease_effect", "disease", "gene", signed=True, aspect=["expression"]),
         effect("target", "chemical", "gene", signed=True, aspect=["expression"])],
        conditions=["target.object_direction_qualifier<>disease_effect.object_direction_qualifier"],
        constraints=[constraint("opposite-expression", "The disease and drug expression directions must be opposite.", kind="property")],
    )

    # This access path is a superset of each rematched raw target requirement.
    for rule in CATALOG.values():
        targets = [
            e for e in rule["graph_pattern"]["edges"]
            if e["subject"] == "chemical" and e["object"] in ("gene", "regulator")
            and e.get("source_constraints") == CURATED
            and e["predicates"] == ["biolink:affects"]
            and e.get("qualifiers", {}).get("qualified_predicate") == "biolink:causes"
        ]
        if not targets:
            continue
        target_node = targets[0]["object"]
        access = (
            f"MATCH (chemical:Drug)-[compact:MINER_R0004_CURATED_TARGET]->"
            f"({target_node}:GeneOrGeneProduct) "
            "WHERE compact.artifact_id='r0004-curated-causal-target-v1' "
            f"WITH DISTINCT chemical,{target_node} "
            "/* END CURATED ACCESS PATH */ "
        )
        rule["execution"]["cypher_template"] = access + rule["execution"]["cypher_template"]
        rule["derived_features"].append({
            "name": "complete curated causal drug-target access path",
            "definition": (
                "A stored Drug-to-GeneOrGeneProduct relationship exists for a causes-qualified "
                "member of the full affects descendant closure with ChEMBL, Guide to Pharmacology, "
                "or DrugCentral primary-source support."
            ),
            "inputs": [
                "The full pinned affects descendant closure on Drug-to-GeneOrGeneProduct edges",
                "Raw qualified_predicate and primary_knowledge_sources properties",
            ],
            "construction": (
                "Filter raw edges by causes qualification and any of the three sources, group "
                "by canonical endpoint pair, count distinct raw relationship identities, and "
                "merge one compact relationship per pair. Missing qualifiers or source arrays "
                "do not qualify. The rule uses only presence, then rematches raw edges with "
                "its recorded exact predicates, qualifiers, and sources. Removing the initial "
                "access-path MATCH and WITH before the marked comment gives the otherwise "
                "identical unmaterialized query."
            ),
            "formula": "compact presence iff count(distinct qualifying raw relationship)>0",
            "interpretation": (
                "This is a query acceleration, not a prediction threshold or an extra biological "
                "condition. Full-closure and exact-filtered target rules both rematch their own "
                "raw evidence. No training or held-out treatment labels define the access path."
            ),
            "neo4j_artifact_id": "r0004-curated-causal-target-v1",
        })
        rule["execution"]["trapi"]["expressibility"] = "partial"
        rule["execution"]["trapi"]["limitations"] += (
            "; the compact curated target access path is a Cypher optimization; "
            "TRAPI should retrieve the equivalent rematched raw target edge."
        )

    # Full closures are evaluated explicitly, not silently equated to exact predicates.
    for value in list(CATALOG.values()):
        if any(e.get("excluded_predicates") for e in value["graph_pattern"]["edges"]):
            full_control(value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--rule-id")
    args = parser.parse_args()
    build()
    if args.rule_id:
        print(json.dumps(CATALOG[args.rule_id], indent=2))
    elif args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for key, candidate in CATALOG.items():
            path = args.output_dir / (key + ".json")
            if path.exists():
                if json.loads(path.read_text()) != candidate:
                    raise RuntimeError("Refusing to replace a changed candidate: " + str(path))
                continue
            path.write_text(json.dumps(candidate, indent=2) + "\n")
        print(f"Generated {len(CATALOG)} validated candidate documents in {args.output_dir}")
    else:
        for key, candidate in CATALOG.items():
            print(key, candidate["family_id"])


if __name__ == "__main__":
    main()
