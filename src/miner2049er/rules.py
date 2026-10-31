from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from miner2049er.rule_families import compile_rule_family

MECHANISM_SCORES = {"low", "medium", "high"}
TRAPI_EXPRESSIBILITY = {"full", "partial", "none"}


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    iteration: int
    status: str
    hypothesis: str
    body: str
    mechanism_score: str
    mechanism_rationale: str
    uses_treatment_edges: bool
    trapi_expressibility: str
    trapi_notes: str
    cypher: str
    description: str | None = None
    criteria: tuple[str, ...] = ()
    parent_rule: str | None = None
    trapi_template: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Rule:
        normalized = {
            **value,
            "criteria": tuple(value.get("criteria", ())),
        }
        rule = cls(**normalized)
        if rule.mechanism_score not in MECHANISM_SCORES:
            raise ValueError(
                f"{rule.id}: mechanism_score must be one of {sorted(MECHANISM_SCORES)}"
            )
        if rule.trapi_expressibility not in TRAPI_EXPRESSIBILITY:
            raise ValueError(
                f"{rule.id}: trapi_expressibility must be one of "
                f"{sorted(TRAPI_EXPRESSIBILITY)}"
            )
        cypher = rule.cypher.strip().removesuffix(";")
        if "RETURN" not in cypher.upper():
            raise ValueError(f"{rule.id}: Cypher must return subject_id and object_id")
        if "subject_id" not in cypher or "object_id" not in cypher:
            raise ValueError(f"{rule.id}: Cypher must return subject_id and object_id")
        return cls(**{**normalized, "cypher": cypher})


def load_rules(
    path: Path,
    selected_ids: set[str] | None = None,
    *,
    include_inactive: bool = False,
) -> list[Rule]:
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    rules = [
        Rule.from_dict(compile_rule_family(value))
        for value in document.get("rules", [])
    ]
    for rule in rules:
        if rule.trapi_template is None:
            continue
        template_path = path.parent / rule.trapi_template
        if not template_path.is_file():
            raise ValueError(f"{rule.id}: missing TRAPI template {template_path}")
        payload = json.loads(template_path.read_text(encoding="utf-8"))
        query_graph = payload.get("message", {}).get("query_graph", {})
        if not query_graph.get("nodes") or not (
            query_graph.get("edges") or query_graph.get("paths")
        ):
            raise ValueError(
                f"{rule.id}: TRAPI template must contain query_graph nodes and edges/paths"
            )
    ids = [rule.id for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate rule IDs in {path}")
    if selected_ids:
        missing = selected_ids - set(ids)
        if missing:
            raise ValueError(f"Unknown rule IDs: {', '.join(sorted(missing))}")
        rules = [rule for rule in rules if rule.id in selected_ids]
    elif not include_inactive:
        rules = [
            rule
            for rule in rules
            if rule.status in {"active", "baseline", "candidate", "retained"}
        ]
    return rules


def f_beta(precision: float, recall: float, beta: float = 0.5) -> float:
    if precision == 0.0 and recall == 0.0:
        return 0.0
    beta_squared = beta * beta
    return (1 + beta_squared) * precision * recall / (beta_squared * precision + recall)


def pareto_rule_ids(
    results: list[dict[str, Any]],
    precision_metric: str = "validation_precision_lower_bound",
    recall_metric: str = "validation_recall",
) -> set[str]:
    successful = [result for result in results if result.get("status") == "completed"]
    front: set[str] = set()
    for candidate in successful:
        candidate_precision = candidate["metrics"][precision_metric]
        candidate_recall = candidate["metrics"][recall_metric]
        dominated = False
        for other in successful:
            if other["id"] == candidate["id"]:
                continue
            other_precision = other["metrics"][precision_metric]
            other_recall = other["metrics"][recall_metric]
            if (
                other_precision >= candidate_precision
                and other_recall >= candidate_recall
                and (
                    other_precision > candidate_precision
                    or other_recall > candidate_recall
                )
            ):
                dominated = True
                break
        if not dominated:
            front.add(candidate["id"])
    return front
