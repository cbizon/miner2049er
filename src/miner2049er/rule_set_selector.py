from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from miner2049er.partitioning import Pair, load_label_pairs
from miner2049er.rules import f_beta
from miner2049er.schema_validation import read_jsonl, validate_document
from miner2049er.settings import ROOT
from miner2049er.settings import evaluations_dir as configured_evaluations_dir

DEFAULT_EVALUATIONS_DIR = configured_evaluations_dir()
DEFAULT_OUTPUT_ROOT = ROOT / "results" / "rule-sets"
DEFAULT_PUBLIC_BENCHMARK_ROOT = ROOT / "data" / "benchmark"
SELECTION_METHOD = "greedy_marginal_f0_5_coverage_v1"
SURFACES = ("treats-included", "same-pair-excluded", "treats-excluded")
# Runs recorded before evidence tiers cannot be split at the same-pair boundary.
UNTIERED_SURFACES = ("treats-included", "treats-excluded")


def surface_eligible(rule: dict[str, Any], surface: str) -> bool:
    if surface == "treats-included":
        return True
    if surface == "treats-excluded":
        return not rule["uses_treatment_edges"]
    if surface == "same-pair-excluded":
        if "evidence_tier" not in rule:
            raise ValueError(
                f"Rule {rule['rule_id']} has no evidence_tier for surface {surface}"
            )
        return rule["evidence_tier"] != "same_pair"
    raise ValueError(f"Unknown rule-set surface: {surface}")


