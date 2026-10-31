"""Report component-removal comparisons using observed aggregate results only."""

import argparse
import json

from audit import EVALUATIONS, records
from probe import RUN, log_event


PAIRS = [
    ("r4-curated-inhibited-genetic-target-direct", "r4-family-genetic-direct-target-genetics", "add the PANTHER family arm and genetic association of a distinct family-related gene"),
    ("r4-curated-inhibited-genetic-target-direct", "r4-process-curated-target-direct-target-genetics", "add target membership in a genetically associated biological process"),
    ("r4-regulatory-unsigned", "r4-regulatory-net-decrease", "require net-decreasing composed direction"),
    ("r4-regulatory-unsigned", "r4-regulatory-net-increase-control", "require net-increasing composed direction as a biological control"),
    ("r4-regulatory-net-decrease", "r4-regulatory-inhibit-activator", "retain only inhibition of an activating regulator"),
    ("r4-regulatory-net-decrease", "r4-regulatory-activate-inhibitor", "retain only activation of an inhibitory regulator"),
    ("r4-regulatory-net-decrease-no-direct", "r4-regulatory-net-decrease", "add direct drug-disease affects evidence"),
    ("r4-regulatory-net-decrease-no-curation", "r4-regulatory-net-decrease", "require curated target primary-source support"),
    ("r4-regulatory-net-decrease", "r4-regulatory-net-decrease-physical-corroboration", "add physical interaction between regulator and disease gene"),
    ("r4-regulatory-net-decrease", "r4-regulatory-net-decrease-majority", "require a strict majority of distinct downstream gene votes for net decrease"),
    ("r4-regulatory-net-decrease-majority", "r4-regulatory-net-decrease-unopposed", "exclude every net-increasing downstream gene path"),
    ("r4-regulatory-net-decrease", "r4-regulatory-net-decrease-ctd-activity", "require CTD primary support for activity regulation"),
    ("r4-regulatory-net-decrease-ctd-activity", "r4-regulatory-net-decrease-ctd-expression", "replace activity regulation with expression regulation"),
    ("r4-regulatory-net-decrease-expression", "r4-regulatory-net-decrease-ctd-expression", "require CTD primary support for expression regulation"),
    ("r4-regulatory-net-decrease", "r4-regulatory-net-decrease-source-disjoint", "require regulatory and causal evidence from disjoint source arrays"),
    ("r4-regulatory-net-decrease", "r4-regulatory-net-decrease-genetic-disease", "replace the causal disease arm with a genetic association arm"),
    ("r4-regulatory-net-decrease", "r4-regulatory-net-decrease-genetic-corroboration", "add an independent genetic disease arm"),
    ("r4-regulatory-net-decrease-genetic-disease", "r4-regulatory-net-decrease-genetic-corroboration", "add the causal arm back to genetic evidence"),
    ("r4-regulatory-net-decrease-physical-corroboration", "r4-regulatory-net-decrease-independent-physical", "require physical and regulatory evidence from disjoint source arrays"),
    ("r4-production-unsigned", "r4-production-decreased", "require drug inhibition of the disease-produced molecule"),
    ("r4-production-decreased", "r4-production-decreased-causal-loop", "require the produced molecule to cause or contribute to the same disease"),
    ("r4-production-decreased", "r4-production-decreased-direct", "add direct drug-disease evidence"),
    ("r4-production-decreased-causal-loop", "r4-production-decreased-causal-loop-direct", "add direct drug-disease evidence to the causal feedback loop"),
    ("r4-production-decreased", "r4-production-decreased-genetic", "add independent genetic evidence for the produced molecule"),
    ("r4-production-decreased-genetic", "r4-production-decreased-causal-genetic", "add the causal feedback arm to genetic evidence"),
    ("r4-production-decreased-causal-loop", "r4-production-decreased-causal-genetic", "add genetic evidence to the causal feedback arm"),
    ("r4-family-genetic", "r4-family-genetic-direct", "add direct drug-disease evidence"),
    ("r4-family-causal", "r4-family-causal-direct", "add direct drug-disease evidence"),
    ("r4-family-genetic-direct", "r4-family-genetic-direct-small-family", "exclude PANTHER families exceeding the fixed fourteen-member bound"),
    ("r4-family-causal-direct", "r4-family-causal-direct-small-family", "exclude PANTHER families exceeding the fixed fourteen-member bound"),
    ("r4-family-genetic-direct", "r4-family-genetic-direct-target-genetics", "add genetic disease evidence for the drug target as well as the related gene"),
    ("r4-family-genetic-direct", "r4-family-genetic-direct-physical", "add physical interaction between the related genes"),
    ("r4-process-curated-target", "r4-process-curated-target-direct", "add direct drug-disease evidence"),
    ("r4-process-unsigned", "r4-process-unsigned-direct", "add direct drug-disease evidence"),
    ("r4-process-curated-target-direct", "r4-process-curated-target-direct-target-genetics", "add genetic disease evidence for the exact drug target"),
    ("r4-process-curated-target-direct", "r4-process-curated-target-direct-target-causality", "add causal disease evidence for the exact drug target"),
    ("r4-process-curated-target-direct", "r4-process-curated-target-direct-dual-unsigned", "add direct causal drug-process evidence without a direction requirement"),
    ("r4-process-unsigned-direct", "r4-process-curated-target-direct-dual-unsigned", "add curated target membership in the genetically associated process"),
    ("r4-process-curated-target-direct-dual-unsigned", "r4-process-dual-perturbation-direct-direction-only", "require the direct process effect to decrease the process"),
    ("r4-process-curated-target-direct", "r4-process-dual-perturbation-direct-direction-only", "add a direction-only decreased drug-process arm"),
    ("r4-process-decreased-direct-direction-only", "r4-process-dual-perturbation-direct-direction-only", "add the curated inhibited-target process arm"),
    ("r4-process-dual-perturbation-direction-only", "r4-process-dual-perturbation-direct-direction-only", "add direct drug-disease evidence to dual process convergence"),
    ("r4-pathogen-product-physical", "r4-pathogen-product-physical-direct", "add direct drug-disease evidence"),
    ("r4-pathogen-product-decreased", "r4-pathogen-product-decreased-direct", "add direct drug-disease evidence"),
    ("r4-pathogen-product-physical-direct", "r4-pathogen-product-decreased-direct", "replace physical engagement with curated causal inhibition of the organism product"),
    ("r4-pathogen-unsigned", "r4-pathogen-decreased", "add causal qualification, decreased direction, and activity or activity-or-abundance aspect to the drug-organism arm"),
    ("r4-pathogen-unsigned", "r4-pathogen-increased", "add causal qualification, increased direction, and activity or activity-or-abundance aspect to the drug-organism arm"),
    ("r4-pathogen-decreased", "r4-pathogen-increased", "reverse only the qualified drug-organism direction"),
    ("r4-pathogen-unsigned", "r4-pathogen-disruption", "replace the exact affects relation with the distinct disrupts relation"),
    ("r4-substrate-genetic", "r4-substrate-genetic-direct", "add direct drug-disease evidence"),
    ("r4-substrate-causal", "r4-substrate-causal-direct", "add direct drug-disease evidence"),
]
for direction in ("decreased", "increased"):
    for direct in (False, True):
        key = "r4-process-" + direction + ("-direct" if direct else "")
        PAIRS.append((key, key + "-direction-only", "remove the object-aspect requirement while retaining the recorded causal direction"))
        PAIRS.append(("r4-process-unsigned" + ("-direct" if direct else ""), key + "-direction-only", "require the specified recorded process direction without a gene-style aspect restriction"))

