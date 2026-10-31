from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from miner2049er.settings import ROOT

DEFAULT_DESCRIPTIONS_PATH = ROOT / "rules" / "rule-descriptions.toml"


def load_rule_descriptions(
    path: Path = DEFAULT_DESCRIPTIONS_PATH,
) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    criteria_sets = document.get("criteria_sets", {})
    descriptions: dict[str, dict[str, Any]] = {}
    for entry in document.get("rules", []):
        rule_id = str(entry.get("id", "")).strip()
        description = str(entry.get("description", "")).strip()
        criteria = []
        for set_name in entry.get("criteria_sets", []):
            if set_name not in criteria_sets:
                raise ValueError(
                    f"{path}: {rule_id} uses unknown criteria set {set_name}"
                )
            criteria.append(str(criteria_sets[set_name]).strip())
        criteria.extend(entry.get("criteria", []))
        if not rule_id:
            raise ValueError(f"{path}: description entry is missing an id")
        if rule_id in descriptions:
            raise ValueError(f"{path}: duplicate description for {rule_id}")
        if not description:
            raise ValueError(f"{path}: {rule_id} is missing a description")
        if not isinstance(criteria, list) or not criteria:
            raise ValueError(f"{path}: {rule_id} must have at least one criterion")
        curated = {
            "description": description,
            "criteria": [str(criterion).strip() for criterion in criteria],
        }
        for field in ("trapi_notes", "mechanism_rationale"):
            if field in entry:
                curated[field] = str(entry[field]).strip()
        descriptions[rule_id] = curated
    return descriptions


def apply_rule_descriptions(
    library: dict[str, Any],
    descriptions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    descriptions = descriptions or load_rule_descriptions()
    for result in library.get("results", []):
        curated = descriptions.get(result.get("id"))
        if curated is not None:
            result.update(curated)
    return library


def refresh_rule_library_descriptions(
    library_path: Path,
    descriptions_path: Path = DEFAULT_DESCRIPTIONS_PATH,
) -> None:
    library = json.loads(library_path.read_text(encoding="utf-8"))
    apply_rule_descriptions(library, load_rule_descriptions(descriptions_path))
    library_path.write_text(json.dumps(library, indent=2) + "\n", encoding="utf-8")


def surface_rule_ids(library: dict[str, Any]) -> set[str]:
    flags = (
        "pareto_visible",
        "pareto_visible_without_treatment_edges",
        "pareto_validation",
        "pareto_validation_without_treatment_edges",
    )
    return {
        result["id"]
        for result in library.get("results", [])
        if any(result.get(flag, False) for flag in flags)
    }
