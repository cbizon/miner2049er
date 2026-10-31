# Treats Rule-Mining Assignment

You are mining rules that predict `biolink:treats` in a fixed Biomedical Data
Translator graph. The graph available to you contains training treatment labels.
Feedback and final labels have been removed from every query store before any
derived mining features were built.

## Objective

Find graph rules that balance precision, recall, and useful novel prediction
volume, with precision weighted more heavily. Search for biologically meaningful
mechanisms rather than merely rediscovering treatment labels or tuning arbitrary
thresholds.

The active round, deadline, and operator instruction are supplied in the round
prompt. Continue working until that round's deadline. Do not stop because you
reach a rule-count target. Spend no more than 25 percent of the available time
adjusting thresholds within existing rule families.

A run may contain multiple rounds. Before beginning a later round, read the
complete existing research log, rules, and aggregate evaluations. Build on that
work rather than restarting it. All rounds share one feedback budget and one
duplicate-prediction ledger.

## Service Access

Run commands from the repository root shown in the active round prompt. The
operator supplies these safe environment variables to the agent:

- `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`;
- `GANDALF_URL`;
- `SCORER_URL`.

Fail immediately if a required variable is missing. Do not read an operator
`.env` file or attempt to access the sealed directory, original graph, final
scoring token, Docker socket, or scorer state.

### Neo4j

Neo4j supports arbitrary Cypher, including property and degree constraints and
documented feature materialization. Connect to the `neo4j` database with the
official Python driver:

```bash
uv run python - <<'PY'
import os
from neo4j import GraphDatabase

required = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")
missing = [name for name in required if not os.environ.get(name)]
if missing:
    raise RuntimeError(f"Missing service variables: {', '.join(missing)}")

with GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
) as driver:
    result = driver.execute_query(
        "MATCH (n) RETURN count(n) AS node_count",
        database_="neo4j",
    )
    print(result.records[0].data())
PY
```

Neo4j relationship types are uppercase Biolink predicate names, while the exact
predicate remains in `r.predicate`. Neo4j does not apply Biolink predicate
inheritance. Treat `r.predicate` as authoritative and query it against the
complete descendant set described below.

### Gandalf TRAPI

Gandalf provides the filtered graph through a standard TRAPI endpoint. It is
preferable for graph patterns expressible in TRAPI and applies Biolink predicate
inheritance. Check it and submit a query with:

```bash
curl --fail --silent --show-error "$GANDALF_URL/metadata"
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  --data @query.json \
  "$GANDALF_URL/query" > response.json
```

A minimal `query.json` has the normal TRAPI query-graph form:

```json
{
  "message": {
    "query_graph": {
      "nodes": {
        "chemical": {"categories": ["biolink:ChemicalEntity"]},
        "disease": {
          "ids": ["MONDO:0005148"],
          "categories": ["biolink:Disease"]
        }
      },
      "edges": {
        "association": {
          "subject": "chemical",
          "object": "disease",
          "predicates": ["biolink:related_to"]
        }
      }
    }
  }
}
```

Because Gandalf expands predicate descendants, the `biolink:related_to` query
can return more specific relationships such as `biolink:treats`. Enforce
unsupported property, degree, cardinality, or cross-result constraints in
Cypher or documented post-processing.

### Biolink Predicate Semantics

This benchmark is pinned to Biolink Model `4.3.2`. In TRAPI, a query edge
predicate means that predicate or any of its Biolink descendants. This rule
applies to every body edge, not only to the `biolink:treats` target. All
training statistics, ablations, predictions, and reruns must use those same
TRAPI subpredicate semantics.

Inspect the exact pinned descendant closure before writing or evaluating a
rule:

```bash
uv run miner-expand-predicate biolink:affects
uv run miner-expand-predicate biolink:related_to
```

Gandalf applies the returned expansion automatically. Neo4j does not. For
Neo4j, pass the command's `expanded_predicates` as a query parameter and use
the exact stored predicate:

```cypher
MATCH (subject)-[relationship]->(object)
WHERE relationship.predicate IN $expanded_predicates
RETURN subject.id AS subject_id, object.id AS object_id
```

