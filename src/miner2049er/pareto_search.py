from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase, Query

from miner2049er.settings import ROOT

VALIDATION_SOURCE = "infores:drug-repurposing-hub"
BLIND_SOURCE = "infores:ttd"

FEATURE_QUERY = """
MATCH (subject:Drug)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(gene:Gene)
MATCH (subject)-[effect:AFFECTS]->(gene)
MATCH (gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(object:Disease)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = 'decreased'
  AND object.id STARTS WITH 'MONDO:'
WITH subject, object, gene, evidence,
     collect(DISTINCT binding) AS bindings,
     collect(DISTINCT effect) AS effects
CALL (subject, object) {
  OPTIONAL MATCH (subject)-[target:TREATS|AMELIORATES_CONDITION]->(object)
  WITH reduce(
         raw_sources = [],
         relation IN collect(target) |
         raw_sources + coalesce(relation.primary_knowledge_sources, [])
       ) AS raw_sources
  RETURN reduce(
           sources = [],
           source IN raw_sources |
           CASE WHEN source IN sources THEN sources ELSE sources + source END
         ) AS target_sources
}
WITH subject, object, gene, evidence,
     reduce(
       sources = [],
       relation IN bindings |
       reduce(
         accumulated = sources,
         source IN coalesce(relation.primary_knowledge_sources, []) |
         CASE
           WHEN source IN accumulated THEN accumulated
           ELSE accumulated + source
         END
       )
     ) AS binding_sources,
     reduce(
       sources = [],
       relation IN effects |
       reduce(
         accumulated = sources,
         source IN coalesce(relation.primary_knowledge_sources, []) |
         CASE
           WHEN source IN accumulated THEN accumulated
           ELSE accumulated + source
         END
       )
     ) AS effect_sources,
     reduce(
       publication_count = 0,
       relation IN bindings |
       publication_count + size(coalesce(relation.publications, []))
     ) AS binding_publication_count,
     target_sources
RETURN subject.id AS subject_id,
       object.id AS object_id,
       gene.id AS gene_id,
       (
         size(target_sources) > 0
         AND NOT (
           size(target_sources) = 1
           AND target_sources[0] IN [$validation_source, $blind_source]
         )
       ) AS training_hit,
       (
         size(target_sources) = 1
         AND target_sources[0] = $validation_source
       ) AS validation_hit,
       subject._miner_affects_aa_decreased_gene_degree AS drug_target_degree,
       object._miner_disease_descendant_degree AS disease_descendant_degree,
       object._miner_disease_superclass_degree AS disease_superclass_degree,
       evidence._miner_causal_publication_count AS causal_publication_count,
       evidence._miner_direct_relation_type_count AS direct_relation_type_count,
       evidence._miner_primary_source_count AS primary_source_count,
       evidence._miner_non_semmed_primary_source_count
         AS non_semmed_primary_source_count,
       evidence._miner_compact_process_count AS compact_process_count,
       evidence._miner_gene_causal_disease_degree AS gene_causal_disease_degree,
       evidence._miner_disease_causal_gene_degree AS disease_causal_gene_degree,
       evidence._miner_causal_publication_share AS causal_publication_share,
       evidence._miner_causal_publication_npmi AS causal_publication_npmi,
       evidence._miner_relevance_score AS relevance_score,
       evidence._miner_disease_rank AS disease_rank,
       evidence._miner_bgee_anatomy_count AS bgee_anatomy_count,
       evidence._miner_min_anatomy_disease_degree
         AS min_anatomy_disease_degree,
       evidence._miner_min_anatomy_gene_degree AS min_anatomy_gene_degree,
       evidence._miner_disease_anatomy_publication_count
         AS disease_anatomy_publication_count,
       evidence._miner_phenotype_supported_anatomy_count
         AS phenotype_supported_anatomy_count,
       evidence._miner_direct_process_count AS direct_process_count,
       evidence._miner_min_direct_process_disease_degree
         AS min_direct_process_disease_degree,
       evidence._miner_min_direct_process_gene_degree
         AS min_direct_process_gene_degree,
       evidence._miner_phenotype_process_count AS phenotype_process_count,
       evidence._miner_supporting_phenotype_count AS supporting_phenotype_count,
       evidence._miner_min_phenotype_process_degree
         AS min_phenotype_process_degree,
       evidence._miner_min_phenotype_process_gene_degree
         AS min_phenotype_process_gene_degree,
       evidence._miner_shared_causal_process_count AS shared_causal_process_count,
       evidence._miner_shared_process_causal_gene_count
         AS shared_process_causal_gene_count,
       size(binding_sources) AS binding_source_count,
       binding_publication_count,
       'infores:bindingdb' IN binding_sources AS binding_bindingdb,
       'infores:dgidb' IN binding_sources AS binding_dgidb,
       'infores:chembl' IN binding_sources AS binding_chembl,
       'infores:ttd' IN binding_sources AS binding_ttd,
       'infores:gtopdb' IN binding_sources AS binding_gtopdb,
       'infores:drugcentral' IN binding_sources AS binding_drugcentral,
       'infores:signor' IN binding_sources AS binding_signor,
       'infores:wombat-pk' IN binding_sources AS binding_wombat,
       'infores:signor' IN effect_sources AS effect_signor,
       EXISTS {
         MATCH (subject)-[:APPLIED_TO_TREAT]->(object)
       } AS pair_applied,
       EXISTS {
         MATCH (subject)-[trial:IN_CLINICAL_TRIALS_FOR]->(object)
         WHERE 'infores:multiomics-clinicaltrials'
               IN coalesce(trial.primary_knowledge_sources, [])
       } AS pair_clinical,
       EXISTS {
         MATCH (subject)-[relation:TREATS_OR_APPLIED_OR_STUDIED_TO_TREAT]->(object)
         WHERE 'infores:ctd' IN coalesce(relation.primary_knowledge_sources, [])
       } AS pair_treatment_parent_ctd,
       EXISTS {
         MATCH (subject)-[relation:TREATS_OR_APPLIED_OR_STUDIED_TO_TREAT]->(object)
         WHERE 'infores:text-mining-provider-targeted'
               IN coalesce(relation.primary_knowledge_sources, [])
       } AS pair_treatment_parent_targeted,
       EXISTS {
         MATCH (subject)-[relation:TREATS_OR_APPLIED_OR_STUDIED_TO_TREAT]->(object)
         WHERE 'infores:semmeddb'
               IN coalesce(relation.primary_knowledge_sources, [])
       } AS pair_treatment_parent_semmed,
       EXISTS {
         MATCH (subject)-[relation:CONTRIBUTES_TO]->(object)
         WHERE 'infores:text-mining-provider-targeted'
               IN coalesce(relation.primary_knowledge_sources, [])
       } AS pair_contributes_targeted,
       EXISTS {
         MATCH (subject)-[relation:CORRELATED_WITH]->(object)
         WHERE 'infores:ctd' IN coalesce(relation.primary_knowledge_sources, [])
       } AS pair_correlated_ctd,
       EXISTS {
         MATCH (subject)-[:AFFECTS|RELATED_TO|DISRUPTS]->(object)
       } AS pair_broad_semantic_support,
       EXISTS {
         MATCH (subject)-[:HAS_SIDE_EFFECT|CONTRAINDICATED_IN|
                          EXACERBATES_CONDITION|CAUSES]->(object)
       } AS pair_direct_adverse,
       EXISTS {
         MATCH (subject)-[:HAS_SIDE_EFFECT]->(:PhenotypicFeature)
               <-[:HAS_PHENOTYPE]-(object)
       } AS pair_shared_adverse_phenotype
ORDER BY subject_id, object_id, gene_id
"""


