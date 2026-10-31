from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx

from miner2049er.rules import Rule, load_rules
from miner2049er.settings import ROOT


def load_trapi_payload(rule: Rule, rules_path: Path) -> dict[str, Any]:
    if rule.trapi_template is None:
        raise ValueError(f"{rule.id} does not define a TRAPI template")
    template_path = rules_path.parent / rule.trapi_template
    return json.loads(template_path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a rule's positive TRAPI motif in Gandalf")
    parser.add_argument("--rule", required=True)
    parser.add_argument(
        "--rules",
        type=Path,
        default=ROOT / "rules" / "treats-rules.toml",
    )
    parser.add_argument(
        "--gandalf-url",
        default=os.environ.get("GANDALF_URL", "http://localhost:6429"),
    )
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--show-response", action="store_true")
    return parser.parse_args()


def response_summary(rule: Rule, response: dict[str, Any]) -> dict[str, Any]:
    message = response.get("message", {})
    knowledge_graph = message.get("knowledge_graph") or {}
    return {
        "rule": rule.id,
        "template": rule.trapi_template,
        "result_count": len(message.get("results") or []),
        "knowledge_graph_node_count": len(knowledge_graph.get("nodes") or {}),
        "knowledge_graph_edge_count": len(knowledge_graph.get("edges") or {}),
        "log_count": len(response.get("logs") or message.get("logs") or []),
    }


def main() -> None:
    args = parse_args()
    rule = load_rules(args.rules, {args.rule}, include_inactive=True)[0]
    payload = load_trapi_payload(rule, args.rules)
    response = httpx.post(
        f"{args.gandalf_url.rstrip('/')}/query",
        json=payload,
        timeout=args.timeout_seconds,
    )
    if not response.is_success:
        raise RuntimeError(
            f"Gandalf returned HTTP {response.status_code}: {response.text[:1000]}"
        )
    document = response.json()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            document if args.show_response else response_summary(rule, document),
            indent=2,
        )
    )
