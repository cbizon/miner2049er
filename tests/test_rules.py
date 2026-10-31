import json
from pathlib import Path

import pytest

from miner2049er.pareto_search import (
    boolean_condition,
    dominated_by_current,
    numeric_condition,
    pair_metrics,
    pareto_configs,
)
from miner2049er.rule_comparator import comparison_query, examples_query
from miner2049er.rule_evaluator import render_rule_cypher, update_rule_library
from miner2049er.rule_families import (
    active_component_regulatory_cascade_cypher,
    activity_class_correction_cypher,
    allele_expression_correction_cypher,
    anatomical_exposure_cypher,
    anatomy_cell_part_localization_cypher,
    causal_module_coverage_cypher,
    causal_module_provenance_cypher,
    cell_localized_target_cypher,
    chemical_clearance_activation_cypher,
    chemical_mediator_antagonism_cypher,
    close_match_mechanism_transfer_cypher,
    coherent_feed_forward_cypher,
    compensatory_bypass_cypher,
    direct_abundance_correction_cypher,
    direct_activity_correction_cypher,
    direct_causal_translational_cypher,
    direct_disease_process_correction_cypher,
    direct_splicing_rescue_cypher,
    disease_module_central_target_cypher,
    disrupted_activity_variant_correction_cypher,
    disrupted_process_variant_correction_cypher,
    dominant_negative_activity_cypher,
    downstream_interception_cypher,
    dual_arm_process_target_correction_cypher,
    dual_process_ontology_convergence_cypher,
    dual_target_dual_driver_connector_cypher,
    dual_upstream_convergence_cypher,
    epigenetic_expression_consensus_cypher,
    etiologic_mediator_production_cypher,
    functional_dosage_consensus_cypher,
    genetic_activity_corroboration_cypher,
    genetic_pathway_corroboration_cypher,
    go_cam_input_flow_cypher,
    interaction_bridged_dual_arm_cypher,
    ligand_receptor_axis_correction_cypher,
    literature_allele_activity_correction_cypher,
    metabolic_rescue_cypher,
    molecular_activity_complex_compensation_cypher,
    molecular_activity_correction_cypher,
    multi_driver_connector_cypher,
    mutant_form_correction_cypher,
    ontology_generalized_signed_interception_cypher,
    ortholog_phenotype_direction_cypher,
    pharmacologic_mechanism_correction_cypher,
    phenotype_therapeutic_decomposition_cypher,
    phosphorylation_activity_consensus_cypher,
    protein_turnover_correction_cypher,
    receptor_ligand_axis_correction_cypher,
    reciprocal_signed_feedback_cypher,
    signed_active_metabolite_cypher,
    signed_go_process_restoration_cypher,
    signed_process_correction_cypher,
    signed_regulatory_bridged_dual_arm_cypher,
    signed_regulatory_cascade_cypher,
    temporal_indication_transfer_cypher,
    tissue_localized_ontology_interception_cypher,
    transporter_tissue_delivery_cypher,
    two_step_signed_directional_cypher,
    variant_component_correction_cypher,
)
from miner2049er.rule_features import CLEAR_QUERIES, INDEX_QUERIES
from miner2049er.rules import Rule, f_beta, load_rules, pareto_rule_ids
from miner2049er.trapi_runner import load_trapi_payload, response_summary

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ITERATION_7_RULE_IDS = {
    "TREAT-I07-R059",
    "TREAT-I07-R060",
    "TREAT-I07-R061",
    "TREAT-I07-R062",
    "TREAT-I07-R063",
}
ITERATION_8_RULE_IDS = {
    f"TREAT-I08-R{number:03d}" for number in range(64, 94)
}


def test_load_rules_and_select(tmp_path: Path):
    path = tmp_path / "rules.toml"
    path.write_text(
        """
[[rules]]
id = "R1"
name = "test"
iteration = 1
status = "candidate"
hypothesis = "test"
body = "a -> b"
mechanism_score = "high"
mechanism_rationale = "test"
uses_treatment_edges = false
trapi_expressibility = "full"
trapi_notes = "test"
cypher = "MATCH (s)-[]->(o) RETURN s.id AS subject_id, o.id AS object_id;"
""",
        encoding="utf-8",
    )

    rules = load_rules(path, {"R1"})

    assert rules == [
        Rule(
            id="R1",
            name="test",
            iteration=1,
            status="candidate",
            hypothesis="test",
            body="a -> b",
            mechanism_score="high",
            mechanism_rationale="test",
            uses_treatment_edges=False,
            trapi_expressibility="full",
            trapi_notes="test",
            cypher="MATCH (s)-[]->(o) RETURN s.id AS subject_id, o.id AS object_id",
        )
    ]


def test_load_rules_normalizes_description_criteria(tmp_path: Path):
    path = tmp_path / "rules.toml"
    path.write_text(
        """
[[rules]]
id = "R1"
name = "test"
iteration = 1
status = "candidate"
hypothesis = "test"
body = "a -> b"
description = "Complete interpretation."
criteria = ["First condition.", "Second condition."]
mechanism_score = "high"
mechanism_rationale = "test"
uses_treatment_edges = false
trapi_expressibility = "full"
trapi_notes = "test"
cypher = "MATCH (s)-[]->(o) RETURN s.id AS subject_id, o.id AS object_id"
""",
        encoding="utf-8",
    )

    rule = load_rules(path, {"R1"})[0]

    assert rule.description == "Complete interpretation."
    assert rule.criteria == ("First condition.", "Second condition.")


def test_default_rule_loading_includes_retained_and_excludes_diagnostics(tmp_path: Path):
    path = tmp_path / "rules.toml"
    rule_template = """
[[rules]]
id = "{rule_id}"
name = "test"
iteration = 1
status = "{status}"
hypothesis = "test"
body = "a -> b"
mechanism_score = "medium"
mechanism_rationale = "test"
uses_treatment_edges = false
trapi_expressibility = "full"
trapi_notes = "test"
cypher = "MATCH (s)-[]->(o) RETURN s.id AS subject_id, o.id AS object_id"
"""
    path.write_text(
        rule_template.format(rule_id="retained", status="retained")
        + rule_template.format(rule_id="diagnostic", status="diagnostic_failure"),
        encoding="utf-8",
    )

    assert [rule.id for rule in load_rules(path)] == ["retained"]
    assert [rule.id for rule in load_rules(path, include_inactive=True)] == [
        "retained",
        "diagnostic",
    ]


def test_invalid_mechanism_score_fails():
    with pytest.raises(ValueError, match="mechanism_score"):
        Rule.from_dict(
            {
                "id": "R1",
                "name": "test",
                "iteration": 1,
                "status": "candidate",
                "hypothesis": "test",
                "body": "test",
                "mechanism_score": "excellent",
                "mechanism_rationale": "test",
                "uses_treatment_edges": False,
                "trapi_expressibility": "full",
                "trapi_notes": "test",
                "cypher": "RETURN 'a' AS subject_id, 'b' AS object_id",
            }
        )


def test_direct_causal_translational_family_compiles():
    cypher = direct_causal_translational_cypher(
        [
            "pair_clinical",
            "binding_dgidb",
            "causal_publication_npmi_>=_0.25",
        ]
    )

    assert "IN_CLINICAL_TRIALS_FOR" in cypher
    assert "'infores:dgidb' IN binding_sources" in cypher
    assert "evidence._miner_causal_publication_npmi >= 0.25" in cypher
    assert "RETURN DISTINCT subject.id AS subject_id" in cypher


def test_direct_causal_translational_family_rejects_unknown_condition():
    with pytest.raises(ValueError, match="Unknown direct causal"):
        direct_causal_translational_cypher(["not_a_feature"])


def test_two_step_signed_directional_family_composes_signs_and_context():
    gof = two_step_signed_directional_cypher(
        "gain_of_function_variant_form",
        "corrective",
        "process_degree",
    )
    lof = two_step_signed_directional_cypher(
        "loss_of_function_variant_form",
        "corrective",
        "process_anatomy",
    )

    assert "regulation1.object_direction_qualifier =" in gof
    assert "COUNT {" in gof
    assert "regulation1.object_direction_qualifier <>" in lof
    assert "target_expression:EXPRESSED_IN" in lof
    assert "'infores:bgee'" in lof