@dataclass(frozen=True)
class Condition:
    name: str
    expression: str
    predicate: Callable[[dict[str, Any]], bool]


def numeric_condition(
    field: str,
    operator: str,
    threshold: float,
    *,
    name: str | None = None,
) -> Condition:
    if operator not in {"<=", ">="}:
        raise ValueError(f"Unsupported operator: {operator}")

    def predicate(row: dict[str, Any]) -> bool:
        value = row.get(field)
        if value is None:
            return False
        if operator == "<=":
            return value <= threshold
        return value >= threshold

    return Condition(
        name=name or f"{field}_{operator}_{threshold}",
        expression=f"{field} {operator} {threshold}",
        predicate=predicate,
    )


def boolean_condition(
    field: str,
    *,
    expected: bool = True,
    name: str | None = None,
) -> Condition:
    return Condition(
        name=name or (field if expected else f"not_{field}"),
        expression=field if expected else f"NOT {field}",
        predicate=lambda row: bool(row.get(field)) is expected,
    )


def evidence_count(row: dict[str, Any]) -> int:
    fields = (
        "pair_applied",
        "pair_clinical",
        "pair_treatment_parent_ctd",
        "pair_treatment_parent_targeted",
        "pair_treatment_parent_semmed",
        "pair_contributes_targeted",
        "pair_correlated_ctd",
    )
    return sum(bool(row.get(field)) for field in fields)


