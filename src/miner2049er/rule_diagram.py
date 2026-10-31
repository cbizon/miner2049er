"""Presentation of recorded rule patterns, without changing their semantics."""

from __future__ import annotations

import re
from html import escape
from textwrap import wrap
from typing import Any

DIAGRAM_CSS = """
.rule-detail .detail-title h1 { font-size:clamp(1.8rem, 3.3vw, 3.2rem); line-height:1.08; }
.rule-detail .detail-id { font-size:.76rem; overflow-wrap:anywhere; }
.rule-badges { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
.rule-badges span { padding:5px 10px; border:1px solid var(--line); font-size:.78rem; }
.rule-badges .treatment-free { background:#e2efe8; color:#174d38; }
.rule-badges .treatment-using { background:#fff0d8; color:#754919; }
.rule-visual { margin:20px 0; }
.diagram-head { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between;
  gap:12px; padding:18px 22px; border-bottom:1px solid var(--line); }
.diagram-head h2 { font-size:1.6rem; margin:0; }
.diagram-head p { color:var(--muted); font-size:.85rem; margin:6px 0 0; }
.diagram-tools { display:flex; gap:6px; }
.diagram-tools button { border:1px solid var(--line); background:#fffdf8; color:var(--ink);
  font:inherit; padding:7px 12px; cursor:pointer; }
.diagram-scroll { overflow:auto; background:radial-gradient(#cfdbd4 .7px, transparent .7px);
  background-size:18px 18px; }
.rule-diagram { display:block; width:100%; min-width:0; height:auto; margin:auto; }
.diagram-item { cursor:pointer; outline:none; }
.diagram-item .node-box { fill:#fffdf8; stroke:var(--green); stroke-width:2; }
.diagram-item.chemical .node-box { fill:#fbeedb; stroke:#ae6727; }
.diagram-item.disease .node-box { fill:#e4eef3; stroke:#276888; }
.diagram-item .edge-line { stroke:#718681; stroke-width:2; fill:none; }
.diagram-item .edge-hit { stroke:transparent; stroke-width:20; fill:none; }
.diagram-item .edge-label-box { fill:#fffdf8; stroke:#c2cfc7; }
.diagram-item text { fill:var(--ink); font-family:inherit; text-anchor:middle; pointer-events:none; }
.diagram-item .node-title { font-size:17px; font-weight:700; }
.diagram-item .node-category { font-size:11px; fill:#526764; }
.diagram-item .edge-label { font-size:13px; font-weight:600; }
.diagram-item .edge-number { font-size:10px; fill:var(--green); letter-spacing:.04em; }
.diagram-item:hover .node-box, .diagram-item:focus-visible .node-box,
.diagram-item.selected .node-box, .diagram-item:hover .edge-label-box,
.diagram-item:focus-visible .edge-label-box, .diagram-item.selected .edge-label-box {
  stroke:#c46c20; stroke-width:3; }
.diagram-item.selected .edge-line { stroke:#c46c20; stroke-width:3; }
.diagram-note-link { cursor:pointer; }
.diagram-note-link rect { fill:#fff0d4; stroke:#a56420; }
.diagram-note-link text { fill:#754919; text-anchor:middle; font-family:inherit;
  font-size:12px; font-weight:700; pointer-events:none; }
.diagram-note-link:hover rect, .diagram-note-link:focus-visible rect {
  fill:#ffe0a3; stroke:var(--ink); stroke-width:2; }
.diagram-note-link.feature rect { fill:#e8eff0; stroke:#607b7e; }
.diagram-note-link.feature text { fill:#355b61; }
.diagram-notes-band { fill:#fff9ed; stroke:#d5b47d; stroke-dasharray:4 3; }
.diagram-notes-label { fill:#785222; font-family:inherit; font-size:11px; font-weight:700; }
.diagram-caption { margin:0; padding:10px 22px; font-size:.79rem; color:var(--muted);
  border-top:1px solid var(--line); }
.diagram-caption a { color:#785222; font-weight:700; }
.diagram-inspector { border-top:1px solid var(--line); padding:16px 22px; background:#f0f5ef; }
.diagram-inspector h3 { margin:0 0 8px; font-size:1.25rem; }
.diagram-inspector p { font-size:.87rem; line-height:1.55; margin:7px 0; overflow-wrap:anywhere; }
.diagram-inspector .inspection-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px 26px; }
.diagram-inspector [hidden] { display:none; }
.diagram-inspector details { margin-top:10px; font-size:.85rem; }
.diagram-inspector summary { cursor:pointer; font-weight:600; }
.diagram-inspector code { overflow-wrap:anywhere; }
.rule-conditions { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:10px;
  padding:0; margin:0; list-style:none; }
.rule-conditions li { border-left:3px solid var(--amber); padding:10px 14px;
  background:#fbf4e8; font-size:.91rem; line-height:1.5; overflow-wrap:anywhere; }
.rule-conditions strong { display:block; font-size:.72rem; text-transform:uppercase;
  color:#785222; letter-spacing:.06em; margin-bottom:5px; }
.constraint-legend { padding:20px 22px; border-top:1px solid var(--line); }
.constraint-legend h3 { margin:0 0 8px; font-size:1.5rem; }
.constraint-legend > p { color:var(--muted); font-size:.84rem; line-height:1.5; }
.constraint-legend .legend-group { margin:18px 0 10px; }
.legend-entry { scroll-margin-top:22px; }
.legend-entry:target, .legend-entry:focus { outline:2px solid #a56420; outline-offset:3px; }
.legend-key { display:inline-block; padding:2px 7px; margin-right:7px; color:#754919;
  background:#fff0d4; border:1px solid #cda263; font-size:.78rem; font-weight:800; }
.legend-entry details { margin-top:9px; }
.legend-entry summary { cursor:pointer; }
.legend-entry p { margin:8px 0; line-height:1.5; overflow-wrap:anywhere; }
details.legend-entry { padding:12px 14px; margin:8px 0; border:1px solid var(--line);
  background:#fffdf8; font-size:.86rem; }
details.legend-entry > summary { font-weight:600; line-height:1.6; }
.legend-fields { display:grid; grid-template-columns:minmax(125px, 180px) minmax(0, 1fr);
  gap:8px 18px; margin:16px 0 8px; }
.legend-fields dt { font-weight:700; }
.legend-fields dd { margin:0; overflow-wrap:anywhere; }
.legend-back { display:inline-block; margin-top:8px; color:var(--green); font-size:.78rem; }
.rule-conclusion { display:flex; flex-wrap:wrap; gap:10px 22px; padding:16px 22px;
  border-top:1px dashed #9eaf9c; background:#f5f6ef; align-items:center; }
.rule-conclusion strong { font-family:"Iowan Old Style", Palatino, serif; font-size:1.3rem; }
.rule-conclusion span { font-size:.84rem; color:var(--muted); }
.rule-scores { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:1px;
  background:var(--line); border:1px solid var(--line); margin:18px 0; }
.rule-score { padding:13px 18px; background:#fffdf8; }
.rule-score strong { display:block; font-family:"Iowan Old Style", Palatino, serif; font-size:1.8rem; }
.rule-score span { display:block; color:var(--muted); font-size:.75rem; }
.rule-fold { margin:14px 0; border:1px solid var(--line); background:var(--panel); }
.rule-fold > summary { padding:16px 20px; cursor:pointer; font-weight:700; }
.rule-fold > .card-body { border-top:1px solid var(--line); }
.rule-fold pre { max-height:32rem; white-space:pre-wrap; overflow-wrap:anywhere; }
.rule-detail .detail-grid { align-items:start; }
.rule-detail .stack { align-content:start; }
@media (max-width:720px) {
  .rule-conditions, .diagram-inspector .inspection-grid, .legend-fields { grid-template-columns:1fr; }
  .rule-scores { grid-template-columns:repeat(2, minmax(0, 1fr)); }
  .diagram-head { padding:16px; }
  .rule-diagram { min-width:var(--graph-width); }
}
@media (prefers-reduced-motion:reduce) {
  .rule-detail *, .rule-detail *::before { animation:none !important; transition:none !important; }
}
"""