def test_nonlinear_signed_families_compile_corrective_and_adverse_modes():
    feedback = reciprocal_signed_feedback_cypher(
        "gain_of_function_variant_form",
        "corrective",
        "process_anatomy",
    )
    convergence = dual_upstream_convergence_cypher(
        "loss_of_function_variant_form",
        "corrective",
        "interacting",
    )
    feed_forward = coherent_feed_forward_cypher(
        "gain_of_function_variant_form",
        "adverse",
        "process",
    )
    dual_arm = reciprocal_signed_feedback_cypher(
        "gain_of_function_variant_form",
        "corrective",
        "base",
        dual_arm=True,
    )

    assert "back.object_direction_qualifier =" in feedback
    assert "target_expression:EXPRESSED_IN" in feedback
    assert "regulation1.object_direction_qualifier = 'downregulated'" in convergence
    assert "DIRECTLY_PHYSICALLY_INTERACTS_WITH]-(target2)" in convergence
    assert "direct.object_direction_qualifier = 'downregulated'" in feed_forward
    assert "regulation1.object_direction_qualifier <>" in feed_forward
    assert "process._miner_gene_member_degree <= 100" in feed_forward
    assert "driver_effect:AFFECTS" in dual_arm
    assert "driver_effect.object_direction_qualifier = 'decreased'" in dual_arm


def test_anatomical_exposure_family_compiles_direction_and_negative_evidence():
    causal = anatomical_exposure_cypher(
        "causal_inhibition",
        top_three=True,
        disruption_mode="exclude",
    )
    lof = anatomical_exposure_cypher(
        "lof_restoration",
        top_three=False,
        disruption_mode="require",
    )

    assert "MINER_GENE_DISEASE_EVIDENCE" in causal
    assert "evidence._miner_disease_rank <= 3" in causal
    assert "NOT EXISTS { MATCH (subject)-[:DISRUPTS]->(anatomy) }" in causal
    assert "loss_of_function_variant_form" in lof
    assert "effect.object_direction_qualifier = 'increased'" in lof
    assert "EXISTS { MATCH (subject)-[:DISRUPTS]->(anatomy) }" in lof


def test_compensatory_bypass_family_compiles_context_and_matched_control():
    corrective = compensatory_bypass_cypher("family_process", "corrective")
    adverse = compensatory_bypass_cypher("component", "adverse")

    assert "loss_of_function_variant_form" in corrective
    assert "effect.object_direction_qualifier = 'increased'" in corrective
    assert "family._miner_gene_family_member_degree <= 14" in corrective
    assert "process._miner_gene_member_degree <= 100" in corrective
    assert "effect.object_direction_qualifier = 'decreased'" in adverse
    assert "component._miner_component_gene_member_degree <= 54" in adverse


def test_metabolic_rescue_family_compiles_replacement_and_directional_modes():
    replacement = metabolic_rescue_cypher("product_replacement")
    subclass = metabolic_rescue_cypher("product_subclass")
    reduction = metabolic_rescue_cypher("substrate_reduction")
    boost = metabolic_rescue_cypher("alternate_product_boost")

    assert "[:PRODUCES]->(subject:Drug)" in replacement
    assert "[:SUBCLASS_OF*1..2]->(product)" in subclass
    assert "[:HAS_SUBSTRATE]->(metabolite:ChemicalEntity)" in reduction
    assert "effect.object_direction_qualifier = 'decreased'" in reduction
    assert "<-[:PRODUCES]-(alternate:Gene)" in boost
    assert "effect.object_direction_qualifier = 'increased'" in boost
    assert "loss_of_function_variant_form" in boost


def test_cell_localized_target_compiles_direct_and_ontology_modes():
    direct = cell_localized_target_cypher("direct_top_three")
    ontology = cell_localized_target_cypher("ontology_median")

    assert "MATCH (object)-[:LOCATED_IN|OCCURS_IN]->(cell)" in direct
    assert "evidence._miner_disease_rank <= 3" in direct
    assert "[:SUBCLASS_OF*1..2]->(anatomy:AnatomicalEntity)" in ontology
    assert "cell._miner_human_gene_expression_degree <= 5512" in ontology


def test_causal_module_coverage_compiles_ranked_module_and_control():
    top = causal_module_coverage_cypher("top_three_two")
    gated = causal_module_coverage_cypher("top_five_three_adverse_gated")
    phenotype_gated = causal_module_coverage_cypher(
        "top_three_two_adverse_gated_phenotype_gated"
    )
    process = causal_module_coverage_cypher("top_three_two_process_adverse_gated")
    component = causal_module_coverage_cypher("top_three_two_component")
    control = causal_module_coverage_cypher("lower_rank_two")

    assert "evidence._miner_disease_rank <= 3" in top
    assert "targeted_genes >= 2" in top
    assert "CONTRAINDICATED_IN|EXACERBATES_CONDITION|CAUSES" in gated
    assert "targeted_genes >= 3" in gated
    assert "[:HAS_SIDE_EFFECT]->(:PhenotypicFeature)" in phenotype_gated
    assert "CONTRAINDICATED_IN|EXACERBATES_CONDITION|CAUSES" in phenotype_gated
    assert "[:INVOLVED_IN]->(context:BiologicalProcess)" in process
    assert "context._miner_gene_member_degree <= 100" in process
    assert "coalesce(context._miner_gene_member_degree" not in process
    assert "CONTRAINDICATED_IN|EXACERBATES_CONDITION|CAUSES" in process
    assert "[:PART_OF]->(context:CellularComponent)" in component
    assert "context._miner_component_gene_member_degree <= 54" in component
    assert "coalesce(context._miner_component_gene_member_degree" not in component
    assert "evidence._miner_disease_rank >= 4" in control
    assert "evidence._miner_disease_rank <= 10" in control


def test_signed_process_correction_compiles_direction_and_cross_channel():
    gof = signed_process_correction_cypher("direct_gof_corrective")
    lof = signed_process_correction_cypher("cross_lof_corrective")
    worsening = signed_process_correction_cypher("cross_gof_worsening")

    assert "gain_of_function_variant_form" in gof
    assert "process_effect.object_direction_qualifier = 'decreased'" in gof
    assert "DIRECTLY_PHYSICALLY_INTERACTS_WITH" not in gof
    assert "loss_of_function_variant_form" in lof
    assert "process_effect.object_direction_qualifier = 'increased'" in lof
    assert "target_effect.object_direction_qualifier = 'increased'" in lof
    assert "target <> driver" in lof
    assert "process_effect.object_direction_qualifier = 'increased'" in worsening
    assert "infores:ctd" in worsening
    assert "infores:gene2phenotype" in worsening


def test_causal_module_provenance_compiles_independent_evidence_modes():
    repeated = causal_module_provenance_cypher("repeated_evidence_top_five")
    publications = causal_module_provenance_cypher(
        "distinct_publications_top_three"
    )
    binding = causal_module_provenance_cypher("multisource_binding_top_three")
    signor = causal_module_provenance_cypher("signor_effect_top_three")
    consensus = causal_module_provenance_cypher(
        "evidence_binding_consensus_top_three"
    )

    assert "effect.evidence_count" in repeated
    assert "targeted_genes >= 3" in repeated
    assert "collect(DISTINCT publication)" in publications
    assert "targeted_genes >= 2" in publications
    assert "collect(DISTINCT binding_source)" in binding
    assert "infores:signor" in signor
    assert "effect.evidence_count" in consensus
    assert "collect(DISTINCT binding_source)" in consensus


def test_disease_module_central_target_compiles_network_and_control_modes():
    base = disease_module_central_target_cypher("top_three_two_neighbors")
    consensus = disease_module_central_target_cypher(
        "top_three_two_neighbors_consensus"
    )
    control = disease_module_central_target_cypher(
        "lower_rank_two_neighbors_consensus"
    )

    assert "size(neighbors) >= 2" in base
    assert "target_evidence._miner_disease_rank <= 3" in base
    assert "size(binding_sources) >= 2" in consensus
    assert "effect.evidence_count" in consensus
    assert "target_evidence._miner_disease_rank >= 4" in control
    assert "target_evidence._miner_disease_rank <= 10" in control


def test_signed_active_metabolite_compiles_directional_controls():
    gof = signed_active_metabolite_cypher("gof_corrective")
    gof_control = signed_active_metabolite_cypher("gof_worsening")
    lof = signed_active_metabolite_cypher("lof_corrective")
    lof_control = signed_active_metabolite_cypher("lof_worsening")

    assert ":HAS_METABOLITE" in gof
    assert "effect.object_aspect_qualifier = 'activity'" in gof
    assert "gain_of_function_variant_form" in gof
    assert "object_direction_qualifier = 'decreased'" in gof
    assert "object_direction_qualifier = 'increased'" in gof_control
    assert "loss_of_function_variant_form" in lof
    assert "object_direction_qualifier = 'increased'" in lof
    assert "object_direction_qualifier = 'decreased'" in lof_control
    assert "infores:drug-repurposing-hub" in gof
    assert "infores:ttd" in gof