for disease_leg in ("causal", "genetic"):
    for direction in ("unsigned", "decreased", "increased"):
        base = "r4-metabolite-" + disease_leg + "-" + direction
        PAIRS.append((base, base + "-direct", "add direct drug-disease evidence to the metabolite-target mechanism"))
    for direct in ("", "-direct"):
        prefix = "r4-metabolite-" + disease_leg + "-"
        PAIRS.append((prefix + "unsigned" + direct, prefix + "decreased" + direct,
                      "require inhibition of the metabolite target"))
        PAIRS.append((prefix + "decreased" + direct, prefix + "increased" + direct,
                      "replace inhibited metabolite action with the opposite-sign control"))
    base = "r4-activity-input-" + disease_leg
    PAIRS.append((base, base + "-direct", "add direct drug-disease evidence to the directed activity-input chain"))
PAIRS.extend([
    ("r4-metabolite-genetic-decreased-direct", "r4-metabolite-concordant-parent-target-direct",
     "require the parent drug to inhibit the same target as its metabolite"),
    ("r4-activity-input-genetic-direct", "r4-activity-input-reverse-control",
     "reverse the stored activity-input direction while retaining the other arms"),
    ("r4-activity-input-genetic-direct", "r4-activity-input-precedes",
     "replace an activity input with temporal precedence"),
    ("r4-activity-input-genetic-direct", "r4-activity-input-two-bridges-direct",
     "insert a second directed activity input and a distinct intermediate gene"),
    ("r4-transfer-pooled-one-direct", "r4-transfer-pooled-two-direct",
     "require two distinct genes pooled across all supported parents"),
    ("r4-transfer-pooled-two-direct", "r4-transfer-same-parent-two-direct",
     "require both genes with one and the same parent rather than pooling across parents"),
    ("r4-transfer-pooled-one-direct", "r4-transfer-same-sign-direct",
     "require matching signed activity effects on the shared target"),
    ("r4-transfer-same-sign-direct", "r4-transfer-opposite-sign-direct",
     "replace matching activity direction with an opposite-sign control"),
    ("r4-transfer-same-parent-two-direct", "r4-transfer-same-parent-two-same-sign-direct",
     "require matching activity direction for the targets shared with the same parent"),
    ("r4-transfer-pooled-one-no-direct", "r4-transfer-pooled-one-direct",
     "add direct candidate-drug disease evidence"),
    ("r4-transfer-same-sign-no-direct", "r4-transfer-same-sign-direct",
     "add direct disease evidence after signed target concordance"),
    ("r4-transfer-pooled-one-direct", "r4-transfer-derived-parent-direct",
     "add a candidate-to-parent chemical derivation arm"),
])
for context in ("", "-genetic-disease", "-genetic-corroboration", "-no-curation"):
    for closure in ("", "-full-closure"):
        suffix = context + closure
        PAIRS.extend([
            ("r4-regulatory-unsigned" + suffix, "r4-regulatory-net-decrease" + suffix,
             "require net decrease under otherwise-identical disease, source, and predicate evidence"),
            ("r4-regulatory-unsigned" + suffix, "r4-regulatory-net-increase-control" + suffix,
             "require net increase as a matched direction control"),
            ("r4-regulatory-net-decrease" + suffix, "r4-regulatory-net-increase-control" + suffix,
             "reverse composed direction under the same disease, source, and predicate definition"),
        ])
