from copy import deepcopy
from html import escape
from xml.etree import ElementTree

import pytest

from miner2049er.benchmark_dashboard import render_rule
from miner2049er.rule_diagram import _node_order, render_rule_diagram
from tests.benchmark_examples import benchmark_rule


def svg_root(html):
    svg = html[html.index("<svg "):html.index("</svg>") + len("</svg>")]
    return ElementTree.fromstring(svg)


def test_diagram_renders_every_node_and_parallel_edge_with_correct_directions():
    rule = benchmark_rule()
    edge = rule["graph_pattern"]["edges"][0]
    reverse = {**deepcopy(edge), "id": "reverse", "direction": "reverse"}
    either = {**deepcopy(edge), "id": "either", "direction": "either"}
    rule["graph_pattern"]["edges"].extend([reverse, either])
    root = svg_root(render_rule_diagram(rule))
    ns = {"s": "http://www.w3.org/2000/svg"}
    groups = {g.attrib["data-inspect"]: g for g in root.findall("s:g", ns)}
    assert set(groups) == {"node-0", "node-1", "edge-0", "edge-1", "edge-2"}
    paths = [groups[f"edge-{i}"].find('s:path[@class="edge-line"]', ns) for i in range(3)]
    assert all(p.attrib["marker-end"] == "url(#rule-arrow)" for p in paths)
    assert "marker-start" not in paths[0].attrib
    assert "marker-start" not in paths[1].attrib
    assert paths[2].attrib["marker-start"] == "url(#rule-arrow-start)"
    assert paths[0].attrib["d"].startswith("M 110 ")
    assert paths[1].attrib["d"].startswith("M 370 ")
    assert len({p.attrib["d"] for p in paths}) == 3
    assert all(g.attrib["role"] == "button" and g.attrib["tabindex"] == "0" for g in groups.values())


def test_diagram_preserves_qualifiers_sources_constraints_and_escapes_recorded_text():
    rule = benchmark_rule()
    rule["name"] = 'Rule <script>alert("no")</script>'
    edge = rule["graph_pattern"]["edges"][0]
    edge["qualifiers"] = {
        "qualified_predicate": "biolink:causes",
        "object_direction_qualifier": ["increased", "decreased"],
        "object_aspect_qualifier": "activity",
    }
    edge["source_constraints"] = ["infores:chembl", 'infores:source"><script>']
    edge["explanation"] = "A < B & C > D"
    edge["predicate_expansion"]["excluded_predicates"] = ["biolink:treats"]
    rule["graph_pattern"]["constraints"] = [{
        "id": "distinct-targets",
        "kind": "cardinality",
        "expression": "At least 2 targets from the same parent; x < y.",
        "explanation": "Do not pool across parents.",
    }]
    html = render_rule_diagram(rule)
    svg_root(html)
    assert escape(rule["name"]) in html
    assert rule["name"] not in html
    assert "increased / decreased" in html
    assert "Qualified Predicate:" in html
    assert "Object Aspect Qualifier:" in html
    assert "infores:chembl" in html
    assert escape(edge["source_constraints"][1]) in html
    assert "A &lt; B &amp; C &gt; D" in html
    assert "biolink:treats" in html
    assert escape(rule["graph_pattern"]["constraints"][0]["expression"]) in html
    assert "Also required" in html
    assert "not a validated therapeutic mechanism" in html


def test_branched_and_disconnected_patterns_keep_every_node_and_edge():
    rule = benchmark_rule()
    pattern = rule["graph_pattern"]
    for node_id in ("regulator", "gene", "family", "isolated"):
        pattern["nodes"].append({
            "id": node_id, "role": node_id, "categories": ["biolink:Gene"], "explanation": node_id,
        })
    edge = pattern["edges"][0]
    pattern["edges"] += [
        {**deepcopy(edge), "id": str(i), "subject": s, "object": o}
        for i, (s, o) in enumerate([
            ("chemical", "regulator"), ("regulator", "family"),
            ("gene", "family"), ("gene", "disease"), ("regulator", "disease"),
        ])
    ]
    order = _node_order(pattern)
    assert order[0] == "chemical"
    assert order[-1] == "disease"
    assert set(order) == {node["id"] for node in pattern["nodes"]}
    html = render_rule_diagram(rule)
    svg_root(html)
    assert html.count('data-inspect="node-') == len(pattern["nodes"])
    assert html.count('data-inspect="edge-') == len(pattern["edges"])


def test_rule_detail_leads_with_visual_evidence_and_keeps_full_record_collapsed():
    rule = benchmark_rule()
    rule["plain_language_rule"] = "Long original explanation that must remain accessible."
    run = {
        "manifest": {"run_id": "test-run"},
        "rules": [rule],
        "evaluations": [{
            "rule_id": rule["rule_id"], "partition": "feedback",
            "metrics": {"precision_lower_bound": .25, "recall": .0125, "f0_5": .1},
            "counts": {"known_hits": 5, "eligible_predictions": 20},
        }],
    }
    html = render_rule(run, rule["rule_id"])
    assert html.index('class="rule-diagram"') < html.index(rule["plain_language_rule"])
    assert "25.00%" in html
    assert "1.2500%" in html
    assert "Feedback precision lower bound" in html
    assert "Surface membership compares rules across all rounds." in html
    assert "<summary>Complete recorded rule JSON</summary>" in html
    assert "<summary>Executable Cypher</summary>" in html
    assert '<details class="rule-fold" open' not in html
    assert "This is a test fixture." in html


