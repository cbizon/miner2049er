from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase, Query

from miner2049er.settings import ROOT

FEATURE_QUERIES = (
    (
        "chemical_affects_activity_or_abundance_decreased_degree",
        """
        MATCH (subject:ChemicalEntity)-[effect:AFFECTS]->(gene:Gene)
        WHERE effect.qualified_predicate = 'biolink:causes'
          AND effect.object_aspect_qualifier = 'activity_or_abundance'
          AND effect.object_direction_qualifier = 'decreased'
        WITH subject, count(DISTINCT gene) AS degree
        SET subject._miner_affects_aa_decreased_gene_degree = degree
        RETURN count(subject) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "disease_phenotype_degree",
        """
        MATCH (disease:Disease)-[:HAS_PHENOTYPE]->(phenotype:PhenotypicFeature)
        WITH disease, count(DISTINCT phenotype) AS degree
        SET disease._miner_phenotype_degree = degree
        RETURN count(disease) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "phenotype_descendant_degree",
        """
        MATCH (child:PhenotypicFeature)-[:SUBCLASS_OF]->(phenotype:PhenotypicFeature)
        WITH phenotype, count(DISTINCT child) AS degree
        SET phenotype._miner_phenotype_descendant_degree = degree
        RETURN count(phenotype) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "phenotype_disease_member_degree",
        """
        MATCH (disease:Disease)-[:HAS_PHENOTYPE]->(phenotype:PhenotypicFeature)
        WITH phenotype, count(DISTINCT disease) AS degree
        SET phenotype._miner_disease_member_degree = degree
        RETURN count(phenotype) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "phenotype_side_effect_drug_degree",
        """
        MATCH (drug:Drug)-[:HAS_SIDE_EFFECT]->(phenotype:PhenotypicFeature)
        WITH phenotype, count(DISTINCT drug) AS degree
        SET phenotype._miner_side_effect_drug_degree = degree
        RETURN count(phenotype) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "drug_side_effect_profile_degree",
        """
        MATCH (drug:Drug)-[:HAS_SIDE_EFFECT]->(phenotype:PhenotypicFeature)
        WITH drug, count(DISTINCT phenotype) AS degree
        SET drug._miner_side_effect_profile_degree = degree
        RETURN count(drug) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "disease_gene_degree",
        """
        MATCH (gene:Gene)-[:GENE_ASSOCIATED_WITH_CONDITION]->(disease:Disease)
        WITH disease, count(DISTINCT gene) AS degree
        SET disease._miner_gene_association_degree = degree
        RETURN count(disease) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "chemical_class_drug_member_degree",
        """
        MATCH (drug:Drug)-[:SUBCLASS_OF]->(chemical_class)
        WITH chemical_class, count(DISTINCT drug) AS degree
        SET chemical_class._miner_drug_member_degree = degree
        RETURN count(chemical_class) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "process_gene_member_degree",
        """
        MATCH (gene:Gene)-[:INVOLVED_IN]->(process)
        WITH process, count(DISTINCT gene) AS degree
        SET process._miner_gene_member_degree = degree
        RETURN count(process) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "molecular_activity_gene_enable_degree",
        """
        MATCH (gene:Gene)-[:ENABLES]->(activity:MolecularActivity)
        WITH activity, count(DISTINCT gene) AS degree
        SET activity._miner_gene_enable_degree = degree
        RETURN count(activity) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "cellular_component_gene_member_degree",
        """
        MATCH (gene:Gene)-[:PART_OF]->(component:CellularComponent)
        WITH component, count(DISTINCT gene) AS degree
        SET component._miner_component_gene_member_degree = degree
        RETURN count(component) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "cellular_component_active_gene_degree",
        """
        MATCH (gene:Gene)-[:ACTIVE_IN]->(component:CellularComponent)
        WITH component, count(DISTINCT gene) AS degree
        SET component._miner_component_active_gene_degree = degree
        RETURN count(component) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "gene_family_member_degree",
        """
        MATCH (gene:Gene)-[:MEMBER_OF]->(family:GeneFamily)
        WITH family, count(DISTINCT gene) AS degree
        SET family._miner_gene_family_member_degree = degree
        RETURN count(family) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "process_disease_genetic_association_degree",
        """
        MATCH (disease:Disease)-[:GENETIC_ASSOCIATION]-(process)
        WHERE process:BiologicalProcess OR process:MolecularActivity
        WITH process, count(DISTINCT disease) AS degree
        SET process._miner_disease_genetic_association_degree = degree
        RETURN count(process) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "process_phenotype_genetic_association_degree",
        """
        MATCH (phenotype:PhenotypicFeature)-[:GENETIC_ASSOCIATION]-(process)
        WHERE process:BiologicalProcess OR process:MolecularActivity
        WITH process, count(DISTINCT phenotype) AS degree
        SET process._miner_phenotype_genetic_association_degree = degree
        RETURN count(process) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "anatomy_disease_location_degree",
        """
        MATCH (disease:Disease)-[:LOCATED_IN|OCCURS_IN]->(anatomy:AnatomicalEntity)
        WITH anatomy, count(DISTINCT disease) AS degree
        SET anatomy._miner_disease_location_degree = degree
        RETURN count(anatomy) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "anatomy_human_gene_expression_degree",
        """
        MATCH (gene:Gene)-[expression:EXPRESSED_IN]->(anatomy:AnatomicalEntity)
        WHERE 'NCBITaxon:9606' IN coalesce(gene.in_taxon, [])
          AND 'infores:bgee' IN coalesce(expression.primary_knowledge_sources, [])
        WITH anatomy, count(DISTINCT gene) AS degree
        SET anatomy._miner_human_gene_expression_degree = degree
        RETURN count(anatomy) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "cell_human_gene_expression_degree",
        """
        MATCH (gene:Gene)-[expression:EXPRESSED_IN]->(cell:Cell)
        WHERE 'infores:bgee' IN
              coalesce(expression.primary_knowledge_sources, [])
        WITH cell, count(DISTINCT gene) AS degree
        SET cell._miner_human_gene_expression_degree = degree
        RETURN count(cell) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "anatomy_phenotype_location_degree",
        """
        MATCH (phenotype:PhenotypicFeature)-[:LOCATED_IN|OCCURS_IN]->
              (anatomy:AnatomicalEntity)
        WITH anatomy, count(DISTINCT phenotype) AS degree
        SET anatomy._miner_phenotype_location_degree = degree
        RETURN count(anatomy) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "disease_descendant_degree",
        """
        MATCH (child:Disease)-[:SUBCLASS_OF]->(disease:Disease)
        WITH disease, count(DISTINCT child) AS degree
        SET disease._miner_disease_descendant_degree = degree
        RETURN count(disease) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "disease_superclass_degree",
        """
        MATCH (disease:Disease)-[:SUBCLASS_OF]->(parent:Disease)
        WITH disease, count(DISTINCT parent) AS degree
        SET disease._miner_disease_superclass_degree = degree
        RETURN count(disease) AS entities_updated,
               min(degree) AS min_degree,
               max(degree) AS max_degree
        """,
    ),
    (
        "disease_process_support",
        """
        MATCH (gene:Gene)-[:GENE_ASSOCIATED_WITH_CONDITION]->(disease:Disease)
        MATCH (gene)-[:INVOLVED_IN]->(process)
        WITH disease, process, count(DISTINCT gene) AS gene_count
        MERGE (disease)-[support:MINER_DISEASE_PROCESS_SUPPORT]->(process)
        SET support.gene_count = gene_count
        RETURN count(support) AS relationships_updated,
               min(gene_count) AS min_gene_count,
               max(gene_count) AS max_gene_count
        """,
    ),
    (
        "gene_disease_evidence",
        """
        MATCH (gene:Gene)-[causal:CAUSES]->(disease:Disease)
        WITH gene, disease, collect(causal) AS causal_edges
        CALL (gene, disease) {
          MATCH (gene)-[relation]-(disease)
          UNWIND CASE
            WHEN size(coalesce(relation.primary_knowledge_sources, [])) = 0
            THEN [NULL]
            ELSE relation.primary_knowledge_sources
          END AS source
          RETURN count(DISTINCT type(relation)) AS direct_relation_type_count,
                 count(DISTINCT source) AS primary_source_count,
                 count(
                   DISTINCT CASE
                     WHEN source <> 'infores:semmeddb' THEN source
                   END
                 ) AS non_semmed_primary_source_count
        }
        CALL (gene, disease) {
          OPTIONAL MATCH
            (disease)-[support:MINER_DISEASE_PROCESS_SUPPORT]->(process)
            <-[:INVOLVED_IN]-(gene)
          WHERE support.gene_count >= 2
            AND support.gene_count <= 20
            AND process._miner_gene_member_degree <= 100
          RETURN count(DISTINCT process) AS compact_process_count
        }
        WITH gene, disease,
             reduce(
               publication_count = 0,
               causal_edge IN causal_edges |
               publication_count + size(coalesce(causal_edge.publications, []))
             ) AS causal_publication_count,
             direct_relation_type_count,
             primary_source_count,
             non_semmed_primary_source_count,
             compact_process_count
        MERGE (gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(disease)
        SET evidence._miner_causal_publication_count = causal_publication_count,
            evidence._miner_direct_relation_type_count = direct_relation_type_count,
            evidence._miner_primary_source_count = primary_source_count,
            evidence._miner_non_semmed_primary_source_count =
              non_semmed_primary_source_count,
            evidence._miner_compact_process_count = compact_process_count
        RETURN count(evidence) AS relationships_updated,
               min(causal_publication_count) AS min_publications,
               max(causal_publication_count) AS max_publications
        """,
    ),
    (
        "gene_disease_evidence_gene_marginals",
        """
        MATCH (gene:Gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(:Disease)
        WITH gene,
             count(evidence) AS disease_degree,
             sum(evidence._miner_causal_publication_count) AS publication_total
        MATCH (gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(:Disease)
        SET evidence._miner_gene_causal_disease_degree = disease_degree,
            evidence._miner_gene_causal_publication_total = publication_total
        RETURN count(evidence) AS relationships_updated,
               min(disease_degree) AS min_disease_degree,
               max(disease_degree) AS max_disease_degree
        """,
    ),
    (
        "gene_disease_evidence_disease_marginals",
        """
        MATCH (:Gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(disease:Disease)
        WITH disease,
             count(evidence) AS gene_degree,
             sum(evidence._miner_causal_publication_count) AS publication_total
        MATCH (:Gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(disease)
        SET evidence._miner_disease_causal_gene_degree = gene_degree,
            evidence._miner_disease_causal_publication_total = publication_total
        RETURN count(evidence) AS relationships_updated,
               min(gene_degree) AS min_gene_degree,
               max(gene_degree) AS max_gene_degree
        """,
    ),
    (
        "gene_disease_evidence_scores",
        """
        MATCH ()-[evidence:MINER_GENE_DISEASE_EVIDENCE]->()
        WITH sum(evidence._miner_causal_publication_count) AS publication_total,
             count(DISTINCT endNode(evidence)) AS disease_count
        MATCH ()-[evidence:MINER_GENE_DISEASE_EVIDENCE]->()
        WITH evidence, publication_total, disease_count,
             toFloat(evidence._miner_causal_publication_count) AS pair_publications,
             toFloat(evidence._miner_gene_causal_publication_total)
               AS gene_publications,
             toFloat(evidence._miner_disease_causal_publication_total)
               AS disease_publications
        WITH evidence, publication_total, disease_count, pair_publications,
             log(
               pair_publications * publication_total /
               (gene_publications * disease_publications)
             ) AS publication_pmi
        SET evidence._miner_causal_publication_share =
              pair_publications /
              toFloat(evidence._miner_gene_causal_publication_total),
            evidence._miner_causal_publication_npmi =
              publication_pmi / (-log(pair_publications / publication_total)),
            evidence._miner_relevance_score =
              publication_pmi / (-log(pair_publications / publication_total)) +
              log(
                1 +
                toFloat(evidence._miner_non_semmed_primary_source_count)
              ) +
              0.25 * log(
                1 + toFloat(evidence._miner_direct_relation_type_count)
              ) +
              0.10 * log(
                1 + toFloat(evidence._miner_compact_process_count)
              )
        RETURN count(evidence) AS relationships_updated,
               publication_total,
               disease_count,
               min(evidence._miner_causal_publication_npmi) AS min_npmi,
               max(evidence._miner_causal_publication_npmi) AS max_npmi,
               min(evidence._miner_relevance_score) AS min_relevance_score,
               max(evidence._miner_relevance_score) AS max_relevance_score
        """,
    ),
    (
        "gene_disease_anatomy_context",
        """
        MATCH (gene:Gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(disease:Disease)
        CALL (gene, disease) {
          OPTIONAL MATCH
            (gene)-[expression:EXPRESSED_IN]->(anatomy:AnatomicalEntity)
            <-[location:LOCATED_IN|OCCURS_IN]-(disease)
          WHERE 'NCBITaxon:9606' IN coalesce(gene.in_taxon, [])
            AND 'infores:bgee' IN coalesce(expression.primary_knowledge_sources, [])
          WITH [item IN collect(
                 DISTINCT {
                   anatomy: anatomy,
                   location: location
                 }
               ) WHERE item.anatomy IS NOT NULL] AS overlaps
          RETURN size(overlaps) AS bgee_anatomy_count,
                 CASE
                   WHEN size(overlaps) = 0 THEN NULL
                   ELSE reduce(
                     minimum = 2147483647,
                     item IN overlaps |
                     CASE
                       WHEN item.anatomy._miner_disease_location_degree < minimum
                       THEN item.anatomy._miner_disease_location_degree
                       ELSE minimum
                     END
                   )
                 END AS min_anatomy_disease_degree,
                 CASE
                   WHEN size(overlaps) = 0 THEN NULL
                   ELSE reduce(
                     minimum = 2147483647,
                     item IN overlaps |
                     CASE
                       WHEN item.anatomy._miner_human_gene_expression_degree < minimum
                       THEN item.anatomy._miner_human_gene_expression_degree
                       ELSE minimum
                     END
                   )
                 END AS min_anatomy_gene_degree,
                 reduce(
                   publication_count = 0,
                   item IN overlaps |
                   publication_count +
                   size(coalesce(item.location.publications, []))
                 ) AS disease_anatomy_publication_count
        }
        CALL (gene, disease) {
          OPTIONAL MATCH
            (gene)-[expression:EXPRESSED_IN]->(anatomy:AnatomicalEntity)
            <-[:LOCATED_IN|OCCURS_IN]-(disease)
          WHERE 'NCBITaxon:9606' IN coalesce(gene.in_taxon, [])
            AND 'infores:bgee' IN coalesce(expression.primary_knowledge_sources, [])
            AND EXISTS {
              MATCH (disease)-[:HAS_PHENOTYPE]->(:PhenotypicFeature)
                    -[:LOCATED_IN|OCCURS_IN]->(anatomy)
            }
          RETURN count(DISTINCT anatomy) AS phenotype_supported_anatomy_count
        }
        SET evidence._miner_bgee_anatomy_count = bgee_anatomy_count,
            evidence._miner_min_anatomy_disease_degree =
              min_anatomy_disease_degree,
            evidence._miner_min_anatomy_gene_degree = min_anatomy_gene_degree,
            evidence._miner_disease_anatomy_publication_count =
              disease_anatomy_publication_count,
            evidence._miner_phenotype_supported_anatomy_count =
              phenotype_supported_anatomy_count
        RETURN count(evidence) AS relationships_updated,
               min(bgee_anatomy_count) AS min_bgee_anatomy_count,
               max(bgee_anatomy_count) AS max_bgee_anatomy_count,
               max(phenotype_supported_anatomy_count)
                 AS max_phenotype_supported_anatomy_count
        """,
    ),
    (
        "gene_disease_process_context",
        """
        MATCH (gene:Gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(disease:Disease)
        CALL (gene, disease) {
          OPTIONAL MATCH (gene)-[:INVOLVED_IN]->(process)
          WHERE (process:BiologicalProcess OR process:MolecularActivity)
            AND EXISTS {
              MATCH (disease)-[:GENETIC_ASSOCIATION]-(process)
            }
          RETURN count(DISTINCT process) AS direct_process_count,
                 min(process._miner_disease_genetic_association_degree)
                   AS min_direct_process_disease_degree,
                 min(process._miner_gene_member_degree)
                   AS min_direct_process_gene_degree
        }
        CALL (gene, disease) {
          OPTIONAL MATCH
            (disease)-[:HAS_PHENOTYPE]->(phenotype:PhenotypicFeature)
            -[:GENETIC_ASSOCIATION]-(process)<-[:INVOLVED_IN]-(gene)
          WHERE process:BiologicalProcess OR process:MolecularActivity
          RETURN count(DISTINCT process) AS phenotype_process_count,
                 count(DISTINCT phenotype) AS supporting_phenotype_count,
                 min(process._miner_phenotype_genetic_association_degree)
                   AS min_phenotype_process_degree,
                 min(process._miner_gene_member_degree)
                   AS min_phenotype_process_gene_degree
        }
        CALL (gene, disease) {
          OPTIONAL MATCH
            (gene)-[:INVOLVED_IN]->(process)<-[:INVOLVED_IN]-(other_gene:Gene)
            -[:CAUSES]->(disease)
          WHERE other_gene <> gene
          RETURN count(DISTINCT process) AS shared_causal_process_count,
                 count(DISTINCT other_gene) AS shared_process_causal_gene_count
        }
        SET evidence._miner_direct_process_count = direct_process_count,
            evidence._miner_min_direct_process_disease_degree =
              min_direct_process_disease_degree,
            evidence._miner_min_direct_process_gene_degree =
              min_direct_process_gene_degree,
            evidence._miner_phenotype_process_count = phenotype_process_count,
            evidence._miner_supporting_phenotype_count =
              supporting_phenotype_count,
            evidence._miner_min_phenotype_process_degree =
              min_phenotype_process_degree,
            evidence._miner_min_phenotype_process_gene_degree =
              min_phenotype_process_gene_degree,
            evidence._miner_shared_causal_process_count =
              shared_causal_process_count,
            evidence._miner_shared_process_causal_gene_count =
              shared_process_causal_gene_count
        RETURN count(evidence) AS relationships_updated,
               max(direct_process_count) AS max_direct_process_count,
               max(phenotype_process_count) AS max_phenotype_process_count,
               max(shared_process_causal_gene_count)
                 AS max_shared_process_causal_gene_count
        """,
    ),
    (
        "gene_disease_evidence_ranks",
        """
        MATCH (:Gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(disease:Disease)
        WITH disease, evidence
        ORDER BY disease.id,
                 evidence._miner_relevance_score DESC,
                 evidence._miner_causal_publication_count DESC
        WITH disease, collect(evidence) AS ranked_evidence
        UNWIND range(0, size(ranked_evidence) - 1) AS rank_index
        WITH ranked_evidence[rank_index] AS evidence, rank_index
        SET evidence._miner_disease_rank = rank_index + 1
        RETURN count(evidence) AS relationships_updated,
               min(evidence._miner_disease_rank) AS min_rank,
               max(evidence._miner_disease_rank) AS max_rank
        """,
    ),
)