def run_surfaces(rules: list[dict[str, Any]]) -> tuple[str, ...]:
    tiered = {"evidence_tier" in rule for rule in rules}
    if tiered == {True}:
        return SURFACES
    if tiered == {False} or not rules:
        return UNTIERED_SURFACES
    raise ValueError("Run mixes rules with and without evidence_tier")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_write_json(path: Path, value: dict[str, Any], schema_name: str) -> None:
    validate_document(value, schema_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _atomic_write_jsonl(
    path: Path,
    values: list[dict[str, Any]],
    schema_name: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("wb") as stream:
        for value in values:
            validate_document(value, schema_name)
            stream.write(orjson.dumps(value, option=orjson.OPT_SORT_KEYS) + b"\n")
    temporary.replace(path)


def _load_prediction_sets(
    path: Path,
    *,
    run_id: str,
    rule_ids: set[str],
) -> dict[str, set[Pair]]:
    predictions = {rule_id: set() for rule_id in rule_ids}
    with path.open("rb") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                record = orjson.loads(line)
                record_run_id = record["run_id"]
                rule_id = record["rule_id"]
                pair = (record["subject_id"], record["object_id"])
            except (KeyError, TypeError, orjson.JSONDecodeError) as error:
                raise ValueError(f"{path}:{line_number}: invalid prediction") from error
            if record_run_id != run_id:
                raise ValueError(f"{path}:{line_number}: prediction uses another run")
            if rule_id not in predictions:
                raise ValueError(f"{path}:{line_number}: prediction uses unknown rule")
            predictions[rule_id].add(pair)
    return predictions


def _logic_signature(rule: dict[str, Any]) -> str:
    pattern = rule["graph_pattern"]
    nodes = {
        node["id"]: {
            "role": node["role"],
            "categories": sorted(node["categories"]),
        }
        for node in pattern["nodes"]
    }
    edges = [
        {
            "subject": nodes[edge["subject"]],
            "object": nodes[edge["object"]],
            "predicates": sorted(edge["predicates"]),
            "expanded_predicates": sorted(
                edge["predicate_expansion"]["expanded_predicates"]
            ),
            "excluded_predicates": sorted(
                edge["predicate_expansion"]["excluded_predicates"]
            ),
            "direction": edge["direction"],
            "qualifiers": edge.get("qualifiers", {}),
            "source_constraints": sorted(edge.get("source_constraints", [])),
        }
        for edge in pattern["edges"]
    ]
    constraints = [
        {
            "kind": constraint["kind"],
            "expression": constraint["expression"],
        }
        for constraint in pattern["constraints"]
    ]
    signature = {
        "nodes": sorted(nodes.values(), key=lambda value: json.dumps(value, sort_keys=True)),
        "edges": sorted(edges, key=lambda value: json.dumps(value, sort_keys=True)),
        "constraints": sorted(
            constraints,
            key=lambda value: json.dumps(value, sort_keys=True),
        ),
        "variant_parameters": rule["variant_parameters"],
        "derived_features": rule["derived_features"],
        "execution_cypher": rule["execution"]["cypher"],
        "uses_treatment_edges": rule["uses_treatment_edges"],
    }
    return json.dumps(signature, sort_keys=True, separators=(",", ":"))


def _feedback_evaluations(
    evaluations_path: Path,
) -> dict[str, dict[str, Any]]:
    if not evaluations_path.is_file():
        return {}
    evaluations: dict[str, dict[str, Any]] = {}
    for evaluation in read_jsonl(evaluations_path, "evaluation.schema.json"):
        if evaluation["partition"] != "feedback":
            continue
        rule_id = evaluation["rule_id"]
        if rule_id in evaluations:
            raise ValueError(f"Duplicate feedback evaluation for rule {rule_id}")
        evaluations[rule_id] = evaluation
    return evaluations


def _selection_status(
    rule: dict[str, Any],
    prediction_count: int,
    evaluation: dict[str, Any] | None,
) -> tuple[str, str]:
    if rule["status"] == "rejected":
        return "rejected", "The mining agent explicitly rejected this rule."
    if prediction_count == 0:
        return "no_predictions", "The rule recorded no prediction pairs."
    if evaluation is None:
        return "unscored", "The rule has no aggregate feedback evaluation."
    if evaluation["metrics"]["precision_lower_bound"] <= 0:
        return "zero_precision", "The rule produced no known feedback hits."
    return "eligible", "The rule has predictions and a positive feedback precision."


def build_overlap_report(
    *,
    run_id: str,
    through_round_id: str,
    rules: list[dict[str, Any]],
    predictions: dict[str, set[Pair]],
    training_labels: set[Pair],
    evaluations: dict[str, dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    rule_summaries = []
    all_pairs: set[Pair] = set()
    signatures = {rule["rule_id"]: _logic_signature(rule) for rule in rules}
    for rule in rules:
        rule_id = rule["rule_id"]
        pairs = predictions[rule_id]
        all_pairs.update(pairs)
        evaluation = evaluations.get(rule_id)
        status, explanation = _selection_status(rule, len(pairs), evaluation)
        rule_summaries.append(
            {
                "rule_id": rule_id,
                "round_id": rule["round_id"],
                "family_id": rule["family_id"],
                "uses_treatment_edges": rule["uses_treatment_edges"],
                **(
                    {"evidence_tier": rule["evidence_tier"]}
                    if "evidence_tier" in rule
                    else {}
                ),
                "prediction_count": len(pairs),
                "feedback_eligible_predictions": len(pairs - training_labels),
                "training_hits": len(pairs & training_labels),
                "feedback_scored": evaluation is not None,
                "feedback_precision": (
                    evaluation["metrics"]["precision_lower_bound"]
                    if evaluation is not None
                    else None
                ),
                "feedback_hits": (
                    evaluation["counts"]["known_hits"]
                    if evaluation is not None
                    else None
                ),
                "selection_status": status,
                "selection_explanation": explanation,
            }
        )

    relations = []
    ordered_rule_ids = sorted(predictions, key=lambda rule_id: (len(predictions[rule_id]), rule_id))
    for left_index, left_rule_id in enumerate(ordered_rule_ids):
        left = predictions[left_rule_id]
        if not left:
            continue
        for right_rule_id in ordered_rule_ids[left_index + 1 :]:
            right = predictions[right_rule_id]
            if len(right) < len(left):
                continue
            if len(left) == len(right):
                if left != right:
                    continue
                relation = "exact_duplicate"
            elif left.issubset(right):
                relation = "left_strict_subset"
            else:
                continue
            intersection_count = len(left)
            union_count = len(right)
            relations.append(
                {
                    "left_rule_id": left_rule_id,
                    "right_rule_id": right_rule_id,
                    "prediction_relation": relation,
                    "logical_equivalent": (
                        signatures[left_rule_id] == signatures[right_rule_id]
                    ),
                    "intersection_count": intersection_count,
                    "left_only_count": 0,
                    "right_only_count": len(right) - len(left),
                    "jaccard": round(intersection_count / union_count, 8),
                }
            )

    report = {
        "schema_version": "1.0",
        "run_id": run_id,
        "through_round_id": through_round_id,
        "generated_at": generated_at,
        "rule_count": len(rules),
        "distinct_prediction_pairs": len(all_pairs),
        "rules": sorted(rule_summaries, key=lambda item: item["rule_id"]),
        "relations": relations,
        "limitations": [
            (
                "Strict-subset relationships are exact for this graph build but may "
                "change when the graph changes."
            ),
            (
                "Logical equivalence is reported only when normalized graph patterns "
                "are identical; more general logical implication is intentionally not "
                "claimed from free-text constraints."
            ),
            (
                "Feedback hit identities remain sealed, so arbitrary overlap in correct "
                "predictions requires aggregate rule-set scoring."
            ),
        ],
    }
    validate_document(report, "rule-overlap.schema.json")
    return report


def _excluded_rules(
    *,
    rules: list[dict[str, Any]],
    predictions: dict[str, set[Pair]],
    evaluations: dict[str, dict[str, Any]],
    surface: str,
    selected_rule_ids: list[str],
    supersets_by_rule: dict[str, set[str]],
    zero_marginal_rule_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    selected = set(selected_rule_ids)
    zero_marginal_rule_ids = zero_marginal_rule_ids or set()
    exclusions = []
    for rule in rules:
        rule_id = rule["rule_id"]
        if rule_id in selected:
            continue
        pairs = predictions[rule_id]
        evaluation = evaluations.get(rule_id)
        redundant_with = sorted(selected & supersets_by_rule.get(rule_id, set()))
        if not surface_eligible(rule, surface):
            reason = "surface_ineligible"
            explanation = (
                "The rule uses treatment evidence for the predicted pair."
                if surface == "same-pair-excluded"
                else "The rule uses treatment-oriented premises."
            )
        elif rule["status"] == "rejected":
            reason = "rule_rejected"
            explanation = "The mining agent explicitly rejected this rule."
        elif not pairs:
            reason = "no_predictions"
            explanation = "The rule recorded no predictions."
        elif evaluation is None:
            reason = "unscored"
            explanation = "The rule has no feedback precision estimate."
        elif evaluation["metrics"]["precision_lower_bound"] <= 0:
            reason = "zero_precision"
            explanation = "The rule produced no known feedback hits."
        elif rule_id in zero_marginal_rule_ids:
            reason = "zero_marginal_confidence"
            explanation = (
                "The selected rules already cover every prediction with at least "
                "this rule's feedback precision."
            )
        else:
            reason = "not_selected_at_this_prefix"
            explanation = (
                "The rule still has positive marginal value but occurs later in "
                "the greedy selection path."
            )
        exclusions.append(
            {
                "rule_id": rule_id,
                "reason": reason,
                "explanation": explanation,
                "redundant_with": redundant_with,
            }
        )
    return exclusions


def _estimated_pareto_ids(rule_sets: list[dict[str, Any]]) -> set[str]:
    front: set[str] = set()
    for candidate in rule_sets:
        candidate_precision = candidate["union"]["estimated_feedback_precision"]
        candidate_recall = candidate["union"]["estimated_feedback_recall"]
        dominated = any(
            other["rule_set_id"] != candidate["rule_set_id"]
            and other["union"]["estimated_feedback_precision"] >= candidate_precision
            and other["union"]["estimated_feedback_recall"] >= candidate_recall
            and (
                other["union"]["estimated_feedback_precision"] > candidate_precision
                or other["union"]["estimated_feedback_recall"] > candidate_recall
            )
            for other in rule_sets
        )
        if not dominated:
            front.add(candidate["rule_set_id"])
    return front


def build_rule_sets(
    *,
    run_id: str,
    through_round_id: str,
    surface: str,
    rules: list[dict[str, Any]],
    predictions: dict[str, set[Pair]],
    training_labels: set[Pair],
    evaluations: dict[str, dict[str, Any]],
    generated_at: str,
    supersets_by_rule: dict[str, set[str]] | None = None,
) -> list[dict[str, Any]]:
    if surface not in SURFACES:
        raise ValueError(f"Unknown rule-set surface: {surface}")
    feedback_label_counts = {
        evaluation["counts"]["partition_labels"] for evaluation in evaluations.values()
    }
    if len(feedback_label_counts) > 1:
        raise ValueError("Feedback evaluations disagree on partition label count")
    feedback_label_count = next(iter(feedback_label_counts), 0)

    if supersets_by_rule is None:
        supersets_by_rule = {rule["rule_id"]: set() for rule in rules}
        ordered_rule_ids = sorted(
            predictions,
            key=lambda rule_id: (len(predictions[rule_id]), rule_id),
        )
        for left_index, left_rule_id in enumerate(ordered_rule_ids):
            left = predictions[left_rule_id]
            if not left:
                continue
            for right_rule_id in ordered_rule_ids[left_index + 1 :]:
                right = predictions[right_rule_id]
                if len(right) == len(left) and left == right:
                    supersets_by_rule[left_rule_id].add(right_rule_id)
                    supersets_by_rule[right_rule_id].add(left_rule_id)
                elif len(right) > len(left) and left.issubset(right):
                    supersets_by_rule[left_rule_id].add(right_rule_id)
    remaining = {
        rule["rule_id"]
        for rule in rules
        if surface_eligible(rule, surface)
        and rule["status"] != "rejected"
        and predictions[rule["rule_id"]]
        and rule["rule_id"] in evaluations
        and evaluations[rule["rule_id"]]["metrics"]["precision_lower_bound"] > 0
    }
    selected_rule_ids: list[str] = []
    member_steps: list[dict[str, Any]] = []
    union_predictions: set[Pair] = set()
    union_eligible: set[Pair] = set()
    union_training_hits: set[Pair] = set()
    guaranteed_feedback_hits = 0
    estimated_feedback_hits = 0.0
    rule_sets: list[dict[str, Any]] = []

    while remaining:
        candidates = []
        for rule_id in remaining:
            pairs = predictions[rule_id]
            eligible_pairs = pairs - training_labels
            precision = evaluations[rule_id]["metrics"]["precision_lower_bound"]
            new_eligible_count = len(eligible_pairs - union_eligible)
            estimated_new_hits = precision * new_eligible_count
            marginal_recall = (
                min(1.0, estimated_new_hits / feedback_label_count)
                if feedback_label_count
                else 0.0
            )
            marginal_f0_5 = f_beta(precision, marginal_recall, beta=0.5)
            candidates.append(
                (
                    marginal_f0_5,
                    precision,
                    estimated_new_hits,
                    new_eligible_count,
                    len(pairs - union_predictions),
                    rule_id,
                )
            )
        (
            marginal_f0_5,
            precision,
            selected_estimated_new_hits,
            _,
            _,
            selected_rule_id,
        ) = max(candidates)
        if marginal_f0_5 <= 1e-12:
            break

        pairs = predictions[selected_rule_id]
        eligible_pairs = pairs - training_labels
        new_predictions = pairs - union_predictions
        new_eligible = eligible_pairs - union_eligible
        overlap_count = len(eligible_pairs & union_eligible)
        feedback_hits = evaluations[selected_rule_id]["counts"]["known_hits"]
        guaranteed_new_hits = max(0, feedback_hits - overlap_count)
        new_training_hits = (pairs & training_labels) - union_training_hits

        union_predictions.update(pairs)
        union_eligible.update(eligible_pairs)
        union_training_hits.update(pairs & training_labels)
        guaranteed_feedback_hits += guaranteed_new_hits
        estimated_feedback_hits += selected_estimated_new_hits
        selected_rule_ids.append(selected_rule_id)
        remaining.remove(selected_rule_id)

        estimated_feedback_precision = (
            estimated_feedback_hits / len(union_eligible) if union_eligible else 0.0
        )
        estimated_feedback_recall = (
            min(1.0, estimated_feedback_hits / feedback_label_count)
            if feedback_label_count
            else 0.0
        )
        training_recall = (
            len(union_training_hits) / len(training_labels) if training_labels else 0.0
        )
        estimated_f0_5 = f_beta(
            estimated_feedback_precision,
            estimated_feedback_recall,
            beta=0.5,
        )
        member_steps.append(
            {
                "position": len(selected_rule_ids),
                "rule_id": selected_rule_id,
                "feedback_precision": precision,
                "prediction_count": len(pairs),
                "eligible_prediction_count": len(eligible_pairs),
                "new_predictions": len(new_predictions),
                "new_eligible_predictions": len(new_eligible),
                "overlapping_eligible_predictions": overlap_count,
                "guaranteed_new_feedback_hits": guaranteed_new_hits,
                "estimated_new_feedback_hits": selected_estimated_new_hits,
                "new_training_hits": len(new_training_hits),
                "cumulative_predictions": len(union_predictions),
                "cumulative_eligible_predictions": len(union_eligible),
                "cumulative_training_hits": len(union_training_hits),
                "cumulative_training_recall": round(training_recall, 8),
                "cumulative_estimated_feedback_hits": round(
                    estimated_feedback_hits,
                    6,
                ),
                "cumulative_estimated_feedback_precision": round(
                    estimated_feedback_precision,
                    8,
                ),
                "cumulative_estimated_feedback_recall": round(
                    estimated_feedback_recall,
                    8,
                ),
                "cumulative_estimated_f0_5": round(estimated_f0_5, 8),
            }
        )
        rule_set_id = f"{surface}-p{len(selected_rule_ids):03d}"
        rule_set = {
            "schema_version": "1.0",
            "run_id": run_id,
            "through_round_id": through_round_id,
            "rule_set_id": rule_set_id,
            "surface": surface,
            "selection_method": SELECTION_METHOD,
            "generated_at": generated_at,
            "is_estimated_pareto": False,
            "members": [dict(member) for member in member_steps],
            "excluded_rules": _excluded_rules(
                rules=rules,
                predictions=predictions,
                evaluations=evaluations,
                surface=surface,
                selected_rule_ids=selected_rule_ids,
                supersets_by_rule=supersets_by_rule,
            ),
            "union": {
                "member_count": len(selected_rule_ids),
                "prediction_count": len(union_predictions),
                "eligible_prediction_count": len(union_eligible),
                "training_hits": len(union_training_hits),
                "training_labels": len(training_labels),
                "training_recall": round(training_recall, 8),
                "guaranteed_feedback_hits": guaranteed_feedback_hits,
                "estimated_feedback_hits": round(estimated_feedback_hits, 6),
                "estimated_feedback_precision": round(
                    estimated_feedback_precision,
                    8,
                ),
                "estimated_feedback_recall": round(
                    estimated_feedback_recall,
                    8,
                ),
                "estimated_f0_5": round(estimated_f0_5, 8),
                "feedback_partition_labels": feedback_label_count,
            },
            "limitations": [
                (
                    "Estimated feedback metrics apply each rule's aggregate precision "
                    "to only the pairs it newly adds at its selection step; they are "
                    "not a substitute for aggregate union scoring."
                ),
                (
                    "A practically subsumed rule may cease to be subsumed on a later "
                    "graph build unless logical equivalence was proved separately."
                ),
                (
                    "Rules without a positive feedback evaluation are reported but "
                    "are not selected by this path."
                ),
            ],
        }
        validate_document(rule_set, "rule-set.schema.json")
        rule_sets.append(rule_set)

    if rule_sets and remaining:
        rule_sets[-1]["excluded_rules"] = _excluded_rules(
            rules=rules,
            predictions=predictions,
            evaluations=evaluations,
            surface=surface,
            selected_rule_ids=selected_rule_ids,
            supersets_by_rule=supersets_by_rule,
            zero_marginal_rule_ids=remaining,
        )
    pareto_ids = _estimated_pareto_ids(rule_sets)
    for rule_set in rule_sets:
        rule_set["is_estimated_pareto"] = rule_set["rule_set_id"] in pareto_ids
        validate_document(rule_set, "rule-set.schema.json")
    return rule_sets


def generate_rule_set_analysis(
    *,
    run_dir: Path,
    evaluations_dir: Path = DEFAULT_EVALUATIONS_DIR,
    public_benchmark_root: Path = DEFAULT_PUBLIC_BENCHMARK_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    validate_document(manifest, "run.schema.json")
    if manifest["status"] == "running":
        raise ValueError("Rule-set analysis requires a completed round boundary")
    run_id = manifest["run_id"]
    through_round_id = f"round-{manifest['round_count']:04d}"
    rules = list(
        read_jsonl(
            run_dir / manifest["artifacts"]["rules"],
            "rule.schema.json",
        )
    )
    rule_ids = {rule["rule_id"] for rule in rules}
    predictions = _load_prediction_sets(
        run_dir / manifest["artifacts"]["predictions"],
        run_id=run_id,
        rule_ids=rule_ids,
    )
    training_labels = load_label_pairs(
        public_benchmark_root
        / manifest["split_id"]
        / "training-labels.jsonl"
    )
    evaluations = _feedback_evaluations(evaluations_dir / f"{run_id}.jsonl")
    generated_at = _now()
    overlap = build_overlap_report(
        run_id=run_id,
        through_round_id=through_round_id,
        rules=rules,
        predictions=predictions,
        training_labels=training_labels,
        evaluations=evaluations,
        generated_at=generated_at,
    )
    supersets_by_rule = {rule["rule_id"]: set() for rule in rules}
    for relation in overlap["relations"]:
        left_rule_id = relation["left_rule_id"]
        right_rule_id = relation["right_rule_id"]
        supersets_by_rule[left_rule_id].add(right_rule_id)
        if relation["prediction_relation"] == "exact_duplicate":
            supersets_by_rule[right_rule_id].add(left_rule_id)
    rule_sets = []
    for surface in run_surfaces(rules):
        rule_sets.extend(
            build_rule_sets(
                run_id=run_id,
                through_round_id=through_round_id,
                surface=surface,
                rules=rules,
                predictions=predictions,
                training_labels=training_labels,
                evaluations=evaluations,
                generated_at=generated_at,
                supersets_by_rule=supersets_by_rule,
            )
        )
    output_dir = output_root / run_id
    _atomic_write_json(
        output_dir / "overlap.json",
        overlap,
        "rule-overlap.schema.json",
    )
    _atomic_write_jsonl(
        output_dir / "rule-sets.jsonl",
        rule_sets,
        "rule-set.schema.json",
    )
    return {
        "run_id": run_id,
        "through_round_id": through_round_id,
        "overlap_path": str(output_dir / "overlap.json"),
        "rule_sets_path": str(output_dir / "rule-sets.jsonl"),
        "rules": len(rules),
        "distinct_prediction_pairs": overlap["distinct_prediction_pairs"],
        "subset_relations": len(overlap["relations"]),
        "rule_sets": len(rule_sets),
        "estimated_pareto_rule_sets": sum(
            rule_set["is_estimated_pareto"] for rule_set in rule_sets
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze rule overlap and construct coverage-aware rule portfolios"
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--evaluations-dir",
        type=Path,
        default=DEFAULT_EVALUATIONS_DIR,
    )
    parser.add_argument(
        "--public-benchmark-root",
        type=Path,
        default=DEFAULT_PUBLIC_BENCHMARK_ROOT,
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = generate_rule_set_analysis(
        run_dir=args.run_dir,
        evaluations_dir=args.evaluations_dir,
        public_benchmark_root=args.public_benchmark_root,
        output_root=args.output_root,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