@pytest.mark.parametrize("note_kind", ["qualifiers", "sources", "exclusions", "predicate scope"])
def test_relationship_markers_link_to_the_correct_legend_entry(note_kind):
    rule = benchmark_rule()
    edge = rule["graph_pattern"]["edges"][0]
    edge["predicate_expansion"]["expanded_predicates"] = list(edge["predicates"])
    if note_kind == "qualifiers":
        edge["qualifiers"] = {"has_property": False}
    elif note_kind == "sources":
        edge["source_constraints"] = ["infores:curated"]
    elif note_kind == "exclusions":
        edge["predicate_expansion"]["excluded_predicates"] = ["biolink:treats"]
        edge["predicate_expansion"]["exclusion_rationale"] = "Never use target treatment labels."
    else:
        edge["predicate_expansion"]["expanded_predicates"].append("biolink:affects")
    # A second unconstrained edge must not inherit the first edge's marker.
    plain = deepcopy(edge)
    plain["id"] = "plain"
    plain.pop("qualifiers", None)
    plain.pop("source_constraints", None)
    plain["predicate_expansion"]["expanded_predicates"] = list(plain["predicates"])
    plain["predicate_expansion"]["excluded_predicates"] = []
    rule["graph_pattern"]["edges"].append(plain)
    before = deepcopy(rule)
    html = render_rule_diagram(rule)
    root = svg_root(html)
    ns = {"s": "http://www.w3.org/2000/svg"}
    markers = root.findall('s:a[@data-note-edge]', ns)
    assert len(markers) == 1
    assert markers[0].attrib["href"] == "#rule-relationship-1"
    assert markers[0].attrib["data-note-edge"] == "edge-0"
    assert note_kind in markers[0].attrib["aria-label"]
    assert '<details class="legend-entry" id="rule-relationship-1"' in html
    assert '<span class="legend-key">R1*</span>' in html
    assert 'id="rule-relationship-2"' not in html
    assert rule == before


def test_whole_rule_conditions_and_features_have_keyed_legends_not_guessed_attachments():
    rule = benchmark_rule()
    rule["graph_pattern"]["constraints"] = [{
        "id": "chemical-property",
        "kind": "property",
        "expression": "chemical.degree < 10",
        "explanation": "The count must be small & source-specific.",
    }]
    rule["derived_features"] = [{
        "name": 'Target count <script>alert("no")</script>',
        "definition": "Distinct target count.",
        "inputs": ["chemical", "gene"],
        "formula": "count(DISTINCT gene.id)",
        "construction": "Deduplicate canonical targets.",
        "interpretation": "Number of targets.",
        "neo4j_artifact_id": None,
    }]
    html = render_rule_diagram(rule)
    root = svg_root(html)
    ns = {"s": "http://www.w3.org/2000/svg"}
    for key, target in [("C1", "rule-condition-1"), ("F1", "rule-feature-1")]:
        marker = root.find(f's:a[@data-note-target="{target}"]', ns)
        assert marker is not None
        assert "data-note-edge" not in marker.attrib
        assert marker.find("s:text", ns).text == key
        assert f'id="{target}"' in html
        assert f'href="#marker-{target}"' in html
    for node in root.findall('s:g[@data-inspect]', ns):
        assert node.find("s:a", ns) is None
    assert "chemical.degree &lt; 10" in html
    assert "The count must be small &amp; source-specific." in html
    assert "count(DISTINCT gene.id)" in html
    assert escape(rule["derived_features"][0]["name"]) in html
    assert rule["derived_features"][0]["name"] not in html
    assert "does not specify those attachments" in html


def test_simple_rule_does_not_show_spurious_markers_or_legend():
    rule = benchmark_rule()
    edge = rule["graph_pattern"]["edges"][0]
    edge["predicates"] = ["biolink:related_to", "biolink:affects"]
    edge["predicate_expansion"]["expanded_predicates"] = list(reversed(edge["predicates"]))
    html = render_rule_diagram(rule)
    root = svg_root(html)
    assert not root.findall("s:a", {"s": "http://www.w3.org/2000/svg"})
    assert 'id="rule-legend"' not in html
    assert 'class="diagram-notes-band"' not in html


def test_note_band_wraps_markers_without_clipping_small_graphs():
    rule = benchmark_rule()
    rule["graph_pattern"]["constraints"] = [
        {"id": f"condition-{i}", "kind": "cardinality",
         "expression": f"At least {i} targets.", "explanation": "Recorded constraint."}
        for i in range(1, 11)
    ]
    root = svg_root(render_rule_diagram(rule))
    ns = {"s": "http://www.w3.org/2000/svg"}
    band = root.find('s:rect[@class="diagram-notes-band"]', ns)
    bx, by, bw, bh = (float(band.attrib[key]) for key in ("x", "y", "width", "height"))
    markers = [a for a in root.findall("s:a", ns) if "data-note-edge" not in a.attrib]
    assert len(markers) == 10
    rows = set()
    for marker in markers:
        box = marker.find("s:rect", ns)
        x, y, w, h = (float(box.attrib[key]) for key in ("x", "y", "width", "height"))
        rows.add(y)
        assert bx <= x and x + w <= bx + bw
        assert by <= y and y + h <= by + bh
    assert len(rows) > 1
