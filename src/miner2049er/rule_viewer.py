from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from miner2049er.rule_descriptions import (
    DEFAULT_DESCRIPTIONS_PATH,
    apply_rule_descriptions,
    load_rule_descriptions,
)
from miner2049er.settings import ROOT

DEFAULT_LIBRARY_PATH = ROOT / "results" / "rule-library.json"

SURFACE_ORDER = (
    "visible",
    "visible-treatment-free",
    "validation",
    "validation-treatment-free",
)

SURFACES: dict[str, dict[str, Any]] = {
    "visible": {
        "title": "Visible labels · all rules",
        "short_title": "Visible · all",
        "flag": "pareto_visible",
        "precision_metric": "visible_target_precision_lower_bound",
        "recall_metric": "visible_target_recall",
        "f_metric": "visible_target_f0_5",
        "description": (
            "All eligible rules scored against training labels plus "
            "Drug Repurposing Hub-exclusive labels."
        ),
        "candidate_label": "All predictions",
        "hit_label": "Visible hits",
        "accent": "amber",
    },
    "visible-treatment-free": {
        "title": "Visible labels · treatment-free rules",
        "short_title": "Visible · treatment-free",
        "flag": "pareto_visible_without_treatment_edges",
        "precision_metric": "visible_target_precision_lower_bound",
        "recall_metric": "visible_target_recall",
        "f_metric": "visible_target_f0_5",
        "description": (
            "The same visible labels, restricted to rules that do not use "
            "treatment-oriented edges as premises."
        ),
        "candidate_label": "All predictions",
        "hit_label": "Visible hits",
        "accent": "green",
    },
    "validation": {
        "title": "Drug Repurposing Hub-exclusive · all rules",
        "short_title": "Hub-exclusive · all",
        "flag": "pareto_validation",
        "precision_metric": "validation_precision_lower_bound",
        "recall_metric": "validation_recall",
        "f_metric": "validation_f0_5",
        "description": (
            "All eligible rules scored only by recovery of Drug Repurposing "
            "Hub-exclusive treatment pairs."
        ),
        "candidate_label": "Non-training predictions",
        "hit_label": "Hub-exclusive hits",
        "accent": "blue",
    },
    "validation-treatment-free": {
        "title": "Drug Repurposing Hub-exclusive · treatment-free rules",
        "short_title": "Hub-exclusive · treatment-free",
        "flag": "pareto_validation_without_treatment_edges",
        "precision_metric": "validation_precision_lower_bound",
        "recall_metric": "validation_recall",
        "f_metric": "validation_f0_5",
        "description": (
            "The Hub-exclusive challenge restricted to rules that do not use "
            "treatment-oriented edges as premises."
        ),
        "candidate_label": "Non-training predictions",
        "hit_label": "Hub-exclusive hits",
        "accent": "red",
    },
}