Do not calculate rule statistics with an exact relationship type such as
`[:AFFECTS]` when the deployable TRAPI rule uses `biolink:affects`; those are
different rules. Relationship-type unions may be used as an optimization only
when they cover the same recorded descendant set.

Broad parents can introduce unexpected evidence. In Biolink 4.3.2,
`biolink:affects` includes treatment-oriented descendants, and
`biolink:related_to` is substantially broader. Therefore
`uses_treatment_edges` refers to the effective expanded predicates, not merely
the authored predicate names. A rule uses treatment edges when any effective
body predicate is a descendant of
`biolink:treats_or_applied_or_studied_to_treat`. This includes `treats`,
`applied_to_treat`, `studied_to_treat`, `in_clinical_trials_for`,
`in_preclinical_trials_for`, and `beneficial_in_models_for`.

If a descendant makes a parent-predicate rule semantically incoherent, you may
exclude it only explicitly:

```bash
uv run miner-expand-predicate biolink:affects \
  --exclude biolink:ameliorates_condition \
  --exclusion-rationale "Treatment assertions would make this body circular."
```

Record every exclusion and its rationale in the rule. Evaluate both the full
TRAPI closure and the filtered ablation. A filtered rule is not fully
expressible by the parent predicate in standard TRAPI; mark TRAPI
expressibility `partial` or `none` and state the required post-filter.

### Aggregate Feedback Scorer

Do not write `rules.jsonl` or `predictions.jsonl` directly and do not create
custom persistence scripts. Define each rule in a candidate JSON document that
validates against `schemas/rule-candidate.schema.json`, then record it with:

```bash
curl --fail --silent --show-error "$SCORER_URL/health"
uv run miner-record-rule \
  --run-dir "<run-directory-from-the-round-prompt>" \
  --candidate "/tmp/<rule-id>.json"
```

`miner-record-rule` deterministically:

- inserts the active `run_id` and `round_id`;
- expands every authored Biolink predicate using the pinned model;
- renders the candidate's Cypher predicate and relationship-type placeholders;
- executes the rendered Cypher read-only;
- validates and deterministically sorts the complete prediction set;
- collapses identical duplicate rows and rejects conflicting duplicates;
- appends the rule and predictions with rollback on validation failure; and
- validates the complete run afterward.

Every graph-pattern edge with ID `effect`, for example, must be enforced in the
Cypher template with `{{predicates:effect}}`. This token becomes the JSON-style
Cypher list of effective predicates after descendant expansion. The optional
`{{relationship_types:effect}}` token becomes the corresponding uppercase
Neo4j relationship-type union. The query must return `subject_id` and
`object_id`; it may also return integer `support_count` and string-array
`evidence_bindings`.

A minimal candidate has this form:

```json
{
  "schema_version": "1.0",
  "rule_id": "causal-example",
  "family_id": "causal-example-family",
  "name": "Causal example",
  "status": "candidate",
  "plain_language_rule": "A chemical is linked to a disease by a causal relationship.",
  "hypothesis": "Causal chemical-disease evidence may predict treatment.",
  "graph_pattern": {
    "nodes": [
      {
        "id": "chemical",
        "role": "candidate treatment",
        "categories": ["biolink:ChemicalEntity"],
        "explanation": "The predicted treatment."
      },
      {
        "id": "disease",
        "role": "target disease",
        "categories": ["biolink:Disease"],
        "explanation": "The predicted disease."
      }
    ],
    "edges": [
      {
        "id": "evidence",
        "subject": "chemical",
        "object": "disease",
        "predicates": ["biolink:causes"],
        "direction": "forward",
        "explanation": "The chemical has causal evidence for the disease."
      }
    ],
    "constraints": []
  },
  "mechanism": {
    "score": "low",
    "rationale": "Direct causation is suggestive but does not establish correction."
  },
  "execution": {
    "cypher_template": "MATCH (subject)-[e:{{relationship_types:evidence}}]->(object) WHERE e.predicate IN {{predicates:evidence}} RETURN DISTINCT subject.id AS subject_id, object.id AS object_id",
    "trapi": {
      "expressibility": "full",
      "query": null,
      "limitations": ""
    }
  }
}
```

