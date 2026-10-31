"""Render candidate documents only; official CLIs own all mining ledgers."""

from copy import deepcopy
import argparse
import json

from miner2049er.schema_validation import validate_document

from candidates import (
    CATALOG, HERE, add, constraint, direct, edge, effect, full_control, match, trapi,
)
from probe import RUN


IDENTITY = (
    "any(taxon IN coalesce(gene.in_taxon,[])+"
    "CASE WHEN gene.taxon IS NULL THEN [] ELSE [gene.taxon] END "
    "WHERE taxon IN [organism.id]+coalesce(organism.equivalent_identifiers,[]))"
)
IDENTITY_EXPLANATION = (
    "The target gene or gene product must have a raw taxon string or an entry in its "
    "raw in_taxon string array exactly equal to the disease-causing organism's canonical "
    "identifier or an entry in its equivalent_identifiers array. Missing values supply "
    "empty lists; comparisons are exact and case-sensitive, with no inferred taxonomy, "
    "prefix conversion, ancestry expansion, or name matching. Either raw taxonomy field "
    "can establish identity. Duplicate strings do not multiply support, and conflicting "
    "annotations are not treated as independent corroboration."
)
LIMITATIONS = [
    "Unknown predictions are unlabeled, not known negatives.",
    "The raw node taxonomy fields do not provide annotation-level primary-source provenance.",
    "Taxonomic membership does not establish target essentiality, exposure, inhibition in an organism, or clinical efficacy.",
    "Organism-causes-disease assertions can be broad or text-mined and do not prove a pathogen-specific clinical mechanism.",
    "One node in the complete graph has disagreeing taxon and in_taxon fields; the existential identity rule can accept either assertion.",
    "Support counts distinct organism nodes per canonical drug-disease output pair, not target edges, aliases, or source occurrences.",
]