def test_genetic_pathway_corroboration_compiles_matched_directions():
    decreased = genetic_pathway_corroboration_cypher("decreased")
    increased = genetic_pathway_corroboration_cypher("increased_control")
    gated = genetic_pathway_corroboration_cypher(
        "decreased_adverse_anatomy_gated"
    )
    conflict = genetic_pathway_corroboration_cypher(
        "decreased_adverse_anatomy_conflict"
    )
    no_black_box = genetic_pathway_corroboration_cypher(
        "decreased_no_black_box_warning"
    )
    black_box = genetic_pathway_corroboration_cypher(
        "decreased_black_box_warning"
    )

    assert ":GENETIC_ASSOCIATION" in decreased
    assert ":INVOLVED_IN" in decreased
    assert "process.id STARTS WITH 'GO:'" in decreased
    assert "infores:geneticskp" in decreased
    assert "gene_evidence._miner_disease_rank <= 3" in decreased
    assert "object_direction_qualifier = 'decreased'" in decreased
    assert "object_direction_qualifier = 'increased'" in increased
    assert "AND NOT EXISTS {" in gated
    assert ":HAS_SIDE_EFFECT" in gated
    assert ":LOCATED_IN" in gated
    assert "AND EXISTS {" in conflict
    assert "chembl_black_box_warning IS NULL" in no_black_box
    assert "chembl_black_box_warning = 'True'" in black_box


def test_genetic_activity_corroboration_compiles_matched_directions():
    decreased = genetic_activity_corroboration_cypher("decreased")
    increased = genetic_activity_corroboration_cypher("increased_control")

    assert "(activity:MolecularActivity)" in decreased
    assert ":GENETIC_ASSOCIATION" in decreased
    assert ":ENABLES" in decreased
    assert "infores:geneticskp" in decreased
    assert "gene_evidence._miner_disease_rank <= 3" in decreased
    assert "object_direction_qualifier = 'decreased'" in decreased
    assert "object_direction_qualifier = 'increased'" in increased


def test_ligand_receptor_axis_correction_compiles_direction_matrix():
    gof = ligand_receptor_axis_correction_cypher("gof_corrective")
    gof_control = ligand_receptor_axis_correction_cypher("gof_worsening")
    lof = ligand_receptor_axis_correction_cypher("lof_corrective")
    lof_control = ligand_receptor_axis_correction_cypher("lof_worsening")

    assert "GO:0005102" in gof
    assert "GO:0038023" in gof
    assert "infores:goa" in gof
    assert "infores:signor" in gof
    assert "gain_of_function_variant_form" in gof
    assert "object_direction_qualifier = 'decreased'" in gof
    assert "object_direction_qualifier = 'increased'" in gof_control
    assert "loss_of_function_variant_form" in lof
    assert "object_direction_qualifier = 'increased'" in lof
    assert "object_direction_qualifier = 'decreased'" in lof_control


def test_receptor_ligand_axis_correction_uses_explicit_ligand_activity():
    gof = receptor_ligand_axis_correction_cypher("gof_corrective")
    gof_control = receptor_ligand_axis_correction_cypher("gof_worsening")
    lof = receptor_ligand_axis_correction_cypher("lof_corrective")
    lof_control = receptor_ligand_axis_correction_cypher("lof_worsening")

    assert "GO:0048018" in gof
    assert "GO:0005102" not in gof
    assert "GO:0038023" in gof
    assert "gain_of_function_variant_form" in gof
    assert "object_direction_qualifier = 'decreased'" in gof
    assert "object_direction_qualifier = 'increased'" in gof_control
    assert "loss_of_function_variant_form" in lof
    assert "object_direction_qualifier = 'increased'" in lof
    assert "object_direction_qualifier = 'decreased'" in lof_control


def test_temporal_indication_transfer_compiles_orientations_and_directions():
    forward = temporal_indication_transfer_cypher("forward_decreased")
    forward_control = temporal_indication_transfer_cypher("forward_increased")
    reverse = temporal_indication_transfer_cypher("reverse_decreased")
    reverse_control = temporal_indication_transfer_cypher("reverse_increased")

    assert "(anchor)-[temporal:PRECEDES]->(object:Disease)" in forward
    assert "(object:Disease)-[temporal:PRECEDES]->(anchor)" in reverse
    assert "object_direction_qualifier = 'decreased'" in forward
    assert "object_direction_qualifier = 'increased'" in forward_control
    assert "object_direction_qualifier = 'decreased'" in reverse
    assert "object_direction_qualifier = 'increased'" in reverse_control
    assert "WITH DISTINCT subject, anchor, gene" in forward
    assert "infores:semmeddb" in forward


def test_chemical_clearance_activation_compiles_control():
    activation = chemical_clearance_activation_cypher("activation")
    control = chemical_clearance_activation_cypher("inhibition_control")

    assert ":HAS_SUBSTRATE" in activation
    assert ":CAUSES" in activation
    assert "NOT chemical:Drug" in activation
    assert "infores:chembl" in activation
    assert "infores:semmeddb" in activation
    assert "object_direction_qualifier = 'increased'" in activation
    assert "object_direction_qualifier = 'decreased'" in control
    assert "infores:ttd" in activation


def test_chemical_mediator_antagonism_compiles_direction_matrix():
    increased_opposed = chemical_mediator_antagonism_cypher("increased_opposed")
    decreased_opposed = chemical_mediator_antagonism_cypher("decreased_opposed")
    increased_reinforced = chemical_mediator_antagonism_cypher(
        "increased_reinforced"
    )
    decreased_reinforced = chemical_mediator_antagonism_cypher(
        "decreased_reinforced"
    )
    genetic = chemical_mediator_antagonism_cypher(
        "increased_opposed_genetic"
    )
    anatomy = chemical_mediator_antagonism_cypher(
        "increased_opposed_genetic_anatomy"
    )

    assert ":CAUSES" in increased_opposed
    assert "WITH DISTINCT mediator, target" in increased_opposed
    assert "object_direction_qualifier = 'increased'" in increased_opposed
    assert "object_direction_qualifier = 'decreased'" in increased_opposed
    assert "object_direction_qualifier = 'decreased'" in decreased_opposed
    assert "object_direction_qualifier = 'increased'" in decreased_opposed
    assert increased_reinforced.count("object_direction_qualifier = 'increased'") == 2
    assert decreased_reinforced.count("object_direction_qualifier = 'decreased'") == 2
    assert ":MINER_GENE_DISEASE_EVIDENCE" not in increased_opposed
    assert ":MINER_GENE_DISEASE_EVIDENCE" in genetic
    assert "gene_evidence._miner_disease_rank <= 3" in genetic
    assert "anatomy:AnatomicalEntity" in anatomy
    assert "production:PRODUCES" in anatomy
    assert "'infores:semmeddb'" in anatomy


def test_causal_module_provenance_compiles_manifestation_gate():
    repeated = causal_module_provenance_cypher(
        "repeated_evidence_top_three_manifestation_gated"
    )
    binding = causal_module_provenance_cypher(
        "multisource_binding_top_three_manifestation_gated"
    )
    consensus = causal_module_provenance_cypher(
        "evidence_binding_consensus_top_three_manifestation_gated"
    )

    for query in (repeated, binding, consensus):
        assert ":HAS_SIDE_EFFECT" in query
        assert ":MANIFESTATION_OF" in query
        assert "NOT EXISTS" in query
    assert "effect.evidence_count" in repeated
    assert "collect(DISTINCT binding_source)" in binding
    assert "effect.evidence_count" in consensus


def test_anatomy_cell_part_localization_compiles_directional_controls():
    gof = anatomy_cell_part_localization_cypher("gof_corrective")
    gof_control = anatomy_cell_part_localization_cypher("gof_worsening")
    lof = anatomy_cell_part_localization_cypher("lof_corrective")
    lof_control = anatomy_cell_part_localization_cypher("lof_worsening")

    assert "(anatomy:AnatomicalEntity)-[part:HAS_PART]->(cell)" in gof
    assert "(target)-[expression:EXPRESSED_IN]->(cell:Cell)" in gof
    assert ":LOCATED_IN|OCCURS_IN" in gof
    assert "gain_of_function_variant_form" in gof
    assert "object_direction_qualifier = 'decreased'" in gof
    assert "object_direction_qualifier = 'increased'" in gof_control
    assert "loss_of_function_variant_form" in lof
    assert "object_direction_qualifier = 'increased'" in lof
    assert "object_direction_qualifier = 'decreased'" in lof_control


def test_ortholog_phenotype_direction_compiles_corrective_and_control_modes():
    gof = ortholog_phenotype_direction_cypher("gof_corrective")
    lof = ortholog_phenotype_direction_cypher("lof_corrective")
    control = ortholog_phenotype_direction_cypher("lof_worsening")
    gated = ortholog_phenotype_direction_cypher("gof_corrective_no_opposite")

    assert "[:ORTHOLOGOUS_TO]" in gof
    assert "infores:mgi" in gof
    assert "gain_of_function_variant_form" in gof
    assert "object_direction_qualifier = 'decreased'" in gof
    assert "loss_of_function_variant_form" in lof
    assert "object_direction_qualifier = 'increased'" in lof
    assert "object_direction_qualifier = 'decreased'" in control
    assert "NOT EXISTS" in gated
    assert "opposite.object_direction_qualifier = 'increased'" in gated