Record every coherent executable candidate, including zero-result, rejected,
diagnostic, and low-volume rules. Prediction count is not a publication
threshold. Use `--submit-feedback` only for selected candidates that merit
held-out evaluation:

```bash
uv run miner-record-rule \
  --run-dir "<run-directory-from-the-round-prompt>" \
  --candidate "/tmp/<rule-id>.json" \
  --submit-feedback
```

The feedback minimum is five predictions remaining after visible training
labels are excluded. This minimum affects feedback submission only. Rules below
it remain recorded and visible in the dashboard. Each rule ID can be scored
once, identical prediction sets cannot be resubmitted, and all rounds share one
submission budget. If recording succeeds but feedback fails, retry only with
`miner-submit-feedback`; never rerun `miner-record-rule` for the same rule ID.

## Search Expectations

Explore genuinely different graph mechanisms, including:

- causal and directional drug-target-disease relationships;
- pathways and biological processes;
- gene-gene regulation and physical interaction;
- anatomy, cell type, and expression context;
- shared and directional phenotypes;
- disease and process ontology structure;
- provenance agreement and disagreement;
- explicit negative or contradictory evidence;
- nonlinear and multi-arm graph patterns;
- property, source, cardinality, and degree constraints.

Do not reduce this assignment to two-hop templates with threshold tweaks. For
each promising biological mechanism, deliberately examine:

- different graph shapes: three-to-five-hop chains, converging and diverging
  arms, independent corroborating arms, interaction bridges, ontology-mediated
  paths, and required side-context attached to an intermediate node;
- different evidence definitions: predicate direction, qualifiers, primary
  source, source agreement or disagreement, positive and negative evidence,
  edge properties, and support cardinality;
- different grouping and scoring strategies: distinct-source counts, ranks,
  normalized evidence scores, compact-support summaries, neighborhood overlap,
  specificity penalties, and combinations whose components have independent
  biological interpretations;
- node properties and neighborhood structure: total and predicate-specific
  degree, source-specific degree, ontology depth, descendant and ancestor
  counts, local density, hub penalties, and disease-, gene-, pathway-,
  phenotype-, anatomy-, or cell-context specificity; and
- a small set of biologically or distributionally justified parameter values,
  not only one convenient cutoff and not a broad feedback-driven sweep.

For each promising family, establish a simple baseline, test structurally
different variants, test at least one plausible grouping or scoring strategy,
and perform otherwise-identical component-removal ablations. A failed first
query is not a failed hypothesis.

Expensive joins are a signal to engineer the search, not a reason to abandon a
mechanism. Before declaring a pathway, interaction, anatomy, phenotype, or
ontology hypothesis infeasible:

1. profile the cardinality and source composition of each individual path leg;
2. constrain indexed labels, predicates, directions, sources, and identifier
   namespaces before joining;
3. test the shape on a bounded sample and inspect the query plan;
4. pre-aggregate or materialize reusable neighborhoods, counts, ranks, scores,
   or compact-support relationships in Neo4j;
5. add and document appropriate indexes when they materially change execution;
6. compare the materialized formulation with the unmaterialized baseline; and
7. record the attempted formulations, runtimes, failures, and remaining graph
   limitation.

Do not equate a Cypher timeout, large intermediate result, or inconvenient raw
path with biological failure. If the graph contains the necessary evidence,
make a serious attempt to construct a tractable representation. If the
mechanism still does not work, record why and move to another family. Perform
ablations to establish whether each added condition improves the rule.

Derived-feature engineering is an expected part of the search, not merely an
optional optimization. When raw graph paths are too noisy, too broad, or too
expensive to reuse, construct biologically interpretable quantities or
structures such as degree measures, evidence counts, normalized association
scores, ranks, compact-support relationships, or contextual annotations. You
are explicitly authorized to use `SET`, `CREATE`, and `MERGE` to materialize
these features in Neo4j, subject to the documentation and cleanup requirements
below. Do not treat Neo4j as read-only.