for family, suffixes in (
    ("family", ("", "-direct", "-direct-small-family")),
    ("activity-input", ("", "-direct")),
    ("substrate", ("", "-direct")),
    ("metabolite", ("-unsigned", "-decreased", "-increased",
                    "-unsigned-direct", "-decreased-direct", "-increased-direct")),
):
    for suffix in suffixes:
        for closure in ("", "-full-closure"):
            PAIRS.append((
                "r4-" + family + "-genetic" + suffix + closure,
                "r4-" + family + "-causal" + suffix + closure,
                "replace GeneticsKP-filtered genetic disease association with all-source causes-or-contributes evidence; predicate and provenance requirements change jointly",
            ))
for closure in ("", "-full-closure"):
    for baseline, variant, change in (
        ("r4-taxon-target-unsigned", "r4-taxon-target-decreased",
         "require decreased rather than either signed activity direction with identical taxonomic identity and source requirements"),
        ("r4-taxon-target-unsigned", "r4-taxon-target-increased",
         "require increased rather than either signed activity direction as the matched biological control"),
        ("r4-taxon-target-decreased", "r4-taxon-target-increased",
         "reverse only the molecular effect direction under the same taxonomic identity constraint"),
        ("r4-taxon-target-decreased", "r4-taxon-target-decreased-direct",
         "add direct drug-disease affects corroboration to taxon-identified target inhibition"),
        ("r4-taxon-target-decreased", "r4-taxon-target-decreased-product",
         "add an explicit organism-produces-target assertion to the taxonomic identity mechanism"),
        ("r4-pathogen-product-decreased", "r4-taxon-target-decreased-product",
         "add exact raw target-to-organism taxonomic identity to the otherwise-identical organism-product mechanism; target access optimization changes only computation"),
        ("r4-taxon-target-decreased", "r4-taxon-target-decreased-two-targets",
         "require two distinct canonical molecular targets belonging to the same causal organism rather than pooling single targets across organisms"),
    ):
        PAIRS.append((baseline + closure, variant + closure, change))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--partition", choices=["training", "feedback"], default="training")
    args = parser.parse_args()
    candidates = {
        p.stem: json.loads(p.read_text())
        for p in (RUN / "rounds/round-0004/mining/active-candidates").glob("*.json")
    }
    ledger = list(records(RUN / "research-log.jsonl"))
    values = {}
    if args.partition == "training":
        for event in ledger:
            details = event["details"]
            m = details.get("metrics", {})
            if details.get("formulation") == "candidate" and details.get("outcome") in ("completed", "empty"):
                key = details.get("candidate_id", m.get("candidate_id"))
                if not key or (m.get("candidate_id") and m["candidate_id"] != key):
                    raise RuntimeError("Candidate profile identifier is missing or inconsistent")
                values[key] = {
                    "count": m["predictions"], "hits": m["visible_hits"],
                    "eligible": m["eligible_predictions"], "source_sequence": event["sequence"],
                }
    else:
        for evaluation in records(EVALUATIONS):
            if evaluation["partition"] != "feedback":
                continue
            counts = evaluation["counts"]
            values[evaluation["rule_id"]] = {
                "count": counts["eligible_predictions"], "hits": counts["known_hits"],
                "eligible": counts["eligible_predictions"], "scored_at": evaluation.get("scored_at"),
            }
        for event in ledger:
            details = event["details"]
            key = details.get("candidate_id")
            if key in values or not event["summary"].startswith(
                "Visible-label exclusion and feedback duplicate preflight:"
            ):
                continue
            identity = json.loads(details["result_summary"])
            matches = [other for other in identity["identical_already_scored_rules"] if other in values]
            if matches:
                source = matches[0]
                values[key] = {
                    "count": values[source]["count"], "hits": values[source]["hits"],
                    "eligible": values[source]["eligible"],
                    "evaluation_source_rule_id": source,
                    "identical_eligible_set": True,
                    "identity_evidence_sequence": event["sequence"],
                    "eligible_pair_sha256": identity["eligible_pair_sha256"],
                }
    pairs = list(PAIRS)
    pairs.extend(
        (key, key.removesuffix("-full-closure"), "explicitly exclude the recorded predicate descendants")
        for key in candidates if key.endswith("-full-closure")
    )
    done = {
        (e["details"].get("baseline_rule_id"), e["details"].get("variant_rule_id"), e["details"].get("partition"))
        for e in ledger if e["event_type"] == "ablation"
    }
    for baseline, variant, change in pairs:
        if baseline not in values or variant not in values or (baseline, variant, args.partition) in done:
            continue
        a, b = values[baseline], values[variant]
        ap = a["hits"] / a["count"] if a["count"] else 0
        bp = b["hits"] / b["count"] if b["count"] else 0
        retention = b["hits"] / a["hits"] if a["hits"] else None
        decision = (
            "keep_change" if bp >= ap and b["hits"] >= a["hits"] and (bp > ap or b["hits"] > a["hits"])
            else "remove_change" if bp <= ap and b["hits"] <= a["hits"] and (bp < ap or b["hits"] < a["hits"])
            else "inconclusive"
        )
        metrics = {
            "baseline_predictions": a["count"], "variant_predictions": b["count"],
            "baseline_hits": a["hits"], "variant_hits": b["hits"],
            "baseline_precision_lower_bound": ap, "variant_precision_lower_bound": bp,
            "hit_retention_fraction": retention,
            "baseline_eligible": a["eligible"], "variant_eligible": b["eligible"],
        }
        log_event("ablation", args.partition.title() + " component comparison: " + variant, {
            "baseline": candidates[baseline]["name"] + " [" + baseline + "]",
            "variant": candidates[variant]["name"] + " [" + variant + "]",
            "baseline_rule_id": baseline, "variant_rule_id": variant, "partition": args.partition,
            "changed_components": [change], "metrics": metrics,
            "interpretation": (
                f"Observed lower-bound precision changes from {ap:.6f} to {bp:.6f}, with "
                f"{a['hits']} versus {b['hits']} known hits. A precision-volume tradeoff is "
                "not treated as mechanistic confirmation. Zero-hit and zero-result comparisons "
                "remain visible. Training comparisons use only visible labels; feedback "
                "comparisons use only the evaluator's aggregate counts. If a set was not "
                "resubmitted because of exact eligible-set identity, source_aggregates "
                "explicitly identifies the original scored rule and identity evidence; "
                "this analytical reference is not a new scorer evaluation or Pareto membership."
            ),
            "decision": decision, "source_aggregates": {"baseline": a, "variant": b},
            "next_action": "Retain scientific controls and seek independent corroboration rather than tune a threshold to this comparison.",
        })
        done.add((baseline, variant, args.partition))
        print(baseline, "->", variant, json.dumps(metrics), flush=True)


if __name__ == "__main__":
    main()