def build():
    infection = edge(
        "infection", "organism", "disease", "causes",
        "The same taxonomically identified organism is asserted to cause the disease",
    )
    product = edge(
        "organism_product", "organism", "gene", "produces",
        "The disease-causing organism is also asserted to produce the exact drug target",
    )
    for direction in ("unsigned", "decreased", "increased"):
        target = effect(
            "target", "chemical", "gene", curated=True,
            signed=direction == "unsigned",
            direction=None if direction == "unsigned" else direction,
        )
        variants = ("", "-direct", "-product", "-two-targets") if direction == "decreased" else ("",)
        for suffix in variants:
            key = "r4-taxon-target-" + direction + suffix
            edges = [target, infection]
            if suffix == "-direct":
                edges.append(direct())
            if suffix == "-product":
                edges.append(product)
            constraints = [
                constraint("target-organism-identity", IDENTITY_EXPLANATION, IDENTITY, "property")
            ]
            if suffix == "-two-targets":
                constraints.append(constraint(
                    "two-targets-same-organism",
                    "For the same drug, organism, and disease, at least two distinct canonical "
                    "gene-or-gene-product target identifiers must qualify. Targets assigned to "
                    "different organisms cannot be pooled to meet this requirement.",
                    "count(DISTINCT gene.id)>=2", "cardinality",
                ))
            rule = add(
                key, "taxon-identified-molecular-intervention",
                "Taxon-Identified Target " + (direction + suffix).replace("-", " ").title(),
                "Explicit target taxonomic identity may connect a pharmacologic molecular effect to a disease-causing organism without relying on an ambiguous production assertion.",
                deepcopy(edges),
                constraints=constraints,
                support="organism",
                status="rejected" if direction == "increased" else "candidate",
            )
            rule["limitations"] = LIMITATIONS.copy()
            query = (
                match(target)
                + " WITH gene,collect(DISTINCT chemical) AS chemicals "
                + "UNWIND coalesce(gene.in_taxon,[])+"
                + "CASE WHEN gene.taxon IS NULL THEN [] ELSE [gene.taxon] END AS taxon "
                + "WITH taxon,collect(DISTINCT {gene:gene,chemicals:chemicals}) AS target_groups "
                + "MATCH (organism:OrganismTaxon) "
                + "WHERE taxon IN [organism.id]+coalesce(organism.equivalent_identifiers,[]) "
                + match(infection)
                + " UNWIND target_groups AS target_group "
                + "UNWIND target_group.chemicals AS chemical "
                + "WITH chemical,target_group.gene AS gene,organism,disease "
            )
            if suffix == "-direct":
                query += match(edges[-1])
            if suffix == "-product":
                query += match(product)
            if suffix == "-two-targets":
                query += (
                    " WITH chemical,organism,disease,count(DISTINCT gene.id) AS targets "
                    "WHERE targets>=2"
                )
            query += (
                " RETURN chemical.id AS subject_id,disease.id AS object_id,"
                "count(DISTINCT organism) AS support_count"
            )
            rule["execution"]["cypher_template"] = query
            rule["plain_language_rule"] += (
                " Group qualifying raw drug-target evidence by target before matching organisms; "
                "this only removes duplicate access paths and does not change which drugs qualify."
            )
            rule["execution"]["trapi"]["limitations"] += (
                " Cypher groups targets by explicit taxon strings before the organism join; "
                "this is query-local deduplication only, with no stored feature or prediction threshold."
            )
            for node in rule["graph_pattern"]["nodes"]:
                if node["id"] == "gene":
                    node["role"] = "Pharmacologic gene or gene-product target carrying raw taxonomic identifiers"
                    node["explanation"] = node["role"] + "."
            full_control(rule)
            for document in (rule, CATALOG[key + "-full-closure"]):
                document["execution"]["trapi"] = trapi(
                    document["graph_pattern"]["edges"],
                    document["graph_pattern"]["nodes"],
                    document["graph_pattern"]["constraints"],
                )
                document["execution"]["trapi"]["limitations"] += (
                    " The taxonomy relation is a raw node-property identity join, not an in_taxon "
                    "graph edge. Retrieve the drug-target and organism-disease components separately "
                    "if the provider rejects disconnected query graphs, then apply the exact "
                    "cross-result property join. Do not substitute a nonexistent in_taxon edge."
                )
                validate_document(document, "rule-candidate.schema.json")

    diagnostic = add(
        "r4-taxon-explicit-edge-diagnostic", "taxonomic-edge-availability-diagnostic",
        "Explicit Molecular Taxonomy Edge Diagnostic",
        "An explicit in_taxon graph edge would provide a directly queryable taxonomic link; its absence must remain distinguishable from the available node-property representation.",
        [
            edge("target", "chemical", "gene", "directly_physically_interacts_with",
                 "The drug directly physically engages a molecular target"),
            edge("taxonomy", "gene", "organism", "in_taxon",
                 "The molecular target has an explicit graph-edge taxonomic assignment to the organism"),
            infection,
        ],
        support="organism", score="low",
    )
    diagnostic["limitations"] = LIMITATIONS[:4] + [
        "This diagnostic requires a real in_taxon relationship and does not read the similarly named raw node property.",
        "Support counts distinct organism nodes; physical engagement alone does not establish inhibition.",
    ]
    validate_document(diagnostic, "rule-candidate.schema.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append")
    parser.add_argument("--refresh-unrecorded", action="store_true")
    args = parser.parse_args()
    build()
    output = HERE / "active-candidates"
    recorded = {
        json.loads(line)["rule_id"]
        for line in (RUN / "rules.jsonl").open() if line.strip()
    }
    for key, document in CATALOG.items():
        if args.only and key not in args.only:
            continue
        path = output / (key + ".json")
        if key in recorded:
            raise RuntimeError("Refusing to modify a recorded candidate: " + key)
        if path.exists() and not args.refresh_unrecorded:
            raise RuntimeError("Refusing to overwrite an existing candidate: " + key)
        path.write_text(json.dumps(document, indent=2) + "\n")
        print(key)


if __name__ == "__main__":
    main()