BASE_CSS = """
:root {
  --ink: #132a2c;
  --muted: #657578;
  --paper: #f5f0e6;
  --panel: rgba(255, 253, 248, 0.92);
  --line: rgba(19, 42, 44, 0.16);
  --amber: #c46c20;
  --green: #1f6b57;
  --blue: #276888;
  --red: #a14332;
  --shadow: 0 22px 70px rgba(34, 54, 49, 0.11);
}

* { box-sizing: border-box; }

html { min-height: 100%; }

body {
  margin: 0;
  min-height: 100%;
  color: var(--ink);
  background:
    radial-gradient(circle at 8% 10%, rgba(196, 108, 32, 0.13), transparent 34rem),
    radial-gradient(circle at 88% 18%, rgba(31, 107, 87, 0.13), transparent 30rem),
    linear-gradient(145deg, #f8f3e9 0%, #eee8dc 100%);
  font-family: "Avenir Next", "Gill Sans", "Helvetica Neue", sans-serif;
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  opacity: 0.2;
  background-image:
    linear-gradient(rgba(19, 42, 44, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(19, 42, 44, 0.08) 1px, transparent 1px);
  background-size: 36px 36px;
  mask-image: linear-gradient(to bottom, black, transparent 75%);
}

a { color: inherit; }

.shell {
  width: min(1520px, calc(100% - 40px));
  margin: 0 auto;
  padding: 42px 0 72px;
  position: relative;
}

.masthead {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 28px;
  margin-bottom: 26px;
  animation: rise 420ms ease-out both;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--green);
  font-size: 0.74rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

h1, h2, h3 {
  font-family: "Iowan Old Style", "Palatino Linotype", Palatino, serif;
  font-weight: 600;
  letter-spacing: -0.025em;
}

h1 {
  margin: 0;
  max-width: 900px;
  font-size: clamp(2.35rem, 5vw, 5.4rem);
  line-height: 0.94;
}

.lede {
  max-width: 760px;
  margin: 18px 0 0;
  color: var(--muted);
  font-size: 1.04rem;
  line-height: 1.55;
}

.graph-stamp {
  min-width: 190px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  background: rgba(255, 253, 248, 0.58);
  font-variant-numeric: tabular-nums;
}

.graph-stamp strong,
.graph-stamp span {
  display: block;
}

.graph-stamp strong { font-size: 0.9rem; }
.graph-stamp span { margin-top: 4px; color: var(--muted); font-size: 0.78rem; }

.tabs {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border: 1px solid var(--line);
  background: rgba(255, 253, 248, 0.64);
  box-shadow: var(--shadow);
  animation: rise 480ms 40ms ease-out both;
}

.tab {
  min-height: 78px;
  padding: 16px 18px;
  border-right: 1px solid var(--line);
  text-decoration: none;
  transition: background 150ms ease, color 150ms ease, transform 150ms ease;
}

.tab:last-child { border-right: 0; }
.tab:hover { transform: translateY(-2px); background: #fffdf8; }
.tab.active { color: white; background: var(--ink); }
.tab-title { display: block; font-size: 0.82rem; font-weight: 800; }
.tab-count {
  display: block;
  margin-top: 7px;
  font-family: "Iowan Old Style", "Palatino Linotype", serif;
  font-size: 1.55rem;
}

.panel {
  margin-top: 22px;
  border: 1px solid var(--line);
  background: var(--panel);
  box-shadow: var(--shadow);
  animation: rise 540ms 80ms ease-out both;
}

.panel-head {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 24px;
  padding: 24px 26px 20px;
  border-bottom: 1px solid var(--line);
}

.panel-head h2 { margin: 0; font-size: clamp(1.55rem, 3vw, 2.5rem); }
.panel-head p { max-width: 760px; margin: 7px 0 0; color: var(--muted); }

.search {
  width: min(360px, 100%);
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 0;
  color: var(--ink);
  background: #fffdf8;
  font: inherit;
}

.search:focus { outline: 3px solid rgba(31, 107, 87, 0.18); border-color: var(--green); }

.table-wrap { overflow-x: auto; }

table {
  width: 100%;
  min-width: 1030px;
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
}

th {
  padding: 12px 14px;
  color: var(--muted);
  background: rgba(19, 42, 44, 0.045);
  border-bottom: 1px solid var(--line);
  font-size: 0.69rem;
  letter-spacing: 0.11em;
  text-align: right;
  text-transform: uppercase;
  white-space: nowrap;
}

th:first-child, th:nth-child(2), td:first-child, td:nth-child(2) { text-align: left; }

td {
  padding: 15px 14px;
  border-bottom: 1px solid rgba(19, 42, 44, 0.1);
  text-align: right;
  vertical-align: middle;
}

tbody tr { transition: background 120ms ease; }
tbody tr:hover { background: rgba(31, 107, 87, 0.065); }
tbody tr:last-child td { border-bottom: 0; }

.rule-link {
  display: block;
  max-width: 520px;
  color: var(--ink);
  font-family: "Iowan Old Style", "Palatino Linotype", serif;
  font-size: 1.04rem;
  font-weight: 600;
  line-height: 1.25;
  text-decoration-color: rgba(31, 107, 87, 0.35);
  text-decoration-thickness: 1px;
  text-underline-offset: 4px;
}

.rule-link:hover { color: var(--green); text-decoration-color: var(--green); }
.rule-id { display: block; margin-top: 4px; color: var(--muted); font-size: 0.69rem; }

.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border: 1px solid currentColor;
  font-size: 0.66rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.badge.high { color: var(--green); }
.badge.medium { color: var(--blue); }
.badge.low { color: var(--red); }
.badge.neutral { color: var(--muted); }

.metric-main { display: block; font-weight: 800; }
.metric-note { display: block; margin-top: 3px; color: var(--muted); font-size: 0.69rem; }

.empty {
  padding: 54px 24px;
  color: var(--muted);
  text-align: center;
}

.footnote {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 15px 26px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 0.74rem;
}

.detail-top {
  display: flex;
  justify-content: space-between;
  gap: 26px;
  align-items: start;
  margin-bottom: 20px;
}

.back-link {
  display: inline-block;
  margin-bottom: 20px;
  color: var(--green);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-decoration: none;
  text-transform: uppercase;
}

.back-link:hover { text-decoration: underline; text-underline-offset: 4px; }

.detail-title { max-width: 1050px; }
.detail-title h1 { font-size: clamp(2.3rem, 5vw, 5rem); }
.detail-id { margin: 13px 0 0; color: var(--muted); font-family: ui-monospace, monospace; }

.badge-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }

.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(300px, 0.75fr);
  gap: 22px;
}

.detail-grid > *,
.stack,
.card { min-width: 0; }

.stack { display: grid; gap: 22px; }

.card {
  border: 1px solid var(--line);
  background: var(--panel);
  box-shadow: var(--shadow);
  animation: rise 460ms ease-out both;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 17px 20px;
  border-bottom: 1px solid var(--line);
}

.card-head h2 { margin: 0; font-size: 1.35rem; }
.card-body { padding: 20px; }
.card-body p { margin: 0; color: #314548; font-size: 1rem; line-height: 1.65; }
.card-body p + p { margin-top: 18px; }

.criteria-list {
  margin: 10px 0 0;
  padding-left: 21px;
  color: #314548;
}

.criteria-list li {
  padding-left: 4px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.criteria-list li + li { margin-top: 8px; }

.rule-shorthand {
  display: block;
  margin-top: 9px;
  padding: 11px 13px;
  border-left: 3px solid var(--amber);
  color: #3f5052;
  background: rgba(196, 108, 32, 0.07);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.79rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.provenance {
  margin-top: 22px;
  color: var(--muted);
}

.provenance summary {
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.09em;
  cursor: pointer;
  text-transform: uppercase;
}

.section-label {
  display: block;
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.score-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  background: var(--line);
}

.score {
  min-height: 116px;
  padding: 16px;
  background: #fffdf8;
}

.score strong {
  display: block;
  font-family: "Iowan Old Style", "Palatino Linotype", serif;
  font-size: 2rem;
  font-weight: 600;
}

.score span { color: var(--muted); font-size: 0.74rem; }

.surface-list { display: grid; gap: 9px; }
.surface-chip {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 13px;
  border: 1px solid var(--line);
  background: #fffdf8;
  text-decoration: none;
  transition: border-color 120ms ease, transform 120ms ease;
}

.surface-chip:hover { border-color: var(--green); transform: translateX(3px); }
.surface-chip strong { font-size: 0.82rem; }
.surface-chip span { color: var(--muted); font-size: 0.73rem; }

pre {
  margin: 0;
  padding: 22px;
  overflow: auto;
  color: #e9f1e9;
  background: #132a2c;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.78rem;
  line-height: 1.62;
  tab-size: 2;
}

.copy-button {
  padding: 8px 11px;
  border: 1px solid var(--line);
  color: var(--ink);
  background: transparent;
  font: inherit;
  font-size: 0.72rem;
  font-weight: 800;
  cursor: pointer;
}

.copy-button:hover { border-color: var(--green); color: var(--green); }

.definition-list { display: grid; grid-template-columns: 140px 1fr; margin: 0; }
.definition-list dt,
.definition-list dd { margin: 0; padding: 10px 0; border-bottom: 1px solid var(--line); }
.definition-list dt { color: var(--muted); font-size: 0.74rem; }
.definition-list dd { font-size: 0.86rem; overflow-wrap: anywhere; }
.definition-list a { color: var(--green); }

@keyframes rise {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 900px) {
  .shell { width: min(100% - 24px, 1520px); padding-top: 24px; }
  .masthead, .panel-head, .detail-top { display: block; }
  .graph-stamp { margin-top: 20px; }
  .tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tab:nth-child(2) { border-right: 0; }
  .tab:nth-child(-n + 2) { border-bottom: 1px solid var(--line); }
  .panel-head .search { margin-top: 18px; }
  .detail-grid { grid-template-columns: 1fr; }
}

@media (max-width: 560px) {
  .shell { width: min(100% - 16px, 1520px); }
  .tabs { grid-template-columns: 1fr; }
  .tab { min-height: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  .tab:last-child { border-bottom: 0; }
  .score-grid { grid-template-columns: 1fr 1fr; }
  .footnote { display: block; }
  .footnote span { display: block; margin-top: 5px; }
}
"""

