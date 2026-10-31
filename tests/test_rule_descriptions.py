import json
import re
from pathlib import Path

import pytest

from miner2049er.rule_descriptions import (
    apply_rule_descriptions,
    load_rule_descriptions,
    refresh_rule_library_descriptions,
    surface_rule_ids,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_load_and_apply_rule_descriptions(tmp_path: Path):
    descriptions_path = tmp_path / "descriptions.toml"
    descriptions_path.write_text(
        """
[criteria_sets]
core = "The subject affects the target."

[[rules]]
id = "R1"
description = "Predict the pair when the graph pattern is present."
criteria_sets = ["core"]
criteria = ["The target is linked to disease."]
trapi_notes = "The positive path is TRAPI-expressible."
""",
        encoding="utf-8",
    )
    library = {"results": [{"id": "R1", "description": None, "criteria": []}]}

    descriptions = load_rule_descriptions(descriptions_path)
    apply_rule_descriptions(library, descriptions)

    assert library["results"][0]["description"].startswith("Predict the pair")
    assert len(library["results"][0]["criteria"]) == 2
    assert library["results"][0]["trapi_notes"].startswith("The positive path")


def test_description_validation_rejects_duplicate_ids(tmp_path: Path):
    path = tmp_path / "descriptions.toml"
    path.write_text(
        """
[[rules]]
id = "R1"
description = "First."
criteria = ["One."]

[[rules]]
id = "R1"
description = "Second."
criteria = ["Two."]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate description"):
        load_rule_descriptions(path)


def test_refresh_rule_library_descriptions(tmp_path: Path):
    library_path = tmp_path / "library.json"
    library_path.write_text(
        json.dumps({"results": [{"id": "R1", "body": "short"}]}),
        encoding="utf-8",
    )
    descriptions_path = tmp_path / "descriptions.toml"
    descriptions_path.write_text(
        """
[[rules]]
id = "R1"
description = "Readable."
criteria = ["Exact."]
""",
        encoding="utf-8",
    )

    refresh_rule_library_descriptions(library_path, descriptions_path)

    result = json.loads(library_path.read_text(encoding="utf-8"))["results"][0]
    assert result["description"] == "Readable."
    assert result["criteria"] == ["Exact."]


def test_every_current_surface_rule_has_a_curated_explanation():
    library = json.loads(
        (PROJECT_ROOT / "results" / "rule-library.json").read_text(encoding="utf-8")
    )
    descriptions = load_rule_descriptions(
        PROJECT_ROOT / "rules" / "rule-descriptions.toml"
    )

    assert set(descriptions) == surface_rule_ids(library)
    apply_rule_descriptions(library, descriptions)
    for rule_id, curated in descriptions.items():
        rendered = " ".join([curated["description"], *curated["criteria"]])
        assert "frontier" not in rendered.lower(), rule_id
        assert "broaden" not in rendered.lower(), rule_id
        assert "more credible" not in rendered.lower(), rule_id
    for result in library["results"]:
        if result["id"] not in descriptions:
            continue
        displayed = " ".join(
            [
                result["description"],
                *result["criteria"],
                result["trapi_notes"],
                result["mechanism_rationale"],
            ]
        )
        assert re.search(r"\bR[0-9]{3}\b", displayed) is None, result["id"]