CLEAR_QUERIES = (
    (
        "relationships",
        """
        MATCH ()-[support:MINER_DISEASE_PROCESS_SUPPORT|MINER_GENE_DISEASE_EVIDENCE]->()
        DELETE support
        RETURN count(support) AS deleted_relationships
        """,
    ),
    (
        "properties",
        """
        MATCH (entity)
        WHERE entity._miner_affects_aa_decreased_gene_degree IS NOT NULL
           OR entity._miner_direct_gene_target_degree IS NOT NULL
           OR entity._miner_phenotype_degree IS NOT NULL
           OR entity._miner_phenotype_descendant_degree IS NOT NULL
           OR entity._miner_disease_member_degree IS NOT NULL
           OR entity._miner_side_effect_drug_degree IS NOT NULL
           OR entity._miner_side_effect_profile_degree IS NOT NULL
           OR entity._miner_condition_gene_degree IS NOT NULL
           OR entity._miner_gene_association_degree IS NOT NULL
           OR entity._miner_drug_member_degree IS NOT NULL
           OR entity._miner_gene_member_degree IS NOT NULL
           OR entity._miner_gene_enable_degree IS NOT NULL
           OR entity._miner_component_gene_member_degree IS NOT NULL
           OR entity._miner_component_active_gene_degree IS NOT NULL
           OR entity._miner_gene_family_member_degree IS NOT NULL
           OR entity._miner_disease_genetic_association_degree IS NOT NULL
           OR entity._miner_phenotype_genetic_association_degree IS NOT NULL
           OR entity._miner_disease_location_degree IS NOT NULL
           OR entity._miner_human_gene_expression_degree IS NOT NULL
           OR entity._miner_phenotype_location_degree IS NOT NULL
           OR entity._miner_disease_descendant_degree IS NOT NULL
           OR entity._miner_disease_superclass_degree IS NOT NULL
        REMOVE entity._miner_affects_aa_decreased_gene_degree,
               entity._miner_direct_gene_target_degree,
               entity._miner_phenotype_degree,
               entity._miner_phenotype_descendant_degree,
               entity._miner_disease_member_degree,
               entity._miner_side_effect_drug_degree,
               entity._miner_side_effect_profile_degree,
               entity._miner_condition_gene_degree,
               entity._miner_gene_association_degree,
               entity._miner_drug_member_degree,
               entity._miner_gene_member_degree,
               entity._miner_gene_enable_degree,
               entity._miner_component_gene_member_degree,
               entity._miner_component_active_gene_degree,
               entity._miner_gene_family_member_degree,
               entity._miner_disease_genetic_association_degree,
               entity._miner_phenotype_genetic_association_degree,
               entity._miner_disease_location_degree,
               entity._miner_human_gene_expression_degree,
               entity._miner_phenotype_location_degree,
               entity._miner_disease_descendant_degree,
               entity._miner_disease_superclass_degree
        RETURN count(entity) AS entities_cleared
        """,
    ),
)