TABLE_SCRIPT = """
<script>
const filter = document.getElementById("rule-filter");
const rows = Array.from(document.querySelectorAll("#rule-table tbody tr"));
const empty = document.getElementById("empty-state");

function filterRules() {
  const query = filter.value.trim().toLowerCase();
  let visible = 0;
  rows.forEach((row) => {
    const match = row.dataset.search.includes(query);
    row.hidden = !match;
    if (match) visible += 1;
  });
  empty.hidden = visible !== 0;
}

filter.addEventListener("input", filterRules);
</script>
"""

COPY_SCRIPT = """
<script>
async function copyCypher(button) {
  const text = document.getElementById("rule-cypher").textContent;
  await navigator.clipboard.writeText(text);
  const original = button.textContent;
  button.textContent = "Copied";
  setTimeout(() => { button.textContent = original; }, 1200);
}
</script>
"""


def load_library(
    path: Path = DEFAULT_LIBRARY_PATH,
    descriptions_path: Path = DEFAULT_DESCRIPTIONS_PATH,
) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Rule library not found: {path}")
    library = json.loads(path.read_text(encoding="utf-8"))
    return apply_rule_descriptions(
        library,
        load_rule_descriptions(descriptions_path),
    )


def surface_path(slug: str) -> str:
    if slug == "visible":
        return "/rules"
    return f"/rules/surface/{slug}"