def test_molecular_activity_correction_compiles_variant_direction_controls():
    gof = molecular_activity_correction_cypher("gof_corrective")
    lof = molecular_activity_correction_cypher("lof_corrective")
    control = molecular_activity_correction_cypher("gof_worsening")

    assert "<-[:ENABLES]-(driver:Gene)" in gof
    assert "gain_of_function_variant_form" in gof
    assert "object_direction_qualifier = 'decreased'" in gof
    assert "loss_of_function_variant_form" in lof
    assert "object_direction_qualifier = 'increased'" in lof
    assert "object_direction_qualifier = 'increased'" in control
    assert "activity._miner_gene_enable_degree <= 58" in control


def test_molecular_activity_degree_is_cleared_and_indexed():
    clear_text = "\n".join(query for _, query in CLEAR_QUERIES)
    index_text = "\n".join(INDEX_QUERIES)

    assert clear_text.count("entity._miner_gene_enable_degree") == 2
    assert "FOR (activity:MolecularActivity)" in index_text
    assert "ON (activity._miner_gene_enable_degree)" in index_text


def test_signed_regulatory_cascade_compiles_corrective_and_control_modes():
    gof = signed_regulatory_cascade_cypher("gof_corrective")
    lof = signed_regulatory_cascade_cypher("lof_corrective")
    control = signed_regulatory_cascade_cypher("gof_worsening")

    assert "[gene_effect:REGULATES]" in gof
    assert "infores:signor" in gof
    assert "gain_of_function_variant_form" in gof
    assert "decreased' AND gene_effect.object_direction_qualifier" in gof
    assert "= 'upregulated'" in gof
    assert "increased' AND gene_effect.object_direction_qualifier" in gof
    assert "= 'downregulated'" in gof
    assert "loss_of_function_variant_form" in lof
    assert "decreased' AND gene_effect.object_direction_qualifier" in lof
    assert "= 'downregulated'" in lof
    assert "increased' AND gene_effect.object_direction_qualifier" in control
    assert "= 'upregulated'" in control


def test_multi_driver_connector_compiles_base_control_and_compact_modes():
    base = multi_driver_connector_cypher("decreased")
    control = multi_driver_connector_cypher("increased_control")
    compact = multi_driver_connector_cypher("decreased_compact")
    process = multi_driver_connector_cypher("decreased_process")

    assert "collect(DISTINCT driver) AS drivers" in base
    assert "size(drivers) >= 2" in base
    assert "object_direction_qualifier = 'decreased'" in base
    assert "object_direction_qualifier = 'increased'" in control
    assert "COUNT {" not in base
    assert "COUNT {" in compact
    assert "} <= 10" in compact
    assert "(target)-[:INVOLVED_IN]->(process:BiologicalProcess)" in process
    assert "process._miner_gene_member_degree <= 100" in process
    assert "object, process, collect(DISTINCT driver)" in process


def test_dual_target_dual_driver_connector_compiles_topologies():
    base = dual_target_dual_driver_connector_cypher("decreased")
    control = dual_target_dual_driver_connector_cypher("increased_control")
    process = dual_target_dual_driver_connector_cypher("decreased_process")

    assert "target1.id < target2.id" in base
    assert "driver1.id < driver2.id" in base
    assert "effect1.object_direction_qualifier = 'decreased'" in base
    assert "effect2.object_direction_qualifier = 'decreased'" in base
    assert "effect1.object_direction_qualifier = 'increased'" in control
    assert "effect2.object_direction_qualifier = 'increased'" in control
    assert "(driver1)-[:INVOLVED_IN]->(process:BiologicalProcess)" in process
    assert "process._miner_gene_member_degree <= 100" in process


def test_phenotype_therapeutic_decomposition_compiles_specificity_ablation():
    base = phenotype_therapeutic_decomposition_cypher("base")
    specific = phenotype_therapeutic_decomposition_cypher("specific")
    gated = phenotype_therapeutic_decomposition_cypher(
        "specific_adverse_gated"
    )
    contraindication_gated = phenotype_therapeutic_decomposition_cypher(
        "specific_contraindication_gated"
    )

    assert "[symptom_treatment:TREATS]" in base
    assert "<-[:HAS_PHENOTYPE]-(object:Disease)" in base
    assert "infores:drug-repurposing-hub" in base
    assert "infores:ttd" in base
    assert "evidence._miner_disease_rank <= 3" in base
    assert "_miner_disease_member_degree" not in base
    assert "phenotype._miner_disease_member_degree <= 34" in specific
    assert "NOT EXISTS" in gated
    assert "CONTRAINDICATED_IN|EXACERBATES_CONDITION|CAUSES" in gated
    assert "CONTRAINDICATED_IN|EXACERBATES_CONDITION" in contraindication_gated
    assert "|CAUSES" not in contraindication_gated


def test_transporter_tissue_delivery_compiles_independent_delivery_branch():
    cypher = transporter_tissue_delivery_cypher()
    no_efflux = transporter_tissue_delivery_cypher("no_efflux")

    assert "(transporter:Gene)-[:HAS_SUBSTRATE]->(subject:Drug)" in cypher
    assert "{id: 'GO:0005215'}" in cypher
    assert "transporter <> target" in cypher
    assert cypher.count("'NCBITaxon:9606'") == 2
    assert "transport_expression:EXPRESSED_IN" in cypher
    assert "target_expression:EXPRESSED_IN" in cypher
    assert "infores:bgee" in cypher
    assert "GO:0015562" not in cypher
    assert "GO:0015562" in no_efflux
    assert "NOT EXISTS" in no_efflux


def test_direct_abundance_correction_compiles_lof_control():
    corrective = direct_abundance_correction_cypher("lof_corrective")
    control = direct_abundance_correction_cypher("lof_worsening")

    assert "object_aspect_qualifier = 'abundance'" in corrective
    assert "loss_of_function_variant_form" in corrective
    assert "object_direction_qualifier = 'increased'" in corrective
    assert "object_direction_qualifier = 'decreased'" in control


def test_direct_splicing_rescue_compiles_lof_mechanism():
    cypher = direct_splicing_rescue_cypher()

    assert "object_aspect_qualifier = 'splicing'" in cypher
    assert "infores:ctd" in cypher
    assert "loss_of_function_variant_form" in cypher
    assert "object_direction_qualifier" not in cypher


def test_direct_activity_correction_compiles_variant_direction_controls():
    gof = direct_activity_correction_cypher("gof_corrective")
    lof = direct_activity_correction_cypher("lof_corrective")
    control = direct_activity_correction_cypher("lof_worsening")

    assert "object_aspect_qualifier = 'activity'" in gof
    assert "gain_of_function_variant_form" in gof
    assert "object_direction_qualifier = 'decreased'" in gof
    assert "loss_of_function_variant_form" in lof
    assert "object_direction_qualifier = 'increased'" in lof
    assert "object_direction_qualifier = 'decreased'" in control


def test_activity_class_correction_compiles_channel_and_enzyme_controls():
    channel = activity_class_correction_cypher("gof_voltage_corrective")
    channel_control = activity_class_correction_cypher(
        "gof_voltage_worsening"
    )
    enzyme = activity_class_correction_cypher("lof_catalytic_corrective")
    enzyme_control = activity_class_correction_cypher(
        "lof_catalytic_worsening"
    )

    assert "GO:0005244" in channel
    assert "gain_of_function_variant_form" in channel
    assert "object_direction_qualifier = 'decreased'" in channel
    assert "object_direction_qualifier = 'increased'" in channel_control
    assert "GO:0003824" in enzyme
    assert "loss_of_function_variant_form" in enzyme
    assert "object_direction_qualifier = 'increased'" in enzyme
    assert "object_direction_qualifier = 'decreased'" in enzyme_control


def test_downstream_interception_compiles_variant_direction_controls():
    gof = downstream_interception_cypher("gof_corrective")
    gof_control = downstream_interception_cypher("gof_worsening")
    lof = downstream_interception_cypher("lof_corrective")
    lof_control = downstream_interception_cypher("lof_worsening")

    assert "gain_of_function_variant_form" in gof
    assert "WHEN 'upregulated' THEN 'decreased'" in gof
    assert "WHEN 'upregulated' THEN 'increased'" in gof_control
    assert "loss_of_function_variant_form" in lof
    assert "WHEN 'upregulated' THEN 'increased'" in lof
    assert "WHEN 'upregulated' THEN 'decreased'" in lof_control
    assert "infores:signor" in gof


