from __future__ import annotations

import json
from collections import Counter
from html import escape
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from miner2049er.rule_diagram import DIAGRAM_CSS, render_rule_diagram
from miner2049er.rule_set_selector import run_surfaces, surface_eligible
from miner2049er.rule_viewer import BASE_CSS
from miner2049er.run_artifacts import DEFAULT_RUNS_DIR, load_run
from miner2049er.schema_validation import read_jsonl, validate_document
from miner2049er.settings import ROOT

DEFAULT_EVALUATIONS_DIR = ROOT / "data" / "evaluations"
DEFAULT_RULE_SET_ROOT = ROOT / "results" / "rule-sets"
DEFAULT_RULE_SET_EVALUATIONS_DIR = ROOT / "data" / "rule-set-evaluations"
DEFAULT_SURFACE = "treats-included"
DEFAULT_RULE_VIEW = "all"
SURFACES = {
    "treats-included": {
        "title": "Treats included",
        "short_title": "Treats included",
        "description": (
            "All rules are eligible, including rules whose premises use "
            "treatment-oriented predicates."
        ),
    },
    "same-pair-excluded": {
        "title": "Same-pair treatment evidence excluded",
        "short_title": "Same pair excluded",
        "description": (
            "Transfer and treatment-free rules are eligible. Rules whose premises "
            "assert treatment evidence for the predicted pair itself are not."
        ),
    },
    "treats-excluded": {
        "title": "Treats excluded",
        "short_title": "Treats excluded",
        "description": (
            "Only treatment-free rules with uses_treatment_edges=false are eligible."
        ),
    },
}
RULE_VIEWS = {
    "all": {
        "title": "All rules",
        "description": "Showing every recorded rule, including unscored candidates.",
    },
    "pareto": {
        "title": "Pareto only",
        "description": "Showing only Pareto-optimal rules for this surface.",
    },
}
REASONING_EFFORT_LABELS = {
    "none": "none",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "extra-high",
}
QUERY_DETAIL_KEYS = {
    "query",
    "queries",
    "query_text",
    "creation_query",
    "next_query",
}


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} · Treats Benchmark</title>
  <style>{BASE_CSS}
  {DIAGRAM_CSS}
  .json-block {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
  .dashboard-nav {{ display:flex; flex-wrap:wrap; gap:12px 24px; margin: 18px 0; }}
  .dashboard-nav div {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; }}
  .dashboard-nav a {{ padding:10px 14px; border:1px solid var(--line); text-decoration:none; }}
  .dashboard-nav a.active {{ color:white; background:var(--green); border-color:var(--green); }}
  .run-title {{ display:flex; flex-wrap:wrap; align-items:center; gap:12px 18px; }}
  .run-title h1 {{ margin:0; }}
  .run-status {{ display:inline-flex; align-items:center; padding:7px 11px; border:1px solid var(--line); font-size:.78rem; font-weight:800; letter-spacing:.04em; text-transform:uppercase; }}
  .run-status.running {{ color:#744b00; background:#fff1c7; border-color:#d8b65a; }}
  .run-status.complete {{ color:#174d38; background:#dff3e9; border-color:#83b89e; }}
  .sortable-table th {{ white-space:nowrap; }}
  .sort-button {{ display:inline-flex; align-items:center; gap:6px; padding:0; border:0; color:inherit; background:transparent; font:inherit; font-weight:inherit; cursor:pointer; }}
  .sort-button:hover, .sort-button:focus-visible {{ color:var(--green); }}
  .sort-indicator {{ color:var(--muted); font-size:.72rem; }}
  .event-counts {{ display:flex; flex-wrap:wrap; gap:8px; margin:14px 0; }}
  .event-count {{ padding:6px 10px; border:1px solid var(--line); background:rgba(255,255,255,.45); }}
  .event-type {{ display:inline-block; padding:4px 8px; color:white; background:var(--green); font-size:.78rem; letter-spacing:.04em; text-transform:uppercase; }}
  .research-event {{ margin-bottom:18px; padding:20px; border:1px solid var(--line); background:var(--panel); box-shadow:var(--shadow); }}
  .research-meta {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px 14px; color:var(--muted); }}
  .research-event h2 {{ margin:12px 0 8px; }}
  .research-details {{ display:grid; grid-template-columns:minmax(150px, 220px) minmax(0, 1fr); gap:8px 18px; }}
  .research-details dt {{ font-weight:700; }}
  .research-details dd {{ margin:0; min-width:0; }}
  .research-details ul {{ margin:0; padding-left:20px; }}
  .research-details pre {{ margin:0; max-height:32rem; overflow:auto; }}
  .research-log-link {{ display:inline-block; margin-top:12px; }}
  .metric-note {{ display:block; margin-top:4px; color:var(--muted); font-size:.78rem; }}
  .portfolio-members {{ counter-reset:portfolio-member; }}
  .portfolio-member {{ margin-bottom:16px; padding:16px; border:1px solid var(--line); background:rgba(255,255,255,.45); }}
  .portfolio-member h3 {{ margin:0 0 8px; }}
  @media (max-width: 720px) {{
    .research-details {{ grid-template-columns:1fr; }}
    .research-details dd {{ margin-bottom:8px; }}
  }}
  </style>
</head>
<body>{body}</body>
</html>"""


def _pareto_ids(evaluations: list[dict[str, Any]]) -> set[str]:
    front: set[str] = set()
    for candidate in evaluations:
        cp = candidate["metrics"]["precision_lower_bound"]
        cr = candidate["metrics"]["recall"]
        dominated = any(
            other["rule_id"] != candidate["rule_id"]
            and other["metrics"]["precision_lower_bound"] >= cp
            and other["metrics"]["recall"] >= cr
            and (
                other["metrics"]["precision_lower_bound"] > cp
                or other["metrics"]["recall"] > cr
            )
            for other in evaluations
        )
        if not dominated:
            front.add(candidate["rule_id"])
    return front


def _surface_evaluations(
    evaluations: list[dict[str, Any]],
    rules: dict[str, dict[str, Any]],
    surface: str,
) -> list[dict[str, Any]]:
    if surface == "treats-included":
        return evaluations
    return [
        evaluation
        for evaluation in evaluations
        if evaluation["rule_id"] in rules
        and surface_eligible(rules[evaluation["rule_id"]], surface)
    ]


def _surface_rules(
    rules: list[dict[str, Any]],
    surface: str,
) -> list[dict[str, Any]]:
    return [rule for rule in rules if surface_eligible(rule, surface)]


def _available_surfaces(run: dict[str, Any], surface: str) -> dict[str, dict[str, str]]:
    available = {name: SURFACES[name] for name in run_surfaces(run["rules"])}
    if surface not in available:
        raise HTTPException(status_code=404, detail="Unknown Pareto surface")
    return available


EVIDENCE_TIER_LABELS = {
    "same_pair": "Same-pair treatment evidence",
    "transfer": "Transfers known treatments",
    "treatment_free": "Treatment-free",
}


def _evidence_label(rule: dict[str, Any]) -> str:
    if "evidence_tier" in rule:
        return EVIDENCE_TIER_LABELS[rule["evidence_tier"]]
    return "Uses treatment edges" if rule["uses_treatment_edges"] else "Treatment-free"


def _main_table_round_id(
    manifest: dict[str, Any],
    rounds: list[dict[str, Any]],
) -> str | None:
    current_round_id = manifest.get("current_round_id")
    if current_round_id:
        return current_round_id
    completed_rounds = [
        round_manifest
        for round_manifest in rounds
        if round_manifest["status"] == "completed"
    ]
    if not completed_rounds:
        return None
    return max(
        completed_rounds,
        key=lambda round_manifest: round_manifest["round_number"],
    )["round_id"]


def _sortable_header(label: str, sort_type: str = "text") -> str:
    return (
        f'<th data-sort-type="{sort_type}" aria-sort="none">'
        f'<button class="sort-button" type="button">{escape(label)} '
        '<span class="sort-indicator">[sort]</span></button></th>'
    )


def _artifact_target(artifact: dict[str, Any]) -> str:
    target = artifact["target"]
    parts = [
        *target["node_labels"],
        *target["relationship_types"],
    ]
    if target["property_name"]:
        parts.append(target["property_name"])
    return " · ".join(parts) or target["scope"]


def _agent_execution_cell(execution: dict[str, Any] | None) -> str:
    if not execution:
        return '<span class="rule-id">Not recorded</span>'
    effort = execution["reasoning_effort"]
    effort_label = REASONING_EFFORT_LABELS.get(effort, effort)
    return (
        f'{escape(execution["model"])}'
        f'<span class="rule-id">{escape(execution["model_provider"])} · '
        f'{escape(effort_label)} reasoning</span>'
    )


def _humanize_detail_key(key: str) -> str:
    return key.replace("_", " ").strip().title()


def _render_detail_value(key: str, value: Any) -> str:
    if value is None:
        return '<span class="rule-id">None</span>'
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return escape(f"{value:,}")
    if isinstance(value, str):
        if key in QUERY_DETAIL_KEYS or "\n" in value:
            return f"<pre><code>{escape(value)}</code></pre>"
        return escape(value)
    if isinstance(value, list):
        if not value:
            return '<span class="rule-id">None</span>'
        return "<ul>" + "".join(
            f"<li>{_render_detail_value(key, item)}</li>" for item in value
        ) + "</ul>"
    if isinstance(value, dict):
        if not value:
            return '<span class="rule-id">None</span>'
        return _render_research_details(value)
    return escape(str(value))


def _render_research_details(details: dict[str, Any]) -> str:
    return '<dl class="research-details">' + "".join(
        f"<dt>{escape(_humanize_detail_key(key))}</dt>"
        f"<dd>{_render_detail_value(key, value)}</dd>"
        for key, value in details.items()
    ) + "</dl>"


def _research_rule_link(
    *,
    event: dict[str, Any],
    manifest: dict[str, Any],
    rules: dict[str, dict[str, Any]],
) -> str:
    rule_id = event.get("rule_id")
    if not rule_id:
        return "—"
    if rule_id not in rules:
        return escape(rule_id)
    return (
        f'<a href="/benchmark/run/{escape(manifest["run_id"])}/rule/'
        f'{escape(rule_id)}">{escape(rule_id)}</a>'
    )


def _research_event_counts(events: list[dict[str, Any]]) -> str:
    if not events:
        return '<span class="rule-id">No research events recorded.</span>'
    counts = Counter(event["event_type"] for event in events)
    return "".join(
        f'<span class="event-count">{escape(_humanize_detail_key(event_type))}: '
        f"{count:,}</span>"
        for event_type, count in sorted(counts.items())
    )


def _predicate_expansion_rows(rule: dict[str, Any]) -> str:
    rows = []
    for edge in rule["graph_pattern"]["edges"]:
        expansion = edge["predicate_expansion"]
        expanded = expansion["expanded_predicates"]
        excluded = expansion["excluded_predicates"]
        excluded_text = (
            f"<p><strong>Excluded descendants:</strong> "
            f"{escape(', '.join(excluded))}</p>"
            f"<p><strong>Reason:</strong> "
            f"{escape(expansion['exclusion_rationale'])}</p>"
            if excluded
            else "<p><strong>Excluded descendants:</strong> none</p>"
        )
        rows.append(
            f"""<li><strong>{escape(edge["id"])}</strong>
<p><strong>Authored predicates:</strong> {escape(", ".join(edge["predicates"]))}</p>
<details><summary>{len(expanded):,} effective predicates after Biolink expansion</summary>
<p>{escape(", ".join(expanded))}</p></details>
{excluded_text}</li>"""
        )
    return "".join(rows)


def load_rule_set_artifacts(
    *,
    run_id: str,
    rule_set_root: Path = DEFAULT_RULE_SET_ROOT,
    rule_set_evaluations_dir: Path = DEFAULT_RULE_SET_EVALUATIONS_DIR,
) -> dict[str, Any]:
    analysis_dir = rule_set_root / run_id
    overlap_path = analysis_dir / "overlap.json"
    rule_sets_path = analysis_dir / "rule-sets.jsonl"
    evaluation_path = rule_set_evaluations_dir / f"{run_id}.jsonl"
    overlap = None
    if overlap_path.is_file():
        overlap = json.loads(overlap_path.read_text(encoding="utf-8"))
        validate_document(overlap, "rule-overlap.schema.json")
    rule_sets = (
        list(read_jsonl(rule_sets_path, "rule-set.schema.json"))
        if rule_sets_path.is_file()
        else []
    )
    evaluations = (
        list(read_jsonl(evaluation_path, "rule-set-evaluation.schema.json"))
        if evaluation_path.is_file()
        else []
    )
    return {
        "rule_overlap": overlap,
        "rule_sets": rule_sets,
        "rule_set_evaluations": evaluations,
    }


def load_dashboard_run(
    *,
    run_dir: Path,
    evaluations_dir: Path,
    rule_set_root: Path,
    rule_set_evaluations_dir: Path,
) -> dict[str, Any]:
    run = load_run(run_dir, evaluations_dir)
    run.update(
        load_rule_set_artifacts(
            run_id=run["manifest"]["run_id"],
            rule_set_root=rule_set_root,
            rule_set_evaluations_dir=rule_set_evaluations_dir,
        )
    )
    return run


def render_run(
    run: dict[str, Any],
    partition: str,
    surface: str,
    rule_view: str = DEFAULT_RULE_VIEW,
    round_id: str = "all",
) -> str:
    manifest = run["manifest"]
    available_surfaces = _available_surfaces(run, surface)
    rounds = {item["round_id"]: item for item in run["rounds"]}
    rules = {rule["rule_id"]: rule for rule in run["rules"]}
    if round_id not in {"all", "latest"} and round_id not in rounds:
        raise HTTPException(status_code=404, detail="Unknown round")
    main_table_round_id = (
        _main_table_round_id(manifest, run["rounds"])
        if round_id == "latest"
        else (None if round_id == "all" else round_id)
    )
    round_rules = [
        rule
        for rule in rules.values()
        if main_table_round_id is None
        or rule.get("round_id") == main_table_round_id
    ]
    round_rule_ids = {rule["rule_id"] for rule in round_rules}
    partition_evaluations = [
        evaluation
        for evaluation in run["evaluations"]
        if evaluation["partition"] == partition
        and evaluation["rule_id"] in round_rule_ids
    ]
    evaluations = _surface_evaluations(partition_evaluations, rules, surface)
    evaluations_by_rule = {
        evaluation["rule_id"]: evaluation for evaluation in evaluations
    }
    front = _pareto_ids(evaluations)
    eligible_rules = _surface_rules(round_rules, surface)
    displayed_rules = (
        eligible_rules
        if rule_view == "all"
        else [
            rule
            for rule in eligible_rules
            if rule["rule_id"] in front
        ]
    )
    surface_config = SURFACES[surface]
    view_config = RULE_VIEWS[rule_view]
    rows = []
    prediction_counts = run.get("prediction_counts", {})
    for rule in sorted(
        displayed_rules,
        key=lambda item: (
            0 if item["rule_id"] in evaluations_by_rule else 1,
            -evaluations_by_rule.get(item["rule_id"], {})
            .get("metrics", {})
            .get("precision_lower_bound", 0),
            -evaluations_by_rule.get(item["rule_id"], {})
            .get("metrics", {})
            .get("recall", 0),
            item["rule_id"],
        ),
    ):
        rule_id = rule["rule_id"]
        evaluation = evaluations_by_rule.get(rule_id)
        metrics = evaluation["metrics"] if evaluation else None
        counts = evaluation["counts"] if evaluation else None
        treatment_use = _evidence_label(rule)
        surface_status = (
            "Pareto"
            if rule_id in front
            else ("Scored" if evaluation else "Not scored")
        )
        prediction_count = prediction_counts.get(
            rule_id,
            (
                counts.get("submitted_predictions", counts["eligible_predictions"])
                if counts
                else 0
            ),
        )
        known_hits = counts["known_hits"] if counts else None
        precision = metrics["precision_lower_bound"] if metrics else None
        recall = metrics["recall"] if metrics else None
        f0_5 = metrics["f0_5"] if metrics else None
        mechanism_rank = {"low": 1, "medium": 2, "high": 3}.get(
            rule["mechanism"]["score"],
            0,
        )
        rows.append(
            f"""<tr data-rule-row>
<td data-sort-value="{escape(rule["name"].casefold())}"><a class="rule-link" href="/benchmark/run/{escape(manifest["run_id"])}/rule/{escape(rule_id)}">{escape(rule["name"])}</a>
<span class="rule-id">{escape(rule_id)}</span></td>
<td data-sort-value="{escape(rule.get("round_id", ""))}">{escape(rule.get("round_id", "unknown"))}</td>
<td data-sort-value="{escape(rule["family_id"].casefold())}">{escape(rule["family_id"])}</td>
<td data-sort-value="{escape(rule.get("status", "unknown").casefold())}">{escape(rule.get("status", "unknown"))}</td>
<td data-sort-value="{mechanism_rank}">{escape(rule["mechanism"]["score"])}</td>
<td data-sort-value="{escape(treatment_use.casefold())}">{treatment_use}</td>
<td data-sort-value="{escape(surface_status.casefold())}">{surface_status}</td>
<td data-sort-value="{prediction_count}">{prediction_count:,}</td>
<td data-sort-value="{known_hits if known_hits is not None else ""}">{f"{known_hits:,}" if known_hits is not None else "—"}</td>
<td data-sort-value="{precision if precision is not None else ""}">{f"{precision * 100:.2f}%" if precision is not None else "—"}</td>
<td data-sort-value="{recall if recall is not None else ""}">{f"{recall * 100:.4f}%" if recall is not None else "—"}</td>
<td data-sort-value="{f0_5 if f0_5 is not None else ""}">{f"{f0_5 * 100:.4f}%" if f0_5 is not None else "—"}</td>
</tr>"""
        )
    table_rows = "".join(rows)
    if not table_rows:
        empty_message = (
            "No Pareto-optimal rules are available for this surface in the "
            "selected evaluation partition."
            if rule_view == "pareto"
            else (
                "No rules are eligible for this Pareto surface in the selected "
                "evaluation partition."
            )
        )
        table_rows = f'<tr><td colspan="12">{empty_message}</td></tr>'
    partition_tabs = "".join(
        f'<a class="{"active" if name == partition else ""}" '
        f'href="/benchmark/run/{escape(manifest["run_id"])}?partition={name}'
        f'&amp;surface={surface}&amp;view={rule_view}&amp;round_id={round_id}">{name.title()}</a>'
        for name in ("feedback", "final")
    )
    surface_tabs = "".join(
        f'<a class="{"active" if name == surface else ""}" '
        f'href="/benchmark/run/{escape(manifest["run_id"])}?partition={partition}'
        f'&amp;surface={name}&amp;view={rule_view}&amp;round_id={round_id}">'
        f'{escape(config["short_title"])}</a>'
        for name, config in available_surfaces.items()
    )
    view_tabs = "".join(
        f'<a class="{"active" if name == rule_view else ""}" '
        f'href="/benchmark/run/{escape(manifest["run_id"])}?partition={partition}'
        f'&amp;surface={surface}&amp;view={name}&amp;round_id={round_id}">{escape(config["title"])}</a>'
        for name, config in RULE_VIEWS.items()
    )
    round_tabs = "".join(
        f'<a class="{"active" if name == (main_table_round_id or "all") else ""}" '
        f'href="/benchmark/run/{escape(manifest["run_id"])}?partition={partition}'
        f'&amp;surface={surface}&amp;view={rule_view}&amp;round_id={escape(name)}">'
        f'{escape(label)}</a>'
        for name, label in [
            ("all", "All rounds"),
            *((item["round_id"], f'Round {item["round_number"]}') for item in run["rounds"]),
        ]
    )
    round_rows = []
    agent_executions = run.get("agent_executions", {})
    for round_manifest in run["rounds"]:
        start = round_manifest["starting_artifacts"]
        end = round_manifest["ending_artifacts"]
        current_rule_count = len(
            [
                rule
                for rule in run["rules"]
                if rule["round_id"] == round_manifest["round_id"]
            ]
        )
        current_artifact_count = len(
            [
                artifact
                for artifact in run["neo4j_artifacts"]
                if artifact["round_id"] == round_manifest["round_id"]
            ]
        )
        current_evaluation_count = len(
            [
                evaluation
                for evaluation in run["evaluations"]
                if evaluation["round_id"] == round_manifest["round_id"]
            ]
        )
        rule_count = (
            end["rules"]["records"] - start["rules"]["records"]
            if end is not None
            else current_rule_count
        )
        evaluation_count = current_evaluation_count
        instruction_path = (
            Path(manifest["artifacts"]["rounds"])
            / round_manifest["round_id"]
            / "instructions.md"
        )
        instruction = (
            Path(run.get("run_dir", ".")) / instruction_path
        )
        instruction_text = (
            instruction.read_text(encoding="utf-8").strip()
            if instruction.is_file()
            else ""
        )
        round_rows.append(
            f"""<tr>
<td>{escape(round_manifest["round_id"])}</td>
<td>{escape(round_manifest["status"])}</td>
<td>{escape(round_manifest["deadline"] or "none")}</td>
<td>{_agent_execution_cell(agent_executions.get(round_manifest["round_id"]))}</td>
<td>{current_artifact_count:,}</td>
<td>{rule_count:,}</td>
<td>{evaluation_count:,}</td>
<td>{escape(instruction_text)}</td>
</tr>"""
        )
    artifact_rows = "".join(
        f"""<tr>
<td><a class="rule-link" href="/benchmark/run/{escape(manifest["run_id"])}/neo4j-artifact/{escape(artifact["artifact_id"])}">{escape(artifact["name"])}</a>
<span class="rule-id">{escape(artifact["artifact_id"])}</span></td>
<td>{escape(artifact["round_id"])}</td>
<td>{escape(artifact["artifact_kind"])}</td>
<td>{escape(_artifact_target(artifact))}</td>
<td>{artifact["observed"]["values_populated"]:,}</td>
<td>{artifact["observed"]["values_missing"]:,}</td>
<td>{escape(artifact["target"]["unit"] or "none")}</td>
</tr>"""
        for artifact in run["neo4j_artifacts"]
    )
    if not artifact_rows:
        artifact_rows = '<tr><td colspan="7">No agent-created Neo4j artifacts.</td></tr>'
    research_events = run.get("research_events", [])
    rule_sets = run.get("rule_sets", [])
    overlap_report = run.get("rule_overlap")
    estimated_pareto_rule_sets = sum(
        rule_set["is_estimated_pareto"] for rule_set in rule_sets
    )
    subset_relations = len(overlap_report["relations"]) if overlap_report else 0
    latest_research_rows = []
    for event in reversed(research_events[-8:]):
        latest_research_rows.append(
            f"""<tr>
<td>{event["sequence"]:,}</td>
<td>{escape(event["timestamp"])}</td>
<td><span class="event-type">{escape(_humanize_detail_key(event["event_type"]))}</span></td>
<td>{escape(event["summary"])}</td>
<td>{_research_rule_link(event=event, manifest=manifest, rules=rules)}</td>
</tr>"""
        )
    research_rows = "".join(latest_research_rows)
    if not research_rows:
        research_rows = '<tr><td colspan="5">No research events recorded.</td></tr>'
    run_status = manifest["status"].replace("_", " ")
    run_status_class = (
        "complete"
        if manifest["status"] in {"round_complete", "completed"}
        else "running"
    )
    round_scope = (
        f"Showing {main_table_round_id}. Pareto is computed within this round only; "
        "earlier and later rounds are not compared."
        if main_table_round_id
        else "Showing all rounds. Pareto is computed across the entire run."
    )
    sortable_headers = "".join(
        [
            _sortable_header("Rule"),
            _sortable_header("Round"),
            _sortable_header("Family"),
            _sortable_header("Status"),
            _sortable_header("Mechanism", "number"),
            _sortable_header("Treatment premises", "number"),
            _sortable_header("Surface"),
            _sortable_header("Predictions", "number"),
            _sortable_header("Hits", "number"),
            _sortable_header("Precision lower bound", "number"),
            _sortable_header("Recall", "number"),
            _sortable_header("F0.5", "number"),
        ]
    )
    body = f"""<main class="shell">
<header class="masthead"><div>
<p class="eyebrow">Schema-validated rule mining</p>
<div class="run-title"><h1>{escape(manifest["run_id"])}</h1>
<span class="run-status {run_status_class}">Run status: {escape(run_status)}</span></div>
<p class="lede">Graph {escape(manifest["graph_version"])} · Biolink {escape(manifest["biolink_version"])} with descendant expansion · split {escape(manifest["split_id"])} · {len(rounds)} rounds</p>
</div></header>
<section class="panel">
<div class="panel-head"><div><p class="eyebrow">Run history</p>
<h2>Rounds</h2></div></div>
<div class="table-wrap"><table><thead><tr>
<th>Round</th><th>Status</th><th>Deadline</th><th>Model</th>
<th>Neo4j artifacts</th><th>Rules</th>
<th>Evaluations</th><th>Operator instruction</th>
</tr></thead><tbody>{''.join(round_rows)}</tbody></table></div>
</section>
<section class="panel">
<div class="panel-head"><div><p class="eyebrow">Experiment history</p>
<h2>Research log</h2>
<p>{len(research_events):,} append-only events. Showing the most recent eight.</p>
<div class="event-counts">{_research_event_counts(research_events)}</div>
<a class="research-log-link" href="/benchmark/run/{escape(manifest["run_id"])}/research">View the complete chronological research log</a>
</div></div>
<div class="table-wrap"><table><thead><tr>
<th>Sequence</th><th>Timestamp</th><th>Type</th><th>Summary</th><th>Rule</th>
</tr></thead><tbody>{research_rows}</tbody></table></div>
</section>
<section class="panel">
<div class="panel-head"><div><p class="eyebrow">Materialized graph features</p>
<h2>Agent-created Neo4j artifacts</h2></div></div>
<div class="table-wrap"><table><thead><tr>
<th>Artifact</th><th>Round</th><th>Kind</th><th>Neo4j target</th>
<th>Values populated</th><th>Values missing</th><th>Unit</th>
</tr></thead><tbody>{artifact_rows}</tbody></table></div>
</section>
<section class="panel">
<div class="panel-head"><div><p class="eyebrow">Coverage-aware selection</p>
<h2>Rule portfolios</h2>
<p>{len(rule_sets):,} ordered portfolio prefixes, {estimated_pareto_rule_sets:,}
on the estimated portfolio surface, with {subset_relations:,} exact duplicate or
strict-subset relationships.</p>
<a class="research-log-link" href="/benchmark/run/{escape(manifest["run_id"])}/rule-sets">Examine portfolio selection and rule overlap</a>
</div></div>
</section>
<nav class="dashboard-nav">
<div><strong>Compare:</strong>{round_tabs}</div>
<div><strong>Evaluation:</strong>{partition_tabs}</div>
<div><strong>Pareto surface:</strong>{surface_tabs}</div>
<div><strong>Rules:</strong>{view_tabs}</div>
</nav>
<section class="panel">
<div class="panel-head"><div><p class="eyebrow">{len(front)} Pareto rules · {len(displayed_rules)} of {len(eligible_rules)} shown</p>
<h2>{escape(partition.title())} · {escape(surface_config["title"])}</h2>
<p>{escape(round_scope)} {escape(surface_config["description"])} {escape(view_config["description"])}</p></div></div>
<div class="table-wrap"><table class="sortable-table" id="rules-table"><thead><tr>
{sortable_headers}
</tr></thead><tbody>{table_rows}</tbody></table></div>
</section></main>
<script>
document.querySelectorAll("#rules-table th[data-sort-type]").forEach((header, columnIndex) => {{
  const button = header.querySelector(".sort-button");
  button.addEventListener("click", () => {{
    const tableBody = document.querySelector("#rules-table tbody");
    const rows = Array.from(tableBody.querySelectorAll("tr[data-rule-row]"));
    if (rows.length < 2) return;

    const direction = header.dataset.direction === "asc" ? "desc" : "asc";
    document.querySelectorAll("#rules-table th[data-sort-type]").forEach((other) => {{
      other.dataset.direction = "";
      other.setAttribute("aria-sort", "none");
      other.querySelector(".sort-indicator").textContent = "[sort]";
    }});
    header.dataset.direction = direction;
    header.setAttribute("aria-sort", direction === "asc" ? "ascending" : "descending");
    header.querySelector(".sort-indicator").textContent =
      direction === "asc" ? "[asc]" : "[desc]";

    const sortType = header.dataset.sortType;
    const compare = (left, right) => {{
      const leftValue = left.cells[columnIndex].dataset.sortValue ?? "";
      const rightValue = right.cells[columnIndex].dataset.sortValue ?? "";
      if (sortType === "number") {{
        return Number(leftValue) - Number(rightValue);
      }}
      return leftValue.localeCompare(rightValue, undefined, {{
        numeric: true,
        sensitivity: "base",
      }});
    }};
    rows.sort((left, right) => {{
      const leftValue = left.cells[columnIndex].dataset.sortValue ?? "";
      const rightValue = right.cells[columnIndex].dataset.sortValue ?? "";
      if (leftValue === "" || rightValue === "") {{
        if (leftValue === rightValue) return 0;
        return leftValue === "" ? 1 : -1;
      }}
      const result = compare(left, right);
      return direction === "asc" ? result : -result;
    }});
    rows.forEach((row) => tableBody.appendChild(row));
  }});
}});
</script>"""
    return _page(manifest["run_id"], body)


def _rule_set_evaluation_map(
    evaluations: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (evaluation["rule_set_id"], evaluation["partition"]): evaluation
        for evaluation in evaluations
    }


def render_rule_sets(run: dict[str, Any], surface: str) -> str:
    available_surfaces = _available_surfaces(run, surface)
    manifest = run["manifest"]
    rule_sets = [
        rule_set
        for rule_set in run.get("rule_sets", [])
        if rule_set["surface"] == surface
    ]
    evaluations = _rule_set_evaluation_map(run.get("rule_set_evaluations", []))
    overlap = run.get("rule_overlap")
    rows = []
    for rule_set in sorted(
        rule_sets,
        key=lambda item: item["union"]["member_count"],
    ):
        union = rule_set["union"]
        feedback = evaluations.get((rule_set["rule_set_id"], "feedback"))
        rows.append(
            f"""<tr>
<td><a class="rule-link" href="/benchmark/run/{escape(manifest["run_id"])}/rule-set/{escape(rule_set["rule_set_id"])}">{escape(rule_set["rule_set_id"])}</a></td>
<td>{"Estimated Pareto" if rule_set["is_estimated_pareto"] else "Candidate"}</td>
<td>{union["member_count"]:,}</td>
<td>{union["prediction_count"]:,}</td>
<td>{union["training_hits"]:,}</td>
<td>{union["training_recall"] * 100:.3f}%</td>
<td>{union["estimated_feedback_precision"] * 100:.2f}%<span class="metric-note">estimated</span></td>
<td>{union["estimated_feedback_recall"] * 100:.3f}%<span class="metric-note">estimated</span></td>
<td>{union["estimated_f0_5"] * 100:.3f}%<span class="metric-note">estimated</span></td>
<td>{f'{feedback["counts"]["known_hits"]:,}' if feedback else "—"}</td>
<td>{f'{feedback["metrics"]["precision_lower_bound"] * 100:.2f}%' if feedback else "—"}</td>
<td>{f'{feedback["metrics"]["recall"] * 100:.3f}%' if feedback else "—"}</td>
<td>{f'{feedback["metrics"]["f0_5"] * 100:.3f}%' if feedback else "—"}</td>
</tr>"""
        )
    table_rows = "".join(rows)
    if not table_rows:
        table_rows = (
            '<tr><td colspan="13">No rule-set analysis has been generated for '
            "this run and surface.</td></tr>"
        )
    tabs = "".join(
        f'<a class="{"active" if name == surface else ""}" '
        f'href="/benchmark/run/{escape(manifest["run_id"])}/rule-sets'
        f'?surface={name}">{escape(config["short_title"])}</a>'
        for name, config in available_surfaces.items()
    )
    duplicate_count = (
        sum(
            relation["prediction_relation"] == "exact_duplicate"
            for relation in overlap["relations"]
        )
        if overlap
        else 0
    )
    subset_count = (
        sum(
            relation["prediction_relation"] == "left_strict_subset"
            for relation in overlap["relations"]
        )
        if overlap
        else 0
    )
    body = f"""<main class="shell">
<a class="back-link" href="/benchmark/run/{escape(manifest["run_id"])}">← Back to run</a>
<header class="detail-top"><div class="detail-title">
<p class="eyebrow">Coverage-aware rule selection</p>
<h1>Rule portfolios</h1>
<p class="detail-id">{escape(manifest["run_id"])} · through round {manifest["round_count"]:04d}</p>
</div></header>
<section class="panel"><p>The selector found {duplicate_count:,} exact duplicate
relationships and {subset_count:,} strict-subset relationships. A subset rule is
retained as a candidate because it may be more precise than its superset; it adds
no marginal coverage after an equal-or-better superset has been selected.</p></section>
<nav class="dashboard-nav"><div><strong>Surface:</strong>{tabs}</div></nav>
<section class="panel">
<div class="panel-head"><div><p class="eyebrow">{len(rule_sets):,} portfolio prefixes</p>
<h2>{escape(SURFACES[surface]["title"])}</h2>
<p>Estimated metrics apply each member's aggregate feedback precision to only
the new pairs added at that step. Scored metrics come only from aggregate union
scoring.</p>
</div></div>
<div class="table-wrap"><table><thead><tr>
<th>Portfolio</th><th>Status</th><th>Rules</th><th>Predictions</th>
<th>Training hits</th><th>Training recall</th>
<th>Estimated precision</th><th>Estimated recall</th><th>Estimated F0.5</th>
<th>Scored hits</th><th>Scored precision</th><th>Scored recall</th>
<th>Scored F0.5</th>
</tr></thead><tbody>{table_rows}</tbody></table></div>
</section></main>"""
    return _page(f"{manifest['run_id']} rule portfolios", body)


def render_rule_set(run: dict[str, Any], rule_set_id: str) -> str:
    manifest = run["manifest"]
    rule_sets = {
        rule_set["rule_set_id"]: rule_set for rule_set in run.get("rule_sets", [])
    }
    rule_set = rule_sets.get(rule_set_id)
    if rule_set is None:
        raise HTTPException(status_code=404, detail="Unknown rule set")
    rules = {rule["rule_id"]: rule for rule in run["rules"]}
    evaluations = _rule_set_evaluation_map(run.get("rule_set_evaluations", []))
    feedback = evaluations.get((rule_set_id, "feedback"))
    final = evaluations.get((rule_set_id, "final"))
    member_rows = []
    for member in rule_set["members"]:
        rule = rules[member["rule_id"]]
        member_rows.append(
            f"""<article class="portfolio-member">
<h3>{member["position"]}. <a href="/benchmark/run/{escape(manifest["run_id"])}/rule/{escape(member["rule_id"])}">{escape(rule["name"])}</a></h3>
<p><strong>Rule precision:</strong> {member["feedback_precision"] * 100:.2f}% ·
<strong>new eligible pairs:</strong> {member["new_eligible_predictions"]:,} ·
<strong>estimated new hits:</strong> {member["estimated_new_feedback_hits"]:.2f} ·
<strong>guaranteed new hits:</strong> {member["guaranteed_new_feedback_hits"]:,}</p>
<p><strong>Cumulative:</strong> {member["cumulative_eligible_predictions"]:,}
eligible predictions, {member["cumulative_estimated_feedback_precision"] * 100:.2f}%
estimated precision, {member["cumulative_estimated_feedback_recall"] * 100:.3f}%
estimated recall.</p>
</article>"""
        )
    exclusion_counts = Counter(
        exclusion["reason"] for exclusion in rule_set["excluded_rules"]
    )
    exclusion_text = "".join(
        f'<span class="event-count">{escape(_humanize_detail_key(reason))}: '
        f"{count:,}</span>"
        for reason, count in sorted(exclusion_counts.items())
    )
    scored_rows = []
    for partition, evaluation in (("feedback", feedback), ("final", final)):
        if evaluation:
            scored_rows.append(
                f"<li><strong>{partition.title()}</strong>: "
                f"{evaluation['counts']['known_hits']:,} hits, "
                f"{evaluation['metrics']['precision_lower_bound'] * 100:.2f}% "
                f"precision, {evaluation['metrics']['recall'] * 100:.3f}% recall, "
                f"{evaluation['metrics']['f0_5'] * 100:.3f}% F0.5.</li>"
            )
    union = rule_set["union"]
    body = f"""<main class="shell">
<a class="back-link" href="/benchmark/run/{escape(manifest["run_id"])}/rule-sets?surface={escape(rule_set["surface"])}">← Back to portfolios</a>
<header class="detail-top"><div class="detail-title">
<p class="eyebrow">{escape(rule_set["surface"])}</p>
<h1>{escape(rule_set_id)}</h1>
<p class="detail-id">{union["member_count"]:,} rules · {union["prediction_count"]:,} predictions</p>
</div></header>
<div class="detail-grid"><div class="stack">
<section class="card"><div class="card-head"><h2>Ordered members</h2></div>
<div class="card-body portfolio-members">{''.join(member_rows)}</div></section>
</div><aside class="stack">
<section class="card"><div class="card-head"><h2>Union estimate</h2></div>
<div class="card-body">
<p><strong>Training recall:</strong> {union["training_recall"] * 100:.3f}%</p>
<p><strong>Estimated feedback precision:</strong> {union["estimated_feedback_precision"] * 100:.2f}%</p>
<p><strong>Estimated feedback recall:</strong> {union["estimated_feedback_recall"] * 100:.3f}%</p>
<p><strong>Estimated F0.5:</strong> {union["estimated_f0_5"] * 100:.3f}%</p>
<p><strong>Guaranteed feedback hits:</strong> {union["guaranteed_feedback_hits"]:,}</p>
<p>The guaranteed count is the minimum implied by each member's aggregate hit
count and overlap with the previously selected union. The estimate assumes each
member's observed precision also applies to the new pairs it contributes.</p>
</div></section>
<section class="card"><div class="card-head"><h2>Aggregate scoring</h2></div>
<div class="card-body"><ul>{''.join(scored_rows) or "<li>Not yet scored as a union.</li>"}</ul></div></section>
<section class="card"><div class="card-head"><h2>Excluded rules</h2></div>
<div class="card-body"><div class="event-counts">{exclusion_text}</div></div></section>
</aside></div></main>"""
    return _page(rule_set_id, body)


def render_research_log(run: dict[str, Any]) -> str:
    manifest = run["manifest"]
    rules = {rule["rule_id"]: rule for rule in run["rules"]}
    events = run.get("research_events", [])
    event_sections = []
    for event in events:
        event_sections.append(
            f"""<article class="research-event" id="event-{event["sequence"]}">
<div class="research-meta">
<span class="event-type">{escape(_humanize_detail_key(event["event_type"]))}</span>
<span>#{event["sequence"]:,}</span>
<span>{escape(event["timestamp"])}</span>
<span>{escape(event["round_id"])}</span>
<span>Rule: {_research_rule_link(event=event, manifest=manifest, rules=rules)}</span>
</div>
<h2>{escape(event["summary"])}</h2>
<details><summary>Structured details</summary>
{_render_research_details(event["details"])}
</details>
<details><summary>Raw event JSON</summary>
<pre class="json-block"><code>{escape(json.dumps(event, indent=2))}</code></pre>
</details>
</article>"""
        )
    event_content = "".join(event_sections)
    if not event_content:
        event_content = '<section class="panel"><p>No research events recorded.</p></section>'
    body = f"""<main class="shell">
<a class="back-link" href="/benchmark/run/{escape(manifest["run_id"])}">← Back to run</a>
<header class="detail-top"><div class="detail-title">
<p class="eyebrow">Append-only experiment history</p>
<h1>Research log</h1>
<p class="detail-id">{escape(manifest["run_id"])} · {len(events):,} events</p>
<div class="event-counts">{_research_event_counts(events)}</div>
</div></header>
{event_content}
</main>"""
    return _page(f"{manifest['run_id']} research log", body)


def render_rule(run: dict[str, Any], rule_id: str) -> str:
    manifest = run["manifest"]
    rules = {rule["rule_id"]: rule for rule in run["rules"]}
    rule = rules.get(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Unknown rule")
    evaluations = [
        evaluation
        for evaluation in run["evaluations"]
        if evaluation["rule_id"] == rule_id
    ]
    evaluation_rows = []
    for item in evaluations:
        partition_evaluations = [
            evaluation
            for evaluation in run["evaluations"]
            if evaluation["partition"] == item["partition"]
        ]
        surface_links = []
        for surface in run_surfaces(run["rules"]):
            config = SURFACES[surface]
            eligible = _surface_evaluations(partition_evaluations, rules, surface)
            if rule_id in _pareto_ids(eligible):
                surface_links.append(
                    f'<a href="/benchmark/run/{escape(manifest["run_id"])}'
                    f'?partition={escape(item["partition"])}&amp;surface={surface}'
                    f'&amp;view=pareto">'
                    f'{escape(config["short_title"])}</a>'
                )
        surface_text = ", ".join(surface_links) or "not Pareto"
        evaluation_rows.append(
            f"<li><strong>{escape(item['partition'])}</strong>: "
            f"{item['metrics']['precision_lower_bound'] * 100:.2f}% precision, "
            f"{item['metrics']['recall'] * 100:.4f}% recall, "
            f"{item['counts']['eligible_predictions']:,} eligible predictions. "
            f"<strong>Surface membership:</strong> {surface_text}</li>"
        )
    feature_rows = []
    for feature in rule["derived_features"]:
        artifact_id = feature["neo4j_artifact_id"]
        artifact_link = (
            f' <a href="/benchmark/run/{escape(manifest["run_id"])}/neo4j-artifact/'
            f'{escape(artifact_id)}">Neo4j artifact {escape(artifact_id)}</a>'
            if artifact_id
            else " Not materialized in Neo4j."
        )
        feature_rows.append(
            f"<li><strong>{escape(feature['name'])}</strong>: "
            f"{escape(feature['definition'])} Construction: "
            f"{escape(feature['construction'])} Interpretation: "
            f"{escape(feature['interpretation'])}.{artifact_link}</li>"
        )
    features = "".join(feature_rows) or "<li>None.</li>"
    trapi = rule["execution"]["trapi"]
    predicate_execution = rule["execution"]["predicate_expansion"]
    predicate_rows = _predicate_expansion_rows(rule)
    feedback = next((item for item in evaluations if item["partition"] == "feedback"), None)
    if feedback:
        metrics, counts = feedback["metrics"], feedback["counts"]
        score_strip = f"""<div class="rule-scores" aria-label="Feedback evaluation">
<div class="rule-score"><strong>{metrics["precision_lower_bound"] * 100:.2f}%</strong><span>Feedback precision lower bound</span></div>
<div class="rule-score"><strong>{metrics["recall"] * 100:.4f}%</strong><span>Feedback recall</span></div>
<div class="rule-score"><strong>{counts["known_hits"]:,}</strong><span>Known feedback hits</span></div>
<div class="rule-score"><strong>{counts["eligible_predictions"]:,}</strong><span>Eligible predictions</span></div></div>"""
    else:
        score_strip = '<p class="metric-note">Not yet scored on feedback.</p>'
    limitations = "".join(f"<li>{escape(item)}</li>" for item in rule["limitations"])
    treatment_class = "treatment-using" if rule["uses_treatment_edges"] else "treatment-free"
    treatment_label = _evidence_label(rule)
    body = f"""<main class="shell rule-detail">
<a class="back-link" href="/benchmark/run/{escape(manifest["run_id"])}">← Back to run</a>
<header class="detail-top"><div class="detail-title">
<p class="eyebrow">{escape(rule["family_id"])}</p>
<h1>{escape(rule["name"])}</h1><p class="detail-id">{escape(rule_id)} · {escape(rule["round_id"])}</p>
<div class="rule-badges"><span class="{treatment_class}">{treatment_label}</span>
<span>Recorded status: {escape(rule["status"])}</span></div>
</div></header>
{render_rule_diagram(rule)}
{score_strip}
<div class="detail-grid"><div class="stack">
<section class="card"><div class="card-head"><h2>Evaluations</h2></div>
<div class="card-body"><p>Surface membership compares rules across all rounds.</p>
<ul class="criteria-list">{"".join(evaluation_rows) or "<li>Not yet scored.</li>"}</ul>
<p class="metric-note">Unknown pairs are unlabeled, not established negatives.</p></div></section>
</div><aside class="stack">
<section class="card"><div class="card-head"><h2>Interpretation limits</h2></div>
<div class="card-body"><ul class="criteria-list">{limitations or "<li>No limitations recorded.</li>"}</ul>
<details class="provenance"><summary>Recorded mechanism assessment: {escape(rule["mechanism"]["score"])}</summary>
<p>{escape(rule["mechanism"]["rationale"])}</p></details></div></section>
</aside></div>
<h2>Technical details</h2>
<details class="rule-fold"><summary>Complete rule and hypothesis</summary>
<div class="card-body"><p>{escape(rule["plain_language_rule"])}</p>
<p><strong>Hypothesis:</strong> {escape(rule["hypothesis"])}</p>
<p><strong>Treatment-oriented premises:</strong>
{"yes" if rule["uses_treatment_edges"] else "no"}</p>
<p><strong>Evidence tier:</strong> {escape(rule.get("evidence_tier", "not recorded"))}</p></div></details>
<details class="rule-fold"><summary>Derived features</summary>
<div class="card-body"><ul>{features}</ul></div></details>
<details class="rule-fold"><summary>Biolink predicate semantics</summary>
<div class="card-body"><p><strong>Biolink version:</strong> {escape(predicate_execution["biolink_version"])}</p>
<p><strong>Statistics semantics:</strong> {escape(predicate_execution["semantics"])}</p>
<p><strong>Execution:</strong> {escape(predicate_execution["implementation"])}</p>
<ul>{predicate_rows}</ul></div></details>
<details class="rule-fold"><summary>Executable Cypher</summary>
<pre><code>{escape(rule["execution"]["cypher"])}</code></pre></details>
<details class="rule-fold"><summary>TRAPI</summary>
<div class="card-body"><p>{escape(trapi["expressibility"])}: {escape(trapi["limitations"])}</p></div>
<pre class="json-block"><code>{escape(json.dumps(trapi.get("query"), indent=2))}</code></pre></details>
<details class="rule-fold"><summary>Graph pattern JSON</summary>
<pre class="json-block"><code>{escape(json.dumps(rule["graph_pattern"], indent=2))}</code></pre></details>
<details class="rule-fold"><summary>Complete recorded rule JSON</summary>
<pre class="json-block"><code>{escape(json.dumps(rule, indent=2))}</code></pre></details>
</main>"""
    return _page(rule["name"], body)


def render_neo4j_artifact(run: dict[str, Any], artifact_id: str) -> str:
    manifest = run["manifest"]
    artifacts = {
        artifact["artifact_id"]: artifact for artifact in run["neo4j_artifacts"]
    }
    artifact = artifacts.get(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Unknown Neo4j artifact")
    semantics = artifact["semantics"]
    execution = artifact["execution"]
    dependencies = "".join(
        f'<li><a href="/benchmark/run/{escape(manifest["run_id"])}/neo4j-artifact/'
        f'{escape(dependency)}">{escape(dependency)}</a></li>'
        for dependency in artifact["dependencies"]
    ) or "<li>None.</li>"
    limitations = "".join(
        f"<li>{escape(limitation)}</li>" for limitation in artifact["limitations"]
    ) or "<li>None.</li>"
    body = f"""<main class="shell">
<a class="back-link" href="/benchmark/run/{escape(manifest["run_id"])}">← Back to run</a>
<header class="detail-top"><div class="detail-title">
<p class="eyebrow">{escape(artifact["artifact_kind"])} · {escape(artifact["round_id"])}</p>
<h1>{escape(artifact["name"])}</h1><p class="detail-id">{escape(artifact_id)}</p>
</div></header>
<div class="detail-grid"><div class="stack">
<section class="card"><div class="card-head"><h2>Materialized quantity</h2></div>
<div class="card-body"><p>{escape(artifact["description"])}</p>
<p><strong>Neo4j target:</strong> {escape(_artifact_target(artifact))}</p>
<p><strong>Value type:</strong> {escape(artifact["target"]["value_type"])} ·
<strong>Unit:</strong> {escape(artifact["target"]["unit"] or "none")}</p>
<p><strong>Scope:</strong> {escape(artifact["target"]["scope"])}</p></div></section>
<section class="card"><div class="card-head"><h2>Semantics</h2></div>
<div class="card-body"><p>{escape(semantics["definition"])}</p>
<p><strong>Inputs:</strong> {escape(", ".join(semantics["inputs"]))}</p>
<p><strong>Formula:</strong> {escape(semantics["formula"] or "none")}</p>
<p><strong>Aggregation:</strong> {escape(semantics["aggregation"])}</p>
<p><strong>Deduplication:</strong> {escape(semantics["deduplication"])}</p>
<p><strong>Missing values:</strong> {escape(semantics["missing_value_policy"])}</p>
<p><strong>Interpretation:</strong> {escape(semantics["interpretation"])}</p>
</div></section>
<section class="card"><div class="card-head"><h2>Create Cypher</h2></div>
<pre><code>{escape(execution["create_cypher"])}</code></pre></section>
<section class="card"><div class="card-head"><h2>Verification Cypher</h2></div>
<pre><code>{escape(execution["verification_cypher"])}</code></pre></section>
<section class="card"><div class="card-head"><h2>Cleanup Cypher</h2></div>
<pre><code>{escape(execution["cleanup_cypher"])}</code></pre></section>
</div><aside class="stack">
<section class="card"><div class="card-head"><h2>Observed population</h2></div>
<pre class="json-block"><code>{escape(json.dumps(artifact["observed"], indent=2))}</code></pre></section>
<section class="card"><div class="card-head"><h2>Dependencies</h2></div>
<div class="card-body"><ul>{dependencies}</ul></div></section>
<section class="card"><div class="card-head"><h2>Limitations</h2></div>
<div class="card-body"><ul>{limitations}</ul></div></section>
</aside></div></main>"""
    return _page(artifact["name"], body)


def install_benchmark_dashboard(
    app: FastAPI,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    evaluations_dir: Path = DEFAULT_EVALUATIONS_DIR,
    rule_set_root: Path = DEFAULT_RULE_SET_ROOT,
    rule_set_evaluations_dir: Path = DEFAULT_RULE_SET_EVALUATIONS_DIR,
) -> None:
    @app.get("/benchmark", response_class=HTMLResponse, include_in_schema=False)
    def benchmark_home() -> HTMLResponse:
        run_paths = sorted(runs_dir.glob("*/run.json"), reverse=True)
        if not run_paths:
            return HTMLResponse(
                _page(
                    "No runs",
                    '<main class="shell"><h1>No benchmark runs</h1></main>',
                )
            )
        return HTMLResponse(
            render_run(
                load_dashboard_run(
                    run_dir=run_paths[0].parent,
                    evaluations_dir=evaluations_dir,
                    rule_set_root=rule_set_root,
                    rule_set_evaluations_dir=rule_set_evaluations_dir,
                ),
                "feedback",
                DEFAULT_SURFACE,
                DEFAULT_RULE_VIEW,
            )
        )

    @app.get(
        "/benchmark/run/{run_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def benchmark_run(
        run_id: str,
        partition: str = "feedback",
        surface: str = DEFAULT_SURFACE,
        view: str = DEFAULT_RULE_VIEW,
        round_id: str = "all",
    ) -> HTMLResponse:
        if partition not in {"feedback", "final"}:
            raise HTTPException(status_code=404, detail="Unknown partition")
        if surface not in SURFACES:
            raise HTTPException(status_code=404, detail="Unknown Pareto surface")
        if view not in RULE_VIEWS:
            raise HTTPException(status_code=404, detail="Unknown rule view")
        run_dir = runs_dir / run_id
        if not (run_dir / "run.json").is_file():
            raise HTTPException(status_code=404, detail="Unknown run")
        return HTMLResponse(
            render_run(
                load_dashboard_run(
                    run_dir=run_dir,
                    evaluations_dir=evaluations_dir,
                    rule_set_root=rule_set_root,
                    rule_set_evaluations_dir=rule_set_evaluations_dir,
                ),
                partition,
                surface,
                view,
                round_id,
            )
        )

    @app.get(
        "/benchmark/run/{run_id}/research",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def benchmark_research_log(run_id: str) -> HTMLResponse:
        run_dir = runs_dir / run_id
        if not (run_dir / "run.json").is_file():
            raise HTTPException(status_code=404, detail="Unknown run")
        return HTMLResponse(
            render_research_log(
                load_dashboard_run(
                    run_dir=run_dir,
                    evaluations_dir=evaluations_dir,
                    rule_set_root=rule_set_root,
                    rule_set_evaluations_dir=rule_set_evaluations_dir,
                )
            )
        )

    @app.get(
        "/benchmark/run/{run_id}/rule/{rule_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def benchmark_rule(run_id: str, rule_id: str) -> HTMLResponse:
        run_dir = runs_dir / run_id
        if not (run_dir / "run.json").is_file():
            raise HTTPException(status_code=404, detail="Unknown run")
        return HTMLResponse(
            render_rule(
                load_dashboard_run(
                    run_dir=run_dir,
                    evaluations_dir=evaluations_dir,
                    rule_set_root=rule_set_root,
                    rule_set_evaluations_dir=rule_set_evaluations_dir,
                ),
                rule_id,
            )
        )

    @app.get(
        "/benchmark/run/{run_id}/neo4j-artifact/{artifact_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def benchmark_neo4j_artifact(run_id: str, artifact_id: str) -> HTMLResponse:
        run_dir = runs_dir / run_id
        if not (run_dir / "run.json").is_file():
            raise HTTPException(status_code=404, detail="Unknown run")
        return HTMLResponse(
            render_neo4j_artifact(
                load_dashboard_run(
                    run_dir=run_dir,
                    evaluations_dir=evaluations_dir,
                    rule_set_root=rule_set_root,
                    rule_set_evaluations_dir=rule_set_evaluations_dir,
                ),
                artifact_id,
            )
        )

    @app.get(
        "/benchmark/run/{run_id}/rule-sets",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def benchmark_rule_sets(
        run_id: str,
        surface: str = DEFAULT_SURFACE,
    ) -> HTMLResponse:
        if surface not in SURFACES:
            raise HTTPException(status_code=404, detail="Unknown Pareto surface")
        run_dir = runs_dir / run_id
        if not (run_dir / "run.json").is_file():
            raise HTTPException(status_code=404, detail="Unknown run")
        return HTMLResponse(
            render_rule_sets(
                load_dashboard_run(
                    run_dir=run_dir,
                    evaluations_dir=evaluations_dir,
                    rule_set_root=rule_set_root,
                    rule_set_evaluations_dir=rule_set_evaluations_dir,
                ),
                surface,
            )
        )

    @app.get(
        "/benchmark/run/{run_id}/rule-set/{rule_set_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def benchmark_rule_set(run_id: str, rule_set_id: str) -> HTMLResponse:
        run_dir = runs_dir / run_id
        if not (run_dir / "run.json").is_file():
            raise HTTPException(status_code=404, detail="Unknown run")
        return HTMLResponse(
            render_rule_set(
                load_dashboard_run(
                    run_dir=run_dir,
                    evaluations_dir=evaluations_dir,
                    rule_set_root=rule_set_root,
                    rule_set_evaluations_dir=rule_set_evaluations_dir,
                ),
                rule_set_id,
            )
        )