def rule_path(rule_id: str) -> str:
    return f"/rules/rule/{rule_id}"


def _format_integer(value: Any) -> str:
    return f"{int(value or 0):,}"


def _format_percent(value: Any, digits: int = 2) -> str:
    return f"{float(value or 0.0) * 100:.{digits}f}%"


def _surface_results(library: dict[str, Any], slug: str) -> list[dict[str, Any]]:
    surface = SURFACES[slug]
    results = [
        result
        for result in library.get("results", [])
        if result.get(surface["flag"], False)
    ]
    return sorted(
        results,
        key=lambda result: (
            -float(result.get("metrics", {}).get(surface["precision_metric"], 0.0)),
            -float(result.get("metrics", {}).get(surface["recall_metric"], 0.0)),
            result["id"],
        ),
    )


def _surface_counts(library: dict[str, Any]) -> dict[str, int]:
    return {
        slug: len(_surface_results(library, slug))
        for slug in SURFACE_ORDER
    }


def _surface_memberships(rule: dict[str, Any]) -> list[str]:
    return [
        slug
        for slug in SURFACE_ORDER
        if rule.get(SURFACES[slug]["flag"], False)
    ]


def _visible_hits(rule: dict[str, Any]) -> int:
    counts = rule.get("counts", {})
    return int(counts.get("training_hits", 0)) + int(counts.get("validation_hits", 0))


def _validation_candidates(rule: dict[str, Any]) -> int:
    counts = rule.get("counts", {})
    return int(counts.get("candidate_pairs", 0)) - int(counts.get("training_hits", 0))


def _surface_candidates(rule: dict[str, Any], slug: str) -> int:
    if slug.startswith("validation"):
        return _validation_candidates(rule)
    return int(rule.get("counts", {}).get("candidate_pairs", 0))


def _surface_hits(rule: dict[str, Any], slug: str) -> int:
    if slug.startswith("validation"):
        return int(rule.get("counts", {}).get("validation_hits", 0))
    return _visible_hits(rule)