def test_downstream_interception_compiles_regulatory_branch_variants():
    gof_up = downstream_interception_cypher("gof_up_corrective")
    gof_down_control = downstream_interception_cypher("gof_down_worsening")
    lof_up = downstream_interception_cypher("lof_up_corrective")
    lof_down = downstream_interception_cypher("lof_down_corrective")

    assert "regulation.object_direction_qualifier = 'upregulated'" in gof_up
    assert "WHEN 'upregulated' THEN 'decreased'" in gof_up
    assert (
        "regulation.object_direction_qualifier = 'downregulated'"
        in gof_down_control
    )
    assert "WHEN 'upregulated' THEN 'increased'" in gof_down_control
    assert "regulation.object_direction_qualifier = 'upregulated'" in lof_up
    assert "regulation.object_direction_qualifier = 'downregulated'" in lof_down


def test_downstream_interception_compiles_multisource_binding_gate():
    corrective = downstream_interception_cypher(
        "lof_down_multisource_corrective"
    )
    control = downstream_interception_cypher("lof_down_multisource_worsening")

    assert "collect(DISTINCT binding)" in corrective
    assert "size(binding_sources) >= 2" in corrective
    assert "WHEN 'upregulated' THEN 'increased'" in corrective
    assert "WHEN 'upregulated' THEN 'decreased'" in control


def test_protein_turnover_correction_compiles_exact_aspect_controls():
    gof_degradation = protein_turnover_correction_cypher(
        "gof_degradation_corrective"
    )
    gof_stability = protein_turnover_correction_cypher(
        "gof_stability_corrective"
    )
    lof_degradation = protein_turnover_correction_cypher(
        "lof_degradation_corrective"
    )
    lof_control = protein_turnover_correction_cypher(
        "lof_degradation_worsening"
    )
    secretion = protein_turnover_correction_cypher(
        "lof_secretion_corrective"
    )

    assert "gain_of_function_variant_form" in gof_degradation
    assert "object_aspect_qualifier = 'degradation'" in gof_degradation
    assert "object_direction_qualifier = 'increased'" in gof_degradation
    assert "object_aspect_qualifier = 'stability'" in gof_stability
    assert "object_direction_qualifier = 'decreased'" in gof_stability
    assert "loss_of_function_variant_form" in lof_degradation
    assert "object_direction_qualifier = 'decreased'" in lof_degradation
    assert "object_direction_qualifier = 'increased'" in lof_control
    assert "object_aspect_qualifier = 'secretion'" in secretion


def test_allele_expression_correction_compiles_inheritance_controls():
    gof = allele_expression_correction_cypher("ad_gof_decrease")
    dominant_negative = allele_expression_correction_cypher(
        "ad_dominant_negative_decrease"
    )
    ad_lof = allele_expression_correction_cypher("ad_lof_increase")
    ar_lof = allele_expression_correction_cypher("ar_lof_increase")

    assert "object_aspect_qualifier = 'expression'" in gof
    assert "gain_of_function_variant_form" in gof
    assert "allelic_requirement = 'HP:0000006'" in gof
    assert "object_direction_qualifier = 'decreased'" in gof
    assert "dominant_negative_variant_form" in dominant_negative
    assert "loss_of_function_variant_form" in ad_lof
    assert "object_direction_qualifier = 'increased'" in ad_lof
    assert "allelic_requirement = 'HP:0000007'" in ar_lof


def test_allele_expression_correction_compiles_opposite_direction_veto():
    corrective = allele_expression_correction_cypher(
        "ad_dominant_negative_decrease_unopposed"
    )
    control = allele_expression_correction_cypher(
        "ad_dominant_negative_increase_unopposed"
    )

    assert "NOT EXISTS" in corrective
    assert "opposite_effect.object_direction_qualifier = 'increased'" in corrective
    assert "opposite_effect.object_direction_qualifier = 'decreased'" in control


def test_epigenetic_expression_consensus_compiles_paired_lof_directions():
    cypher = epigenetic_expression_consensus_cypher()

    assert "methylation.object_aspect_qualifier = 'methylation'" in cypher
    assert "methylation.object_direction_qualifier = 'decreased'" in cypher
    assert "expression.object_aspect_qualifier = 'expression'" in cypher
    assert "expression.object_direction_qualifier = 'increased'" in cypher
    assert "loss_of_function_variant_form" in cypher


def test_functional_dosage_consensus_compiles_matched_lof_directions():
    corrective = functional_dosage_consensus_cypher("lof_corrective")
    control = functional_dosage_consensus_cypher("lof_worsening")

    assert "activity.object_aspect_qualifier = 'activity'" in corrective
    assert "abundance.object_aspect_qualifier = 'abundance'" in corrective
    assert "activity.object_direction_qualifier = 'increased'" in corrective
    assert "abundance.object_direction_qualifier = 'increased'" in corrective
    assert "activity.object_direction_qualifier = 'decreased'" in control
    assert "loss_of_function_variant_form" in corrective


def test_dominant_negative_activity_compiles_matched_directions():
    corrective = dominant_negative_activity_cypher("corrective")
    control = dominant_negative_activity_cypher("worsening")

    assert "dominant_negative_variant_form" in corrective
    assert "object_aspect_qualifier = 'activity'" in corrective
    assert "object_direction_qualifier = 'decreased'" in corrective
    assert "object_direction_qualifier = 'increased'" in control


def test_phosphorylation_activity_consensus_compiles_signed_branches():
    gof_corrective = phosphorylation_activity_consensus_cypher("gof_corrective")
    gof_unopposed = phosphorylation_activity_consensus_cypher("gof_unopposed")
    gof_discordant = phosphorylation_activity_consensus_cypher("gof_discordant")
    lof_corrective = phosphorylation_activity_consensus_cypher("lof_corrective")

    assert "activity.object_aspect_qualifier = 'activity'" in gof_corrective
    assert (
        "phosphorylation.object_aspect_qualifier = 'phosphorylation'"
        in gof_corrective
    )
    assert "gain_of_function_variant_form" in gof_corrective
    assert "phosphorylation.object_direction_qualifier = 'decreased'" in gof_corrective
    assert "phosphorylation.object_direction_qualifier = 'increased'" in gof_discordant
    assert "AND NOT EXISTS {" in gof_unopposed
    assert "opposite.object_direction_qualifier = 'increased'" in gof_unopposed
    assert "loss_of_function_variant_form" in lof_corrective
    assert "activity.object_direction_qualifier = 'increased'" in lof_corrective


def test_literature_allele_activity_correction_compiles_controls():
    gof = literature_allele_activity_correction_cypher("gof_corrective")
    lof = literature_allele_activity_correction_cypher("lof_corrective")
    lof_control = literature_allele_activity_correction_cypher("lof_worsening")

    assert "gain_of_function_variant_form" in gof
    assert "effect.object_direction_qualifier = 'decreased'" in gof
    assert "loss_of_function_variant_form" in lof
    assert "effect.object_direction_qualifier = 'increased'" in lof
    assert "effect.object_direction_qualifier = 'decreased'" in lof_control
    assert "evidence._miner_causal_publication_count >= 3" in gof
    assert "evidence._miner_causal_publication_npmi >= 0.5" in gof
    assert "evidence._miner_disease_rank <= 3" in gof


def test_go_cam_input_flow_compiles_signed_branches():
    gof = go_cam_input_flow_cypher("gof_corrective")
    lof = go_cam_input_flow_cypher("lof_corrective")
    control = go_cam_input_flow_cypher("lof_worsening")

    assert "[flow:IS_INPUT_OF]" in gof
    assert "'infores:go-cam' IN" in gof
    assert "gain_of_function_variant_form" in gof
    assert "effect.object_direction_qualifier = 'decreased'" in gof
    assert "loss_of_function_variant_form" in lof
    assert "effect.object_direction_qualifier = 'increased'" in lof
    assert "effect.object_direction_qualifier = 'decreased'" in control


def test_active_component_regulatory_cascade_compiles_controls():
    gof = active_component_regulatory_cascade_cypher("gof_corrective")
    lof = active_component_regulatory_cascade_cypher("lof_corrective")
    control = active_component_regulatory_cascade_cypher("gof_worsening")

    assert "[gene_effect:REGULATES]" in gof
    assert "[:ACTIVE_IN]->(component:CellularComponent)" in gof
    assert "component._miner_component_active_gene_degree <= 185" in gof
    assert "gain_of_function_variant_form" in gof
    assert "'decreased' AND gene_effect.object_direction_qualifier" in gof
    assert "loss_of_function_variant_form" in lof
    assert "'increased' AND gene_effect.object_direction_qualifier" in lof
    assert "gain_of_function_variant_form" in control


