from __future__ import annotations

from typing import Any

DIRECT_CAUSAL_TRANSLATIONAL = "direct_causal_translational"
TWO_STEP_SIGNED_DIRECTIONAL = "two_step_signed_directional"
RECIPROCAL_SIGNED_FEEDBACK = "reciprocal_signed_feedback"
DUAL_UPSTREAM_CONVERGENCE = "dual_upstream_convergence"
COHERENT_FEED_FORWARD = "coherent_feed_forward"
ANATOMICAL_EXPOSURE = "anatomical_exposure"
COMPENSATORY_BYPASS = "compensatory_bypass"
METABOLIC_RESCUE = "metabolic_rescue"
SIGNED_ACTIVE_METABOLITE = "signed_active_metabolite"
GENETIC_PATHWAY_CORROBORATION = "genetic_pathway_corroboration"
GENETIC_ACTIVITY_CORROBORATION = "genetic_activity_corroboration"
LIGAND_RECEPTOR_AXIS_CORRECTION = "ligand_receptor_axis_correction"
RECEPTOR_LIGAND_AXIS_CORRECTION = "receptor_ligand_axis_correction"
TEMPORAL_INDICATION_TRANSFER = "temporal_indication_transfer"
CHEMICAL_CLEARANCE_ACTIVATION = "chemical_clearance_activation"
CHEMICAL_MEDIATOR_ANTAGONISM = "chemical_mediator_antagonism"
ANATOMY_CELL_PART_LOCALIZATION = "anatomy_cell_part_localization"
CELL_LOCALIZED_TARGET = "cell_localized_target"
CAUSAL_MODULE_COVERAGE = "causal_module_coverage"
CAUSAL_MODULE_PROVENANCE = "causal_module_provenance"
DISEASE_MODULE_CENTRAL_TARGET = "disease_module_central_target"
SIGNED_PROCESS_CORRECTION = "signed_process_correction"
ORTHOLOG_PHENOTYPE_DIRECTION = "ortholog_phenotype_direction"
MOLECULAR_ACTIVITY_CORRECTION = "molecular_activity_correction"
SIGNED_REGULATORY_CASCADE = "signed_regulatory_cascade"
MULTI_DRIVER_CONNECTOR = "multi_driver_connector"
DUAL_TARGET_DUAL_DRIVER_CONNECTOR = "dual_target_dual_driver_connector"
PHENOTYPE_THERAPEUTIC_DECOMPOSITION = "phenotype_therapeutic_decomposition"
TRANSPORTER_TISSUE_DELIVERY = "transporter_tissue_delivery"
DIRECT_ABUNDANCE_CORRECTION = "direct_abundance_correction"
DIRECT_SPLICING_RESCUE = "direct_splicing_rescue"
DIRECT_ACTIVITY_CORRECTION = "direct_activity_correction"
ACTIVITY_CLASS_CORRECTION = "activity_class_correction"
MUTANT_FORM_CORRECTION = "mutant_form_correction"
PHARMACOLOGIC_MECHANISM_CORRECTION = "pharmacologic_mechanism_correction"
DOWNSTREAM_INTERCEPTION = "downstream_interception"
PROTEIN_TURNOVER_CORRECTION = "protein_turnover_correction"
ALLELE_EXPRESSION_CORRECTION = "allele_expression_correction"
EPIGENETIC_EXPRESSION_CONSENSUS = "epigenetic_expression_consensus"
FUNCTIONAL_DOSAGE_CONSENSUS = "functional_dosage_consensus"
DOMINANT_NEGATIVE_ACTIVITY = "dominant_negative_activity"
PHOSPHORYLATION_ACTIVITY_CONSENSUS = "phosphorylation_activity_consensus"
LITERATURE_ALLELE_ACTIVITY_CORRECTION = "literature_allele_activity_correction"
GO_CAM_INPUT_FLOW = "go_cam_input_flow"
ACTIVE_COMPONENT_REGULATORY_CASCADE = "active_component_regulatory_cascade"
SIGNED_GO_PROCESS_RESTORATION = "signed_go_process_restoration"
MOLECULAR_ACTIVITY_COMPLEX_COMPENSATION = (
    "molecular_activity_complex_compensation"
)
DIRECT_DISEASE_PROCESS_CORRECTION = "direct_disease_process_correction"
ETIOLOGIC_MEDIATOR_PRODUCTION = "etiologic_mediator_production"
CLOSE_MATCH_MECHANISM_TRANSFER = "close_match_mechanism_transfer"
VARIANT_COMPONENT_CORRECTION = "variant_component_correction"
DISRUPTED_PROCESS_VARIANT_CORRECTION = (
    "disrupted_process_variant_correction"
)
DISRUPTED_ACTIVITY_VARIANT_CORRECTION = (
    "disrupted_activity_variant_correction"
)
DUAL_ARM_PROCESS_TARGET_CORRECTION = "dual_arm_process_target_correction"
INTERACTION_BRIDGED_DUAL_ARM = "interaction_bridged_dual_arm"
SIGNED_REGULATORY_BRIDGED_DUAL_ARM = "signed_regulatory_bridged_dual_arm"
ONTOLOGY_GENERALIZED_SIGNED_INTERCEPTION = (
    "ontology_generalized_signed_interception"
)
TISSUE_LOCALIZED_ONTOLOGY_INTERCEPTION = (
    "tissue_localized_ontology_interception"
)
DUAL_PROCESS_ONTOLOGY_CONVERGENCE = "dual_process_ontology_convergence"

PAIR_APPLIED = """
EXISTS {
  MATCH (subject)-[:APPLIED_TO_TREAT]->(object)
}
""".strip()

PAIR_CLINICAL = """
EXISTS {
  MATCH (subject)-[trial:IN_CLINICAL_TRIALS_FOR]->(object)
  WHERE 'infores:multiomics-clinicaltrials'
        IN coalesce(trial.primary_knowledge_sources, [])
}
""".strip()

PAIR_TREATMENT_PARENT_CTD = """
EXISTS {
  MATCH (subject)-[relation:TREATS_OR_APPLIED_OR_STUDIED_TO_TREAT]->(object)
  WHERE 'infores:ctd' IN coalesce(relation.primary_knowledge_sources, [])
}
""".strip()

PAIR_TREATMENT_PARENT_TARGETED = """
EXISTS {
  MATCH (subject)-[relation:TREATS_OR_APPLIED_OR_STUDIED_TO_TREAT]->(object)
  WHERE 'infores:text-mining-provider-targeted'
        IN coalesce(relation.primary_knowledge_sources, [])
}
""".strip()

PAIR_TREATMENT_PARENT_SEMMED = """
EXISTS {
  MATCH (subject)-[relation:TREATS_OR_APPLIED_OR_STUDIED_TO_TREAT]->(object)
  WHERE 'infores:semmeddb' IN coalesce(relation.primary_knowledge_sources, [])
}
""".strip()

PAIR_CONTRIBUTES_TARGETED = """
EXISTS {
  MATCH (subject)-[relation:CONTRIBUTES_TO]->(object)
  WHERE 'infores:text-mining-provider-targeted'
        IN coalesce(relation.primary_knowledge_sources, [])
}
""".strip()

PAIR_CORRELATED_CTD = """
EXISTS {
  MATCH (subject)-[relation:CORRELATED_WITH]->(object)
  WHERE 'infores:ctd' IN coalesce(relation.primary_knowledge_sources, [])
}
""".strip()

TRANSLATIONAL_EVIDENCE_COUNT = f"""
(
  CASE WHEN {PAIR_APPLIED} THEN 1 ELSE 0 END +
  CASE WHEN {PAIR_CLINICAL} THEN 1 ELSE 0 END +
  CASE WHEN {PAIR_TREATMENT_PARENT_CTD} THEN 1 ELSE 0 END +
  CASE WHEN {PAIR_TREATMENT_PARENT_TARGETED} THEN 1 ELSE 0 END +
  CASE WHEN {PAIR_TREATMENT_PARENT_SEMMED} THEN 1 ELSE 0 END +
  CASE WHEN {PAIR_CONTRIBUTES_TARGETED} THEN 1 ELSE 0 END +
  CASE WHEN {PAIR_CORRELATED_CTD} THEN 1 ELSE 0 END
)
""".strip()

DIRECT_CAUSAL_TRANSLATIONAL_CONDITIONS = {
    "pair_applied": PAIR_APPLIED,
    "pair_clinical": PAIR_CLINICAL,
    "pair_treatment_parent_targeted": PAIR_TREATMENT_PARENT_TARGETED,
    "pair_treatment_parent_semmed": PAIR_TREATMENT_PARENT_SEMMED,
    "binding_ttd": "'infores:ttd' IN binding_sources",
    "binding_gtopdb": "'infores:gtopdb' IN binding_sources",
    "binding_dgidb": "'infores:dgidb' IN binding_sources",
    "translational_evidence_count_gte_3": (
        f"{TRANSLATIONAL_EVIDENCE_COUNT} >= 3"
    ),
    "translational_evidence_count_gte_4": (
        f"{TRANSLATIONAL_EVIDENCE_COUNT} >= 4"
    ),
    "non_semmed_primary_source_count_>=_1": (
        "evidence._miner_non_semmed_primary_source_count >= 1"
    ),
    "binding_source_count_>=_4": "size(binding_sources) >= 4",
    "binding_source_count_>=_5": "size(binding_sources) >= 5",
    "disease_descendant_degree_<=_500": (
        "object._miner_disease_descendant_degree <= 500"
    ),
    "min_anatomy_gene_degree_<=_8000": (
        "evidence._miner_min_anatomy_gene_degree <= 8000"
    ),
    "bgee_anatomy_count_>=_1": "evidence._miner_bgee_anatomy_count >= 1",
    "causal_publication_npmi_>=_0.0": (
        "evidence._miner_causal_publication_npmi >= 0.0"
    ),
    "causal_publication_npmi_>=_0.25": (
        "evidence._miner_causal_publication_npmi >= 0.25"
    ),
    "causal_publication_count_>=_2": (
        "evidence._miner_causal_publication_count >= 2"
    ),
    "causal_publication_count_>=_3": (
        "evidence._miner_causal_publication_count >= 3"
    ),
    "direct_relation_type_count_>=_2": (
        "evidence._miner_direct_relation_type_count >= 2"
    ),
    "direct_relation_type_count_>=_3": (
        "evidence._miner_direct_relation_type_count >= 3"
    ),
}


def direct_causal_translational_cypher(condition_names: list[str]) -> str:
    unknown = set(condition_names) - set(DIRECT_CAUSAL_TRANSLATIONAL_CONDITIONS)
    if unknown:
        raise ValueError(
            "Unknown direct causal translational conditions: "
            + ", ".join(sorted(unknown))
        )
    expressions = [
        DIRECT_CAUSAL_TRANSLATIONAL_CONDITIONS[name] for name in condition_names
    ]
    conditions = "\n  AND ".join(f"({expression})" for expression in expressions)
    return f"""
MATCH (subject:Drug)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(gene:Gene)
MATCH (subject)-[effect:AFFECTS]->(gene)
MATCH (gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(object:Disease)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = 'decreased'
  AND object.id STARTS WITH 'MONDO:'
WITH subject, object, gene, evidence,
     collect(DISTINCT binding) AS bindings
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
     ) AS binding_sources
WHERE {conditions}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def two_step_signed_directional_cypher(
    variant_form: str,
    sign_mode: str,
    context: str,
) -> str:
    variant_forms = {
        "gain_of_function_variant_form",
        "loss_of_function_variant_form",
    }
    if variant_form not in variant_forms:
        raise ValueError(f"Unknown disease variant form: {variant_form}")
    if sign_mode not in {"corrective", "adverse"}:
        raise ValueError(f"Unknown signed path mode: {sign_mode}")
    if context not in {"process", "process_degree", "process_anatomy"}:
        raise ValueError(f"Unknown signed path context: {context}")

    corrective_same_sign = variant_form == "gain_of_function_variant_form"
    same_sign = corrective_same_sign == (sign_mode == "corrective")
    sign_operator = "=" if same_sign else "<>"

    context_matches = """
MATCH (target)-[:INVOLVED_IN]->(process:BiologicalProcess)
      <-[:INVOLVED_IN]-(middle)
MATCH (driver)-[:INVOLVED_IN]->(process)
""".strip()
    context_conditions = ["process._miner_gene_member_degree <= 100"]
    if context == "process_degree":
        context_conditions.extend(
            [
                """COUNT {
  (target)-[target_out:REGULATES]->(:Gene)
  WHERE 'infores:signor' IN
        coalesce(target_out.primary_knowledge_sources, [])
} <= 9""",
                """COUNT {
  (:Gene)-[middle_in:REGULATES]->(middle)
  WHERE 'infores:signor' IN
        coalesce(middle_in.primary_knowledge_sources, [])
} <= 8""",
                """COUNT {
  (middle)-[middle_out:REGULATES]->(:Gene)
  WHERE 'infores:signor' IN
        coalesce(middle_out.primary_knowledge_sources, [])
} <= 9""",
                """COUNT {
  (:Gene)-[driver_in:REGULATES]->(driver)
  WHERE 'infores:signor' IN
        coalesce(driver_in.primary_knowledge_sources, [])
} <= 8""",
            ]
        )
    elif context == "process_anatomy":
        context_matches += """
MATCH (target)-[target_expression:EXPRESSED_IN]->
      (anatomy:AnatomicalEntity)
      <-[middle_expression:EXPRESSED_IN]-(middle)
