"""Generate new metabolic and directed functional-activity hypotheses."""

from copy import deepcopy
import json

from miner2049er.schema_validation import validate_document

from candidates import (
    CATALOG, HERE, NODES, add, build, causal, constraint, direct, edge, effect,
    full_control, node,
)
from variants import derive, genetic


def main():
    build()
    original = set(CATALOG)
    NODES["metabolite"] = node("metabolite", "ChemicalEntity", "Metabolite formed from the candidate drug")
    NODES["middle"] = node("middle", "GeneOrGeneProduct", "Intermediate gene or gene product in a directed activity-input chain")
    metabolism = edge(
        "metabolism", "chemical", "metabolite", "has_metabolite",
        "The candidate drug forms the molecular metabolite",
        sources=["infores:chembl"],
    )
    family = "active-metabolite-target-intervention"
    for disease_leg in ("genetic", "causal"):
        for has_direct in (False, True):
            for direction in ("decreased", "increased", None):
                key = (
                    "r4-metabolite-" + disease_leg + "-" + (direction or "unsigned")
                    + ("-direct" if has_direct else "")
                )
                add(
                    key, family,
                    "Metabolite " + (direction or "Unsigned").title() + " Target With " + disease_leg.title() + " Disease Evidence",
                    "A drug may act through a formed metabolite whose curated molecular pharmacology engages a disease-implicated target.",
                    ([direct()] if has_direct else [])
                    + [deepcopy(metabolism), effect("target", "metabolite", "gene", direction=direction, curated=True)]
                    + [genetic() if disease_leg == "genetic" else causal()],
                    conditions=["chemical<>metabolite"],
                    constraints=[constraint(
                        "distinct-molecules", "The candidate drug and its metabolite must be different canonical nodes.",
                    )],
                    limitation="A listed metabolite need not reach an effective concentration or have suitable exposure. Genetic or causal disease evidence does not establish the corrective pharmacologic sign.",
                    score="medium",
                )
    base_id = "r4-metabolite-genetic-decreased-direct"
    base = CATALOG[base_id]
    derive(
        base_id, "r4-metabolite-concordant-parent-target-direct",
        "Parent And Metabolite Converge On The Same Inhibited Genetic Target",
        "Concordant curated inhibition by both parent and metabolite is a distinct converging-arm test of the pharmacologic explanation.",
        edges=deepcopy(base["graph_pattern"]["edges"])
        + [effect("parent_target", "chemical", "gene", direction="decreased", curated=True)],
        conditions=["chemical<>metabolite"],
        constraints=deepcopy(base["graph_pattern"]["constraints"]),
    )

    family = "directed-causal-activity-input-intervention"
    prototype = CATALOG["r4-regulatory-net-decrease"]
    target = effect("target", "chemical", "regulator", direction="decreased", curated=True)
    distinct = constraint("distinct-genes", "The drug-target gene and disease-implicated gene must be distinct canonical nodes.")
    for disease_leg in ("genetic", "causal"):
        for has_direct in (False, True):
            key = "r4-activity-input-" + disease_leg + ("-direct" if has_direct else "")
            result = derive(
                prototype["rule_id"], key,
                "Curated Target Upstream In A Gene Ontology Activity Model With " + disease_leg.title() + " Disease Evidence",
                "An inhibited target whose modeled activity is an input to a disease-gene activity may intervene through a directed functional dependency rather than generic physical proximity.",
                edges=([direct()] if has_direct else []) + [
                    deepcopy(target),
                    edge("activity_input", "regulator", "gene", "is_input_of",
                         "The target-associated activity is a directed input to the disease-gene activity in a Gene Ontology causal activity model",
                         sources=["infores:go-cam"]),
                    genetic() if disease_leg == "genetic" else causal(),
                ],
                conditions=["regulator<>gene"], constraints=[distinct],
            )
            result["family_id"] = family
            result["limitations"].append(
                "The source models activities, but graph canonicalization places gene identifiers at the endpoints. "
                "An input edge is not a measured signed regulatory effect, and some source models are nonhuman."
            )
    base_id = "r4-activity-input-genetic-direct"
    for label, predicate, reverse in [
        ("reverse-control", "is_input_of", True),
        ("precedes", "precedes", False),
    ]:
        edges = deepcopy(CATALOG[base_id]["graph_pattern"]["edges"])
        subject, object_ = ("gene", "regulator") if reverse else ("regulator", "gene")
        edges[2] = edge(
            "activity_input", subject, object_, predicate,
            "The Gene Ontology activity-model connection follows the stated stored direction "
            + ("from the disease gene toward the drug target as a reverse-direction control" if reverse
               else "from the drug target toward the disease gene as a temporal-precedence relation"),
            sources=["infores:go-cam"],
        )
        derive(
            base_id, "r4-activity-input-" + label,
            "Gene Ontology Activity " + label.replace("-", " ").title(),
            "Changing functional direction or using temporal precedence tests which part of the activity-model connection supplies predictive evidence.",
            edges=edges, conditions=["regulator<>gene"], constraints=[distinct],
        )
    edges = deepcopy(CATALOG[base_id]["graph_pattern"]["edges"])
    edges = [e for e in edges if e["id"] != "activity_input"]
    edges += [
        edge("upstream_input", "regulator", "middle", "is_input_of",
             "The drug-target activity is an input to the intermediate gene activity",
             sources=["infores:go-cam"]),
        edge("downstream_input", "middle", "gene", "is_input_of",
             "The intermediate activity is an input to the genetically implicated disease-gene activity",
             sources=["infores:go-cam"]),
    ]
    derive(
        base_id, "r4-activity-input-two-bridges-direct",
        "Two Consecutive Gene Ontology Activity Inputs",
        "A four-edge drug-to-target-to-intermediate-to-disease-gene-to-disease chain tests a longer directed functional route with direct drug-disease corroboration.",
        edges=edges,
        conditions=["regulator<>gene", "middle<>regulator", "middle<>gene"],
        constraints=[constraint("three-distinct-genes", "The target, intermediate, and disease-associated genes must all be distinct canonical nodes.")],
    )
    for key in list(set(CATALOG) - original):
        full_control(CATALOG[key])
    output = HERE / "active-candidates"
    new = {key: value for key, value in CATALOG.items() if key not in original}
    for key, value in new.items():
        validate_document(value, "rule-candidate.schema.json")
        path = output / (key + ".json")
        if path.exists():
            if json.loads(path.read_text()) != value:
                raise RuntimeError("Refusing to change existing candidate " + key)
            continue
        path.write_text(json.dumps(value, indent=2) + "\n")
    print("Generated", len(new), "validated metabolic and directed activity candidates.")


if __name__ == "__main__":
    main()