Derived features provide many opportunities to overfit the feedback partition.
Define each feature and choose a small, biologically or statistically motivated
set of thresholds before submitting feedback. For every rule that uses a
derived feature, evaluate the otherwise identical rule without that feature
and perform component-removal ablations for composite scores or multi-part
features. Record unsuccessful ablations as well as successful ones. Do not use
broad threshold sweeps or repeatedly redesign a feature in response to feedback
metrics. Retain a derived feature only when its ablations show a meaningful
improvement that is not explained solely by collapsing prediction volume.

## Semantic Requirements

- The target is exactly `biolink:treats`, interpreted with its Biolink predicate
  descendants. Neo4j does not perform this expansion automatically.
- Every graph-pattern edge must record its authored predicates, complete
  Biolink 4.3.2 descendant expansion, exclusions, and exclusion rationale.
- Predictions submitted to the scorer must come from the recorded expanded
  predicates. The rule's `execution.predicate_expansion` section must explain
  how its Cypher or TRAPI execution enforced that set.
- A rule may use treatment-oriented evidence, but it must set
  `uses_treatment_edges` accurately after descendant expansion. Treatment-free
  rules are analyzed separately.
- Do not use external information to apply a rule.
- Do not attempt to access, reconstruct, enumerate, or infer individual hidden
  labels.
- Unknown predictions are unlabeled, not known negatives. Report precision as a
  lower bound.

### Required Pareto Surfaces

For every available evaluation partition, maintain and report two distinct
precision-recall Pareto surfaces:

1. **Treats included:** all eligible rules compete on one surface. This includes
   both treatment-free rules and rules with `uses_treatment_edges=true`; it does
   not mean only treatment-using rules.
2. **Treats excluded:** only rules with `uses_treatment_edges=false` compete on
   this surface.

Compute dominance independently within each surface. A treatment-free rule may
be dominated on the treats-included surface while remaining Pareto-optimal on
the treats-excluded surface. Record both memberships and counts explicitly.
Never combine the surfaces or use the treats-included surface as a substitute
for the treatment-free comparison.

## Explanation Requirements

Every rule must be self-contained for a reader who has not seen your research
process or private notation.

- Do not use unexplained abbreviations or internal names such as `R123`,
  `MINER_*`, or feature-property names as the explanation.
- State every node, edge, direction, qualifier, provenance requirement,
  cardinality constraint, and threshold in ordinary language.
- If the rule uses a derived edge or property, define its source data,
  construction algorithm, aggregation and deduplication policy, formula,
  threshold interpretation, and known limitations.
- Include complete executable Cypher.
- Include a TRAPI query when fully or partially expressible, and state exactly
  what must be enforced outside TRAPI.
- Never describe a parent predicate without stating what its descendant
  expansion contributes to the actual rule.

## Neo4j Materialization Requirements

Every persistent quantity or structure that you add to Neo4j must have one
schema-valid record in `neo4j-artifacts.jsonl`. This includes node and
relationship properties, labels, derived nodes, derived relationships, indexes,
and constraints.

- Record the artifact immediately after running its verification query.
- Give it a stable, unique `artifact_id`; never reuse an ID for a replacement.
- State the exact Neo4j target, value type, unit, scope, semantic definition,
  source inputs, formula, aggregation, deduplication, missing-value policy, and
  interpretation.
- Include complete creation, verification, and cleanup Cypher.
- Record observed node, relationship, populated-value, missing-value, distinct
  value, range, mean, and quantile statistics. Use zero or null only when the
  quantity is genuinely not applicable.
- List dependencies on earlier Neo4j artifacts. A replacement must use a new ID
  and identify the artifact it supersedes.
- A rule that uses a materialized derived feature must set that feature's
  `neo4j_artifact_id`. Use null only when the feature is not stored in Neo4j.
- Record failed or temporary materialization attempts in the research log even
  if they are cleaned up and never become artifacts.

The Neo4j artifact ledger is append-only. Never rewrite an artifact record or
silently change the semantics of an existing property.

## Required Artifacts

The operator provides `run.json`, the active round manifest, and round prompt.
Do not edit those files. Use the designated deterministic writers:

- `neo4j-artifacts.jsonl`, one record per persistent Neo4j addition, validated
  by `schemas/neo4j-artifact.schema.json`;