INDEX_QUERIES = (
    """
    CREATE RANGE INDEX miner_affects_aa_decreased_degree IF NOT EXISTS
    FOR (entity:ChemicalEntity)
    ON (entity._miner_affects_aa_decreased_gene_degree)
    """,
    """
    CREATE RANGE INDEX miner_gene_disease_relevance IF NOT EXISTS
    FOR ()-[evidence:MINER_GENE_DISEASE_EVIDENCE]-()
    ON (evidence._miner_relevance_score)
    """,
    """
    CREATE RANGE INDEX miner_gene_disease_rank IF NOT EXISTS
    FOR ()-[evidence:MINER_GENE_DISEASE_EVIDENCE]-()
    ON (evidence._miner_disease_rank)
    """,
    """
    CREATE RANGE INDEX miner_anatomy_disease_location_degree IF NOT EXISTS
    FOR (anatomy:AnatomicalEntity)
    ON (anatomy._miner_disease_location_degree)
    """,
    """
    CREATE RANGE INDEX miner_anatomy_human_gene_expression_degree IF NOT EXISTS
    FOR (anatomy:AnatomicalEntity)
    ON (anatomy._miner_human_gene_expression_degree)
    """,
    """
    CREATE RANGE INDEX miner_cell_human_gene_expression_degree IF NOT EXISTS
    FOR (cell:Cell)
    ON (cell._miner_human_gene_expression_degree)
    """,
    """
    CREATE RANGE INDEX miner_phenotype_disease_member_degree IF NOT EXISTS
    FOR (phenotype:PhenotypicFeature)
    ON (phenotype._miner_disease_member_degree)
    """,
    """
    CREATE RANGE INDEX miner_phenotype_side_effect_drug_degree IF NOT EXISTS
    FOR (phenotype:PhenotypicFeature)
    ON (phenotype._miner_side_effect_drug_degree)
    """,
    """
    CREATE RANGE INDEX miner_drug_side_effect_profile_degree IF NOT EXISTS
    FOR (drug:Drug)
    ON (drug._miner_side_effect_profile_degree)
    """,
    """
    CREATE RANGE INDEX miner_process_disease_genetic_association_degree
    IF NOT EXISTS
    FOR (process:BiologicalProcess)
    ON (process._miner_disease_genetic_association_degree)
    """,
    """
    CREATE RANGE INDEX miner_process_phenotype_genetic_association_degree
    IF NOT EXISTS
    FOR (process:BiologicalProcess)
    ON (process._miner_phenotype_genetic_association_degree)
    """,
    """
    CREATE RANGE INDEX miner_chemical_class_drug_member_degree IF NOT EXISTS
    FOR (chemical_class:ChemicalEntity)
    ON (chemical_class._miner_drug_member_degree)
    """,
    """
    CREATE RANGE INDEX miner_cellular_component_gene_member_degree IF NOT EXISTS
    FOR (component:CellularComponent)
    ON (component._miner_component_gene_member_degree)
    """,
    """
    CREATE RANGE INDEX miner_cellular_component_active_gene_degree IF NOT EXISTS
    FOR (component:CellularComponent)
    ON (component._miner_component_active_gene_degree)
    """,
    """
    CREATE RANGE INDEX miner_gene_family_member_degree IF NOT EXISTS
    FOR (family:GeneFamily)
    ON (family._miner_gene_family_member_degree)
    """,
    """
    CREATE RANGE INDEX miner_molecular_activity_gene_enable_degree IF NOT EXISTS
    FOR (activity:MolecularActivity)
    ON (activity._miner_gene_enable_degree)
    """,
)