def test_signed_go_process_restoration_compiles_controls():
    lof = signed_go_process_restoration_cypher("lof_corrective")
    control = signed_go_process_restoration_cypher("lof_worsening")
    gof = signed_go_process_restoration_cypher("gof_corrective")
    unopposed = signed_go_process_restoration_cypher("lof_corrective_unopposed")

    assert "[target_process]->(process:BiologicalProcess)" in lof
    assert "ACTS_UPSTREAM_OF_OR_WITHIN_POSITIVE_EFFECT" in lof
    assert "loss_of_function_variant_form" in lof
    assert "WHERE 'corrective' IN path_modes" in lof
    assert "WHERE 'worsening' IN path_modes" in control
    assert "NOT 'worsening' IN path_modes" in unopposed
    assert "gain_of_function_variant_form" in gof


def test_molecular_activity_complex_compensation_compiles_controls():
    lof = molecular_activity_complex_compensation_cypher("lof_corrective")
    gof = molecular_activity_complex_compensation_cypher("gof_corrective")
    control = molecular_activity_complex_compensation_cypher("lof_worsening")

    assert "[:ENABLES]->(activity:MolecularActivity)" in lof
    assert "[:DIRECTLY_PHYSICALLY_INTERACTS_WITH]-(driver)" in lof
    assert "loss_of_function_variant_form" in lof
    assert "effect.object_direction_qualifier = 'increased'" in lof
    assert "gain_of_function_variant_form" in gof
    assert "effect.object_direction_qualifier = 'decreased'" in gof
    assert "effect.object_direction_qualifier = 'decreased'" in control


def test_causal_module_provenance_compiles_unopposed_variants():
    repeated = causal_module_provenance_cypher(
        "repeated_evidence_unopposed_top_three"
    )
    consensus = causal_module_provenance_cypher(
        "evidence_binding_consensus_unopposed_top_three"
    )

    assert "opposite.object_direction_qualifier = 'increased'" in repeated
    assert "effect.evidence_count" in repeated
    assert "binding.primary_knowledge_sources" in consensus
    assert "count(DISTINCT gene) AS targeted_genes" in consensus


def test_activity_class_correction_compiles_extended_classes():
    kinase = activity_class_correction_cypher("gof_kinase_corrective")
    gtpase = activity_class_correction_cypher("gof_gtpase_worsening")
    receptor = activity_class_correction_cypher("lof_receptor_corrective")
    multisource = activity_class_correction_cypher(
        "gof_gtpase_corrective_multisource"
    )

    assert "GO:0016301" in kinase
    assert "gain_of_function_variant_form" in kinase
    assert "object_direction_qualifier = 'decreased'" in kinase
    assert "GO:0003924" in gtpase
    assert "object_direction_qualifier = 'increased'" in gtpase
    assert "GO:0004888" in receptor
    assert "loss_of_function_variant_form" in receptor
    assert "count(DISTINCT effect_source) AS effect_source_count" in multisource
    assert "effect_source_count >= 2" in multisource
    assert "GO:0003925" in activity_class_correction_cypher(
        "gof_gprotein_corrective_multisource"
    )


def test_mutant_form_correction_compiles_corrective_and_control():
    corrective = mutant_form_correction_cypher("gof_corrective")
    control = mutant_form_correction_cypher("gof_worsening")

    assert corrective.count("object_form_or_variant_qualifier = 'mutant_form'") == 2
    assert "gain_of_function_variant_form" in corrective
    assert "effect.object_direction_qualifier = 'decreased'" in corrective
    assert "effect.object_direction_qualifier = 'increased'" in control


def test_pharmacologic_mechanism_correction_compiles_all_modes():
    gof = pharmacologic_mechanism_correction_cypher("gof_corrective")
    gof_control = pharmacologic_mechanism_correction_cypher("gof_worsening")
    lof = pharmacologic_mechanism_correction_cypher("lof_corrective")
    lof_control = pharmacologic_mechanism_correction_cypher("lof_worsening")
    activation = pharmacologic_mechanism_correction_cypher(
        "lof_activation_only"
    )
    activation_control = pharmacologic_mechanism_correction_cypher(
        "gof_activation_only_control"
    )
    opening = pharmacologic_mechanism_correction_cypher("lof_opening_only")
    opening_control = pharmacologic_mechanism_correction_cypher(
        "gof_opening_only_control"
    )
    antibody = pharmacologic_mechanism_correction_cypher(
        "gof_antibody_inhibition_only"
    )
    antibody_control = pharmacologic_mechanism_correction_cypher(
        "lof_antibody_inhibition_control"
    )

    assert "gain_of_function_variant_form" in gof
    assert "effect.object_direction_qualifier = 'decreased'" in gof
    assert "'inhibition'" in gof
    assert "'molecular_channel_blockage'" in gof
    assert "effect.object_direction_qualifier = 'increased'" in gof_control
    assert "'agonism'" in gof_control
    assert "loss_of_function_variant_form" in lof
    assert "'positive_allosteric_modulation'" in lof
    assert "effect.object_direction_qualifier = 'decreased'" in lof_control
    assert "effect.object_aspect_qualifier = 'activity'" in lof_control
    assert "['activation']" in activation
    assert "loss_of_function_variant_form" in activation
    assert "gain_of_function_variant_form" in activation_control
    assert "['opening']" in opening
    assert "loss_of_function_variant_form" in opening
    assert "gain_of_function_variant_form" in opening_control
    assert "['antibody_inhibition']" in antibody
    assert "gain_of_function_variant_form" in antibody
    assert "loss_of_function_variant_form" in antibody_control


def test_direct_disease_process_correction_compiles_orientations_and_signs():
    downstream = direct_disease_process_correction_cypher(
        "disease_causes_process_decreased"
    )
    downstream_control = direct_disease_process_correction_cypher(
        "disease_causes_process_increased"
    )
    etiologic = direct_disease_process_correction_cypher(
        "process_causes_disease_decreased"
    )
    etiologic_control = direct_disease_process_correction_cypher(
        "process_causes_disease_increased"
    )

    assert "(object:Disease)-[etiology:CAUSES]->" in downstream
    assert "effect.object_direction_qualifier = 'decreased'" in downstream
    assert "effect.object_direction_qualifier = 'increased'" in downstream_control
    assert "(process:BiologicalProcess)-[etiology:CAUSES]->" in etiologic
    assert "effect.object_direction_qualifier = 'decreased'" in etiologic
    assert "effect.object_direction_qualifier = 'increased'" in etiologic_control
    assert "'infores:ctd'" in etiologic
    assert "'infores:semmeddb'" in etiologic


def test_etiologic_mediator_production_compiles_directional_control():
    corrective = etiologic_mediator_production_cypher("decreased")
    control = etiologic_mediator_production_cypher("increased_control")

    assert "producer:Gene" in corrective
    assert "production:PRODUCES" in corrective
    assert "mediator:ChemicalEntity" in corrective
    assert "etiology:CAUSES" in corrective
    assert "evidence._miner_disease_rank <= 3" in corrective
    assert "effect.object_aspect_qualifier = 'activity'" in corrective
    assert "effect.object_direction_qualifier = 'decreased'" in corrective
    assert "effect.object_direction_qualifier = 'increased'" in control
    assert "infores:drug-repurposing-hub" in corrective
    assert "infores:ttd" in corrective


def test_close_match_mechanism_transfer_compiles_directional_control():
    corrective = close_match_mechanism_transfer_cypher("decreased")
    control = close_match_mechanism_transfer_cypher("increased_control")

    assert "similarity:CLOSE_MATCH" in corrective
    assert "comparator:ChemicalEntity" in corrective
    assert "effect.object_aspect_qualifier = 'activity'" in corrective
    assert "effect.object_direction_qualifier = 'decreased'" in corrective
    assert "effect.object_direction_qualifier = 'increased'" in control
    assert "evidence._miner_disease_rank <= 3" in corrective
    assert "'infores:semmeddb'" in corrective
    assert "infores:drug-repurposing-hub" in corrective
    assert "infores:ttd" in corrective


def test_variant_component_correction_compiles_variant_sign_cells():
    lof = variant_component_correction_cypher("lof_corrective")
    gof_control = variant_component_correction_cypher("gof_worsening")

    assert "(component:CellularComponent)" in lof
    assert "<-[:PART_OF]-(driver:Gene)" in lof
    assert "loss_of_function_variant_form" in lof
    assert "object_direction_qualifier = 'increased'" in lof
    assert "gain_of_function_variant_form" in gof_control
    assert "object_direction_qualifier = 'increased'" in gof_control


def test_disrupted_process_variant_correction_compiles_sign_cells():
    gof = disrupted_process_variant_correction_cypher("gof_corrective")
    lof_control = disrupted_process_variant_correction_cypher("lof_worsening")

    assert "(process:BiologicalProcess)" in gof
    assert "disruption:DISRUPTS" in gof
    assert "binding:DIRECTLY_PHYSICALLY_INTERACTS_WITH" in gof
    assert "gain_of_function_variant_form" in gof
    assert "object_direction_qualifier = 'decreased'" in gof
    assert "loss_of_function_variant_form" in lof_control
    assert "object_direction_qualifier = 'decreased'" in lof_control