def conditions() -> list[Condition]:
    values: list[Condition] = [
        boolean_condition("pair_direct_adverse", expected=False),
        boolean_condition("pair_shared_adverse_phenotype", expected=False),
        boolean_condition("pair_applied"),
        boolean_condition("pair_clinical"),
        boolean_condition("pair_treatment_parent_ctd"),
        boolean_condition("pair_treatment_parent_targeted"),
        boolean_condition("pair_treatment_parent_semmed"),
        boolean_condition("pair_contributes_targeted"),
        boolean_condition("pair_correlated_ctd"),
        boolean_condition("pair_broad_semantic_support"),
        boolean_condition("binding_bindingdb"),
        boolean_condition("binding_dgidb"),
        boolean_condition("binding_chembl"),
        boolean_condition("binding_ttd"),
        boolean_condition("binding_gtopdb"),
        boolean_condition("binding_drugcentral"),
        boolean_condition("binding_signor"),
        boolean_condition("binding_wombat"),
        boolean_condition("effect_signor"),
    ]
    for threshold in (2, 3, 4, 5):
        values.append(
            Condition(
                name=f"translational_evidence_count_gte_{threshold}",
                expression=f"translational_evidence_count >= {threshold}",
                predicate=lambda row, threshold=threshold: evidence_count(row) >= threshold,
            )
        )
    for threshold in (5, 10, 15, 20, 25, 30, 32, 35, 40, 44, 45, 50, 75, 100):
        values.append(numeric_condition("drug_target_degree", "<=", threshold))
    for threshold in (1, 2, 3, 5, 8, 12, 20, 50):
        values.append(numeric_condition("gene_causal_disease_degree", "<=", threshold))
    for threshold in (1, 2, 3, 5):
        values.append(numeric_condition("disease_rank", "<=", threshold))
    for threshold in (1, 2, 3, 5, 10):
        values.append(numeric_condition("causal_publication_count", ">=", threshold))
    for threshold in (0.0, 0.25, 0.5, 0.75):
        values.append(numeric_condition("causal_publication_npmi", ">=", threshold))
    for threshold in (1, 2, 3, 4):
        values.append(numeric_condition("direct_relation_type_count", ">=", threshold))
    for threshold in (1, 2):
        values.append(numeric_condition("non_semmed_primary_source_count", ">=", threshold))
        values.append(numeric_condition("compact_process_count", ">=", threshold))
    for threshold in (1, 2, 3, 4, 5):
        values.append(numeric_condition("bgee_anatomy_count", ">=", threshold))
    for threshold in (20, 50, 100, 200):
        values.append(numeric_condition("min_anatomy_disease_degree", "<=", threshold))
    for threshold in (4000, 6000, 8000, 10000):
        values.append(numeric_condition("min_anatomy_gene_degree", "<=", threshold))
    values.extend(
        [
            numeric_condition("phenotype_supported_anatomy_count", ">=", 1),
            numeric_condition("direct_process_count", ">=", 1),
            numeric_condition("phenotype_process_count", ">=", 1),
            numeric_condition("shared_causal_process_count", ">=", 1),
            numeric_condition("shared_process_causal_gene_count", ">=", 1),
            numeric_condition("shared_process_causal_gene_count", ">=", 2),
        ]
    )
    for threshold in (1, 2, 3, 4, 5):
        values.append(numeric_condition("binding_source_count", ">=", threshold))
    for threshold in (20, 50, 100, 200, 500):
        values.append(numeric_condition("disease_descendant_degree", "<=", threshold))
    values.append(numeric_condition("disease_superclass_degree", ">=", 1))
    return values


