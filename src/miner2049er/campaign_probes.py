from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase, Query
from neo4j.exceptions import Neo4jError

from miner2049er.settings import ROOT

PROBES = {
    "direct_context_coverage": """
        MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(gene:Gene)
        MATCH (subject)-[effect:AFFECTS]->(gene)
        MATCH (gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(disease:Disease)
        WHERE effect.qualified_predicate = 'biolink:causes'
          AND effect.object_aspect_qualifier = 'activity_or_abundance'
          AND effect.object_direction_qualifier = 'decreased'
          AND disease.id STARTS WITH 'MONDO:'
        WITH DISTINCT subject, gene, disease, evidence
        RETURN count(*) AS path_rows,
               count(DISTINCT [subject.id, disease.id]) AS candidate_pairs,
               sum(CASE WHEN evidence._miner_direct_process_count > 0
                        THEN 1 ELSE 0 END) AS direct_process_rows,
               sum(CASE WHEN evidence._miner_shared_causal_process_count > 0
                        THEN 1 ELSE 0 END) AS shared_causal_process_rows,
               sum(CASE WHEN evidence._miner_direct_process_count > 0
                              AND evidence._miner_shared_causal_process_count > 0
                        THEN 1 ELSE 0 END) AS dual_process_rows,
               sum(CASE WHEN evidence._miner_bgee_anatomy_count >= 2
                        THEN 1 ELSE 0 END) AS multi_anatomy_rows,
               sum(CASE WHEN evidence._miner_phenotype_supported_anatomy_count > 0
                        THEN 1 ELSE 0 END) AS phenotype_anatomy_rows,
               sum(CASE WHEN evidence._miner_phenotype_process_count > 0
                        THEN 1 ELSE 0 END) AS phenotype_process_rows
    """,
    "physical_propagation_coverage": """
        MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target:Gene)
        MATCH (subject)-[effect:AFFECTS]->(target)
        MATCH (target)-[interaction:DIRECTLY_PHYSICALLY_INTERACTS_WITH]-(driver:Gene)
        MATCH (driver)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(disease:Disease)
        WHERE target <> driver
          AND effect.qualified_predicate = 'biolink:causes'
          AND effect.object_aspect_qualifier = 'activity_or_abundance'
          AND effect.object_direction_qualifier = 'decreased'
          AND disease.id STARTS WITH 'MONDO:'
        WITH DISTINCT subject, target, driver, disease, interaction, evidence
        RETURN count(*) AS path_rows,
               count(DISTINCT [subject.id, disease.id]) AS candidate_pairs,
               count(DISTINCT subject) AS drugs,
               count(DISTINCT disease) AS diseases,
               sum(CASE WHEN 'infores:signor'
                               IN coalesce(interaction.primary_knowledge_sources, [])
                        THEN 1 ELSE 0 END) AS signor_rows,
               sum(CASE WHEN EXISTS {
                              MATCH (target)-[:INVOLVED_IN]->(process)
                                    <-[:INVOLVED_IN]-(driver)
                              WHERE process._miner_gene_member_degree <= 100
                            }
                        THEN 1 ELSE 0 END) AS compact_process_rows,
               sum(CASE WHEN EXISTS {
                              MATCH (target)-[expression:EXPRESSED_IN]->
                                    (anatomy:AnatomicalEntity)
                                    <-[:LOCATED_IN|OCCURS_IN]-(disease)
                              WHERE 'infores:bgee'
                                    IN coalesce(
                                      expression.primary_knowledge_sources,
                                      []
                                    )
                                AND anatomy._miner_disease_location_degree <= 50
                            }
                        THEN 1 ELSE 0 END) AS specific_anatomy_rows
    """,
    "signed_propagation_coverage": """
        MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target:Gene)
        MATCH (subject)-[effect:AFFECTS]->(target)
        MATCH (target)-[regulation:REGULATES]->(driver:Gene)
        MATCH (driver)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(disease:Disease)
        WHERE target <> driver
          AND effect.qualified_predicate = 'biolink:causes'
          AND effect.object_aspect_qualifier = 'activity_or_abundance'
          AND effect.object_direction_qualifier = 'decreased'
          AND regulation.qualified_predicate = 'biolink:causes'
          AND regulation.object_direction_qualifier = 'upregulated'
          AND disease.id STARTS WITH 'MONDO:'
        WITH DISTINCT subject, target, driver, disease, regulation, evidence
        RETURN count(*) AS path_rows,
               count(DISTINCT [subject.id, disease.id]) AS candidate_pairs,
               count(DISTINCT subject) AS drugs,
               count(DISTINCT disease) AS diseases,
               sum(CASE WHEN 'infores:signor'
                               IN coalesce(regulation.primary_knowledge_sources, [])
                        THEN 1 ELSE 0 END) AS signor_rows,
               sum(CASE WHEN evidence._miner_disease_rank <= 3
                        THEN 1 ELSE 0 END) AS top_driver_rows,
               sum(CASE WHEN EXISTS {
                              MATCH (target)-[:INVOLVED_IN]->(process)
                                    <-[:INVOLVED_IN]-(driver)
                              WHERE process._miner_gene_member_degree <= 100
                            }
                        THEN 1 ELSE 0 END) AS compact_process_rows
    """,
    "multi_target_convergence_coverage": """
        MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(gene1:Gene)
        MATCH (subject)-[effect1:AFFECTS]->(gene1)
        MATCH (gene1)-[:MINER_GENE_DISEASE_EVIDENCE]->(disease:Disease)
        MATCH (subject)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(gene2:Gene)
        MATCH (subject)-[effect2:AFFECTS]->(gene2)
        MATCH (gene2)-[:MINER_GENE_DISEASE_EVIDENCE]->(disease)
        WHERE gene1.id < gene2.id
          AND effect1.qualified_predicate = 'biolink:causes'
          AND effect1.object_aspect_qualifier = 'activity_or_abundance'
          AND effect1.object_direction_qualifier = 'decreased'
          AND effect2.qualified_predicate = 'biolink:causes'
          AND effect2.object_aspect_qualifier = 'activity_or_abundance'
          AND effect2.object_direction_qualifier = 'decreased'
          AND disease.id STARTS WITH 'MONDO:'
        WITH DISTINCT subject, disease, gene1, gene2
        RETURN count(*) AS gene_pair_rows,
               count(DISTINCT [subject.id, disease.id]) AS candidate_pairs,
               count(DISTINCT subject) AS drugs,
               count(DISTINCT disease) AS diseases,
               sum(CASE WHEN EXISTS {
                              MATCH (gene1)-[:INVOLVED_IN]->(process)
                                    <-[:INVOLVED_IN]-(gene2)
                              WHERE process._miner_gene_member_degree <= 100
                            }
                        THEN 1 ELSE 0 END) AS compact_process_rows,
               sum(CASE WHEN EXISTS {
                              MATCH (gene1)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]-
                                    (gene2)
                            }
                        THEN 1 ELSE 0 END) AS interacting_gene_rows
    """,
    "phenotype_representation_inventory": """
        CALL () {
          MATCH (disease:Disease)-[:HAS_PHENOTYPE]->(phenotype)
          RETURN 'disease_has_phenotype' AS branch,
                 count(*) AS edge_rows,
                 count(DISTINCT disease) AS subjects,
                 count(DISTINCT phenotype) AS objects,
                 collect(DISTINCT split(phenotype.id, ':')[0])[0..20]
                   AS object_prefixes
          UNION ALL
          MATCH (gene:Gene)-[:GENE_ASSOCIATED_WITH_CONDITION]->(phenotype)
          WHERE phenotype:PhenotypicFeature
          RETURN 'gene_condition_phenotype' AS branch,
                 count(*) AS edge_rows,
                 count(DISTINCT gene) AS subjects,
                 count(DISTINCT phenotype) AS objects,
                 collect(DISTINCT split(phenotype.id, ':')[0])[0..20]
                   AS object_prefixes
          UNION ALL
          MATCH (gene:Gene)-[:GENE_ASSOCIATED_WITH_CONDITION]->(condition)
          WHERE condition:Disease
          RETURN 'gene_condition_disease' AS branch,
                 count(*) AS edge_rows,
                 count(DISTINCT gene) AS subjects,
                 count(DISTINCT condition) AS objects,
                 collect(DISTINCT split(condition.id, ':')[0])[0..20]
                   AS object_prefixes
        }
        RETURN branch, edge_rows, subjects, objects, object_prefixes
        ORDER BY branch
    """,
    "phenotype_bridge_coverage": """
        MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(gene:Gene)
        MATCH (subject)-[effect:AFFECTS]->(gene)
        MATCH (gene)-[:MINER_GENE_DISEASE_EVIDENCE]->(disease:Disease)
        WHERE effect.qualified_predicate = 'biolink:causes'
          AND effect.object_aspect_qualifier = 'activity_or_abundance'
          AND effect.object_direction_qualifier = 'decreased'
          AND disease.id STARTS WITH 'MONDO:'
        WITH DISTINCT subject, gene, disease
        RETURN count(*) AS base_path_rows,
               count(DISTINCT [subject.id, disease.id]) AS base_pairs,
               sum(CASE WHEN EXISTS {
                              MATCH (disease)-[:HAS_PHENOTYPE]->
                                    (phenotype:PhenotypicFeature)
                                    <-[:GENE_ASSOCIATED_WITH_CONDITION]-(gene)
                            }
                        THEN 1 ELSE 0 END) AS exact_rows,
               sum(CASE WHEN EXISTS {
                              MATCH (disease)-[:HAS_PHENOTYPE]->
                                    (disease_phenotype:PhenotypicFeature)
                              MATCH (gene)-[:GENE_ASSOCIATED_WITH_CONDITION]->
                                    (gene_phenotype:PhenotypicFeature)
                              MATCH (disease_phenotype)
                                    -[:SUBCLASS_OF*0..2]->(ancestor)
                                    <-[:SUBCLASS_OF*0..2]-(gene_phenotype)
                              WHERE ancestor:PhenotypicFeature
                                AND coalesce(
                                      ancestor._miner_phenotype_descendant_degree,
                                      0
                                    ) <= 500
                            }
                        THEN 1 ELSE 0 END) AS ontology_bridge_rows,
               sum(CASE WHEN EXISTS {
                              MATCH (disease)-[:HAS_PHENOTYPE]->
                                    (disease_phenotype:PhenotypicFeature)
                              MATCH (gene)-[:GENE_ASSOCIATED_WITH_CONDITION]->
                                    (gene_phenotype:PhenotypicFeature)
                              MATCH (disease_phenotype)
                                    -[:LOCATED_IN|OCCURS_IN]->
                                    (anatomy:AnatomicalEntity)
                                    <-[:LOCATED_IN|OCCURS_IN]-(gene_phenotype)
                              WHERE anatomy._miner_phenotype_location_degree <= 100
                            }
                        THEN 1 ELSE 0 END) AS anatomy_bridge_rows,
               sum(CASE WHEN EXISTS {
                              MATCH (disease)-[:HAS_PHENOTYPE]->
                                    (disease_phenotype:PhenotypicFeature)
                              MATCH (gene)-[:GENE_ASSOCIATED_WITH_CONDITION]->
                                    (gene_phenotype:PhenotypicFeature)
                              MATCH (disease_phenotype)-[:GENETIC_ASSOCIATION]-
                                    (process)<-[:GENETIC_ASSOCIATION]-
                                    (gene_phenotype)
                              WHERE process:BiologicalProcess
                                 OR process:MolecularActivity
                            }
                        THEN 1 ELSE 0 END) AS process_bridge_rows
    """,
    "ontology_transfer_coverage": """
        MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(gene:Gene)
        MATCH (subject)-[effect:AFFECTS]->(gene)
        MATCH (gene)-[:MINER_GENE_DISEASE_EVIDENCE]->(candidate:Disease)
        MATCH (subject)-[treatment:TREATS|AMELIORATES_CONDITION]->(anchor:Disease)
        MATCH (gene)-[:MINER_GENE_DISEASE_EVIDENCE]->(anchor)
        WHERE candidate <> anchor
          AND effect.qualified_predicate = 'biolink:causes'
          AND effect.object_aspect_qualifier = 'activity_or_abundance'
          AND effect.object_direction_qualifier = 'decreased'
          AND candidate.id STARTS WITH 'MONDO:'
          AND anchor.id STARTS WITH 'MONDO:'
          AND any(
            source IN coalesce(treatment.primary_knowledge_sources, [])
            WHERE NOT source IN ['infores:drug-repurposing-hub', 'infores:ttd']
          )
        WITH DISTINCT subject, gene, anchor, candidate,
             (
               EXISTS {
                 MATCH (anchor)-[:SUBCLASS_OF*1..3]->(candidate)
               }
               OR EXISTS {
                 MATCH (candidate)-[:SUBCLASS_OF*1..3]->(anchor)
               }
             ) AS direct_lineage,
             EXISTS {
               MATCH (anchor)-[:SUBCLASS_OF*1..3]->
                     (ancestor:Disease)
                     <-[:SUBCLASS_OF*1..3]-(candidate)
               WHERE coalesce(
                       ancestor._miner_disease_descendant_degree,
                       0
                     ) >= 2
                 AND coalesce(
                       ancestor._miner_disease_descendant_degree,
                       0
                     ) <= 200
             } AS specific_sibling,
             EXISTS {
               MATCH (anchor)-[:HAS_PHENOTYPE]->
                     (phenotype:PhenotypicFeature)
                     <-[:HAS_PHENOTYPE]-(candidate)
             } AS shared_phenotype,
             EXISTS {
               MATCH (anchor)-[:LOCATED_IN|OCCURS_IN]->
                     (anatomy:AnatomicalEntity)
                     <-[:LOCATED_IN|OCCURS_IN]-(candidate)
               WHERE anatomy._miner_disease_location_degree <= 50
             } AS shared_specific_anatomy
        RETURN count(*) AS transfer_rows,
               count(DISTINCT [subject.id, candidate.id]) AS candidate_pairs,
               sum(CASE WHEN direct_lineage
                        THEN 1 ELSE 0 END) AS direct_lineage_rows,
               sum(CASE WHEN specific_sibling
                        THEN 1 ELSE 0 END) AS specific_sibling_rows,
               sum(CASE WHEN shared_phenotype
                        THEN 1 ELSE 0 END) AS shared_phenotype_rows,
               sum(CASE WHEN shared_specific_anatomy
                        THEN 1 ELSE 0 END) AS shared_specific_anatomy_rows
    """,
    "negative_evidence_coverage": """
        MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(gene:Gene)
        MATCH (subject)-[effect:AFFECTS]->(gene)
        MATCH (gene)-[:MINER_GENE_DISEASE_EVIDENCE]->(disease:Disease)
        WHERE effect.qualified_predicate = 'biolink:causes'
          AND effect.object_aspect_qualifier = 'activity_or_abundance'
          AND effect.object_direction_qualifier = 'decreased'
          AND disease.id STARTS WITH 'MONDO:'
        WITH DISTINCT subject, gene, disease
        RETURN count(*) AS path_rows,
               count(DISTINCT [subject.id, disease.id]) AS candidate_pairs,
               sum(CASE WHEN EXISTS {
                              MATCH (subject)-[:CONTRAINDICATED_IN|
                                              EXACERBATES_CONDITION|
                                              CAUSES]->(disease)
                            }
                        THEN 1 ELSE 0 END) AS direct_adverse_rows,
               sum(CASE WHEN EXISTS {
                              MATCH (subject)-[:HAS_SIDE_EFFECT]->
                                    (:PhenotypicFeature)
                                    <-[:HAS_PHENOTYPE]-(disease)
                            }
                        THEN 1 ELSE 0 END) AS shared_adverse_phenotype_rows,
               sum(CASE WHEN EXISTS {
                              MATCH (subject)-[opposite:AFFECTS]->(gene)
                              WHERE opposite.qualified_predicate = 'biolink:causes'
                                AND opposite.object_aspect_qualifier =
                                      'activity_or_abundance'
                                AND opposite.object_direction_qualifier =
                                      'increased'
                            }
                        THEN 1 ELSE 0 END) AS bidirectional_effect_rows,
               sum(CASE WHEN coalesce(
                              disease._miner_disease_descendant_degree,
                              0
                            ) > 500
                        THEN 1 ELSE 0 END) AS ontology_hub_rows
    """,
}