MATCH (driver)-[driver_expression:EXPRESSED_IN]->(anatomy)
MATCH (object)-[:LOCATED_IN|OCCURS_IN]->(anatomy)
"""
        context_conditions.extend(
            [
                (
                    "'infores:bgee' IN "
                    "coalesce(target_expression.primary_knowledge_sources, [])"
                ),
                (
                    "'infores:bgee' IN "
                    "coalesce(middle_expression.primary_knowledge_sources, [])"
                ),
                (
                    "'infores:bgee' IN "
                    "coalesce(driver_expression.primary_knowledge_sources, [])"
                ),
            ]
        )
    context_where = "\n  AND ".join(context_conditions)

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target:Gene)
MATCH (subject)-[effect:AFFECTS]->(target)
MATCH (target)-[regulation1:REGULATES]->(middle:Gene)
MATCH (middle)-[regulation2:REGULATES]->(driver:Gene)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
{context_matches}
WHERE target <> middle
  AND middle <> driver
  AND target <> driver
  AND 'infores:signor' IN
      coalesce(regulation1.primary_knowledge_sources, [])
  AND 'infores:signor' IN
      coalesce(regulation2.primary_knowledge_sources, [])
  AND regulation1.qualified_predicate = 'biolink:causes'
  AND regulation2.qualified_predicate = 'biolink:causes'
  AND regulation1.object_direction_qualifier IN
      ['upregulated', 'downregulated']
  AND regulation2.object_direction_qualifier IN
      ['upregulated', 'downregulated']
  AND regulation1.object_direction_qualifier {sign_operator}
      regulation2.object_direction_qualifier
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = 'decreased'
  AND {context_where}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def _signed_driver_direction(variant_form: str, sign_mode: str) -> str:
    if variant_form not in {
        "gain_of_function_variant_form",
        "loss_of_function_variant_form",
    }:
        raise ValueError(f"Unknown disease variant form: {variant_form}")
    if sign_mode not in {"corrective", "adverse"}:
        raise ValueError(f"Unknown signed path mode: {sign_mode}")
    corrective_up = variant_form == "gain_of_function_variant_form"
    upregulated = corrective_up == (sign_mode == "corrective")
    return "upregulated" if upregulated else "downregulated"


def reciprocal_signed_feedback_cypher(
    variant_form: str,
    sign_mode: str,
    context: str,
    *,
    dual_arm: bool = False,
) -> str:
    direction = _signed_driver_direction(variant_form, sign_mode)
    if context not in {"base", "process", "anatomy", "process_anatomy"}:
        raise ValueError(f"Unknown feedback context: {context}")

    conditions: list[str] = []
    if context in {"process", "process_anatomy"}:
        conditions.append(
            """EXISTS {
  MATCH (target)-[:INVOLVED_IN]->(process:BiologicalProcess)
        <-[:INVOLVED_IN]-(driver)
  WHERE process._miner_gene_member_degree <= 100
}"""
        )
    if context in {"anatomy", "process_anatomy"}:
        conditions.append(
            """EXISTS {
  MATCH (target)-[target_expression:EXPRESSED_IN]->
        (anatomy:AnatomicalEntity)
        <-[driver_expression:EXPRESSED_IN]-(driver)
  MATCH (object)-[:LOCATED_IN|OCCURS_IN]->(anatomy)
  WHERE 'infores:bgee' IN
        coalesce(target_expression.primary_knowledge_sources, [])
    AND 'infores:bgee' IN
        coalesce(driver_expression.primary_knowledge_sources, [])
}"""
        )
    context_where = "".join(f"\n  AND {condition}" for condition in conditions)
    dual_arm_match = ""
    dual_arm_where = ""
    if dual_arm:
        driver_effect_direction = (
            "decreased"
            if (variant_form == "gain_of_function_variant_form")
            == (sign_mode == "corrective")
            else "increased"
        )
        dual_arm_match = """
MATCH (subject)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver)
MATCH (subject)-[driver_effect:AFFECTS]->(driver)
""".strip()
        dual_arm_where = f"""
  AND driver_effect.qualified_predicate = 'biolink:causes'
  AND driver_effect.object_aspect_qualifier = 'activity_or_abundance'
  AND driver_effect.object_direction_qualifier = '{driver_effect_direction}'
""".rstrip()

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target:Gene)
MATCH (subject)-[effect:AFFECTS]->(target)
MATCH (target)-[forward:REGULATES]->(driver:Gene)
MATCH (driver)-[back:REGULATES]->(target)
{dual_arm_match}
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE target <> driver
  AND 'infores:signor' IN coalesce(forward.primary_knowledge_sources, [])
  AND 'infores:signor' IN coalesce(back.primary_knowledge_sources, [])
  AND forward.qualified_predicate = 'biolink:causes'
  AND back.qualified_predicate = 'biolink:causes'
  AND forward.object_direction_qualifier = '{direction}'
  AND back.object_direction_qualifier = forward.object_direction_qualifier
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = 'decreased'{dual_arm_where}{context_where}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def dual_upstream_convergence_cypher(
    variant_form: str,
    sign_mode: str,
    context: str,
) -> str:
    direction = _signed_driver_direction(variant_form, sign_mode)
    if context not in {"base", "interacting", "process"}:
        raise ValueError(f"Unknown convergence context: {context}")

    context_match = ""
    context_condition = ""
    if context == "interacting":
        context_match = """
MATCH (target1)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]-(target2)
""".strip()
    elif context == "process":
        context_condition = """
  AND EXISTS {
    MATCH (target1)-[:INVOLVED_IN]->(process:BiologicalProcess)
          <-[:INVOLVED_IN]-(target2)
    MATCH (driver)-[:INVOLVED_IN]->(process)
    WHERE process._miner_gene_member_degree <= 100
  }
""".rstrip()

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target1:Gene)
MATCH (subject)-[effect1:AFFECTS]->(target1)
MATCH (subject)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target2:Gene)
MATCH (subject)-[effect2:AFFECTS]->(target2)
MATCH (target1)-[regulation1:REGULATES]->(driver:Gene)
      <-[regulation2:REGULATES]-(target2)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
{context_match}
WHERE target1.id < target2.id
  AND target1 <> driver
  AND target2 <> driver
  AND 'infores:signor' IN
      coalesce(regulation1.primary_knowledge_sources, [])
  AND 'infores:signor' IN
      coalesce(regulation2.primary_knowledge_sources, [])
  AND regulation1.qualified_predicate = 'biolink:causes'
  AND regulation2.qualified_predicate = 'biolink:causes'
  AND regulation1.object_direction_qualifier = '{direction}'
  AND regulation2.object_direction_qualifier =
      regulation1.object_direction_qualifier
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND effect1.qualified_predicate = 'biolink:causes'
  AND effect1.object_aspect_qualifier = 'activity_or_abundance'
  AND effect1.object_direction_qualifier = 'decreased'
  AND effect2.qualified_predicate = 'biolink:causes'
  AND effect2.object_aspect_qualifier = 'activity_or_abundance'
  AND effect2.object_direction_qualifier = 'decreased'{context_condition}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def coherent_feed_forward_cypher(
    variant_form: str,
    sign_mode: str,
    context: str,
) -> str:
    direction = _signed_driver_direction(variant_form, sign_mode)
    if context not in {"base", "process"}:
        raise ValueError(f"Unknown feed-forward context: {context}")
    indirect_operator = "=" if direction == "upregulated" else "<>"
    context_condition = ""
    if context == "process":
        context_condition = """
  AND EXISTS {
    MATCH (target)-[:INVOLVED_IN]->(process:BiologicalProcess)
          <-[:INVOLVED_IN]-(middle)
    MATCH (driver)-[:INVOLVED_IN]->(process)
    WHERE process._miner_gene_member_degree <= 100
  }
""".rstrip()

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target:Gene)
MATCH (subject)-[effect:AFFECTS]->(target)
MATCH (target)-[direct:REGULATES]->(driver:Gene)
MATCH (target)-[regulation1:REGULATES]->(middle:Gene)
MATCH (middle)-[regulation2:REGULATES]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE target <> middle
  AND middle <> driver
  AND target <> driver
  AND 'infores:signor' IN coalesce(direct.primary_knowledge_sources, [])
  AND 'infores:signor' IN
      coalesce(regulation1.primary_knowledge_sources, [])
  AND 'infores:signor' IN
      coalesce(regulation2.primary_knowledge_sources, [])
  AND direct.qualified_predicate = 'biolink:causes'
  AND regulation1.qualified_predicate = 'biolink:causes'
  AND regulation2.qualified_predicate = 'biolink:causes'
  AND direct.object_direction_qualifier = '{direction}'
  AND regulation1.object_direction_qualifier IN
      ['upregulated', 'downregulated']
  AND regulation2.object_direction_qualifier IN
      ['upregulated', 'downregulated']
  AND regulation1.object_direction_qualifier {indirect_operator}
      regulation2.object_direction_qualifier
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = 'decreased'{context_condition}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def anatomical_exposure_cypher(
    mechanism: str,
    *,
    top_three: bool,
    disruption_mode: str,
) -> str:
    if mechanism == "causal_inhibition":
        disease_match = (
            "MATCH (gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->"
            "(object:Disease)"
        )
        effect_direction = "decreased"
        disease_conditions = []
        if top_three:
            disease_conditions.append("evidence._miner_disease_rank <= 3")
    elif mechanism in {"gof_correction", "lof_restoration"}:
        disease_match = "MATCH (gene)-[association:ASSOCIATED_WITH]->(object:Disease)"
        variant_form = (
            "gain_of_function_variant_form"
            if mechanism == "gof_correction"
            else "loss_of_function_variant_form"
        )
        effect_direction = "decreased" if mechanism == "gof_correction" else "increased"
        disease_conditions = [
            (
                "'infores:gene2phenotype' IN "
                "coalesce(association.primary_knowledge_sources, [])"
            ),
            f"association.subject_form_or_variant_qualifier = '{variant_form}'",
            "coalesce(object._miner_disease_descendant_degree, 0) <= 500",
            "object._miner_disease_superclass_degree >= 1",
        ]
    else:
        raise ValueError(f"Unknown anatomical exposure mechanism: {mechanism}")

    if disruption_mode not in {"allow", "exclude", "require"}:
        raise ValueError(f"Unknown disruption mode: {disruption_mode}")
    if disruption_mode == "exclude":
        disease_conditions.append(
            "NOT EXISTS { MATCH (subject)-[:DISRUPTS]->(anatomy) }"
        )
    elif disruption_mode == "require":
        disease_conditions.append(
            "EXISTS { MATCH (subject)-[:DISRUPTS]->(anatomy) }"
        )
    extra_conditions = "".join(
        f"\n  AND {condition}" for condition in disease_conditions
    )

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(gene:Gene)
MATCH (subject)-[effect:AFFECTS]->(gene)
{disease_match}
MATCH (subject)-[location:LOCATED_IN]->(anatomy:AnatomicalEntity)
MATCH (gene)-[expression:EXPRESSED_IN]->(anatomy)
MATCH (object)-[:LOCATED_IN|OCCURS_IN]->(anatomy)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{effect_direction}'
  AND 'infores:semmeddb' IN coalesce(location.primary_knowledge_sources, [])
  AND 'infores:bgee' IN coalesce(expression.primary_knowledge_sources, [])
  AND object.id STARTS WITH 'MONDO:'{extra_conditions}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def compensatory_bypass_cypher(context: str, sign_mode: str) -> str:
    if context == "family":
        context_match = """
MATCH (target)-[:MEMBER_OF]->(family:GeneFamily)
      <-[:MEMBER_OF]-(driver)
""".strip()
        context_conditions = ["family._miner_gene_family_member_degree <= 14"]
    elif context == "family_process":
        context_match = """
MATCH (target)-[:MEMBER_OF]->(family:GeneFamily)
      <-[:MEMBER_OF]-(driver)
MATCH (target)-[:INVOLVED_IN]->(process:BiologicalProcess)
      <-[:INVOLVED_IN]-(driver)
""".strip()
        context_conditions = [
            "family._miner_gene_family_member_degree <= 14",
            "process._miner_gene_member_degree <= 100",
        ]
    elif context == "component":
        context_match = """
MATCH (target)-[:PART_OF]->(component:CellularComponent)
      <-[:PART_OF]-(driver)
""".strip()
        context_conditions = ["component._miner_component_gene_member_degree <= 54"]
    elif context == "interaction":
        context_match = (
            "MATCH (target)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]-(driver)"
        )
        context_conditions = []
    else:
        raise ValueError(f"Unknown compensatory bypass context: {context}")

    if sign_mode not in {"corrective", "adverse"}:
        raise ValueError(f"Unknown compensatory bypass sign mode: {sign_mode}")
    effect_direction = "increased" if sign_mode == "corrective" else "decreased"
    extra_conditions = "".join(
        f"\n  AND {condition}" for condition in context_conditions
    )

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target:Gene)
MATCH (subject)-[effect:AFFECTS]->(target)
{context_match}
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE target <> driver
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{effect_direction}'
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier =
      'loss_of_function_variant_form'{extra_conditions}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def metabolic_rescue_cypher(mode: str) -> str:
    disease_match = """
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier =
      'loss_of_function_variant_form'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
""".strip()

    if mode == "product_replacement":
        mechanism_match = """
MATCH (driver:Gene)-[:PRODUCES]->(subject:Drug)
""".strip()
    elif mode == "product_subclass":
        mechanism_match = """
MATCH (driver:Gene)-[:PRODUCES]->(product:ChemicalEntity)
MATCH (subject:Drug)-[:SUBCLASS_OF*1..2]->(product)
WHERE subject <> product
""".strip()
    elif mode == "product_formulation":
        mechanism_match = """
MATCH (driver:Gene)-[:PRODUCES]->(product:ChemicalEntity)
MATCH (subject:Drug)-[:HAS_PART]->(product)
WHERE subject <> product
""".strip()
    elif mode == "substrate_supplementation":
        mechanism_match = """
MATCH (driver:Gene)-[:HAS_SUBSTRATE]->(subject:Drug)
""".strip()
    elif mode == "substrate_reduction":
        mechanism_match = """
MATCH (driver:Gene)-[:HAS_SUBSTRATE]->(metabolite:ChemicalEntity)
      <-[:PRODUCES]-(alternate:Gene)
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(alternate)
MATCH (subject)-[effect:AFFECTS]->(alternate)
WHERE alternate <> driver
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = 'decreased'
""".strip()
    elif mode in {"alternate_product_boost", "alternate_product_suppression"}:
        direction = (
            "increased" if mode == "alternate_product_boost" else "decreased"
        )
        mechanism_match = f"""