def _html_page(title: str, body: str, script: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{escape(title)} · Treats Rule Atlas</title>
  <style>{BASE_CSS}</style>
</head>
<body>
  {body}
  {script}
</body>
</html>
"""


def _render_tabs(library: dict[str, Any], active_slug: str) -> str:
    counts = _surface_counts(library)
    tabs = []
    for slug in SURFACE_ORDER:
        surface = SURFACES[slug]
        active = " active" if slug == active_slug else ""
        current = ' aria-current="page"' if slug == active_slug else ""
        tabs.append(
            f"""<a class="tab{active}" href="{surface_path(slug)}"{current}>
  <span class="tab-title">{escape(surface["short_title"])}</span>
  <span class="tab-count">{counts[slug]}</span>
</a>"""
        )
    return '<nav class="tabs" aria-label="Pareto surfaces">' + "".join(tabs) + "</nav>"


def _render_surface_row(rule: dict[str, Any], slug: str) -> str:
    surface = SURFACES[slug]
    metrics = rule.get("metrics", {})
    counts = rule.get("counts", {})
    training_hits = int(counts.get("training_hits", 0))
    validation_hits = int(counts.get("validation_hits", 0))
    hit_note = (
        f"{training_hits:,} training + {validation_hits:,} Hub-exclusive"
        if not slug.startswith("validation")
        else f"{_validation_candidates(rule):,} non-training predictions"
    )
    search = " ".join(
        [
            str(rule.get("id", "")),
            str(rule.get("name", "")),
            str(rule.get("mechanism_score", "")),
            str(rule.get("body", "")),
        ]
    ).lower()
    return f"""<tr data-search="{escape(search, quote=True)}">
  <td>
    <a class="rule-link" href="{rule_path(rule["id"])}">{escape(rule["name"])}</a>
    <span class="rule-id">{escape(rule["id"])}</span>
  </td>
  <td><span class="badge {escape(rule["mechanism_score"])}">{escape(rule["mechanism_score"])}</span></td>
  <td>{_format_integer(_surface_candidates(rule, slug))}</td>
  <td>
    <span class="metric-main">{_format_integer(_surface_hits(rule, slug))}</span>
    <span class="metric-note">{escape(hit_note)}</span>
  </td>
  <td><span class="metric-main">{_format_percent(metrics.get(surface["precision_metric"]))}</span></td>
  <td>{_format_percent(metrics.get(surface["recall_metric"]), 4)}</td>
  <td>{_format_percent(metrics.get(surface["f_metric"]), 4)}</td>
</tr>"""


def render_surface_page(library: dict[str, Any], slug: str) -> str:
    if slug not in SURFACES:
        raise HTTPException(status_code=404, detail="Unknown Pareto surface")
    surface = SURFACES[slug]
    results = _surface_results(library, slug)
    inventory = library.get("target_inventory", {})
    graph_count = inventory.get("counts", {}).get("semantic_pairs", 0)
    rows = "".join(_render_surface_row(rule, slug) for rule in results)
    body = f"""
<main class="shell">
  <header class="masthead">
    <div>
      <p class="eyebrow">Translator 2026_06_21 · Treats Rule Atlas</p>
      <h1>Pareto surfaces,<br>without the fog.</h1>
      <p class="lede">
        Each page is one non-dominated precision–recall frontier. Open a rule
        to inspect its biological claim, mechanism assessment, executable
        Cypher, and membership in the other surfaces.
      </p>
    </div>
    <div class="graph-stamp">
      <strong>{_format_integer(graph_count)} labeled pairs</strong>
      <span>Library updated {escape(str(library.get("updated_at", "unknown")))}</span>
    </div>
  </header>
  {_render_tabs(library, slug)}
  <section class="panel">
    <div class="panel-head">
      <div>
        <p class="eyebrow">{len(results)} non-dominated rules</p>
        <h2>{escape(surface["title"])}</h2>
        <p>{escape(surface["description"])}</p>
      </div>
      <label>
        <span class="section-label">Filter this surface</span>
        <input id="rule-filter" class="search" type="search"
               placeholder="Rule ID, name, mechanism…" autocomplete="off">
      </label>
    </div>
    <div class="table-wrap">
      <table id="rule-table">
        <thead>
          <tr>
            <th>Rule</th>
            <th>Mechanism</th>
            <th>{escape(surface["candidate_label"])}</th>
            <th>{escape(surface["hit_label"])}</th>
            <th>Precision lower bound</th>
            <th>Recall</th>
            <th>F0.5</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <div id="empty-state" class="empty" hidden>No rules match this filter.</div>
    </div>
    <footer class="footnote">
      <div>Sorted by precision. Click a rule name for its complete definition.</div>
      <span>Therapeutic Target Database-exclusive labels remain blind.</span>
    </footer>
  </section>
</main>
"""
    return _html_page(surface["title"], body, TABLE_SCRIPT)


def _render_surface_memberships(rule: dict[str, Any]) -> str:
    memberships = _surface_memberships(rule)
    if not memberships:
        return '<p class="empty">This rule is not on a current Pareto surface.</p>'
    links = []
    for slug in memberships:
        surface = SURFACES[slug]
        precision = rule.get("metrics", {}).get(surface["precision_metric"])
        links.append(
            f"""<a class="surface-chip" href="{surface_path(slug)}">
  <strong>{escape(surface["short_title"])}</strong>
  <span>{_format_percent(precision)} precision →</span>
</a>"""
        )
    return '<div class="surface-list">' + "".join(links) + "</div>"


def _definition_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return escape(str(value))


def _render_rule_description(rule: dict[str, Any]) -> str:
    description = rule.get("description")
    hypothesis = str(rule.get("hypothesis", "No hypothesis recorded."))
    interpretation = str(description or hypothesis)
    criteria = rule.get("criteria") or []
    criteria_block = ""
    if criteria:
        items = "".join(f"<li>{escape(str(item))}</li>" for item in criteria)
        criteria_block = f"""
          <span class="section-label" style="margin-top: 22px">Required graph evidence</span>
          <ol class="criteria-list">{items}</ol>"""
    shorthand = str(rule.get("body", "No mining shorthand recorded."))
    return f"""
          <span class="section-label">Interpretation</span>
          <p>{escape(interpretation)}</p>
          {criteria_block}
          <span class="section-label" style="margin-top: 22px">Mechanism assessment</span>
          <p>{escape(str(rule.get("mechanism_rationale", "No rationale recorded.")))}</p>
          <details class="provenance">
            <summary>Mining provenance</summary>
            <code class="rule-shorthand">{escape(shorthand)}</code>
          </details>
"""


def render_rule_page(library: dict[str, Any], rule_id: str) -> str:
    rules = {
        rule["id"]: rule
        for rule in library.get("results", [])
    }
    rule = rules.get(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Unknown rule")

    memberships = _surface_memberships(rule)
    back_slug = memberships[0] if memberships else "visible"
    counts = rule.get("counts", {})
    metrics = rule.get("metrics", {})
    parent_id = rule.get("parent_rule")
    parent_value = (
        f'<a href="{rule_path(parent_id)}">{escape(parent_id)}</a>'
        if parent_id in rules
        else _definition_value(parent_id)
    )
    treatment_label = (
        "Uses treatment edges"
        if rule.get("uses_treatment_edges")
        else "Treatment-free"
    )
    body = f"""
<main class="shell">
  <a class="back-link" href="{surface_path(back_slug)}">← Back to Pareto surface</a>
  <header class="detail-top">
    <div class="detail-title">
      <p class="eyebrow">Executable treats rule</p>
      <h1>{escape(rule["name"])}</h1>
      <p class="detail-id">{escape(rule["id"])}</p>
      <div class="badge-row">
        <span class="badge {escape(rule["mechanism_score"])}">{escape(rule["mechanism_score"])} mechanism</span>
        <span class="badge neutral">{escape(treatment_label)}</span>
        <span class="badge neutral">{escape(str(rule.get("library_status", "unknown")))}</span>
        <span class="badge neutral">TRAPI {escape(str(rule.get("trapi_expressibility", "unknown")))}</span>
      </div>
    </div>
    <div class="graph-stamp">
      <strong>Iteration {escape(str(rule.get("iteration", "—")))}</strong>
      <span>{len(memberships)} current surface membership(s)</span>
    </div>
  </header>

  <div class="detail-grid">
    <div class="stack">
      <section class="card">
        <div class="card-head"><h2>What this rule says</h2></div>
        <div class="card-body">
          {_render_rule_description(rule)}
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <h2>Executable Cypher</h2>
          <button class="copy-button" type="button" onclick="copyCypher(this)">Copy query</button>
        </div>
        <pre><code id="rule-cypher">{escape(str(rule.get("cypher", "")))}</code></pre>
      </section>

      <section class="card">
        <div class="card-head"><h2>TRAPI expression</h2></div>
        <div class="card-body">
          <p>{escape(str(rule.get("trapi_notes", "No TRAPI notes recorded.")))}</p>
        </div>
      </section>
    </div>

    <aside class="stack">
      <section class="card">
        <div class="card-head"><h2>Visible scores</h2></div>
        <div class="score-grid">
          <div class="score">
            <span class="section-label">Predictions</span>
            <strong>{_format_integer(counts.get("candidate_pairs"))}</strong>
            <span>all returned pairs</span>
          </div>
          <div class="score">
            <span class="section-label">Visible hits</span>
            <strong>{_format_integer(_visible_hits(rule))}</strong>
            <span>{_format_integer(counts.get("training_hits"))} training +
              {_format_integer(counts.get("validation_hits"))} Hub-exclusive</span>
          </div>
          <div class="score">
            <span class="section-label">Precision</span>
            <strong>{_format_percent(metrics.get("visible_target_precision_lower_bound"))}</strong>
            <span>lower bound</span>
          </div>
          <div class="score">
            <span class="section-label">Recall</span>
            <strong>{_format_percent(metrics.get("visible_target_recall"), 4)}</strong>
            <span>of visible labels</span>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head"><h2>Hub-exclusive scores</h2></div>
        <div class="score-grid">
          <div class="score">
            <span class="section-label">Evaluated</span>
            <strong>{_format_integer(_validation_candidates(rule))}</strong>
            <span>non-training predictions</span>
          </div>
          <div class="score">
            <span class="section-label">Hits</span>
            <strong>{_format_integer(counts.get("validation_hits"))}</strong>
            <span>Hub-exclusive pairs</span>
          </div>
          <div class="score">
            <span class="section-label">Precision</span>
            <strong>{_format_percent(metrics.get("validation_precision_lower_bound"))}</strong>
            <span>lower bound</span>
          </div>
          <div class="score">
            <span class="section-label">Recall</span>
            <strong>{_format_percent(metrics.get("validation_recall"), 4)}</strong>
            <span>of Hub-exclusive labels</span>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head"><h2>Surface membership</h2></div>
        <div class="card-body">{_render_surface_memberships(rule)}</div>
      </section>

      <section class="card">
        <div class="card-head"><h2>Rule record</h2></div>
        <div class="card-body">
          <dl class="definition-list">
            <dt>Parent rule</dt><dd>{parent_value}</dd>
            <dt>Contraindications</dt><dd>{_format_integer(counts.get("contraindicated_pairs"))}</dd>
            <dt>Unresolved or blind</dt><dd>{_format_integer(counts.get("unresolved_or_blind_pairs"))}</dd>
            <dt>TRAPI template</dt><dd>{_definition_value(rule.get("trapi_template"))}</dd>
            <dt>Runtime</dt><dd>{float(rule.get("runtime_seconds", 0.0)):.3f} seconds</dd>
          </dl>
        </div>
      </section>
    </aside>
  </div>
</main>
"""
    return _html_page(rule["name"], body, COPY_SCRIPT)


def install_rule_viewer(
    app: FastAPI,
    library_path: Path = DEFAULT_LIBRARY_PATH,
    descriptions_path: Path = DEFAULT_DESCRIPTIONS_PATH,
) -> None:
    @app.get("/rules", response_class=HTMLResponse, include_in_schema=False)
    def rule_viewer_home() -> HTMLResponse:
        return HTMLResponse(
            render_surface_page(
                load_library(library_path, descriptions_path),
                "visible",
            )
        )

    @app.get(
        "/rules/surface/{surface_slug}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def rule_viewer_surface(surface_slug: str) -> HTMLResponse:
        return HTMLResponse(
            render_surface_page(
                load_library(library_path, descriptions_path),
                surface_slug,
            )
        )

    @app.get(
        "/rules/rule/{rule_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def rule_viewer_rule(rule_id: str) -> HTMLResponse:
        return HTMLResponse(
            render_rule_page(
                load_library(library_path, descriptions_path),
                rule_id,
            )
        )