def run_query(session, query: str, timeout_seconds: int) -> dict[str, Any]:
    record = session.run(Query(query, timeout=timeout_seconds)).single(strict=True)
    return record.data()


def build_features(uri: str, password: str, timeout_seconds: int) -> dict[str, Any]:
    report: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(),
        "features": [],
    }
    with (
        GraphDatabase.driver(uri, auth=("neo4j", password)) as driver,
        driver.session(database="neo4j") as session,
    ):
        report["clear"] = {}
        for name, query in CLEAR_QUERIES:
            started = time.monotonic()
            report["clear"][name] = {
                **run_query(session, query, timeout_seconds),
                "runtime_seconds": time.monotonic() - started,
            }
        for name, query in FEATURE_QUERIES:
            print(f"Building {name}", flush=True)
            started = time.monotonic()
            values = run_query(session, query, timeout_seconds)
            feature = {
                "name": name,
                **values,
                "runtime_seconds": time.monotonic() - started,
            }
            report["features"].append(feature)
            print(json.dumps(feature, indent=2), flush=True)
        for query in INDEX_QUERIES:
            session.run(query).consume()
        session.run("CALL db.awaitIndexes(1800)").consume()
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build reusable Neo4j rule-mining features")
    parser.add_argument("--neo4j-uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument(
        "--neo4j-password",
        default=os.environ.get("NEO4J_PASSWORD", "translator-local"),
    )
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "rule-features.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_features(args.neo4j_uri, args.neo4j_password, args.timeout_seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