def test_disrupted_activity_variant_correction_compiles_sign_cells():
    gof = disrupted_activity_variant_correction_cypher("gof_corrective")
    exact = disrupted_activity_variant_correction_cypher(
        "gof_corrective_activity"
    )
    broad = disrupted_activity_variant_correction_cypher(
        "gof_corrective_activity_or_abundance"
    )
    lof_control = disrupted_activity_variant_correction_cypher("lof_worsening")

    assert "(activity:MolecularActivity)" in gof
    assert "disruption:DISRUPTS" in gof
    assert "<-[:ENABLES]-(driver:Gene)" in gof
    assert "gain_of_function_variant_form" in gof
    assert "object_direction_qualifier = 'decreased'" in gof
    assert "object_aspect_qualifier = 'activity'" in exact
    assert "object_aspect_qualifier = 'activity_or_abundance'" in broad
    assert "loss_of_function_variant_form" in lof_control
    assert "object_direction_qualifier = 'decreased'" in lof_control


def test_dual_arm_process_target_correction_compiles_control():
    corrective = dual_arm_process_target_correction_cypher("decreased")
    control = dual_arm_process_target_correction_cypher("increased_control")
    clean = dual_arm_process_target_correction_cypher(
        "decreased_no_strong_harm"
    )

    assert "disruption:DISRUPTS" in corrective
    assert "path_evidence:GENETIC_ASSOCIATION" in corrective
    assert "gene_evidence:MINER_GENE_DISEASE_EVIDENCE" in corrective
    assert "gene_evidence._miner_disease_rank <= 3" in corrective
    assert "object_direction_qualifier = 'decreased'" in corrective
    assert "object_direction_qualifier = 'increased'" in control
    assert "NOT EXISTS" in clean
    assert "HAS_SIDE_EFFECT" in clean
    assert "PREDISPOSES_TO_CONDITION" in clean


def test_interaction_bridged_dual_arm_compiles_bridge_modes():
    physical = interaction_bridged_dual_arm_cypher("physical_decreased")
    direct_control = interaction_bridged_dual_arm_cypher("direct_increased")

    assert "type(bridge) = 'PHYSICALLY_INTERACTS_WITH'" in physical
    assert "(partner:Gene)-[:INVOLVED_IN]->(process)" in physical
    assert "infores:intact" not in physical
    assert "object_direction_qualifier = 'decreased'" in physical
    assert (
        "type(bridge) = 'DIRECTLY_PHYSICALLY_INTERACTS_WITH'"
        in direct_control
    )
    assert "object_direction_qualifier = 'increased'" in direct_control


def test_signed_regulatory_bridged_dual_arm_compiles_controls():
    corrective = signed_regulatory_bridged_dual_arm_cypher(
        "downstream_decreased"
    )
    direction_control = signed_regulatory_bridged_dual_arm_cypher(
        "downstream_increased"
    )
    topology_control = signed_regulatory_bridged_dual_arm_cypher(
        "reverse_decreased"
    )
    clean = signed_regulatory_bridged_dual_arm_cypher(
        "reverse_decreased_no_curated_adverse_manifestation"
    )
    adverse = signed_regulatory_bridged_dual_arm_cypher(
        "reverse_decreased_curated_adverse_manifestation"
    )

    assert "(target)-[bridge:REGULATES]->(partner)" in corrective
    assert "bridge.object_direction_qualifier = 'upregulated'" in corrective
    assert "object_direction_qualifier = 'decreased'" in corrective
    assert "object_direction_qualifier = 'increased'" in direction_control
    assert "(partner)-[bridge:REGULATES]->(target)" in topology_control
    assert "AND NOT EXISTS" in clean
    assert "phenotype:HAS_PHENOTYPE" in clean
    assert "infores:hpo-annotations" in clean
    assert "MANIFESTATION_OF" in clean
    assert "AND EXISTS" in adverse


def test_ontology_generalized_signed_interception_compiles_control():
    corrective = ontology_generalized_signed_interception_cypher(
        "parent_decreased"
    )
    control = ontology_generalized_signed_interception_cypher(
        "parent_increased"
    )

    assert "<-[ontology:SUBCLASS_OF]-(disease_process" in corrective
    assert "infores:ubergraph" in corrective
    assert "(partner)-[bridge:REGULATES]->(target)" in corrective
    assert "object_direction_qualifier = 'decreased'" in corrective
    assert "object_direction_qualifier = 'increased'" in control


def test_tissue_localized_ontology_interception_compiles_control():
    corrective = tissue_localized_ontology_interception_cypher("decreased")
    control = tissue_localized_ontology_interception_cypher("increased")

    assert "target_expression:EXPRESSED_IN" in corrective
    assert "partner_expression:EXPRESSED_IN" in corrective
    assert "(object)-[:LOCATED_IN|OCCURS_IN]->(anatomy)" in corrective
    assert corrective.count("infores:bgee") == 2
    assert "object_direction_qualifier = 'decreased'" in corrective
    assert "object_direction_qualifier = 'increased'" in control


def test_dual_process_ontology_convergence_compiles_control():
    corrective = dual_process_ontology_convergence_cypher("decreased")
    control = dual_process_ontology_convergence_cypher("increased")

    assert "count(DISTINCT broader_process)" in corrective
    assert "parent_process_count >= 2" in corrective
    assert "object_direction_qualifier = 'decreased'" in corrective
    assert "object_direction_qualifier = 'increased'" in control


def test_rule_trapi_template_is_loaded_relative_to_rules_file(tmp_path: Path):
    template_dir = tmp_path / "trapi"
    template_dir.mkdir()
    template = {
        "message": {
            "query_graph": {
                "nodes": {"n0": {"ids": ["CHEBI:1"]}, "n1": {"ids": ["MONDO:1"]}},
                "edges": {
                    "e0": {
                        "subject": "n0",
                        "object": "n1",
                        "predicates": ["biolink:related_to"],
                    }
                },
            }
        }
    }
    (template_dir / "rule.json").write_text(json.dumps(template), encoding="utf-8")
    rules_path = tmp_path / "rules.toml"
    rules_path.write_text(
        """
[[rules]]
id = "R1"
name = "test"
iteration = 1
status = "candidate"
hypothesis = "test"
body = "test"
mechanism_score = "medium"
mechanism_rationale = "test"
uses_treatment_edges = false
trapi_expressibility = "partial"
trapi_notes = "test"
trapi_template = "trapi/rule.json"
cypher = "RETURN 'a' AS subject_id, 'b' AS object_id"
""",
        encoding="utf-8",
    )

    rule = load_rules(rules_path, {"R1"})[0]

    assert load_trapi_payload(rule, rules_path) == template
    assert response_summary(
        rule,
        {
            "message": {
                "results": [{}, {}],
                "knowledge_graph": {"nodes": {"a": {}}, "edges": {"e": {}}},
            }
        },
    ) == {
        "rule": "R1",
        "template": "trapi/rule.json",
        "result_count": 2,
        "knowledge_graph_node_count": 1,
        "knowledge_graph_edge_count": 1,
        "log_count": 0,
    }


def test_iteration_7_rules_are_retained_with_executable_artifacts():
    rules_path = PROJECT_ROOT / "rules" / "treats-rules.toml"
    rules = load_rules(rules_path, ITERATION_7_RULE_IDS)

    assert {rule.id for rule in rules} == ITERATION_7_RULE_IDS
    assert all(rule.status == "retained" for rule in rules)
    assert all(rule.trapi_template is not None for rule in rules)
    assert all("RETURN DISTINCT subject.id AS subject_id" in rule.cypher for rule in rules)


def test_iteration_7_rules_are_retained_but_superseded_on_the_visible_front():
    library = json.loads(
        (PROJECT_ROOT / "results" / "rule-library.json").read_text(encoding="utf-8")
    )
    results = {
        result["id"]: result
        for result in library["results"]
        if result["id"] in ITERATION_7_RULE_IDS
    }

    assert set(results) == ITERATION_7_RULE_IDS
    assert all(result["library_status"] == "retained" for result in results.values())
    assert all(result["status"] == "completed" for result in results.values())
    assert all(not result["pareto_visible"] for result in results.values())
    assert all(
        result["counts"]["unresolved_or_blind_pairs"] > 0
        for result in results.values()
    )