def _words(value: str) -> str:
    value = value.removeprefix("biolink:").removeprefix("infores:")
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value).replace("_", " ").replace("-", " ")


def _value(value: Any) -> str:
    if isinstance(value, list):
        return " / ".join(_value(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{_words(key)}: {_value(item)}" for key, item in value.items())
    return _words(str(value))


def _edge_label(edge: dict[str, Any]) -> str:
    predicates = edge["predicates"]
    if predicates == ["biolink:treats_or_applied_or_studied_to_treat"]:
        label = "Treatment-oriented evidence"
    else:
        label = " / ".join(_words(predicate) for predicate in predicates)
    direction = edge.get("qualifiers", {}).get("object_direction_qualifier")
    if direction is not None:
        label += f" ({_value(direction)})"
    return label


def _edge_note_kinds(edge: dict[str, Any]) -> list[str]:
    kinds = []
    if edge.get("qualifiers"):
        kinds.append("qualifiers")
    if edge.get("source_constraints"):
        kinds.append("sources")
    expansion = edge["predicate_expansion"]
    if expansion["excluded_predicates"]:
        kinds.append("exclusions")
    if set(expansion["expanded_predicates"]) != set(edge["predicates"]):
        kinds.append("predicate scope")
    return kinds


def _note_link(
    key: str, target: str, label: str, x: float, y: float, *,
    feature: bool = False, edge_index: int | None = None,
) -> str:
    width = 18 if key == "*" else max(40, 12 + 8 * len(key))
    height = 18 if key == "*" else 24
    edge_attribute = f' data-note-edge="edge-{edge_index}"' if edge_index is not None else ""
    return f"""<a class="diagram-note-link{" feature" if feature else ""}"
id="marker-{target}" href="#{target}" data-note-target="{target}"{edge_attribute}
aria-label="{escape(label)}">
<title>{escape(label)}</title>
<rect x="{x:g}" y="{y:g}" width="{width}" height="{height}" rx="5"/>
<text x="{x + width / 2:g}" y="{y + height - 7:g}">{escape(key)}</text></a>"""


def _legend_fields(fields: list[tuple[str, str]]) -> str:
    return '<dl class="legend-fields">' + "".join(
        f"<dt>{escape(label)}</dt><dd>{escape(value)}</dd>"
        for label, value in fields
    ) + "</dl>"


def _constraint_legend(rule: dict[str, Any]) -> str:
    pattern = rule["graph_pattern"]
    conditions = []
    for index, condition in enumerate(pattern["constraints"]):
        target = f"rule-condition-{index + 1}"
        explanation = (
            f'<details><summary>Why this condition</summary>'
            f'<p>{escape(condition["explanation"])}</p></details>'
            if condition["explanation"] != condition["expression"] else ""
        )
        conditions.append(f"""<li class="legend-entry" id="{target}" tabindex="-1">
<strong><span class="legend-key">C{index + 1}</span>
{escape(_words(condition["id"]))} &middot; {escape(_words(condition["kind"]))}</strong>
{escape(condition["expression"])}{explanation}
<a class="legend-back" href="#marker-{target}">Back to graph marker</a></li>""")
    relationships = []
    for index, edge in enumerate(pattern["edges"]):
        kinds = _edge_note_kinds(edge)
        if not kinds:
            continue
        fields = [
            (_words(key).title(), _value(value))
            for key, value in edge.get("qualifiers", {}).items()
        ]
        if edge.get("source_constraints"):
            fields.append(("Recorded source constraints", ", ".join(edge["source_constraints"])))
        expansion = edge["predicate_expansion"]
        if "predicate scope" in kinds or "exclusions" in kinds:
            fields.extend([
                ("Authored predicates", ", ".join(edge["predicates"])),
                ("Effective predicate count", str(len(expansion["expanded_predicates"]))),
            ])
        if expansion["excluded_predicates"]:
            fields.extend([
                ("Excluded predicates", ", ".join(expansion["excluded_predicates"])),
                ("Exclusion rationale", expansion["exclusion_rationale"] or "Not recorded."),
            ])
        target = f"rule-relationship-{index + 1}"
        relationships.append(f"""<details class="legend-entry" id="{target}" tabindex="-1">
<summary><span class="legend-key">R{index + 1}*</span>
Relationship {index + 1}: {escape(_edge_label(edge))} &middot; {escape(", ".join(kinds))}</summary>
{_legend_fields(fields)}
<details><summary>Full relationship definition and effective predicates</summary>
<p>{escape(edge["explanation"])}</p>
<p>{escape(", ".join(expansion["expanded_predicates"]))}</p></details>
<a class="legend-back" href="#marker-{target}">Back to graph marker</a></details>""")
    features = []
    for index, feature in enumerate(rule["derived_features"]):
        fields = [("Definition", feature["definition"]), ("Inputs", "; ".join(feature["inputs"]))]
        if feature.get("formula"):
            fields.append(("Formula", feature["formula"]))
        fields.extend([
            ("Construction", feature["construction"]),
            ("Interpretation", feature["interpretation"]),
        ])
        if feature["neo4j_artifact_id"]:
            fields.append(("Neo4j artifact", feature["neo4j_artifact_id"]))
        target = f"rule-feature-{index + 1}"
        features.append(f"""<details class="legend-entry" id="{target}" tabindex="-1">
<summary><span class="legend-key">F{index + 1}</span>{escape(feature["name"])}</summary>
{_legend_fields(fields)}
<a class="legend-back" href="#marker-{target}">Back to graph marker</a></details>""")
    if not (conditions or relationships or features):
        return ""
    return (
        '<section class="constraint-legend" id="rule-legend" aria-label="Properties and constraints">'
        "<h3>Properties &amp; constraints</h3>"
        "<p>The markers below describe recorded conditions, not additional evidence. "
        "Whole-rule conditions are not assigned to individual nodes or arrows because "
        "the saved schema does not specify those attachments.</p>"
        + (
            '<p class="eyebrow legend-group">Also required: whole-rule conditions</p>'
            f'<ul class="rule-conditions">{"".join(conditions)}</ul>' if conditions else ""
        )
        + (
            '<p class="eyebrow legend-group">Starred relationship details</p>'
            + "".join(relationships) if relationships else ""
        )
        + (
            '<p class="eyebrow legend-group">Derived features used by this rule</p>'
            + "".join(features) if features else ""
        )
        + "</section>"
    )


def _node_order(pattern: dict[str, Any]) -> list[str]:
    nodes = [node["id"] for node in pattern["nodes"]]
    if len(nodes) > 8:
        return nodes
    adjacent: dict[str, list[str]] = {node: [] for node in nodes}
    for edge in pattern["edges"]:
        subject, object_ = edge["subject"], edge["object"]
        adjacent[subject].append(object_)
        adjacent[object_].append(subject)
    best = [nodes[0], nodes[1]]

    # A bounded path search improves small-rule layouts; all remaining nodes
    # are still drawn. Layout never changes arrow direction or rule membership.
    def visit(path: list[str]) -> None:
        nonlocal best
        if path[-1] == nodes[1]:
            if len(path) > len(best):
                best = path
            return
        if len(path) >= 8:
            return
        for neighbor in dict.fromkeys(adjacent[path[-1]]):
            if neighbor not in path:
                visit([*path, neighbor])

    visit([nodes[0]])
    return [*best[:-1], *(node for node in nodes if node not in best), best[-1]]


def _text_lines(text: str, x: float, y: float, css: str, width: int = 24) -> str:
    lines = wrap(text, width=width) or [""]
    return (
        f'<text class="{css}" x="{x:g}" y="{y:g}">'
        + "".join(
            f'<tspan x="{x:g}" dy="{0 if i == 0 else 16}">{escape(line)}</tspan>'
            for i, line in enumerate(lines)
        )
        + "</text>"
    )


def _edge_inspector(edge: dict[str, Any], index: int) -> str:
    subject, object_ = edge["subject"], edge["object"]
    if edge["direction"] == "reverse":
        subject, object_ = object_, subject
    arrow = "&harr;" if edge["direction"] == "either" else "&rarr;"
    qualifiers = "".join(
        f"<p><strong>{escape(_words(key).title())}:</strong> {escape(_value(value))}</p>"
        for key, value in edge.get("qualifiers", {}).items()
    ) or "<p>No qualifiers recorded.</p>"
    sources = ", ".join(edge.get("source_constraints", [])) or "No edge-level source restriction."
    expansion = edge["predicate_expansion"]
    excluded = ", ".join(expansion["excluded_predicates"]) or "None"
    expanded = expansion["expanded_predicates"]
    return f"""<section data-inspection="edge-{index}" hidden>
<h3>Relationship {index + 1}: {escape(_edge_label(edge))}</h3>
<div class="inspection-grid"><div>
<p><strong>Pattern endpoints:</strong> {escape(subject)} {arrow} {escape(object_)}
&middot; <strong>Direction:</strong> {escape(edge["direction"])}</p>
<p><strong>Authored predicates:</strong> {escape(", ".join(edge["predicates"]))}</p>
<p><strong>Recorded source constraints:</strong> {escape(sources)}</p>
</div><div>{qualifiers}
<p><strong>Effective predicates:</strong> {len(expanded):,} &middot;
<strong>Excluded:</strong> {len(expansion["excluded_predicates"]):,}</p></div></div>
<details><summary>Full relationship definition and predicate expansion</summary>
<p>{escape(edge["explanation"])}</p>
<p><strong>Effective predicates:</strong> {escape(", ".join(expanded))}</p>
<p><strong>Excluded predicates:</strong> {escape(excluded)}</p>
<p>{escape(expansion["exclusion_rationale"] or "")}</p>
</details></section>"""


def render_rule_diagram(rule: dict[str, Any]) -> str:
    pattern = rule["graph_pattern"]
    order = _node_order(pattern)
    positions = {node: 110 + i * 260 for i, node in enumerate(order)}
    width = 220 + (len(order) - 1) * 260
    whole_rule_notes = [
        (f"C{i + 1}", f"rule-condition-{i + 1}",
         f"Condition C{i + 1}: {condition['expression']}", False)
        for i, condition in enumerate(pattern["constraints"])
    ] + [
        (f"F{i + 1}", f"rule-feature-{i + 1}",
         f"Derived feature F{i + 1}: {feature['name']}", True)
        for i, feature in enumerate(rule["derived_features"])
    ]
    note_columns = max(1, (width - 190) // 52)
    note_rows = (len(whole_rule_notes) + note_columns - 1) // note_columns
    notes_height = 32 + note_rows * 34 if whole_rule_notes else 0
    note_band = ""
    if whole_rule_notes:
        note_band = (
            f'<rect class="diagram-notes-band" x="16" y="12" width="{width - 32}" '
            f'height="{notes_height - 16}" rx="6"/>'
            '<text class="diagram-notes-label" x="30" y="40">WHOLE-RULE NOTES</text>'
            + "".join(
                _note_link(key, target, label,
                           172 + (i % note_columns) * 52,
                           24 + (i // note_columns) * 34, feature=feature)
                for i, (key, target, label, feature) in enumerate(whole_rule_notes)
            )
        )
    lanes: dict[tuple[int, int], list[tuple[float, float]]] = {}
    routes = []
    for index, edge in sorted(
        enumerate(pattern["edges"]),
        key=lambda item: abs(positions[item[1]["subject"]] - positions[item[1]["object"]]),
    ):
        xs, xt = positions[edge["subject"]], positions[edge["object"]]
        if edge["direction"] == "reverse":
            xs, xt = xt, xs
        if xs == xt:
            xs, xt = xs - 32, xt + 32
        label = _edge_label(edge)
        label_lines = wrap(label, width=24)
        label_height = 30 + 16 * len(label_lines)
        label_width = min(224, max(150, 7 * max(map(len, label_lines)) + 24))
        midpoint = (xs + xt) / 2
        interval = (
            min(min(xs, xt) + 30, midpoint - label_width / 2 - 8),
            max(max(xs, xt) - 30, midpoint + label_width / 2 + 8),
        )
        lane = 0
        while True:
            found = False
            for sign in (-1, 1):
                occupied = lanes.get((sign, lane), [])
                if all(interval[1] < left or interval[0] > right for left, right in occupied):
                    lanes.setdefault((sign, lane), []).append(interval)
                    found = True
                    break
            if found:
                break
            lane += 1
        routes.append((index, edge, xs, xt, sign, lane, label, label_width, label_height))
    spacing = max((route[-1] for route in routes), default=60) + 28
    top = max((lane + 1 for sign, lane in lanes if sign == -1), default=0)
    bottom = max((lane + 1 for sign, lane in lanes if sign == 1), default=0)
    baseline = notes_height + 80 + top * spacing
    height = baseline + 80 + bottom * spacing
    edges = []
    markers = []
    for index, edge, xs, xt, sign, lane, label, label_width, label_height in routes:
        endpoint_y = baseline + sign * 49
        label_y = baseline + sign * (80 + lane * spacing)
        control_y = (label_y - 0.25 * endpoint_y) / 0.75
        path = (
            f"M {xs:g} {endpoint_y:g} C {xs:g} {control_y:g} "
            f"{xt:g} {control_y:g} {xt:g} {endpoint_y:g}"
        )
        start_marker = ' marker-start="url(#rule-arrow-start)"' if edge["direction"] == "either" else ""
        midpoint = (xs + xt) / 2
        label_top = label_y - label_height / 2
        edges.append(f"""<g class="diagram-item" role="button" tabindex="0" aria-pressed="false"
aria-label="Relationship {index + 1}: {escape(edge["subject"])} to {escape(edge["object"])}: {escape(label)}; {escape(edge["direction"])}"
data-inspect="edge-{index}">
<path class="edge-line" d="{path}" marker-end="url(#rule-arrow)"{start_marker}/>
<path class="edge-hit" d="{path}"/>
<rect class="edge-label-box" x="{midpoint - label_width / 2:g}" y="{label_top:g}"
width="{label_width:g}" height="{label_height:g}" rx="6"/>
<text class="edge-number" x="{midpoint:g}" y="{label_top + 14:g}">RELATIONSHIP {index + 1}</text>
{_text_lines(label, midpoint, label_top + 31, "edge-label")}
</g>""")
        kinds = _edge_note_kinds(edge)
        if kinds:
            markers.append(_note_link(
                "*", f"rule-relationship-{index + 1}",
                f"Relationship {index + 1} properties and constraints: {', '.join(kinds)}",
                midpoint + label_width / 2 - 20, label_top + 3, edge_index=index,
            ))
    nodes = []
    inspectors = []
    for index, node in enumerate(pattern["nodes"]):
        x = positions[node["id"]]
        category = " / ".join(_words(c) for c in node["categories"])
        style = (
            "chemical" if any(c in {"biolink:Drug", "biolink:ChemicalEntity"} for c in node["categories"])
            else ("disease" if "biolink:Disease" in node["categories"] else "entity")
        )
        label = _words(node["id"]).title()
        nodes.append(f"""<g class="diagram-item {style}" role="button" tabindex="0"
aria-pressed="false" aria-label="{escape(label)}: {escape(node["role"])}"
data-inspect="node-{index}">
<rect class="node-box" x="{x - 85:g}" y="{baseline - 48:g}" width="170" height="96" rx="10"/>
{_text_lines(label, x, baseline - 16, "node-title", 18)}
{_text_lines(category, x, baseline + 20, "node-category", 27)}
</g>""")
        inspectors.append(f"""<section data-inspection="node-{index}" hidden>
<h3>{escape(label)}</h3>
<p><strong>Role:</strong> {escape(node["role"])}</p>
<p>{escape(node["explanation"])}</p>
<p><strong>Categories:</strong> {escape(", ".join(node["categories"]))}
&middot; <strong>Pattern ID:</strong> {escape(node["id"])}</p></section>""")
    inspectors.extend(_edge_inspector(edge, i) for i, edge in enumerate(pattern["edges"]))
    legend = _constraint_legend(rule)
    legend_caption = (
        '<p class="diagram-caption"><a href="#rule-legend">Properties &amp; constraints legend</a>: '
        '<strong>*</strong> = extra relationship details; '
        '<strong>C</strong> = whole-rule condition; <strong>F</strong> = derived feature. '
        'Select a marker to jump to its details.</p>'
        if legend else ""
    )
    return f"""<section class="card rule-visual" aria-label="Visual rule">
<div class="diagram-head"><div><p class="eyebrow">If this pattern matches</p>
<h2>Required graph evidence</h2>
<p>{len(nodes)} entities &middot; {len(edges)} relationships &middot;
{len(pattern["constraints"])} additional {"condition" if len(pattern["constraints"]) == 1 else "conditions"}.
Select a node or relationship to inspect it.</p>
</div><div class="diagram-tools" aria-label="Graph zoom">
<button type="button" data-zoom="out" aria-label="Zoom out">&minus;</button>
<button type="button" data-zoom="fit">Fit</button>
<button type="button" data-zoom="in" aria-label="Zoom in">+</button></div></div>
<div class="diagram-scroll" tabindex="0" aria-label="Rule graph; scroll horizontally on small screens">
<svg class="rule-diagram" style="max-width:{width}px;--graph-width:{width}px"
viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg"
role="group" aria-labelledby="rule-graph-title rule-graph-description">
<title id="rule-graph-title">{escape(rule["name"])}</title>
<desc id="rule-graph-description">Recorded rule pattern. Arrows show relationship direction,
not necessarily causation. Nodes and numbered relationships can be selected for details.</desc>
<defs><marker id="rule-arrow" viewBox="0 0 10 10" refX="9" refY="5"
markerWidth="7" markerHeight="7" orient="auto"><path d="M 0 0 L 10 5 L 0 10 Z" fill="#718681"/></marker>
<marker id="rule-arrow-start" viewBox="0 0 10 10" refX="1" refY="5"
markerWidth="7" markerHeight="7" orient="auto"><path d="M 10 0 L 0 5 L 10 10 Z" fill="#718681"/></marker></defs>
{note_band}{''.join(edges)}{''.join(nodes)}{''.join(markers)}</svg></div>
<p class="diagram-caption">Arrows indicate recorded relationships, not proof of causation.
Arrowheads at both ends mean either direction is allowed. Predicate exclusions, sources,
and qualifiers are available by selecting a relationship.</p>
{legend_caption}
<div class="diagram-inspector" aria-live="polite">
<p data-inspection="intro">Select any node or numbered relationship above for its definition,
source restrictions, and qualifiers.</p>{''.join(inspectors)}</div>
{legend}
<div class="rule-conclusion"><p class="eyebrow">Then predict</p>
<strong>Chemical &rarr; treats &rarr; disease</strong>
<span>A rule prediction, not a validated therapeutic mechanism.</span></div>
</section>
<script>
(() => {{
  const root = document.querySelector(".rule-visual");
  const items = root.querySelectorAll("[data-inspect]");
  const select = (item) => {{
    items.forEach(other => {{
      const active = other === item;
      other.classList.toggle("selected", active);
      other.setAttribute("aria-pressed", String(active));
    }});
    root.querySelectorAll("[data-inspection]").forEach(panel => {{
      panel.hidden = panel.dataset.inspection !== (item?.dataset.inspect ?? "intro");
    }});
  }};
  items.forEach(item => {{
    item.addEventListener("click", () => select(item));
    item.addEventListener("keydown", event => {{
      if (event.key === "Enter" || event.key === " ") {{
        event.preventDefault();
        select(item);
      }}
    }});
  }});
  const openNote = (id) => {{
    const note = document.getElementById(id);
    if (!note || !root.contains(note) || !note.classList.contains("legend-entry")) return;
    if (note.tagName === "DETAILS") note.open = true;
    note.focus({{preventScroll: true}});
  }};
  root.querySelectorAll("[data-note-target]").forEach(link => {{
    link.addEventListener("click", () => {{
      if (link.dataset.noteEdge) {{
        const edge = Array.from(items).find(item => item.dataset.inspect === link.dataset.noteEdge);
        if (edge) select(edge);
      }} else {{
        select(null);
      }}
      openNote(link.dataset.noteTarget);
    }});
  }});
  openNote(location.hash.slice(1));
  const svg = root.querySelector("svg");
  const scroll = root.querySelector(".diagram-scroll");
  root.querySelectorAll("[data-zoom]").forEach(button => {{
    button.addEventListener("click", () => {{
      const fitWidth = Math.min(scroll.clientWidth, {width});
      let zoom = svg.getBoundingClientRect().width / fitWidth;
      zoom = button.dataset.zoom === "fit" ? 1
        : Math.max(1, Math.min(Math.max(4, {width} / fitWidth * 2),
            zoom + (button.dataset.zoom === "in" ? .25 : -.25)));
      svg.style.minWidth = "0";
      svg.style.maxWidth = button.dataset.zoom === "fit" ? "{width}px" : "none";
      svg.style.width = button.dataset.zoom === "fit" ? "100%" : `${{fitWidth * zoom}}px`;
    }});
  }});
}})();
</script>"""
