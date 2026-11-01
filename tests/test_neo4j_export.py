import json
from pathlib import Path

import pytest

from miner2049er.neo4j_export import (
    edge_schema,
    export_file,
    flatten_sources,
    node_schema,
    sanitize_token,
    supporting_studies,
    transform_edge,
    transform_node,
)


def test_transform_node_adds_base_and_category_labels():
    node = {
        "id": "CHEBI:1",
        "name": "test",
        "category": ["biolink:SmallMolecule", "biolink:NamedThing"],
        "equivalent_identifiers": ["CHEBI:1"],
    }

    transformed = transform_node(node)

    assert transformed["id:ID(Entity)"] == "CHEBI:1"
    assert transformed[":LABEL"] == "Entity;SmallMolecule;NamedThing"
    assert transformed["categories"] == node["category"]


def test_transform_edge_preserves_queryable_trapi_fields():
    edge = {
        "id": "edge-1",
        "subject": "CHEBI:1",
        "predicate": "biolink:affects",
        "object": "NCBIGene:1",
        "category": ["biolink:ChemicalAffectsGeneAssociation"],
        "object_aspect_qualifier": "activity_or_abundance",
        "publications": ["PMID:1"],
        "sources": [
            {
                "resource_id": "infores:kp",
                "resource_role": "primary_knowledge_source",
            },
            {
                "resource_id": "infores:agg",
                "resource_role": "aggregator_knowledge_source",
                "upstream_resource_ids": ["infores:kp"],
            },
        ],
    }

    transformed = transform_edge(edge)

    assert transformed[":TYPE"] == "AFFECTS"
    assert transformed["edge_id"] == "edge-1"
    assert transformed["object_aspect_qualifier"] == "activity_or_abundance"
    assert transformed["primary_knowledge_sources"] == ["infores:kp"]
    assert transformed["aggregator_knowledge_sources"] == ["infores:agg"]
    assert transformed["upstream_resource_ids"] == ["infores:kp"]


def test_flatten_sources_handles_missing_sources():
    primary, aggregators, upstream = flatten_sources(None)

    assert primary == []
    assert aggregators == []
    assert upstream == []


def test_sanitize_token_handles_prefix_and_leading_digit():
    assert sanitize_token("biolink:subclass_of", uppercase=True) == "SUBCLASS_OF"
    assert sanitize_token("example:1 thing") == "_1_thing"


def test_export_fixture_to_parquet(tmp_path):
    fixture_dir = Path(__file__).parent / "fixtures"

    node_count, _ = export_file(
        fixture_dir / "nodes.jsonl",
        tmp_path / "nodes.parquet",
        node_schema(),
        transform_node,
        batch_size=1,
    )
    edge_count, _ = export_file(
        fixture_dir / "edges.jsonl",
        tmp_path / "edges.parquet",
        edge_schema(),
        transform_edge,
        batch_size=1,
    )

    assert node_count == 2
    assert edge_count == 1
    assert (tmp_path / "nodes.parquet").is_file()
    assert (tmp_path / "edges.parquet").is_file()


def test_edge_keeps_supporting_studies_and_drops_raw_copies():
    studies = {
        "PMID:15341483": {
            "id": "PMID:15341483",
            "category": ["biolink:Study"],
            "has_study_results": [
                {
                    "id": "r1",
                    "category": ["biolink:ProteinLigandAssayResult"],
                    "pIC50": {"has_numeric_value": 7.0, "has_binary_relation": "greater_than"},
                }
            ],
        }
    }
    transformed = transform_edge(
        {
            "id": "e1",
            "subject": "CHEBI:1",
            "object": "NCBIGene:1",
            "predicate": "biolink:directly_physically_interacts_with",
            "has_supporting_studies": studies,
            "subject_activity_qualifier": "binding",
            "max_research_phase": "clinical_trial_phase_2",
            "anatomical_context_qualifier": ["MESH:D008099"],
            "supporting_text": ["one sentence", "another"],
        }
    )

    assert transformed["supporting_study_count"] == 1
    assert json.loads(transformed["supporting_studies_json"]) == studies
    assert transformed["subject_activity_qualifier"] == "binding"
    assert transformed["max_research_phase"] == "clinical_trial_phase_2"
    assert transformed["anatomical_context_qualifier"] == ["MESH:D008099"]
    assert transformed["supporting_text"] == ["one sentence", "another"]
    assert "raw_json" not in transformed
    assert "sources_json" not in transformed
    assert set(transformed) <= set(edge_schema().names)


def test_supporting_studies_must_be_an_object():
    with pytest.raises(TypeError, match="must be an object"):
        supporting_studies(3)


def test_converters_raise_on_values_of_the_wrong_shape():
    with pytest.raises(TypeError, match="Expected an integer"):
        transform_edge(
            {"subject": "A", "object": "B", "predicate": "biolink:related_to", "has_count": [1]}
        )
    with pytest.raises(TypeError, match="Expected a string"):
        transform_edge(
            {"subject": "A", "object": "B", "predicate": "biolink:related_to", "update_date": {}}
        )
    with pytest.raises(ValueError, match="Expected a boolean"):
        transform_node({"id": "A", "chembl_prodrug": "sometimes"})