def test_iteration_8_rules_are_retained_and_have_current_surface_annotations():
    rules_path = PROJECT_ROOT / "rules" / "treats-rules.toml"
    rules = load_rules(rules_path, ITERATION_8_RULE_IDS)
    library = json.loads(
        (PROJECT_ROOT / "results" / "rule-library.json").read_text(encoding="utf-8")
    )
    results = {
        result["id"]: result
        for result in library["results"]
        if result["id"] in ITERATION_8_RULE_IDS
    }

    assert {rule.id for rule in rules} == ITERATION_8_RULE_IDS
    assert all(rule.status == "retained" for rule in rules)
    assert set(results) == ITERATION_8_RULE_IDS
    assert all(result["status"] == "completed" for result in results.values())
    assert all("pareto_visible" in result for result in results.values())
    assert any(result["pareto_visible"] for result in results.values())
    assert all(
        result["counts"]["validation_hits"] > 0
        and result["counts"]["unresolved_or_blind_pairs"] > 0
        for result in results.values()
    )


def test_f_beta_skews_toward_precision():
    assert f_beta(0.8, 0.2, beta=0.5) > f_beta(0.2, 0.8, beta=0.5)


def test_search_conditions_treat_missing_numeric_values_as_false():
    assert numeric_condition("degree", "<=", 5).predicate({"degree": 5})
    assert not numeric_condition("degree", "<=", 5).predicate({"degree": None})
    assert boolean_condition("supported").predicate({"supported": True})
    assert boolean_condition("supported", expected=False).predicate(
        {"supported": False}
    )


def test_pair_metrics_deduplicates_paths():
    rows = [
        {
            "subject_id": "CHEM:1",
            "object_id": "MONDO:1",
            "training_hit": True,
            "validation_hit": False,
        },
        {
            "subject_id": "CHEM:1",
            "object_id": "MONDO:1",
            "training_hit": True,
            "validation_hit": False,
        },
        {
            "subject_id": "CHEM:2",
            "object_id": "MONDO:2",
            "training_hit": False,
            "validation_hit": True,
        },
        {
            "subject_id": "CHEM:3",
            "object_id": "MONDO:3",
            "training_hit": False,
            "validation_hit": False,
        },
    ]

    assert pair_metrics(rows, range(len(rows))) == {
        "candidate_pairs": 3,
        "training_hits": 1,
        "validation_hits": 1,
        "visible_hits": 2,
        "unresolved_or_blind_pairs": 1,
        "visible_precision": 2 / 3,
    }


def test_pareto_search_requires_an_unresolved_prediction():
    configs = [
        {
            "name": "no prediction",
            "metrics": {
                "candidate_pairs": 2,
                "visible_hits": 2,
                "visible_precision": 1.0,
            },
        },
        {
            "name": "predictive",
            "metrics": {
                "candidate_pairs": 3,
                "visible_hits": 2,
                "visible_precision": 2 / 3,
            },
        },
    ]

    assert pareto_configs(configs) == [configs[1]]


def test_current_front_dominance():
    front = [{"visible_precision": 0.8, "visible_hits": 10}]
    assert dominated_by_current(
        {"visible_precision": 0.7, "visible_hits": 10},
        front,
    )
    assert not dominated_by_current(
        {"visible_precision": 0.9, "visible_hits": 9},
        front,
    )


def test_pareto_front():
    results = [
        {
            "id": "balanced",
            "status": "completed",
            "metrics": {
                "validation_precision_lower_bound": 0.5,
                "validation_recall": 0.5,
            },
        },
        {
            "id": "precise",
            "status": "completed",
            "metrics": {
                "validation_precision_lower_bound": 0.9,
                "validation_recall": 0.2,
            },
        },
        {
            "id": "dominated",
            "status": "completed",
            "metrics": {
                "validation_precision_lower_bound": 0.4,
                "validation_recall": 0.4,
            },
        },
    ]

    assert pareto_rule_ids(results) == {"balanced", "precise"}


def test_pareto_front_can_use_visible_metrics():
    results = [
        {
            "id": "a",
            "status": "completed",
            "metrics": {
                "visible_target_precision_lower_bound": 0.8,
                "visible_target_recall": 0.2,
            },
        },
        {
            "id": "b",
            "status": "completed",
            "metrics": {
                "visible_target_precision_lower_bound": 0.7,
                "visible_target_recall": 0.1,
            },
        },
    ]

    assert pareto_rule_ids(
        results,
        "visible_target_precision_lower_bound",
        "visible_target_recall",
    ) == {"a"}


def test_render_rule_cypher_expands_target_relationship_types():
    rule = Rule(
        id="R1",
        name="test",
        iteration=1,
        status="candidate",
        hypothesis="test",
        body="test",
        mechanism_score="medium",
        mechanism_rationale="test",
        uses_treatment_edges=True,
        trapi_expressibility="partial",
        trapi_notes="test",
        cypher=(
            "MATCH (s)-[:__TARGET_RELATIONSHIPS__]->(o) "
            "RETURN s.id AS subject_id, o.id AS object_id"
        ),
    )

    rendered = render_rule_cypher(rule, "TREATS|AMELIORATES_CONDITION")

    assert ":TREATS|AMELIORATES_CONDITION" in rendered


def test_rule_comparison_preserves_blind_examples():
    def rule(rule_id: str) -> Rule:
        return Rule(
            id=rule_id,
            name=rule_id,
            iteration=1,
            status="candidate",
            hypothesis="test",
            body="test",
            mechanism_score="medium",
            mechanism_rationale="test",
            uses_treatment_edges=False,
            trapi_expressibility="partial",
            trapi_notes="test",
            cypher=(
                f"RETURN '{rule_id}:subject' AS subject_id, "
                f"'{rule_id}:object' AS object_id"
            ),
        )

    parent = rule("parent")
    child = rule("child")
    counts = comparison_query(parent, child, "TREATS|AMELIORATES_CONDITION")
    novel = examples_query(
        parent,
        child,
        "TREATS|AMELIORATES_CONDITION",
        "parent_only",
        "novel",
    )

    assert "unresolved_or_blind_pairs" in counts
    assert "$blind_source" in counts
    assert "WHERE size(sources) = 0" in novel
    assert "$blind_source" not in novel


def test_rule_library_separates_treatment_free_and_rejected_fronts(tmp_path: Path):
    def result(
        rule_id: str,
        precision: float,
        recall: float,
        *,
        uses_treatment_edges: bool,
        library_status: str = "candidate",
    ):
        return {
            "id": rule_id,
            "status": "completed",
            "library_status": library_status,
            "uses_treatment_edges": uses_treatment_edges,
            "mechanism_score": "high",
            "metrics": {
                "validation_precision_lower_bound": precision,
                "validation_recall": recall,
                "visible_target_precision_lower_bound": precision,
                "visible_target_recall": recall,
            },
        }

    path = tmp_path / "rule-library.json"
    update_rule_library(
        path,
        {},
        [
            result("pure", 0.5, 0.4, uses_treatment_edges=False),
            result("treatment", 0.9, 0.5, uses_treatment_edges=True),
            result(
                "rejected",
                1.0,
                1.0,
                uses_treatment_edges=False,
                library_status="rejected",
            ),
        ],
    )

    library = json.loads(path.read_text(encoding="utf-8"))
    by_id = {entry["id"]: entry for entry in library["results"]}

    assert by_id["treatment"]["pareto_validation"]
    assert not by_id["pure"]["pareto_validation"]
    assert by_id["pure"]["pareto_validation_without_treatment_edges"]
    assert not by_id["treatment"]["pareto_validation_without_treatment_edges"]
    assert not by_id["rejected"]["pareto_validation"]


def test_rule_library_includes_executable_cypher(tmp_path: Path):
    rule = Rule(
        id="R1",
        name="test",
        iteration=1,
        status="retained",
        hypothesis="test",
        body="test",
        mechanism_score="medium",
        mechanism_rationale="test",
        uses_treatment_edges=False,
        trapi_expressibility="partial",
        trapi_notes="test",
        cypher=(
            "MATCH (s)-[:__TARGET_RELATIONSHIPS__]->(o) "
            "RETURN s.id AS subject_id, o.id AS object_id"
        ),
    )
    result = {
        "id": "R1",
        "status": "completed",
        "library_status": "retained",
        "uses_treatment_edges": False,
        "mechanism_score": "medium",
        "metrics": {
            "validation_precision_lower_bound": 0.5,
            "validation_recall": 0.1,
            "visible_target_precision_lower_bound": 0.5,
            "visible_target_recall": 0.1,
        },
    }
    path = tmp_path / "rule-library.json"

    update_rule_library(
        path,
        {"neo4j_relationship_types": ["TREATS", "AMELIORATES_CONDITION"]},
        [result],
        [rule],
    )

    library = json.loads(path.read_text(encoding="utf-8"))
    assert (
        library["results"][0]["cypher"]
        == "MATCH (s)-[:TREATS|AMELIORATES_CONDITION]->(o) "
        "RETURN s.id AS subject_id, o.id AS object_id"
    )