MATCH (driver:Gene)-[:PRODUCES]->(metabolite:ChemicalEntity)
      <-[:PRODUCES]-(alternate:Gene)
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(alternate)
MATCH (subject)-[effect:AFFECTS]->(alternate)
WHERE alternate <> driver
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
""".strip()
    else:
        raise ValueError(f"Unknown metabolic rescue mode: {mode}")

    connector = "\nWITH subject, driver\n" if "WHERE" in mechanism_match else "\n"
    return f"""
{mechanism_match}{connector}{disease_match}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def signed_active_metabolite_cypher(mode: str) -> str:
    modes = {
        "gof_corrective": ("gain_of_function_variant_form", "decreased"),
        "gof_worsening": ("gain_of_function_variant_form", "increased"),
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = modes[mode]
    except KeyError as error:
        raise ValueError(f"Unknown signed active metabolite mode: {mode}") from error

    return f"""
MATCH (subject:Drug)-[:HAS_METABOLITE]->(metabolite:ChemicalEntity)
MATCH (metabolite)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (driver:Gene)
MATCH (metabolite)-[effect:AFFECTS]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE subject <> metabolite
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def genetic_pathway_corroboration_cypher(mode: str) -> str:
    modes = {
        "decreased": ("decreased", ""),
        "increased_control": ("increased", ""),
        "decreased_adverse_anatomy_gated": (
            "decreased",
            """
  AND NOT EXISTS {
    MATCH (subject)-[:HAS_SIDE_EFFECT]->(:PhenotypicFeature)
          -[:LOCATED_IN]->(adverse_anatomy:AnatomicalEntity)
    MATCH (object)-[:LOCATED_IN|OCCURS_IN]->(adverse_anatomy)
  }
""",
        ),
        "decreased_adverse_anatomy_conflict": (
            "decreased",
            """
  AND EXISTS {
    MATCH (subject)-[:HAS_SIDE_EFFECT]->(:PhenotypicFeature)
          -[:LOCATED_IN]->(adverse_anatomy:AnatomicalEntity)
    MATCH (object)-[:LOCATED_IN|OCCURS_IN]->(adverse_anatomy)
}
""",
        ),
        "decreased_no_black_box_warning": (
            "decreased",
            """
  AND subject.chembl_black_box_warning IS NULL
""",
        ),
        "decreased_black_box_warning": (
            "decreased",
            """
  AND subject.chembl_black_box_warning = 'True'
""",
        ),
    }
    try:
        direction, additional_condition = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown genetic pathway corroboration mode: {mode}"
        ) from error

    return f"""
MATCH (process:Pathway)-[path_evidence:GENETIC_ASSOCIATION]->
      (object:Disease)
MATCH (target:Gene)-[membership:INVOLVED_IN]->(process)
MATCH (target)-[gene_evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
MATCH (subject:Drug)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (target)
MATCH (subject)-[effect:AFFECTS]->(target)
WHERE process.id STARTS WITH 'GO:'
  AND 'infores:geneticskp' IN
      coalesce(path_evidence.primary_knowledge_sources, [])
  AND 'infores:goa' IN coalesce(membership.primary_knowledge_sources, [])
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND gene_evidence._miner_disease_rank <= 3
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
{additional_condition.rstrip()}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def genetic_activity_corroboration_cypher(mode: str) -> str:
    directions = {
        "decreased": "decreased",
        "increased_control": "increased",
    }
    try:
        direction = directions[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown genetic activity corroboration mode: {mode}"
        ) from error

    return f"""
MATCH (activity:MolecularActivity)-[activity_evidence:GENETIC_ASSOCIATION]->
      (object:Disease)
MATCH (target:Gene)-[enables:ENABLES]->(activity)
MATCH (target)-[gene_evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
MATCH (subject:Drug)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (target)
MATCH (subject)-[effect:AFFECTS]->(target)
WHERE 'infores:geneticskp' IN
      coalesce(activity_evidence.primary_knowledge_sources, [])
  AND 'infores:goa' IN coalesce(enables.primary_knowledge_sources, [])
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND gene_evidence._miner_disease_rank <= 3
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def ligand_receptor_axis_correction_cypher(mode: str) -> str:
    modes = {
        "gof_corrective": ("gain_of_function_variant_form", "decreased"),
        "gof_worsening": ("gain_of_function_variant_form", "increased"),
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown ligand-receptor axis correction mode: {mode}"
        ) from error

    return f"""
MATCH (driver:Gene)-[ligand_function:ENABLES]->
      (:MolecularActivity)-[:SUBCLASS_OF*0..5]->
      (:MolecularActivity {{id: 'GO:0005102'}})
MATCH (driver)-[interaction:DIRECTLY_PHYSICALLY_INTERACTS_WITH]-
      (receptor:Gene)
MATCH (receptor)-[receptor_function:ENABLES]->
      (:MolecularActivity)-[:SUBCLASS_OF*0..5]->
      (:MolecularActivity {{id: 'GO:0038023'}})
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE driver <> receptor
  AND 'infores:goa' IN
      coalesce(ligand_function.primary_knowledge_sources, [])
  AND 'infores:signor' IN
      coalesce(interaction.primary_knowledge_sources, [])
  AND 'infores:goa' IN
      coalesce(receptor_function.primary_knowledge_sources, [])
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
WITH DISTINCT driver, receptor, object
MATCH (subject:Drug)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (receptor)
MATCH (subject)-[effect:AFFECTS]->(receptor)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def receptor_ligand_axis_correction_cypher(mode: str) -> str:
    modes = {
        "gof_corrective": ("gain_of_function_variant_form", "decreased"),
        "gof_worsening": ("gain_of_function_variant_form", "increased"),
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown receptor-ligand axis correction mode: {mode}"
        ) from error

    return f"""
MATCH (driver:Gene)-[ligand_function:ENABLES]->
      (:MolecularActivity)-[:SUBCLASS_OF*0..5]->
      (:MolecularActivity {{id: 'GO:0048018'}})
MATCH (driver)-[interaction:DIRECTLY_PHYSICALLY_INTERACTS_WITH]-
      (receptor:Gene)
MATCH (receptor)-[receptor_function:ENABLES]->
      (:MolecularActivity)-[:SUBCLASS_OF*0..5]->
      (:MolecularActivity {{id: 'GO:0038023'}})
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE driver <> receptor
  AND 'infores:goa' IN
      coalesce(ligand_function.primary_knowledge_sources, [])
  AND 'infores:signor' IN
      coalesce(interaction.primary_knowledge_sources, [])
  AND 'infores:goa' IN
      coalesce(receptor_function.primary_knowledge_sources, [])
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
WITH DISTINCT driver, receptor, object
MATCH (subject:Drug)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (receptor)
MATCH (subject)-[effect:AFFECTS]->(receptor)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def temporal_indication_transfer_cypher(mode: str) -> str:
    modes = {
        "forward_decreased": (
            "(anchor)-[temporal:PRECEDES]->(object:Disease)",
            "decreased",
        ),
        "forward_increased": (
            "(anchor)-[temporal:PRECEDES]->(object:Disease)",
            "increased",
        ),
        "reverse_decreased": (
            "(object:Disease)-[temporal:PRECEDES]->(anchor)",
            "decreased",
        ),
        "reverse_increased": (
            "(object:Disease)-[temporal:PRECEDES]->(anchor)",
            "increased",
        ),
    }
    try:
        temporal_pattern, direction = modes[mode]
    except KeyError as error:
        raise ValueError(f"Unknown temporal indication transfer mode: {mode}") from error

    return f"""
MATCH (subject:Drug)-[treatment:TREATS|AMELIORATES_CONDITION]->
      (anchor:Disease)
WHERE any(
  source IN coalesce(treatment.primary_knowledge_sources, [])
  WHERE NOT source IN ['infores:drug-repurposing-hub', 'infores:ttd']
)
MATCH (subject)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(gene:Gene)
MATCH (subject)-[effect:AFFECTS]->(gene)
MATCH (gene)-[anchor_evidence:MINER_GENE_DISEASE_EVIDENCE]->(anchor)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND anchor_evidence._miner_disease_rank <= 3
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
WITH DISTINCT subject, anchor, gene
MATCH {temporal_pattern}
WHERE 'infores:semmeddb' IN
      coalesce(temporal.primary_knowledge_sources, [])
MATCH (gene)-[object_evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
WHERE object_evidence._miner_disease_rank <= 3
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def chemical_clearance_activation_cypher(mode: str) -> str:
    directions = {
        "activation": "increased",
        "inhibition_control": "decreased",
    }
    try:
        direction = directions[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown chemical clearance activation mode: {mode}"
        ) from error

    return f"""
MATCH (enzyme:Gene)-[substrate:HAS_SUBSTRATE]->(chemical:ChemicalEntity)
      -[etiology:CAUSES]->(object:Disease)
MATCH (subject:Drug)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(enzyme)
MATCH (subject)-[effect:AFFECTS]->(enzyme)
WHERE NOT chemical:Drug
  AND subject <> chemical
  AND 'infores:chembl' IN
      coalesce(substrate.primary_knowledge_sources, [])
  AND 'infores:semmeddb' IN
      coalesce(etiology.primary_knowledge_sources, [])
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def chemical_mediator_antagonism_cypher(mode: str) -> str:
    directions = {
        "increased_opposed": ("increased", "decreased", False, False),
        "decreased_opposed": ("decreased", "increased", False, False),
        "increased_reinforced": ("increased", "increased", False, False),
        "decreased_reinforced": ("decreased", "decreased", False, False),
        "increased_opposed_genetic": ("increased", "decreased", True, False),
        "decreased_opposed_genetic": ("decreased", "increased", True, False),
        "increased_reinforced_genetic": (
            "increased",
            "increased",
            True,
            False,
        ),
        "decreased_reinforced_genetic": (
            "decreased",
            "decreased",
            True,
            False,
        ),
        "increased_opposed_genetic_anatomy": (
            "increased",
            "decreased",
            True,
            True,
        ),
        "decreased_opposed_genetic_anatomy": (
            "decreased",
            "increased",
            True,
            True,
        ),
        "increased_reinforced_genetic_anatomy": (
            "increased",
            "increased",
            True,
            True,
        ),
        "decreased_reinforced_genetic_anatomy": (
            "decreased",
            "decreased",
            True,
            True,
        ),
    }
    try:
        (
            mediator_direction,
            drug_direction,
            require_genetic_support,
            require_anatomy_support,
        ) = directions[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown chemical mediator antagonism mode: {mode}"
        ) from error

    genetic_support = ""
    if require_genetic_support:
        genetic_support = """
MATCH (target)-[gene_evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
WHERE gene_evidence._miner_disease_rank <= 3
"""

    anatomy_support = ""
    if require_anatomy_support:
        anatomy_support = """
MATCH (object)-[:LOCATED_IN|OCCURS_IN]->
      (anatomy:AnatomicalEntity)-[production:PRODUCES]->(mediator)
WHERE 'infores:semmeddb' IN
      coalesce(production.primary_knowledge_sources, [])
"""

    return f"""
MATCH (mediator:ChemicalEntity)
      -[mediator_binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (target:Gene)
MATCH (mediator)-[mediator_effect:AFFECTS]->(target)
WHERE mediator_effect.qualified_predicate = 'biolink:causes'
  AND mediator_effect.object_aspect_qualifier = 'activity_or_abundance'
  AND mediator_effect.object_direction_qualifier = '{mediator_direction}'
  AND none(
    source IN coalesce(mediator_binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(mediator_effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
WITH DISTINCT mediator, target
MATCH (mediator)-[etiology:CAUSES]->(object:Disease)
WHERE 'infores:semmeddb' IN
      coalesce(etiology.primary_knowledge_sources, [])
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
WITH DISTINCT mediator, target, object
{genetic_support}
{anatomy_support}
MATCH (subject:Drug)-[drug_binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (target)
MATCH (subject)-[drug_effect:AFFECTS]->(target)
WHERE subject <> mediator
  AND drug_effect.qualified_predicate = 'biolink:causes'
  AND drug_effect.object_aspect_qualifier = 'activity_or_abundance'
  AND drug_effect.object_direction_qualifier = '{drug_direction}'
  AND none(
    source IN coalesce(drug_binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(drug_effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def anatomy_cell_part_localization_cypher(mode: str) -> str:
    modes = {
        "gof_corrective": ("gain_of_function_variant_form", "decreased"),
        "gof_worsening": ("gain_of_function_variant_form", "increased"),
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown anatomy cell-part localization mode: {mode}"
        ) from error

    return f"""
MATCH (subject:Drug)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (target:Gene)
MATCH (subject)-[effect:AFFECTS]->(target)
MATCH (target)-[association:ASSOCIATED_WITH]->(object:Disease)
MATCH (target)-[expression:EXPRESSED_IN]->(cell:Cell)
MATCH (anatomy:AnatomicalEntity)-[part:HAS_PART]->(cell)
MATCH (object)-[:LOCATED_IN|OCCURS_IN]->(anatomy)
WHERE 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:bgee' IN coalesce(expression.primary_knowledge_sources, [])
  AND 'infores:semmeddb' IN coalesce(part.primary_knowledge_sources, [])
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def cell_localized_target_cypher(mode: str) -> str:
    if mode == "direct":
        context_match = """
MATCH (gene)-[expression:EXPRESSED_IN]->(cell:Cell)
MATCH (object)-[:LOCATED_IN|OCCURS_IN]->(cell)
""".strip()
        context_conditions: list[str] = []
    elif mode == "direct_top_three":
        context_match = """
MATCH (gene)-[expression:EXPRESSED_IN]->(cell:Cell)
MATCH (object)-[:LOCATED_IN|OCCURS_IN]->(cell)
""".strip()
        context_conditions = ["evidence._miner_disease_rank <= 3"]
    elif mode == "ontology_median":
        context_match = """
MATCH (gene)-[expression:EXPRESSED_IN]->(cell:Cell)
MATCH (cell)-[:SUBCLASS_OF*1..2]->(anatomy:AnatomicalEntity)
MATCH (object)-[:LOCATED_IN|OCCURS_IN]->(anatomy)
""".strip()
        context_conditions = ["cell._miner_human_gene_expression_degree <= 5512"]
    else:
        raise ValueError(f"Unknown cell-localized target mode: {mode}")

    extra_conditions = "".join(
        f"\n  AND {condition}" for condition in context_conditions
    )
    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(gene:Gene)
MATCH (subject)-[effect:AFFECTS]->(gene)
MATCH (gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(object:Disease)
{context_match}
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = 'decreased'
  AND 'infores:bgee' IN coalesce(expression.primary_knowledge_sources, [])
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'{extra_conditions}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def causal_module_coverage_cypher(mode: str) -> str:
    phenotype_gate = mode.endswith("_phenotype_gated")
    mode_without_phenotype = mode.removesuffix("_phenotype_gated")
    adverse_gate = mode_without_phenotype.endswith("_adverse_gated")
    base_mode = mode_without_phenotype.removesuffix("_adverse_gated")
    context_match = ""
    context_condition = ""
    context_group = ""
    if base_mode == "top_three_two":
        rank_condition = "evidence._miner_disease_rank <= 3"
        minimum_targets = 2
    elif base_mode == "top_five_three":
        rank_condition = "evidence._miner_disease_rank <= 5"
        minimum_targets = 3
    elif base_mode == "top_three_two_process":
        rank_condition = "evidence._miner_disease_rank <= 3"
        minimum_targets = 2
        context_match = """
MATCH (gene)-[:INVOLVED_IN]->(context:BiologicalProcess)
"""
        context_condition = "\n  AND context._miner_gene_member_degree <= 100"
        context_group = ", context"
    elif base_mode == "top_three_two_component":
        rank_condition = "evidence._miner_disease_rank <= 3"
        minimum_targets = 2
        context_match = """
MATCH (gene)-[:PART_OF]->(context:CellularComponent)
"""
        context_condition = (
            "\n  AND context._miner_component_gene_member_degree <= 54"
        )
        context_group = ", context"
    elif base_mode == "lower_rank_two":
        rank_condition = (
            "evidence._miner_disease_rank >= 4 "
            "AND evidence._miner_disease_rank <= 10"
        )
        minimum_targets = 2
    else:
        raise ValueError(f"Unknown causal module coverage mode: {mode}")

    adverse_condition = ""
    if adverse_gate:
        adverse_condition = """
  AND NOT EXISTS {
    MATCH (subject)-[:CONTRAINDICATED_IN|EXACERBATES_CONDITION|CAUSES]->(object)
  }
"""
    phenotype_condition = ""
    if phenotype_gate:
        phenotype_condition = """
  AND NOT EXISTS {
    MATCH (subject)-[:HAS_SIDE_EFFECT]->(:PhenotypicFeature)
          <-[:HAS_PHENOTYPE]-(object)
  }
"""
    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(gene:Gene)
MATCH (subject)-[effect:AFFECTS]->(gene)
MATCH (gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(object:Disease)
{context_match}
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = 'decreased'
  AND {rank_condition}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'{context_condition}{adverse_condition}{phenotype_condition}
WITH subject, object{context_group}, count(DISTINCT gene) AS targeted_genes
WHERE targeted_genes >= {minimum_targets}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def causal_module_provenance_cypher(mode: str) -> str:
    manifestation_gated = mode.endswith("_manifestation_gated")
    mode = mode.removesuffix("_manifestation_gated")
    unopposed = "_unopposed_" in mode
    mode = mode.replace("_unopposed_", "_")
    if mode.endswith("_top_three"):
        provenance_mode = mode.removesuffix("_top_three")
        rank_condition = "evidence._miner_disease_rank <= 3"
        minimum_targets = 2
    elif mode.endswith("_top_five"):
        provenance_mode = mode.removesuffix("_top_five")
        rank_condition = "evidence._miner_disease_rank <= 5"
        minimum_targets = 3
    else:
        raise ValueError(f"Unknown causal module provenance mode: {mode}")

    opposite_condition = ""
    if unopposed:
        opposite_condition = """
  AND NOT EXISTS {
    MATCH (subject)-[opposite:AFFECTS]->(gene)
    WHERE opposite.qualified_predicate = 'biolink:causes'
      AND opposite.object_aspect_qualifier = 'activity_or_abundance'
      AND opposite.object_direction_qualifier = 'increased'
  }
"""
    provenance_condition = ""
    provenance_aggregation = ""
    if provenance_mode == "repeated_evidence":
        provenance_condition = """
  AND coalesce(
        effect.evidence_count,
        size(coalesce(effect.publications, [])),
        1
      ) >= 2
"""
    elif provenance_mode == "distinct_publications":
        provenance_aggregation = """
UNWIND coalesce(effect.publications, []) AS publication
WITH subject, object, gene,
     collect(DISTINCT publication) AS provenance_values
WHERE size(provenance_values) >= 2
"""
    elif provenance_mode == "multisource_binding":
        provenance_aggregation = """
UNWIND coalesce(binding.primary_knowledge_sources, []) AS binding_source
WITH subject, object, gene,
     collect(DISTINCT binding_source) AS provenance_values
WHERE size(provenance_values) >= 2
"""
    elif provenance_mode == "signor_effect":
        provenance_condition = """
  AND 'infores:signor' IN coalesce(effect.primary_knowledge_sources, [])
"""
    elif provenance_mode == "evidence_binding_consensus":
        provenance_condition = """
  AND coalesce(
        effect.evidence_count,
        size(coalesce(effect.publications, [])),
        1
      ) >= 2
"""
        provenance_aggregation = """
UNWIND coalesce(binding.primary_knowledge_sources, []) AS binding_source
WITH subject, object, gene,
     collect(DISTINCT binding_source) AS provenance_values
WHERE size(provenance_values) >= 2
"""
    else:
        raise ValueError(f"Unknown causal module provenance mode: {mode}")

    manifestation_condition = ""
    if manifestation_gated:
        manifestation_condition = """
  AND NOT EXISTS {
    MATCH (subject)-[:HAS_SIDE_EFFECT]->(:NamedThing)
          -[:MANIFESTATION_OF]->(object)
  }
"""

    return f"""
MATCH (subject:Drug)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (gene:Gene)
MATCH (subject)-[effect:AFFECTS]->(gene)
MATCH (gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(object:Disease)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = 'decreased'
  AND {rank_condition}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'{opposite_condition}{provenance_condition}
{provenance_aggregation}
WITH subject, object, count(DISTINCT gene) AS targeted_genes
WHERE targeted_genes >= {minimum_targets}{manifestation_condition}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def disease_module_central_target_cypher(mode: str) -> str:
    modes = {
        "top_three_two_neighbors": (1, 3, False),
        "top_three_two_neighbors_consensus": (1, 3, True),
        "lower_rank_two_neighbors_consensus": (4, 10, True),
    }
    try:
        minimum_rank, maximum_rank, require_consensus = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown disease module central target mode: {mode}"
        ) from error

    evidence_condition = ""
    binding_condition = ""
    if require_consensus:
        evidence_condition = """
  AND coalesce(
        effect.evidence_count,
        size(coalesce(effect.publications, [])),
        1
      ) >= 2
"""
        binding_condition = """
WITH subject, target, object, neighbors,
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
     ) AS binding_sources
WHERE size(binding_sources) >= 2
"""

    return f"""
MATCH (subject:Drug)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (target:Gene)
MATCH (subject)-[effect:AFFECTS]->(target)
MATCH (target)-[target_evidence:MINER_GENE_DISEASE_EVIDENCE]->
      (object:Disease)
MATCH (target)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]-(neighbor:Gene)
      -[neighbor_evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
WHERE target <> neighbor
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = 'decreased'{evidence_condition}
  AND target_evidence._miner_disease_rank >= {minimum_rank}
  AND target_evidence._miner_disease_rank <= {maximum_rank}
  AND neighbor_evidence._miner_disease_rank <= 10
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
WITH subject, target, object,
     collect(DISTINCT neighbor) AS neighbors,
     collect(DISTINCT binding) AS bindings
WHERE size(neighbors) >= 2
{binding_condition}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def signed_process_correction_cypher(mode: str) -> str:
    cross_channel = mode.startswith("cross_")
    base_mode = mode.removeprefix("cross_").removeprefix("direct_")
    modes = {
        "gof_corrective": ("gain_of_function_variant_form", "decreased"),
        "gof_worsening": ("gain_of_function_variant_form", "increased"),
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = modes[base_mode]
    except KeyError as error:
        raise ValueError(f"Unknown signed process correction mode: {mode}") from error

    target_match = ""
    target_conditions = ""
    if cross_channel:
        target_match = """
MATCH (subject)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target:Gene)
MATCH (subject)-[target_effect:AFFECTS]->(target)
MATCH (target)-[:INVOLVED_IN]->(process)
"""
        target_conditions = f"""
  AND target <> driver
  AND target_effect.qualified_predicate = 'biolink:causes'
  AND target_effect.object_aspect_qualifier = 'activity_or_abundance'
  AND target_effect.object_direction_qualifier = '{direction}'
"""

    return f"""
MATCH (subject:Drug)-[process_effect:AFFECTS]->
      (process:BiologicalProcess)
MATCH (driver:Gene)-[:INVOLVED_IN]->(process)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
{target_match}
WHERE process_effect.qualified_predicate = 'biolink:causes'
  AND process_effect.object_direction_qualifier = '{direction}'
  AND 'infores:ctd' IN
      coalesce(process_effect.primary_knowledge_sources, [])
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND process._miner_gene_member_degree <= 100
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'{target_conditions}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def ortholog_phenotype_direction_cypher(mode: str) -> str:
    no_opposite = mode.endswith("_no_opposite")
    base_mode = mode.removesuffix("_no_opposite")
    modes = {
        "gof_corrective": ("gain_of_function_variant_form", "decreased"),
        "gof_worsening": ("gain_of_function_variant_form", "increased"),
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = modes[base_mode]
    except KeyError as error:
        raise ValueError(f"Unknown ortholog phenotype direction mode: {mode}") from error

    opposite_condition = ""
    if no_opposite:
        opposite_direction = "increased" if direction == "decreased" else "decreased"
        opposite_condition = f"""
  AND NOT EXISTS {{
    MATCH (subject)-[opposite:AFFECTS]->(human_gene)
    WHERE opposite.qualified_predicate = 'biolink:causes'
      AND opposite.object_aspect_qualifier = 'activity_or_abundance'
      AND opposite.object_direction_qualifier = '{opposite_direction}'
  }}
"""

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (human_gene:Gene)
MATCH (subject)-[effect:AFFECTS]->(human_gene)
MATCH (human_gene)-[association:ASSOCIATED_WITH]->(object:Disease)
MATCH (human_gene)-[:ORTHOLOGOUS_TO]-(mouse_gene:Gene)
      -[model_evidence:HAS_PHENOTYPE]->(phenotype:PhenotypicFeature)
      <-[:HAS_PHENOTYPE]-(object)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND 'NCBITaxon:9606' IN coalesce(human_gene.in_taxon, [])
  AND 'NCBITaxon:10090' IN coalesce(mouse_gene.in_taxon, [])
  AND 'infores:mgi' IN
      coalesce(model_evidence.primary_knowledge_sources, [])
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'{opposite_condition}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def molecular_activity_correction_cypher(mode: str) -> str:
    modes = {
        "gof_corrective": ("gain_of_function_variant_form", "decreased"),
        "gof_worsening": ("gain_of_function_variant_form", "increased"),
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = modes[mode]
    except KeyError as error:
        raise ValueError(f"Unknown molecular activity correction mode: {mode}") from error

    return f"""
MATCH (subject:Drug)-[effect:AFFECTS]->(activity:MolecularActivity)
      <-[:ENABLES]-(driver:Gene)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:ctd' IN coalesce(effect.primary_knowledge_sources, [])
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND activity._miner_gene_enable_degree <= 58
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def signed_regulatory_cascade_cypher(mode: str) -> str:
    modes = {
        "gof_corrective": (
            "gain_of_function_variant_form",
            (("decreased", "upregulated"), ("increased", "downregulated")),
        ),
        "gof_worsening": (
            "gain_of_function_variant_form",
            (("increased", "upregulated"), ("decreased", "downregulated")),
        ),
        "lof_corrective": (
            "loss_of_function_variant_form",
            (("increased", "upregulated"), ("decreased", "downregulated")),
        ),
        "lof_worsening": (
            "loss_of_function_variant_form",
            (("decreased", "upregulated"), ("increased", "downregulated")),
        ),
    }
    try:
        variant_form, sign_pairs = modes[mode]
    except KeyError as error:
        raise ValueError(f"Unknown signed regulatory cascade mode: {mode}") from error

    sign_condition = " OR\n    ".join(
        (
            f"(drug_effect.object_direction_qualifier = '{drug_direction}' "
            "AND gene_effect.object_direction_qualifier = "
            f"'{gene_direction}')"
        )
        for drug_direction, gene_direction in sign_pairs
    )
    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (regulator:Gene)
MATCH (subject)-[drug_effect:AFFECTS]->(regulator)
MATCH (regulator)-[gene_effect:REGULATES]->(driver:Gene)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
MATCH (driver)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
WHERE regulator <> driver
  AND drug_effect.qualified_predicate = 'biolink:causes'
  AND drug_effect.object_aspect_qualifier = 'activity_or_abundance'
  AND gene_effect.qualified_predicate = 'biolink:causes'
  AND 'infores:signor' IN
      coalesce(gene_effect.primary_knowledge_sources, [])
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND evidence._miner_disease_rank <= 3
  AND (
    {sign_condition}
  )
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def multi_driver_connector_cypher(mode: str) -> str:
    modes = {
        "decreased": ("decreased", None, False),
        "increased_control": ("increased", None, False),
        "decreased_compact": ("decreased", 10, False),
        "decreased_process": ("decreased", None, True),
    }
    try:
        direction, maximum_degree, process_localized = modes[mode]
    except KeyError as error:
        raise ValueError(f"Unknown multi-driver connector mode: {mode}") from error

    process_match = ""
    process_condition = ""
    process_group = ""
    if process_localized:
        process_match = """
MATCH (target)-[:INVOLVED_IN]->(process:BiologicalProcess)
      <-[:INVOLVED_IN]-(driver)
"""
        process_condition = "\n  AND process._miner_gene_member_degree <= 100"
        process_group = ", process"
    degree_condition = ""
    if maximum_degree is not None:
        degree_condition = f"""
  AND COUNT {{
    (target)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]-(:Gene)
  }} <= {maximum_degree}
"""
    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target:Gene)
MATCH (subject)-[effect:AFFECTS]->(target)
MATCH (target)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]-(driver:Gene)
{process_match}
MATCH (driver)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(object:Disease)
WHERE target <> driver
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND evidence._miner_disease_rank <= 3{process_condition}{degree_condition}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
WITH subject, target, object{process_group}, collect(DISTINCT driver) AS drivers
WHERE size(drivers) >= 2
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def dual_target_dual_driver_connector_cypher(mode: str) -> str:
    modes = {
        "decreased": ("decreased", False),
        "increased_control": ("increased", False),
        "decreased_process": ("decreased", True),
    }
    try:
        direction, require_process = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown dual-target dual-driver connector mode: {mode}"
        ) from error

    process_match = ""
    process_condition = ""
    if require_process:
        process_match = """
MATCH (driver1)-[:INVOLVED_IN]->(process:BiologicalProcess)
      <-[:INVOLVED_IN]-(driver2)
"""
        process_condition = "\n  AND process._miner_gene_member_degree <= 100"

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target1:Gene)
MATCH (subject)-[effect1:AFFECTS]->(target1)
MATCH (target1)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]-(driver1:Gene)
MATCH (driver1)-[evidence1:MINER_GENE_DISEASE_EVIDENCE]->(object:Disease)
MATCH (subject)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target2:Gene)
MATCH (subject)-[effect2:AFFECTS]->(target2)
MATCH (target2)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]-(driver2:Gene)
MATCH (driver2)-[evidence2:MINER_GENE_DISEASE_EVIDENCE]->(object)
{process_match}WHERE target1.id < target2.id
  AND driver1.id < driver2.id
  AND target1 <> driver1
  AND target2 <> driver2
  AND effect1.qualified_predicate = 'biolink:causes'
  AND effect1.object_aspect_qualifier = 'activity_or_abundance'
  AND effect1.object_direction_qualifier = '{direction}'
  AND effect2.qualified_predicate = 'biolink:causes'
  AND effect2.object_aspect_qualifier = 'activity_or_abundance'
  AND effect2.object_direction_qualifier = '{direction}'
  AND evidence1._miner_disease_rank <= 3
  AND evidence2._miner_disease_rank <= 3{process_condition}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def phenotype_therapeutic_decomposition_cypher(mode: str) -> str:
    adverse_condition = ""
    if mode == "base":
        phenotype_condition = ""
    elif mode == "specific":
        phenotype_condition = "\n  AND phenotype._miner_disease_member_degree <= 34"
    elif mode == "specific_adverse_gated":
        phenotype_condition = "\n  AND phenotype._miner_disease_member_degree <= 34"
        adverse_condition = """
  AND NOT EXISTS {
    MATCH (subject)-[:CONTRAINDICATED_IN|EXACERBATES_CONDITION|CAUSES]->(object)
  }
"""
    elif mode == "specific_contraindication_gated":
        phenotype_condition = "\n  AND phenotype._miner_disease_member_degree <= 34"
        adverse_condition = """
  AND NOT EXISTS {
    MATCH (subject)-[:CONTRAINDICATED_IN|EXACERBATES_CONDITION]->(object)
  }
"""
    else:
        raise ValueError(
            f"Unknown phenotype therapeutic decomposition mode: {mode}"
        )

    return f"""
MATCH (subject:Drug)-[symptom_treatment:TREATS]->
      (phenotype:PhenotypicFeature)
      <-[:HAS_PHENOTYPE]-(object:Disease)
MATCH (subject)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(gene:Gene)
MATCH (subject)-[effect:AFFECTS]->(gene)
MATCH (gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
WHERE none(
    source IN coalesce(symptom_treatment.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = 'decreased'
  AND evidence._miner_disease_rank <= 3{phenotype_condition}
{adverse_condition}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def transporter_tissue_delivery_cypher(mode: str = "base") -> str:
    if mode == "base":
        efflux_condition = ""
    elif mode == "no_efflux":
        efflux_condition = """
  AND NOT EXISTS {
    MATCH (transporter)-[:ENABLES]->(:MolecularActivity)
          -[:SUBCLASS_OF*0..5]->
          (:MolecularActivity {id: 'GO:0015562'})
  }
"""
    else:
        raise ValueError(f"Unknown transporter tissue delivery mode: {mode}")

    return f"""
MATCH (transporter:Gene)-[:HAS_SUBSTRATE]->(subject:Drug)
MATCH (transporter)-[:ENABLES]->(activity:MolecularActivity)
      -[:SUBCLASS_OF*0..5]->(:MolecularActivity {{id: 'GO:0005215'}})
MATCH (subject)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target:Gene)
MATCH (subject)-[effect:AFFECTS]->(target)
MATCH (target)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(object:Disease)
MATCH (transporter)-[transport_expression:EXPRESSED_IN]->
      (anatomy:AnatomicalEntity)
      <-[target_expression:EXPRESSED_IN]-(target)
MATCH (object)-[:LOCATED_IN|OCCURS_IN]->(anatomy)
WHERE transporter <> target
  AND 'NCBITaxon:9606' IN coalesce(transporter.in_taxon, [])
  AND 'NCBITaxon:9606' IN coalesce(target.in_taxon, [])
{efflux_condition}
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = 'decreased'
  AND evidence._miner_disease_rank <= 3
  AND 'infores:bgee' IN
      coalesce(transport_expression.primary_knowledge_sources, [])
  AND 'infores:bgee' IN
      coalesce(target_expression.primary_knowledge_sources, [])
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def direct_abundance_correction_cypher(mode: str) -> str:
    modes = {
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = modes[mode]
    except KeyError as error:
        raise ValueError(f"Unknown direct abundance correction mode: {mode}") from error

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver:Gene)
MATCH (subject)-[effect:AFFECTS]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def direct_splicing_rescue_cypher() -> str:
    return """
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver:Gene)
MATCH (subject)-[effect:AFFECTS]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'splicing'
  AND 'infores:ctd' IN coalesce(effect.primary_knowledge_sources, [])
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier =
      'loss_of_function_variant_form'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def direct_activity_correction_cypher(mode: str) -> str:
    modes = {
        "gof_corrective": ("gain_of_function_variant_form", "decreased"),
        "gof_worsening": ("gain_of_function_variant_form", "increased"),
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = modes[mode]
    except KeyError as error:
        raise ValueError(f"Unknown direct activity correction mode: {mode}") from error

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver:Gene)
MATCH (subject)-[effect:AFFECTS]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def activity_class_correction_cypher(mode: str) -> str:
    require_multisource = mode.endswith("_multisource")
    mode = mode.removesuffix("_multisource")
    modes = {
        "gof_voltage_corrective": (
            "gain_of_function_variant_form",
            "decreased",
            "GO:0005244",
        ),
        "gof_voltage_worsening": (
            "gain_of_function_variant_form",
            "increased",
            "GO:0005244",
        ),
        "lof_catalytic_corrective": (
            "loss_of_function_variant_form",
            "increased",
            "GO:0003824",
        ),
        "lof_catalytic_worsening": (
            "loss_of_function_variant_form",
            "decreased",
            "GO:0003824",
        ),
        "gof_kinase_corrective": (
            "gain_of_function_variant_form",
            "decreased",
            "GO:0016301",
        ),
        "gof_kinase_worsening": (
            "gain_of_function_variant_form",
            "increased",
            "GO:0016301",
        ),
        "gof_gtpase_corrective": (
            "gain_of_function_variant_form",
            "decreased",
            "GO:0003924",
        ),
        "gof_gtpase_worsening": (
            "gain_of_function_variant_form",
            "increased",
            "GO:0003924",
        ),
        "gof_gprotein_corrective": (
            "gain_of_function_variant_form",
            "decreased",
            "GO:0003925",
        ),
        "gof_gprotein_worsening": (
            "gain_of_function_variant_form",
            "increased",
            "GO:0003925",
        ),
        "lof_receptor_corrective": (
            "loss_of_function_variant_form",
            "increased",
            "GO:0004888",
        ),
        "lof_receptor_worsening": (
            "loss_of_function_variant_form",
            "decreased",
            "GO:0004888",
        ),
    }
    try:
        variant_form, direction, activity_root = modes[mode]
    except KeyError as error:
        raise ValueError(f"Unknown activity class correction mode: {mode}") from error

    provenance_aggregation = ""
    if require_multisource:
        provenance_aggregation = """
UNWIND coalesce(effect.primary_knowledge_sources, []) AS effect_source
WITH subject, driver, object, count(DISTINCT effect_source) AS effect_source_count
WHERE effect_source_count >= 2
"""
    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver:Gene)
MATCH (subject)-[effect:AFFECTS]->(driver)
MATCH (driver)-[:ENABLES]->(:MolecularActivity)
      -[:SUBCLASS_OF*0..5]->
      (:MolecularActivity {{id: '{activity_root}'}})
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
{provenance_aggregation}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def mutant_form_correction_cypher(mode: str) -> str:
    modes = {
        "gof_corrective": "decreased",
        "gof_worsening": "increased",
    }
    try:
        direction = modes[mode]
    except KeyError as error:
        raise ValueError(f"Unknown mutant-form correction mode: {mode}") from error

    return f"""
MATCH (subject:Drug)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (driver:Gene)
MATCH (subject)-[effect:AFFECTS]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE binding.object_form_or_variant_qualifier = 'mutant_form'
  AND effect.object_form_or_variant_qualifier = 'mutant_form'
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier =
      'gain_of_function_variant_form'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def pharmacologic_mechanism_correction_cypher(mode: str) -> str:
    negative_mechanisms = [
        "inhibition",
        "antagonism",
        "molecular_channel_blockage",
        "antibody_inhibition",
        "inverse_agonism",
        "negative_modulation",
        "negative_allosteric_modulation",
        "gating_inhibition",
        "competitive_inhibition",
        "antisense_oligonucleotide_inhibition",
    ]
    positive_mechanisms = [
        "agonism",
        "partial_agonism",
        "positive_modulation",
        "positive_allosteric_modulation",
        "activation",
        "potentiation",
        "opening",
        "molecular_channel_opening",
    ]
    modes = {
        "gof_corrective": (
            "gain_of_function_variant_form",
            "decreased",
            negative_mechanisms,
        ),
        "gof_worsening": (
            "gain_of_function_variant_form",
            "increased",
            positive_mechanisms,
        ),
        "lof_corrective": (
            "loss_of_function_variant_form",
            "increased",
            positive_mechanisms,
        ),
        "lof_worsening": (
            "loss_of_function_variant_form",
            "decreased",
            negative_mechanisms,
        ),
        "lof_activation_only": (
            "loss_of_function_variant_form",
            "increased",
            ["activation"],
        ),
        "gof_activation_only_control": (
            "gain_of_function_variant_form",
            "increased",
            ["activation"],
        ),
        "lof_opening_only": (
            "loss_of_function_variant_form",
            "increased",
            ["opening"],
        ),
        "gof_opening_only_control": (
            "gain_of_function_variant_form",
            "increased",
            ["opening"],
        ),
        "gof_antibody_inhibition_only": (
            "gain_of_function_variant_form",
            "decreased",
            ["antibody_inhibition"],
        ),
        "lof_antibody_inhibition_control": (
            "loss_of_function_variant_form",
            "decreased",
            ["antibody_inhibition"],
        ),
    }
    try:
        variant_form, direction, mechanisms = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown pharmacologic mechanism correction mode: {mode}"
        ) from error

    mechanisms_literal = ", ".join(f"'{mechanism}'" for mechanism in mechanisms)
    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver:Gene)
MATCH (subject)-[effect:AFFECTS]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity'
  AND effect.object_direction_qualifier = '{direction}'
  AND effect.causal_mechanism_qualifier IN [{mechanisms_literal}]
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def downstream_interception_cypher(mode: str) -> str:
    modes = {
        "gof_corrective": ("gain_of_function_variant_form", True, None, False),
        "gof_worsening": ("gain_of_function_variant_form", False, None, False),
        "lof_corrective": ("loss_of_function_variant_form", False, None, False),
        "lof_worsening": ("loss_of_function_variant_form", True, None, False),
        "gof_up_corrective": (
            "gain_of_function_variant_form",
            True,
            "upregulated",
            False,
        ),
        "gof_down_corrective": (
            "gain_of_function_variant_form",
            True,
            "downregulated",
            False,
        ),
        "lof_up_corrective": (
            "loss_of_function_variant_form",
            False,
            "upregulated",
            False,
        ),
        "lof_down_corrective": (
            "loss_of_function_variant_form",
            False,
            "downregulated",
            False,
        ),
        "gof_up_worsening": (
            "gain_of_function_variant_form",
            False,
            "upregulated",
            False,
        ),
        "gof_down_worsening": (
            "gain_of_function_variant_form",
            False,
            "downregulated",
            False,
        ),
        "lof_up_worsening": (
            "loss_of_function_variant_form",
            True,
            "upregulated",
            False,
        ),
        "lof_down_worsening": (
            "loss_of_function_variant_form",
            True,
            "downregulated",
            False,
        ),
        "lof_down_multisource_corrective": (
            "loss_of_function_variant_form",
            False,
            "downregulated",
            True,
        ),
        "lof_down_multisource_worsening": (
            "loss_of_function_variant_form",
            True,
            "downregulated",
            True,
        ),
    }
    try:
        (
            variant_form,
            oppose_regulation,
            regulation_direction,
            require_multisource_binding,
        ) = modes[mode]
    except KeyError as error:
        raise ValueError(f"Unknown downstream interception mode: {mode}") from error

    if oppose_regulation:
        expected_effect = """
CASE regulation.object_direction_qualifier
  WHEN 'upregulated' THEN 'decreased'
  ELSE 'increased'
END
""".strip()
    else:
        expected_effect = """
CASE regulation.object_direction_qualifier
  WHEN 'upregulated' THEN 'increased'
  ELSE 'decreased'
END
""".strip()

    regulation_direction_condition = ""
    if regulation_direction is not None:
        regulation_direction_condition = (
            "\n  AND regulation.object_direction_qualifier = "
            f"'{regulation_direction}'"
        )

    provenance_aggregation = ""
    if require_multisource_binding:
        provenance_aggregation = """
WITH subject, object, collect(DISTINCT binding) AS bindings
WITH subject, object,
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
     ) AS binding_sources
WHERE size(binding_sources) >= 2
"""

    return f"""
MATCH (driver:Gene)-[regulation:REGULATES]->(effector:Gene)
MATCH (subject:Drug)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(effector)
MATCH (subject)-[effect:AFFECTS]->(effector)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE driver <> effector
  AND 'infores:signor' IN
      coalesce(regulation.primary_knowledge_sources, [])
  AND regulation.qualified_predicate = 'biolink:causes'
  AND regulation.object_direction_qualifier IN
      ['upregulated', 'downregulated']{regulation_direction_condition}
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = {expected_effect}
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
{provenance_aggregation}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def protein_turnover_correction_cypher(mode: str) -> str:
    modes = {
        "gof_degradation_corrective": (
            "gain_of_function_variant_form",
            "degradation",
            "increased",
        ),
        "gof_stability_corrective": (
            "gain_of_function_variant_form",
            "stability",
            "decreased",
        ),
        "lof_degradation_corrective": (
            "loss_of_function_variant_form",
            "degradation",
            "decreased",
        ),
        "lof_degradation_worsening": (
            "loss_of_function_variant_form",
            "degradation",
            "increased",
        ),
        "lof_secretion_corrective": (
            "loss_of_function_variant_form",
            "secretion",
            "increased",
        ),
        "lof_secretion_worsening": (
            "loss_of_function_variant_form",
            "secretion",
            "decreased",
        ),
    }
    try:
        variant_form, aspect, direction = modes[mode]
    except KeyError as error:
        raise ValueError(f"Unknown protein turnover correction mode: {mode}") from error

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver:Gene)
MATCH (subject)-[effect:AFFECTS]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = '{aspect}'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def allele_expression_correction_cypher(mode: str) -> str:
    modes = {
        "ad_gof_decrease": (
            "gain_of_function_variant_form",
            "HP:0000006",
            "decreased",
            False,
        ),
        "ad_gof_increase": (
            "gain_of_function_variant_form",
            "HP:0000006",
            "increased",
            False,
        ),
        "ad_dominant_negative_decrease": (
            "dominant_negative_variant_form",
            "HP:0000006",
            "decreased",
            False,
        ),
        "ad_dominant_negative_increase": (
            "dominant_negative_variant_form",
            "HP:0000006",
            "increased",
            False,
        ),
        "ad_lof_increase": (
            "loss_of_function_variant_form",
            "HP:0000006",
            "increased",
            False,
        ),
        "ad_lof_decrease": (
            "loss_of_function_variant_form",
            "HP:0000006",
            "decreased",
            False,
        ),
        "ar_lof_increase": (
            "loss_of_function_variant_form",
            "HP:0000007",
            "increased",
            False,
        ),
        "ar_lof_decrease": (
            "loss_of_function_variant_form",
            "HP:0000007",
            "decreased",
            False,
        ),
        "ad_gof_decrease_unopposed": (
            "gain_of_function_variant_form",
            "HP:0000006",
            "decreased",
            True,
        ),
        "ad_gof_increase_unopposed": (
            "gain_of_function_variant_form",
            "HP:0000006",
            "increased",
            True,
        ),
        "ad_dominant_negative_decrease_unopposed": (
            "dominant_negative_variant_form",
            "HP:0000006",
            "decreased",
            True,
        ),
        "ad_dominant_negative_increase_unopposed": (
            "dominant_negative_variant_form",
            "HP:0000006",
            "increased",
            True,
        ),
    }
    try:
        variant_form, allelic_requirement, direction, exclude_opposite = modes[mode]
    except KeyError as error:
        raise ValueError(f"Unknown allele expression correction mode: {mode}") from error

    opposite_condition = ""
    if exclude_opposite:
        opposite_direction = "increased" if direction == "decreased" else "decreased"
        opposite_condition = f"""
  AND NOT EXISTS {{
    MATCH (subject)-[opposite_effect:AFFECTS]->(driver)
    WHERE opposite_effect.qualified_predicate = 'biolink:causes'
      AND opposite_effect.object_aspect_qualifier = 'expression'
      AND opposite_effect.object_direction_qualifier = '{opposite_direction}'
  }}
"""

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver:Gene)
MATCH (subject)-[effect:AFFECTS]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'expression'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND association.allelic_requirement = '{allelic_requirement}'
{opposite_condition}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def epigenetic_expression_consensus_cypher() -> str:
    return """
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver:Gene)
MATCH (subject)-[methylation:AFFECTS]->(driver)
MATCH (subject)-[expression:AFFECTS]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE methylation.qualified_predicate = 'biolink:causes'
  AND methylation.object_aspect_qualifier = 'methylation'
  AND methylation.object_direction_qualifier = 'decreased'
  AND expression.qualified_predicate = 'biolink:causes'
  AND expression.object_aspect_qualifier = 'expression'
  AND expression.object_direction_qualifier = 'increased'
  AND methylation <> expression
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier =
      'loss_of_function_variant_form'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def functional_dosage_consensus_cypher(mode: str) -> str:
    directions = {
        "lof_corrective": "increased",
        "lof_worsening": "decreased",
    }
    try:
        direction = directions[mode]
    except KeyError as error:
        raise ValueError(f"Unknown functional dosage consensus mode: {mode}") from error

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver:Gene)
MATCH (subject)-[activity:AFFECTS]->(driver)
MATCH (subject)-[abundance:AFFECTS]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE activity.qualified_predicate = 'biolink:causes'
  AND activity.object_aspect_qualifier = 'activity'
  AND activity.object_direction_qualifier = '{direction}'
  AND abundance.qualified_predicate = 'biolink:causes'
  AND abundance.object_aspect_qualifier = 'abundance'
  AND abundance.object_direction_qualifier = '{direction}'
  AND activity <> abundance
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier =
      'loss_of_function_variant_form'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def dominant_negative_activity_cypher(mode: str) -> str:
    directions = {
        "corrective": "decreased",
        "worsening": "increased",
    }
    try:
        direction = directions[mode]
    except KeyError as error:
        raise ValueError(f"Unknown dominant-negative activity mode: {mode}") from error

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver:Gene)
MATCH (subject)-[effect:AFFECTS]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier =
      'dominant_negative_variant_form'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def phosphorylation_activity_consensus_cypher(mode: str) -> str:
    settings = {
        "gof_corrective": (
            "gain_of_function_variant_form",
            "decreased",
            "decreased",
            False,
        ),
        "gof_unopposed": (
            "gain_of_function_variant_form",
            "decreased",
            "decreased",
            True,
        ),
        "gof_discordant": (
            "gain_of_function_variant_form",
            "decreased",
            "increased",
            False,
        ),
        "lof_corrective": (
            "loss_of_function_variant_form",
            "increased",
            "increased",
            False,
        ),
        "lof_worsening": (
            "loss_of_function_variant_form",
            "decreased",
            "decreased",
            False,
        ),
    }
    try:
        (
            variant_form,
            activity_direction,
            phosphorylation_direction,
            exclude_opposite_phosphorylation,
        ) = settings[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown phosphorylation-activity consensus mode: {mode}"
        ) from error

    opposite_phosphorylation = (
        """
  AND NOT EXISTS {
    MATCH (subject)-[opposite:AFFECTS]->(driver)
    WHERE opposite.qualified_predicate = 'biolink:causes'
      AND opposite.object_aspect_qualifier = 'phosphorylation'
      AND opposite.object_direction_qualifier = 'increased'
  }
"""
        if exclude_opposite_phosphorylation
        else ""
    )

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver:Gene)
MATCH (subject)-[activity:AFFECTS]->(driver)
MATCH (subject)-[phosphorylation:AFFECTS]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE activity.qualified_predicate = 'biolink:causes'
  AND activity.object_aspect_qualifier = 'activity'
  AND activity.object_direction_qualifier = '{activity_direction}'
  AND phosphorylation.qualified_predicate = 'biolink:causes'
  AND phosphorylation.object_aspect_qualifier = 'phosphorylation'
  AND phosphorylation.object_direction_qualifier = '{phosphorylation_direction}'
  AND activity <> phosphorylation
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
{opposite_phosphorylation.rstrip()}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def literature_allele_activity_correction_cypher(mode: str) -> str:
    settings = {
        "gof_corrective": ("gain_of_function_variant_form", "decreased"),
        "gof_worsening": ("gain_of_function_variant_form", "increased"),
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = settings[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown literature allele activity correction mode: {mode}"
        ) from error

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver:Gene)
MATCH (subject)-[effect:AFFECTS]->(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
MATCH (driver)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND evidence._miner_causal_publication_count >= 3
  AND evidence._miner_causal_publication_npmi >= 0.5
  AND evidence._miner_disease_rank <= 3
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def go_cam_input_flow_cypher(mode: str) -> str:
    settings = {
        "gof_corrective": ("gain_of_function_variant_form", "decreased"),
        "gof_worsening": ("gain_of_function_variant_form", "increased"),
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = settings[mode]
    except KeyError as error:
        raise ValueError(f"Unknown GO-CAM input-flow mode: {mode}") from error

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (upstream:Gene)
MATCH (subject)-[effect:AFFECTS]->(upstream)
MATCH (upstream)-[flow:IS_INPUT_OF]->(driver:Gene)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE upstream <> driver
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:go-cam' IN coalesce(flow.primary_knowledge_sources, [])
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def active_component_regulatory_cascade_cypher(mode: str) -> str:
    settings = {
        "gof_corrective": (
            "gain_of_function_variant_form",
            (("decreased", "upregulated"), ("increased", "downregulated")),
        ),
        "gof_worsening": (
            "gain_of_function_variant_form",
            (("increased", "upregulated"), ("decreased", "downregulated")),
        ),
        "lof_corrective": (
            "loss_of_function_variant_form",
            (("increased", "upregulated"), ("decreased", "downregulated")),
        ),
        "lof_worsening": (
            "loss_of_function_variant_form",
            (("decreased", "upregulated"), ("increased", "downregulated")),
        ),
    }
    try:
        variant_form, sign_pairs = settings[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown active-component regulatory cascade mode: {mode}"
        ) from error

    sign_condition = " OR\n    ".join(
        (
            f"(drug_effect.object_direction_qualifier = '{drug_direction}' "
            "AND gene_effect.object_direction_qualifier = "
            f"'{gene_direction}')"
        )
        for drug_direction, gene_direction in sign_pairs
    )
    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (regulator:Gene)
MATCH (subject)-[drug_effect:AFFECTS]->(regulator)
MATCH (regulator)-[gene_effect:REGULATES]->(driver:Gene)
MATCH (regulator)-[:ACTIVE_IN]->(component:CellularComponent)
      <-[:ACTIVE_IN]-(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE regulator <> driver
  AND drug_effect.qualified_predicate = 'biolink:causes'
  AND drug_effect.object_aspect_qualifier = 'activity_or_abundance'
  AND gene_effect.qualified_predicate = 'biolink:causes'
  AND 'infores:signor' IN
      coalesce(gene_effect.primary_knowledge_sources, [])
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND component._miner_component_active_gene_degree <= 185
  AND (
    {sign_condition}
  )
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def signed_go_process_restoration_cypher(mode: str) -> str:
    settings = {
        "gof_corrective": ("gain_of_function_variant_form", "corrective", None),
        "gof_worsening": ("gain_of_function_variant_form", "worsening", None),
        "lof_corrective": ("loss_of_function_variant_form", "corrective", None),
        "lof_worsening": ("loss_of_function_variant_form", "worsening", None),
        "lof_corrective_unopposed": (
            "loss_of_function_variant_form",
            "corrective",
            "worsening",
        ),
    }
    try:
        variant_form, required_path_mode, excluded_path_mode = settings[mode]
    except KeyError as error:
        raise ValueError(f"Unknown signed GO process restoration mode: {mode}") from error

    variant_sign = "1" if variant_form == "gain_of_function_variant_form" else "-1"
    exclusion = (
        f"\n  AND NOT '{excluded_path_mode}' IN path_modes"
        if excluded_path_mode is not None
        else ""
    )
    signed_process_types = """
      ['ACTS_UPSTREAM_OF_POSITIVE_EFFECT',
       'ACTS_UPSTREAM_OF_NEGATIVE_EFFECT',
       'ACTS_UPSTREAM_OF_OR_WITHIN_POSITIVE_EFFECT',
       'ACTS_UPSTREAM_OF_OR_WITHIN_NEGATIVE_EFFECT']""".strip()
    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target:Gene)
MATCH (subject)-[effect:AFFECTS]->(target)
MATCH (target)-[target_process]->(process:BiologicalProcess)
      <-[driver_process]-(driver:Gene)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE target <> driver
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier IN ['increased', 'decreased']
  AND type(target_process) IN {signed_process_types}
  AND type(driver_process) IN {signed_process_types}
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND process._miner_gene_member_degree <= 100
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
WITH subject, object,
     collect(DISTINCT
       CASE WHEN
         CASE effect.object_direction_qualifier
           WHEN 'increased' THEN 1 ELSE -1
         END *
         CASE WHEN type(target_process) CONTAINS 'POSITIVE'
           THEN 1 ELSE -1
         END
         <>
         {variant_sign} *
         CASE WHEN type(driver_process) CONTAINS 'POSITIVE'
           THEN 1 ELSE -1
         END
       THEN 'corrective' ELSE 'worsening' END
     ) AS path_modes
WHERE '{required_path_mode}' IN path_modes{exclusion}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def molecular_activity_complex_compensation_cypher(mode: str) -> str:
    settings = {
        "gof_corrective": ("gain_of_function_variant_form", "decreased"),
        "gof_worsening": ("gain_of_function_variant_form", "increased"),
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = settings[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown molecular activity complex compensation mode: {mode}"
        ) from error

    return f"""
MATCH (subject:Drug)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target:Gene)
MATCH (subject)-[effect:AFFECTS]->(target)
MATCH (target)-[:ENABLES]->(activity:MolecularActivity)
      <-[:ENABLES]-(driver:Gene)
MATCH (target)-[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]-(driver)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
MATCH (driver)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
WHERE target <> driver
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND evidence._miner_disease_rank <= 3
  AND activity._miner_gene_enable_degree <= 58
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def direct_disease_process_correction_cypher(mode: str) -> str:
    settings = {
        "disease_causes_process_decreased": ("disease_to_process", "decreased"),
        "disease_causes_process_increased": ("disease_to_process", "increased"),
        "process_causes_disease_decreased": ("process_to_disease", "decreased"),
        "process_causes_disease_increased": ("process_to_disease", "increased"),
    }
    try:
        orientation, direction = settings[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown direct disease-process correction mode: {mode}"
        ) from error

    if orientation == "disease_to_process":
        causal_match = (
            "MATCH (object:Disease)-[etiology:CAUSES]->"
            "(process:BiologicalProcess)"
        )
    else:
        causal_match = (
            "MATCH (process:BiologicalProcess)-[etiology:CAUSES]->"
            "(object:Disease)"
        )

    return f"""
{causal_match}
MATCH (subject:Drug)-[effect:AFFECTS]->(process)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:ctd' IN
      coalesce(effect.primary_knowledge_sources, [])
  AND 'infores:semmeddb' IN
      coalesce(etiology.primary_knowledge_sources, [])
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def etiologic_mediator_production_cypher(mode: str) -> str:
    directions = {
        "decreased": "decreased",
        "increased_control": "increased",
    }
    try:
        direction = directions[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown etiologic mediator production mode: {mode}"
        ) from error

    return f"""
MATCH (producer:Gene)-[production:PRODUCES]->
      (mediator:ChemicalEntity)-[etiology:CAUSES]->(object:Disease)
MATCH (producer)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
MATCH (subject:Drug)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (producer)
MATCH (subject)-[effect:AFFECTS]->(producer)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity'
  AND effect.object_direction_qualifier = '{direction}'
  AND evidence._miner_disease_rank <= 3
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def close_match_mechanism_transfer_cypher(mode: str) -> str:
    directions = {
        "decreased": "decreased",
        "increased_control": "increased",
    }
    try:
        direction = directions[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown close-match mechanism transfer mode: {mode}"
        ) from error

    return f"""
MATCH (subject:Drug)-[similarity:CLOSE_MATCH]-
      (comparator:ChemicalEntity)
MATCH (comparator)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->
      (gene:Gene)
MATCH (comparator)-[effect:AFFECTS]->(gene)
MATCH (gene)-[evidence:MINER_GENE_DISEASE_EVIDENCE]->(object:Disease)
WHERE subject <> comparator
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity'
  AND effect.object_direction_qualifier = '{direction}'
  AND evidence._miner_disease_rank <= 3
  AND 'infores:semmeddb' IN
      coalesce(similarity.primary_knowledge_sources, [])
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def variant_component_correction_cypher(mode: str) -> str:
    modes = {
        "gof_corrective": ("gain_of_function_variant_form", "decreased"),
        "gof_worsening": ("gain_of_function_variant_form", "increased"),
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown variant component correction mode: {mode}"
        ) from error

    return f"""
MATCH (subject:Drug)-[effect:AFFECTS]->(component:CellularComponent)
      <-[:PART_OF]-(driver:Gene)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
WHERE effect.qualified_predicate = 'biolink:causes'
  AND effect.object_direction_qualifier = '{direction}'
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def disrupted_process_variant_correction_cypher(mode: str) -> str:
    modes = {
        "gof_corrective": ("gain_of_function_variant_form", "decreased"),
        "gof_worsening": ("gain_of_function_variant_form", "increased"),
        "lof_corrective": ("loss_of_function_variant_form", "increased"),
        "lof_worsening": ("loss_of_function_variant_form", "decreased"),
    }
    try:
        variant_form, direction = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown disrupted process variant correction mode: {mode}"
        ) from error

    return f"""
MATCH (subject:Drug)-[disruption:DISRUPTS]->
      (process:BiologicalProcess)<-[:INVOLVED_IN]-(driver:Gene)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
MATCH (subject)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver)
MATCH (subject)-[effect:AFFECTS]->(driver)
WHERE 'infores:semmeddb' IN
      coalesce(disruption.primary_knowledge_sources, [])
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier IN ['activity', 'activity_or_abundance']
  AND effect.object_direction_qualifier = '{direction}'
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def disrupted_activity_variant_correction_cypher(mode: str) -> str:
    modes = {
        "gof_corrective": (
            "gain_of_function_variant_form",
            "decreased",
            (
                "effect.object_aspect_qualifier IN "
                "['activity', 'activity_or_abundance']"
            ),
        ),
        "gof_corrective_activity": (
            "gain_of_function_variant_form",
            "decreased",
            "effect.object_aspect_qualifier = 'activity'",
        ),
        "gof_corrective_activity_or_abundance": (
            "gain_of_function_variant_form",
            "decreased",
            "effect.object_aspect_qualifier = 'activity_or_abundance'",
        ),
        "gof_worsening": (
            "gain_of_function_variant_form",
            "increased",
            (
                "effect.object_aspect_qualifier IN "
                "['activity', 'activity_or_abundance']"
            ),
        ),
        "lof_corrective": (
            "loss_of_function_variant_form",
            "increased",
            (
                "effect.object_aspect_qualifier IN "
                "['activity', 'activity_or_abundance']"
            ),
        ),
        "lof_worsening": (
            "loss_of_function_variant_form",
            "decreased",
            (
                "effect.object_aspect_qualifier IN "
                "['activity', 'activity_or_abundance']"
            ),
        ),
    }
    try:
        variant_form, direction, aspect_condition = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown disrupted activity variant correction mode: {mode}"
        ) from error

    return f"""
MATCH (subject:Drug)-[disruption:DISRUPTS]->
      (activity:MolecularActivity)<-[:ENABLES]-(driver:Gene)
MATCH (driver)-[association:ASSOCIATED_WITH]->(object:Disease)
MATCH (subject)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(driver)
MATCH (subject)-[effect:AFFECTS]->(driver)
WHERE 'infores:semmeddb' IN
      coalesce(disruption.primary_knowledge_sources, [])
  AND 'infores:gene2phenotype' IN
      coalesce(association.primary_knowledge_sources, [])
  AND association.subject_form_or_variant_qualifier = '{variant_form}'
  AND effect.qualified_predicate = 'biolink:causes'
  AND {aspect_condition}
  AND effect.object_direction_qualifier = '{direction}'
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def dual_arm_process_target_correction_cypher(mode: str) -> str:
    modes = {
        "decreased": ("decreased", ""),
        "increased_control": ("increased", ""),
        "decreased_no_direct_harm": (
            "decreased",
            """
  AND NOT EXISTS {
    MATCH (subject)-[:CONTRAINDICATED_IN|EXACERBATES_CONDITION|
                     CAUSES|CONTRIBUTES_TO|PREDISPOSES_TO_CONDITION]->
          (object)
  }
""",
        ),
        "decreased_direct_harm": (
            "decreased",
            """
  AND EXISTS {
    MATCH (subject)-[:CONTRAINDICATED_IN|EXACERBATES_CONDITION|
                     CAUSES|CONTRIBUTES_TO|PREDISPOSES_TO_CONDITION]->
          (object)
  }
""",
        ),
        "decreased_no_adverse_phenotype": (
            "decreased",
            """
  AND NOT EXISTS {
    MATCH (subject)-[:HAS_SIDE_EFFECT]->(phenotype:PhenotypicFeature)
          <-[:HAS_PHENOTYPE]-(object)
  }
""",
        ),
        "decreased_adverse_phenotype": (
            "decreased",
            """
  AND EXISTS {
    MATCH (subject)-[:HAS_SIDE_EFFECT]->(phenotype:PhenotypicFeature)
          <-[:HAS_PHENOTYPE]-(object)
  }
""",
        ),
        "decreased_no_strong_harm": (
            "decreased",
            """
  AND NOT EXISTS {
    MATCH (subject)-[:CONTRAINDICATED_IN|EXACERBATES_CONDITION|
                     CAUSES|CONTRIBUTES_TO|PREDISPOSES_TO_CONDITION]->
          (object)
  }
  AND NOT EXISTS {
    MATCH (subject)-[:HAS_SIDE_EFFECT]->(phenotype:PhenotypicFeature)
          <-[:HAS_PHENOTYPE]-(object)
  }
""",
        ),
    }
    try:
        direction, extra_conditions = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown dual-arm process-target correction mode: {mode}"
        ) from error

    return f"""
MATCH (subject:Drug)-[disruption:DISRUPTS]->
      (process:BiologicalProcess)-[path_evidence:GENETIC_ASSOCIATION]-
      (object:Disease)
MATCH (target:Gene)-[gene_evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
MATCH (subject)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target)
MATCH (subject)-[effect:AFFECTS]->(target)
WHERE 'infores:semmeddb' IN
      coalesce(disruption.primary_knowledge_sources, [])
  AND 'infores:geneticskp' IN
      coalesce(path_evidence.primary_knowledge_sources, [])
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND gene_evidence._miner_disease_rank <= 3
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'{extra_conditions}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def interaction_bridged_dual_arm_cypher(mode: str) -> str:
    modes = {
        "direct_decreased": ("DIRECTLY_PHYSICALLY_INTERACTS_WITH", "decreased"),
        "direct_increased": ("DIRECTLY_PHYSICALLY_INTERACTS_WITH", "increased"),
        "generic_decreased": ("INTERACTS_WITH", "decreased"),
        "generic_increased": ("INTERACTS_WITH", "increased"),
        "physical_decreased": ("PHYSICALLY_INTERACTS_WITH", "decreased"),
        "physical_increased": ("PHYSICALLY_INTERACTS_WITH", "increased"),
    }
    try:
        bridge_type, direction = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown interaction-bridged dual-arm mode: {mode}"
        ) from error

    return f"""
MATCH (subject:Drug)-[disruption:DISRUPTS]->
      (process:BiologicalProcess)-[path_evidence:GENETIC_ASSOCIATION]-
      (object:Disease)
MATCH (partner:Gene)-[:INVOLVED_IN]->(process)
MATCH (target:Gene)-[bridge]-(partner)
MATCH (target)-[gene_evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
MATCH (subject)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target)
MATCH (subject)-[effect:AFFECTS]->(target)
WHERE type(bridge) = '{bridge_type}'
  AND partner <> target
  AND 'infores:semmeddb' IN
      coalesce(disruption.primary_knowledge_sources, [])
  AND 'infores:geneticskp' IN
      coalesce(path_evidence.primary_knowledge_sources, [])
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND gene_evidence._miner_disease_rank <= 3
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(bridge.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND NOT EXISTS {{
    MATCH (subject)-[:CONTRAINDICATED_IN|EXACERBATES_CONDITION|
                     CAUSES|CONTRIBUTES_TO|PREDISPOSES_TO_CONDITION]->
          (object)
  }}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def signed_regulatory_bridged_dual_arm_cypher(mode: str) -> str:
    modes = {
        "downstream_decreased": ("target", "partner", "decreased", ""),
        "downstream_increased": ("target", "partner", "increased", ""),
        "reverse_decreased": ("partner", "target", "decreased", ""),
        "reverse_decreased_no_curated_adverse_manifestation": (
            "partner",
            "target",
            "decreased",
            """
  AND NOT EXISTS {
    MATCH (subject)-[harm:CONTRIBUTES_TO|CAUSES]->(adverse)
    WHERE 'infores:text-mining-provider-targeted' IN
          coalesce(harm.primary_knowledge_sources, [])
      AND (
        EXISTS {
          MATCH (object)-[phenotype:HAS_PHENOTYPE]->(adverse)
          WHERE 'infores:hpo-annotations' IN
                coalesce(phenotype.primary_knowledge_sources, [])
        }
        OR EXISTS {
          MATCH (adverse)-[:MANIFESTATION_OF]->(object)
        }
      )
  }
""",
        ),
        "reverse_decreased_curated_adverse_manifestation": (
            "partner",
            "target",
            "decreased",
            """
  AND EXISTS {
    MATCH (subject)-[harm:CONTRIBUTES_TO|CAUSES]->(adverse)
    WHERE 'infores:text-mining-provider-targeted' IN
          coalesce(harm.primary_knowledge_sources, [])
      AND (
        EXISTS {
          MATCH (object)-[phenotype:HAS_PHENOTYPE]->(adverse)
          WHERE 'infores:hpo-annotations' IN
                coalesce(phenotype.primary_knowledge_sources, [])
        }
        OR EXISTS {
          MATCH (adverse)-[:MANIFESTATION_OF]->(object)
        }
      )
  }
""",
        ),
    }
    try:
        regulator, regulated, direction, extra_conditions = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown signed regulatory-bridged dual-arm mode: {mode}"
        ) from error

    return f"""
MATCH (subject:Drug)-[disruption:DISRUPTS]->
      (process:BiologicalProcess)-[path_evidence:GENETIC_ASSOCIATION]-
      (object:Disease)
MATCH (partner:Gene)-[:INVOLVED_IN]->(process)
MATCH (target:Gene)-[gene_evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
MATCH ({regulator})-[bridge:REGULATES]->({regulated})
MATCH (subject)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target)
MATCH (subject)-[effect:AFFECTS]->(target)
WHERE partner <> target
  AND 'infores:semmeddb' IN
      coalesce(disruption.primary_knowledge_sources, [])
  AND 'infores:geneticskp' IN
      coalesce(path_evidence.primary_knowledge_sources, [])
  AND 'infores:signor' IN
      coalesce(bridge.primary_knowledge_sources, [])
  AND bridge.qualified_predicate = 'biolink:causes'
  AND bridge.object_direction_qualifier = 'upregulated'
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND gene_evidence._miner_disease_rank <= 3
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND NOT EXISTS {{
    MATCH (subject)-[:CONTRAINDICATED_IN|EXACERBATES_CONDITION|
                     CAUSES|CONTRIBUTES_TO|PREDISPOSES_TO_CONDITION]->
          (object)
  }}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'{extra_conditions}
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def ontology_generalized_signed_interception_cypher(mode: str) -> str:
    modes = {
        "parent_decreased": "decreased",
        "parent_increased": "increased",
    }
    try:
        direction = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown ontology-generalized signed-interception mode: {mode}"
        ) from error

    return f"""
MATCH (subject:Drug)-[disruption:DISRUPTS]->
      (broader_process:BiologicalProcess)
      <-[ontology:SUBCLASS_OF]-(disease_process:BiologicalProcess)
      -[path_evidence:GENETIC_ASSOCIATION]-(object:Disease)
MATCH (partner:Gene)-[:INVOLVED_IN]->(disease_process)
MATCH (target:Gene)-[gene_evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
MATCH (partner)-[bridge:REGULATES]->(target)
MATCH (subject)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target)
MATCH (subject)-[effect:AFFECTS]->(target)
WHERE broader_process <> disease_process
  AND partner <> target
  AND 'infores:semmeddb' IN
      coalesce(disruption.primary_knowledge_sources, [])
  AND 'infores:geneticskp' IN
      coalesce(path_evidence.primary_knowledge_sources, [])
  AND 'infores:ubergraph' IN
      coalesce(ontology.primary_knowledge_sources, [])
  AND 'infores:signor' IN
      coalesce(bridge.primary_knowledge_sources, [])
  AND bridge.qualified_predicate = 'biolink:causes'
  AND bridge.object_direction_qualifier = 'upregulated'
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND gene_evidence._miner_disease_rank <= 3
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND NOT EXISTS {{
    MATCH (subject)-[:CONTRAINDICATED_IN|EXACERBATES_CONDITION|
                     CAUSES|CONTRIBUTES_TO|PREDISPOSES_TO_CONDITION]->
          (object)
  }}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def tissue_localized_ontology_interception_cypher(mode: str) -> str:
    modes = {
        "decreased": "decreased",
        "increased": "increased",
    }
    try:
        direction = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown tissue-localized ontology-interception mode: {mode}"
        ) from error

    return f"""
MATCH (subject:Drug)-[disruption:DISRUPTS]->
      (broader_process:BiologicalProcess)
      <-[ontology:SUBCLASS_OF]-(disease_process:BiologicalProcess)
      -[path_evidence:GENETIC_ASSOCIATION]-(object:Disease)
MATCH (partner:Gene)-[:INVOLVED_IN]->(disease_process)
MATCH (target:Gene)-[gene_evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
MATCH (partner)-[bridge:REGULATES]->(target)
MATCH (subject)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target)
MATCH (subject)-[effect:AFFECTS]->(target)
MATCH (target)-[target_expression:EXPRESSED_IN]->
      (anatomy:AnatomicalEntity)
MATCH (partner)-[partner_expression:EXPRESSED_IN]->(anatomy)
MATCH (object)-[:LOCATED_IN|OCCURS_IN]->(anatomy)
WHERE broader_process <> disease_process
  AND partner <> target
  AND 'infores:semmeddb' IN
      coalesce(disruption.primary_knowledge_sources, [])
  AND 'infores:geneticskp' IN
      coalesce(path_evidence.primary_knowledge_sources, [])
  AND 'infores:ubergraph' IN
      coalesce(ontology.primary_knowledge_sources, [])
  AND 'infores:signor' IN
      coalesce(bridge.primary_knowledge_sources, [])
  AND 'infores:bgee' IN
      coalesce(target_expression.primary_knowledge_sources, [])
  AND 'infores:bgee' IN
      coalesce(partner_expression.primary_knowledge_sources, [])
  AND bridge.qualified_predicate = 'biolink:causes'
  AND bridge.object_direction_qualifier = 'upregulated'
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND gene_evidence._miner_disease_rank <= 3
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND NOT EXISTS {{
    MATCH (subject)-[:CONTRAINDICATED_IN|EXACERBATES_CONDITION|
                     CAUSES|CONTRIBUTES_TO|PREDISPOSES_TO_CONDITION]->
          (object)
  }}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def dual_process_ontology_convergence_cypher(mode: str) -> str:
    modes = {
        "decreased": "decreased",
        "increased": "increased",
    }
    try:
        direction = modes[mode]
    except KeyError as error:
        raise ValueError(
            f"Unknown dual-process ontology-convergence mode: {mode}"
        ) from error

    return f"""
MATCH (subject:Drug)-[disruption:DISRUPTS]->
      (broader_process:BiologicalProcess)
      <-[ontology:SUBCLASS_OF]-(disease_process:BiologicalProcess)
      -[path_evidence:GENETIC_ASSOCIATION]-(object:Disease)
MATCH (partner:Gene)-[:INVOLVED_IN]->(disease_process)
MATCH (target:Gene)-[gene_evidence:MINER_GENE_DISEASE_EVIDENCE]->(object)
MATCH (partner)-[bridge:REGULATES]->(target)
MATCH (subject)-[binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH]->(target)
MATCH (subject)-[effect:AFFECTS]->(target)
WHERE broader_process <> disease_process
  AND partner <> target
  AND 'infores:semmeddb' IN
      coalesce(disruption.primary_knowledge_sources, [])
  AND 'infores:geneticskp' IN
      coalesce(path_evidence.primary_knowledge_sources, [])
  AND 'infores:ubergraph' IN
      coalesce(ontology.primary_knowledge_sources, [])
  AND 'infores:signor' IN
      coalesce(bridge.primary_knowledge_sources, [])
  AND bridge.qualified_predicate = 'biolink:causes'
  AND bridge.object_direction_qualifier = 'upregulated'
  AND effect.qualified_predicate = 'biolink:causes'
  AND effect.object_aspect_qualifier = 'activity_or_abundance'
  AND effect.object_direction_qualifier = '{direction}'
  AND gene_evidence._miner_disease_rank <= 3
  AND none(
    source IN coalesce(binding.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND none(
    source IN coalesce(effect.primary_knowledge_sources, [])
    WHERE source IN ['infores:drug-repurposing-hub', 'infores:ttd']
  )
  AND NOT EXISTS {{
    MATCH (subject)-[:CONTRAINDICATED_IN|EXACERBATES_CONDITION|
                     CAUSES|CONTRIBUTES_TO|PREDISPOSES_TO_CONDITION]->
          (object)
  }}
  AND coalesce(object._miner_disease_descendant_degree, 0) <= 500
  AND object._miner_disease_superclass_degree >= 1
  AND object.id STARTS WITH 'MONDO:'
WITH subject, object, target,
     count(DISTINCT broader_process) AS parent_process_count
WHERE parent_process_count >= 2
RETURN DISTINCT subject.id AS subject_id, object.id AS object_id
""".strip()


def compile_rule_family(value: dict[str, Any]) -> dict[str, Any]:
    family = value.get("family")
    if family is None:
        return value
    compiled = dict(value)
    compiled.pop("family")
    if family == TWO_STEP_SIGNED_DIRECTIONAL:
        variant_form = compiled.pop("variant_form", None)
        sign_mode = compiled.pop("sign_mode", None)
        context = compiled.pop("context", None)
        if not all(isinstance(item, str) for item in (variant_form, sign_mode, context)):
            raise ValueError(
                f"{value.get('id', '<unknown>')}: variant_form, sign_mode, "
                "and context must be strings"
            )
        compiled["cypher"] = two_step_signed_directional_cypher(
            variant_form,
            sign_mode,
            context,
        )
        return compiled
    if family == RECIPROCAL_SIGNED_FEEDBACK:
        variant_form = compiled.pop("variant_form", None)
        sign_mode = compiled.pop("sign_mode", None)
        context = compiled.pop("context", None)
        if not all(isinstance(item, str) for item in (variant_form, sign_mode, context)):
            raise ValueError(
                f"{value.get('id', '<unknown>')}: variant_form, sign_mode, "
                "and context must be strings"
            )
        dual_arm = compiled.pop("dual_arm", False)
        if not isinstance(dual_arm, bool):
            raise ValueError(f"{value.get('id', '<unknown>')}: dual_arm must be boolean")
        compiled["cypher"] = reciprocal_signed_feedback_cypher(
            variant_form,
            sign_mode,
            context,
            dual_arm=dual_arm,
        )
        return compiled
    if family in {DUAL_UPSTREAM_CONVERGENCE, COHERENT_FEED_FORWARD}:
        variant_form = compiled.pop("variant_form", None)
        sign_mode = compiled.pop("sign_mode", None)
        context = compiled.pop("context", None)
        if not all(isinstance(item, str) for item in (variant_form, sign_mode, context)):
            raise ValueError(
                f"{value.get('id', '<unknown>')}: variant_form, sign_mode, "
                "and context must be strings"
            )
        compiler = {
            DUAL_UPSTREAM_CONVERGENCE: dual_upstream_convergence_cypher,
            COHERENT_FEED_FORWARD: coherent_feed_forward_cypher,
        }[family]
        compiled["cypher"] = compiler(variant_form, sign_mode, context)
        return compiled
    if family == ANATOMICAL_EXPOSURE:
        mechanism = compiled.pop("mechanism", None)
        top_three = compiled.pop("top_three", False)
        disruption_mode = compiled.pop("disruption_mode", "allow")
        if not isinstance(mechanism, str):
            raise ValueError(
                f"{value.get('id', '<unknown>')}: mechanism must be a string"
            )
        if not isinstance(top_three, bool):
            raise ValueError(
                f"{value.get('id', '<unknown>')}: top_three must be boolean"
            )
        if not isinstance(disruption_mode, str):
            raise ValueError(
                f"{value.get('id', '<unknown>')}: disruption_mode must be a string"
            )
        compiled["cypher"] = anatomical_exposure_cypher(
            mechanism,
            top_three=top_three,
            disruption_mode=disruption_mode,
        )
        return compiled
    if family == COMPENSATORY_BYPASS:
        context = compiled.pop("context", None)
        sign_mode = compiled.pop("sign_mode", None)
        if not all(isinstance(item, str) for item in (context, sign_mode)):
            raise ValueError(
                f"{value.get('id', '<unknown>')}: context and sign_mode "
                "must be strings"
            )
        compiled["cypher"] = compensatory_bypass_cypher(context, sign_mode)
        return compiled
    if family == METABOLIC_RESCUE:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = metabolic_rescue_cypher(mode)
        return compiled
    if family == SIGNED_ACTIVE_METABOLITE:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = signed_active_metabolite_cypher(mode)
        return compiled
    if family == GENETIC_PATHWAY_CORROBORATION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = genetic_pathway_corroboration_cypher(mode)
        return compiled
    if family == GENETIC_ACTIVITY_CORROBORATION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = genetic_activity_corroboration_cypher(mode)
        return compiled
    if family == LIGAND_RECEPTOR_AXIS_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = ligand_receptor_axis_correction_cypher(mode)
        return compiled
    if family == RECEPTOR_LIGAND_AXIS_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = receptor_ligand_axis_correction_cypher(mode)
        return compiled
    if family == TEMPORAL_INDICATION_TRANSFER:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = temporal_indication_transfer_cypher(mode)
        return compiled
    if family == CHEMICAL_CLEARANCE_ACTIVATION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = chemical_clearance_activation_cypher(mode)
        return compiled
    if family == CHEMICAL_MEDIATOR_ANTAGONISM:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = chemical_mediator_antagonism_cypher(mode)
        return compiled
    if family == ANATOMY_CELL_PART_LOCALIZATION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = anatomy_cell_part_localization_cypher(mode)
        return compiled
    if family == CELL_LOCALIZED_TARGET:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = cell_localized_target_cypher(mode)
        return compiled
    if family == CAUSAL_MODULE_COVERAGE:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = causal_module_coverage_cypher(mode)
        return compiled
    if family == CAUSAL_MODULE_PROVENANCE:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = causal_module_provenance_cypher(mode)
        return compiled
    if family == DISEASE_MODULE_CENTRAL_TARGET:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = disease_module_central_target_cypher(mode)
        return compiled
    if family == SIGNED_PROCESS_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = signed_process_correction_cypher(mode)
        return compiled
    if family == ORTHOLOG_PHENOTYPE_DIRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = ortholog_phenotype_direction_cypher(mode)
        return compiled
    if family == MOLECULAR_ACTIVITY_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = molecular_activity_correction_cypher(mode)
        return compiled
    if family == SIGNED_REGULATORY_CASCADE:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = signed_regulatory_cascade_cypher(mode)
        return compiled
    if family == MULTI_DRIVER_CONNECTOR:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = multi_driver_connector_cypher(mode)
        return compiled
    if family == DUAL_TARGET_DUAL_DRIVER_CONNECTOR:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = dual_target_dual_driver_connector_cypher(mode)
        return compiled
    if family == PHENOTYPE_THERAPEUTIC_DECOMPOSITION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = phenotype_therapeutic_decomposition_cypher(mode)
        return compiled
    if family == TRANSPORTER_TISSUE_DELIVERY:
        mode = compiled.pop("mode", "base")
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = transporter_tissue_delivery_cypher(mode)
        return compiled
    if family == DIRECT_ABUNDANCE_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = direct_abundance_correction_cypher(mode)
        return compiled
    if family == DIRECT_SPLICING_RESCUE:
        compiled["cypher"] = direct_splicing_rescue_cypher()
        return compiled
    if family == DIRECT_ACTIVITY_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = direct_activity_correction_cypher(mode)
        return compiled
    if family == ACTIVITY_CLASS_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = activity_class_correction_cypher(mode)
        return compiled
    if family == MUTANT_FORM_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = mutant_form_correction_cypher(mode)
        return compiled
    if family == PHARMACOLOGIC_MECHANISM_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = pharmacologic_mechanism_correction_cypher(mode)
        return compiled
    if family == DOWNSTREAM_INTERCEPTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = downstream_interception_cypher(mode)
        return compiled
    if family == PROTEIN_TURNOVER_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = protein_turnover_correction_cypher(mode)
        return compiled
    if family == ALLELE_EXPRESSION_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = allele_expression_correction_cypher(mode)
        return compiled
    if family == EPIGENETIC_EXPRESSION_CONSENSUS:
        compiled["cypher"] = epigenetic_expression_consensus_cypher()
        return compiled
    if family == FUNCTIONAL_DOSAGE_CONSENSUS:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = functional_dosage_consensus_cypher(mode)
        return compiled
    if family == DOMINANT_NEGATIVE_ACTIVITY:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = dominant_negative_activity_cypher(mode)
        return compiled
    if family == PHOSPHORYLATION_ACTIVITY_CONSENSUS:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = phosphorylation_activity_consensus_cypher(mode)
        return compiled
    if family == LITERATURE_ALLELE_ACTIVITY_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = literature_allele_activity_correction_cypher(mode)
        return compiled
    if family == GO_CAM_INPUT_FLOW:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = go_cam_input_flow_cypher(mode)
        return compiled
    if family == ACTIVE_COMPONENT_REGULATORY_CASCADE:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = active_component_regulatory_cascade_cypher(mode)
        return compiled
    if family == SIGNED_GO_PROCESS_RESTORATION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = signed_go_process_restoration_cypher(mode)
        return compiled
    if family == MOLECULAR_ACTIVITY_COMPLEX_COMPENSATION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = molecular_activity_complex_compensation_cypher(mode)
        return compiled
    if family == DIRECT_DISEASE_PROCESS_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = direct_disease_process_correction_cypher(mode)
        return compiled
    if family == ETIOLOGIC_MEDIATOR_PRODUCTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = etiologic_mediator_production_cypher(mode)
        return compiled
    if family == CLOSE_MATCH_MECHANISM_TRANSFER:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = close_match_mechanism_transfer_cypher(mode)
        return compiled
    if family == VARIANT_COMPONENT_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = variant_component_correction_cypher(mode)
        return compiled
    if family == DISRUPTED_PROCESS_VARIANT_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = disrupted_process_variant_correction_cypher(mode)
        return compiled
    if family == DISRUPTED_ACTIVITY_VARIANT_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = disrupted_activity_variant_correction_cypher(mode)
        return compiled
    if family == DUAL_ARM_PROCESS_TARGET_CORRECTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = dual_arm_process_target_correction_cypher(mode)
        return compiled
    if family == INTERACTION_BRIDGED_DUAL_ARM:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = interaction_bridged_dual_arm_cypher(mode)
        return compiled
    if family == SIGNED_REGULATORY_BRIDGED_DUAL_ARM:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = signed_regulatory_bridged_dual_arm_cypher(mode)
        return compiled
    if family == ONTOLOGY_GENERALIZED_SIGNED_INTERCEPTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = ontology_generalized_signed_interception_cypher(
            mode
        )
        return compiled
    if family == TISSUE_LOCALIZED_ONTOLOGY_INTERCEPTION:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = tissue_localized_ontology_interception_cypher(
            mode
        )
        return compiled
    if family == DUAL_PROCESS_ONTOLOGY_CONVERGENCE:
        mode = compiled.pop("mode", None)
        if not isinstance(mode, str):
            raise ValueError(f"{value.get('id', '<unknown>')}: mode must be a string")
        compiled["cypher"] = dual_process_ontology_convergence_cypher(mode)
        return compiled
    condition_names = compiled.pop("conditions", None)
    if not isinstance(condition_names, list) or not all(
        isinstance(name, str) for name in condition_names
    ):
        raise ValueError(f"{value.get('id', '<unknown>')}: conditions must be strings")
    if family == DIRECT_CAUSAL_TRANSLATIONAL:
        compiled["cypher"] = direct_causal_translational_cypher(condition_names)
        return compiled
    raise ValueError(f"{value.get('id', '<unknown>')}: unknown rule family {family}")