def pair_metrics(rows: list[dict[str, Any]], row_indexes: Iterable[int]) -> dict[str, Any]:
    pairs: dict[tuple[str, str], tuple[bool, bool]] = {}
    for row_index in row_indexes:
        row = rows[row_index]
        key = (row["subject_id"], row["object_id"])
        prior = pairs.get(key, (False, False))
        pairs[key] = (
            prior[0] or row["training_hit"],
            prior[1] or row["validation_hit"],
        )
    training_hits = sum(training for training, _ in pairs.values())
    validation_hits = sum(validation for _, validation in pairs.values())
    candidate_pairs = len(pairs)
    visible_hits = training_hits + validation_hits
    return {
        "candidate_pairs": candidate_pairs,
        "training_hits": training_hits,
        "validation_hits": validation_hits,
        "visible_hits": visible_hits,
        "unresolved_or_blind_pairs": candidate_pairs - visible_hits,
        "visible_precision": visible_hits / candidate_pairs if candidate_pairs else 0.0,
    }


def pareto_configs(configs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [
        config
        for config in configs
        if config["metrics"]["candidate_pairs"] > config["metrics"]["visible_hits"]
    ]
    front: list[dict[str, Any]] = []
    for candidate in eligible:
        metrics = candidate["metrics"]
        dominated = any(
            other["metrics"]["visible_precision"] >= metrics["visible_precision"]
            and other["metrics"]["visible_hits"] >= metrics["visible_hits"]
            and (
                other["metrics"]["visible_precision"] > metrics["visible_precision"]
                or other["metrics"]["visible_hits"] > metrics["visible_hits"]
            )
            for other in eligible
            if other is not candidate
        )
        if not dominated:
            front.append(candidate)
    return sorted(
        front,
        key=lambda value: (
            value["metrics"]["visible_hits"],
            -value["metrics"]["visible_precision"],
        ),
    )


def current_front(path: Path) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return [
        {
            "id": result["id"],
            "visible_hits": (
                result["counts"]["training_hits"] + result["counts"]["validation_hits"]
            ),
            "visible_precision": result["metrics"][
                "visible_target_precision_lower_bound"
            ],
        }
        for result in document["results"]
        if result.get("pareto_visible")
    ]


def dominated_by_current(metrics: dict[str, Any], front: list[dict[str, Any]]) -> bool:
    return any(
        point["visible_precision"] >= metrics["visible_precision"]
        and point["visible_hits"] >= metrics["visible_hits"]
        and (
            point["visible_precision"] > metrics["visible_precision"]
            or point["visible_hits"] > metrics["visible_hits"]
        )
        for point in front
    )


def extract_features(
    uri: str,
    password: str,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    with (
        GraphDatabase.driver(uri, auth=("neo4j", password)) as driver,
        driver.session(database="neo4j") as session,
    ):
        return [
            record.data()
            for record in session.run(
                Query(FEATURE_QUERY, timeout=timeout_seconds),
                validation_source=VALIDATION_SOURCE,
                blind_source=BLIND_SOURCE,
            )
        ]


def search(
    rows: list[dict[str, Any]],
    *,
    max_depth: int,
    beam_size: int,
) -> list[dict[str, Any]]:
    search_conditions = conditions()
    condition_masks = [
        frozenset(index for index, row in enumerate(rows) if condition.predicate(row))
        for condition in search_conditions
    ]
    all_rows = frozenset(range(len(rows)))
    metrics_cache: dict[frozenset[int], dict[str, Any]] = {}

    def metrics(mask: frozenset[int]) -> dict[str, Any]:
        if mask not in metrics_cache:
            metrics_cache[mask] = pair_metrics(rows, mask)
        return metrics_cache[mask]

    candidates: dict[frozenset[int], tuple[int, ...]] = {all_rows: ()}
    all_configs: dict[frozenset[int], tuple[int, ...]] = {}
    for _depth in range(1, max_depth + 1):
        next_candidates: dict[frozenset[int], tuple[int, ...]] = {}
        for mask, selected in candidates.items():
            start = selected[-1] + 1 if selected else 0
            for condition_index in range(start, len(search_conditions)):
                next_mask = mask & condition_masks[condition_index]
                if not next_mask or next_mask == mask:
                    continue
                next_selected = (*selected, condition_index)
                prior = next_candidates.get(next_mask)
                if prior is None or len(next_selected) < len(prior):
                    next_candidates[next_mask] = next_selected
                prior_all = all_configs.get(next_mask)
                if prior_all is None or len(next_selected) < len(prior_all):
                    all_configs[next_mask] = next_selected

        ranked = sorted(
            next_candidates.items(),
            key=lambda item: (
                metrics(item[0])["visible_precision"],
                metrics(item[0])["visible_hits"],
                -metrics(item[0])["candidate_pairs"],
            ),
            reverse=True,
        )
        candidate_configs = [
            {"mask": mask, "metrics": metrics(mask)}
            for mask, _selected in ranked
        ]
        front_masks = {
            config["mask"] for config in pareto_configs(candidate_configs)
        }
        retained = ranked[:beam_size]
        retained_masks = {mask for mask, _selected in retained}
        for mask, selected in ranked:
            if mask in front_masks and mask not in retained_masks:
                retained.append((mask, selected))
        candidates = dict(retained)

    configs = []
    for mask, selected in all_configs.items():
        configs.append(
            {
                "conditions": [search_conditions[index].name for index in selected],
                "expressions": [
                    search_conditions[index].expression for index in selected
                ],
                "metrics": metrics(mask),
            }
        )
    return configs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search a cached direct-causal-target feature matrix"
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
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--beam-size", type=int, default=1000)
    parser.add_argument(
        "--features",
        type=Path,
        default=ROOT / "results" / "pareto-search-features.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "pareto-search.json",
    )
    parser.add_argument("--refresh-features", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.refresh_features or not args.features.is_file():
        print("Extracting direct-causal-target feature matrix", flush=True)
        rows = extract_features(
            args.neo4j_uri,
            args.neo4j_password,
            args.timeout_seconds,
        )
        args.features.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "rows": rows,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        rows = json.loads(args.features.read_text(encoding="utf-8"))["rows"]

    print(f"Searching {len(rows)} path rows", flush=True)
    configs = search(
        rows,
        max_depth=args.max_depth,
        beam_size=args.beam_size,
    )
    front = current_front(ROOT / "results" / "rule-library.json")
    for config in configs:
        config["dominated_by_current"] = dominated_by_current(
            config["metrics"],
            front,
        )
    candidate_front = pareto_configs(
        [config for config in configs if not config["dominated_by_current"]]
    )
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "feature_rows": len(rows),
        "configurations": len(configs),
        "current_front": front,
        "new_front": candidate_front,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.output}: {len(candidate_front)} candidate Pareto points",
        flush=True,
    )


if __name__ == "__main__":
    main()