- `rules.jsonl` and `predictions.jsonl`, written only by
  `uv run miner-record-rule`; never append either file manually;
- `research-log.jsonl`, append-only events validated by
  `schemas/research-event.schema.json`. Never write this file directly. Append
  events with `uv run miner-log-research-event`; that command owns the sequence
  number, append-time timestamp, active run ID, and active round ID.

The scorer writes evaluations separately. Do not invent, edit, or copy evaluator
results into agent-authored records.

The research log must include every hypothesis, executable query, observation
or example inspected from visible data, evaluation, ablation, materialization
attempt, failure, graph limitation, checkpoint, and final summary. Existing
entries must never be rewritten. Put source occurrence times such as a scorer's
`scored_at` value in the event `details`; do not use them as the ledger
timestamp.

Research events use schema `1.0`. Each event type has required structured
details so another researcher can reconstruct what was tried:

- `hypothesis`: `mechanism_family`, `rationale`, `proposed_test`,
  `variables_to_explore`, `success_criterion`, and `next_action`;
- `query`: `purpose`, `query_language`, complete `query_text`, `outcome`,
  `result_summary`, and `next_action`; also record parameters and runtime when
  available;
- `observation`: `source`, `finding`, `implication`, and `next_action`, with
  representative visible examples when useful;
- `evaluation`: `method`, `metrics`, `interpretation`, `decision`, and
  `next_action`;
- `ablation`: `baseline`, `variant`, `changed_components`, `metrics`,
  `interpretation`, and `decision`;
- `materialization`: `purpose`, `feature_definition`, `status`,
  `creation_query`, `verification_summary`, and `ablation_plan`;
- `failure`: `stage`, `error`, `diagnosis`, `next_action`, and
  `hypothesis_status`;
- `graph_limitation`: `limitation`, `evidence`, `affected_hypotheses`, and
  `workaround`;
- `checkpoint`: `progress`, `active_hypotheses`, and `next_actions`; and
- `final_summary`: `families_explored`, `surviving_rule_ids`,
  `failed_families`, `pareto_summary`, `graph_gaps`, and
  `next_round_priorities`.

For example:

```bash
uv run miner-log-research-event \
  --run-dir <run-dir> \
  --event-type hypothesis \
  --summary "Pathway convergence may distinguish causal targets." \
  --details-json '{
    "mechanism_family": "pathway convergence",
    "rationale": "Independent drug and disease evidence converging on a specific pathway may suppress unrelated gene associations.",
    "proposed_test": "Compare direct gene overlap with one-arm and two-arm pathway convergence.",
    "variables_to_explore": ["pathway member degree", "independent source count", "directional target effect"],
    "success_criterion": "Improved visible precision without collapsing to a trivial prediction set.",
    "next_action": "Profile each path leg and materialize compact drug-pathway and disease-pathway support if the full join is expensive."
  }'
```

## Feedback Evaluation

Submit selected complete prediction sets with `miner-record-rule
--submit-feedback`, or use `miner-submit-feedback` for a rule that is already
recorded. The scorer returns only counts, lower-bound precision, recall, and
F0.5. Each rule ID may be scored once, identical prediction sets cannot be
resubmitted under different IDs, and the run has a fixed submission budget
shared by every round.

Use feedback results to refine hypotheses, not to probe individual pairs. The
final partition remains unavailable until the experiment is closed.

## Round Completion

During the controller's final wrap-up window, before the round deadline:

1. Rerun every surviving rule from its recorded executable query.
2. Validate all artifacts against their schemas.
3. Identify distinct rule families separately from parameter variants.
4. Recompute both feedback Pareto surfaces: treats included and treats
   excluded.
5. Record failed families and graph limitations, not only successful rules.
6. Append a `final_summary` research event with
   `uv run miner-log-research-event`.
7. Run `uv run miner-validate-run <run-dir>` after appending the final summary.
8. Exit normally. Do not sleep merely to remain alive until the deadline.

The controller validates the same artifacts, seals the completed round, and
disables feedback scoring. The operator may then start another round with a new
instruction or close the run. Final scoring is released only after the operator
closes the run.