def run_probe(session, name: str, timeout_seconds: int) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    started = time.monotonic()
    records = session.run(
        Query(PROBES[name], timeout=timeout_seconds)
    ).data()
    return {
        "name": name,
        "started_at": started_at.isoformat(),
        "status": "completed",
        "runtime_seconds": time.monotonic() - started,
        "rows": records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run named read-only coverage probes for the timed campaign"
    )
    parser.add_argument(
        "--probe",
        action="append",
        choices=sorted(PROBES),
        dest="probes",
    )
    parser.add_argument(
        "--neo4j-uri",
        default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
    )
    parser.add_argument(
        "--neo4j-password",
        default=os.environ.get("NEO4J_PASSWORD", "translator-local"),
    )
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "campaign-probes.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected = args.probes or list(PROBES)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "probes": [],
    }
    with (
        GraphDatabase.driver(
            args.neo4j_uri,
            auth=("neo4j", args.neo4j_password),
        ) as driver,
        driver.session(database="neo4j") as session,
    ):
        for name in selected:
            print(f"Running {name}", flush=True)
            try:
                result = run_probe(session, name, args.timeout_seconds)
            except Neo4jError as error:
                result = {
                    "name": name,
                    "started_at": datetime.now(UTC).isoformat(),
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                }
                print(result["error"], flush=True)
            report["probes"].append(result)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2) + "\n",
                encoding="utf-8",
            )
    print(f"Wrote {args.output}", flush=True)


if __name__ == "__main__":
    main()
