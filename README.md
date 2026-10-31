# Translator Treats Rule-Mining Benchmark

This repository prepares and runs reproducible, hypothesis-guided rule-mining
experiments against an immutable Translator KGX snapshot. It provides:

- a deterministic 70% training, 20% feedback, and 10% final pair split;
- Neo4j and Gandalf stores from which every held-out target edge is removed;
- schema-defined Neo4j-materialization, rule, prediction, research-log, run, and
  evaluation artifacts;
- explicit, append-only rounds within each experiment run;
- an aggregate-only feedback scorer and operator-gated final scorer;
- a coverage-aware rule-portfolio selector and aggregate union scorer;
- a dashboard for Neo4j artifacts, schema-validated rules, Pareto surfaces, and
  selected rule portfolios.

The configured source is the Translator June 21, 2026 (`2026_06_21`) build:

- `/Users/bizon/Projects/ROBOKOP/ORION/nodes.jsonl`
- `/Users/bizon/Projects/ROBOKOP/ORION/edges.jsonl`
- `/Users/bizon/Projects/ROBOKOP/ORION/graph-metadata.json`

The source files are read in place and are never copied.

## Benchmark Security Boundary

The split is performed after collapsing every predicate in the configured
`biolink:treats` closure to subject-object pairs. Source does not determine
partition membership: DrugCentral, drug approvals, DRH, TTD, clinical-trial
ingests, and any other source contribute to the same pair pool. A pair supported
by multiple sources is still one pair and is assigned to exactly one partition.
All target edges for feedback and final pairs are omitted from both query
stores. Mining features must be built only after those filtered stores are
created.

Hidden labels are written outside the repository by default, to the sibling
directory `../miner2049er-sealed`. Encryption would not protect labels if the
agent also had the decryption key, so the benchmark instead relies on an
execution boundary:

- the setup operator can read the original graph and sealed directory;
- the rule agent can access only the training stores, run directory, prompt,
  schemas, and feedback-scoring endpoint;
- the operator owns `run.json`, round manifests, round prompts, and sealed run
  authorizations; the agent appends Neo4j, rule, and prediction artifacts, while
  `miner-log-research-event` is the sole writer for `research-log.jsonl`;
- the scorer alone mounts the sealed labels;
- the final endpoint requires an operator-only token.

Do not mount the original graph, sealed directory, Docker socket, or final token
inside the rule-agent environment.

Repeated aggregate feedback can still be overfit. The scorer therefore requires
at least five feedback-eligible predictions after visible training labels are
removed, scores each rule or recorded rule-set ID once, rejects duplicate
prediction sets and unions, and allows at most 200 feedback submissions across
all individual rules and rule sets in a run. Run and round IDs are accepted only
when an operator-owned authorization record exists in the sealed directory.

## Benchmark Setup

Configure absolute paths in `.env`, particularly `BENCHMARK_SEALED_DIR`, then:

```bash
make setup
uv run miner-benchmark-setup prepare
uv run miner-benchmark-setup build-stores
uv run miner-benchmark-setup start
```

The complete operation is also available as:

```bash
uv run miner-benchmark-setup all
```

`prepare` writes a public split manifest and training labels under
`data/benchmark/<split-id>/`, while feedback and final labels are written only
under `BENCHMARK_SEALED_DIR/<split-id>/`. `build-stores` streams the original
JSONL directly and does not create another 23 GiB edge file.

Initialize an agent run with:

```bash
uv run miner-benchmark-setup init-run \
  --run-id run-2026-08-18 \
  --deadline 2026-08-19T07:00:00-04:00
```

This creates `round-0001` and prints the generated agent prompt path. The base
assignment is snapshotted into the run, and the round prompt adds the active
round ID, deadline, append-only requirements, and operator instruction.

The controller normally finishes a valid round automatically. To finish a
stopped round manually after repairing or completing its artifacts, run:

```bash
uv run miner-benchmark-setup finish-round --run-id run-2026-08-18
```

This requires a schema-valid run and a `final_summary` research event. It seals
the round checkpoint, changes the run to `round_complete`, and disables
feedback scoring without releasing final scoring.

When the agent should perform another round, start it from that completed round
boundary:

```bash
uv run miner-benchmark-setup start-round \
  --run-id run-2026-08-18 \
  --deadline 2026-08-20T07:00:00-04:00 \
  --instruction "Review the first round and pursue new pathway and anatomy mechanisms."
```

Run this only after the controller or `finish-round` has completed the current
round and outstanding feedback requests have completed. Longer instructions can
be supplied with `--instruction-file`. Starting a round requires a
`round_complete` run and generates a new `rounds/<round-id>/agent-prompt.md`
from the prior cryptographic checkpoint. Existing Neo4j artifacts, rules,
predictions, research events, evaluations, duplicate checks, and feedback usage
remain part of the same run.

When no further rounds will be requested, close the run:

```bash
uv run miner-benchmark-setup close-run --run-id run-2026-08-18
```

Closing a `round_complete` run authorizes operator-gated final scoring. It is
intentionally not possible to reopen a closed run.

Agent output must validate against the schemas under `schemas/`. Every Neo4j
artifact, rule, prediction, research event, and evaluation carries both
`run_id` and `round_id`.

```bash
uv run miner-log-research-event \
  --run-dir runs/<run-id> \
  --event-type checkpoint \
  --summary "Completed the pathway-family ablation." \
  --details-json '{
    "progress":["Completed the pathway-family ablation."],
    "active_hypotheses":["interaction-supported pathway convergence"],
    "completed_hypotheses":["direct pathway overlap"],
    "next_actions":["Materialize compact pathway support and test degree penalties."],
    "resource_summary":"The raw four-hop join was replaced by two reusable support relationships."
  }'
uv run miner-validate-run runs/<run-id>
```

The research-event command is the only supported writer for
`research-log.jsonl`. It locks the ledger and assigns canonical sequence numbers
and append-time timestamps, so parallel queries and delayed scorer responses
cannot create an invalid event order. Research events use schema version `1.0`.
Its event-specific details make hypotheses, complete queries, observations,
evaluations, ablations, materializations, failures, graph limitations,
checkpoints, and final summaries reconstructable.

## Agent Service Access

The agent environment receives only the safe service variables
`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `GANDALF_URL`, and `SCORER_URL`.
It must not receive the operator `.env`, sealed directory, final token, Docker
socket, scorer state, or prototype rule-mining outputs under `results/` and
`rules/`.

- Neo4j is queried with the installed official Python driver against the
  `neo4j` database.
- Gandalf accepts standard TRAPI requests at `$GANDALF_URL/query` and applies
  Biolink predicate inheritance.
- `uv run miner-expand-predicate <biolink-predicate>` returns the exact pinned
  descendant set and Neo4j relationship types for reproducing TRAPI semantics.
- Rules and complete prediction sets are recorded with
  `uv run miner-record-rule --run-dir <run-dir> --candidate <candidate.json>`.
  Add `--submit-feedback` only for selected candidates. Already-recorded rules
  can be submitted later with `miner-submit-feedback`.

The generated round prompt contains executable connection checks, a Neo4j
driver example, a complete minimal TRAPI request, and the feedback command using
the exact run directory.

Launch the active round in a detached, blind Codex process with:

```bash
uv run miner-run-agent start \
  --run-dir runs/run-2026-08-18 \
  --runtime-dir .run/agents/run-2026-08-18-round-0001
```

Claude Code is also supported through the locally authenticated subscription:

```bash
uv run miner-run-agent start \
  --run-dir runs/run-2026-08-18-opus-low \
  --runtime-dir .run/agents/run-2026-08-18-opus-low-round-0001 \
  --agent-runtime claude \
  --model-provider anthropic \
  --model opus \
  --reasoning-effort low
```

The runner gives the mining process only the documented service variables. It
uses an isolated home and applies a macOS sandbox that blocks the original ORION
graph, sealed labels, operator `.env`, scorer state, operator agent history, and
Docker sockets. Codex additionally disables user configuration, memories, and
web search. Claude receives a one-use OAuth access token through an inherited
pipe; the token is consumed before its shell tools run and is never placed in
the agent environment.
Aggregate evaluation files are readable so the official run validator and the
agent can inspect prior metrics, but the sandbox blocks writes to them. If an
invocation exits before the wrap-up window without a valid final summary, the
controller starts a continuation against the same append-only run artifacts.
During wrap-up, a clean exit is accepted only after official validation and a
`final_summary`; the controller then validates again and seals the round. A
short wall-clock poll prevents macOS sleep from turning the absolute deadline
into accumulated awake time. If the host resumes after the deadline, the
controller stops research and launches one bounded, summary-only recovery
invocation. If model or network failure still prevents that invocation from
writing `final_summary`, the controller appends an explicitly interrupted
fallback summary and seals the round only when all existing artifacts pass
official validation. Invalid artifacts remain visible as `finalization_failed`
rather than being reported as success.

Inspect or stop the controller with:

```bash
uv run miner-run-agent status \
  --runtime-dir .run/agents/run-2026-08-18-round-0001
uv run miner-run-agent stop \
  --runtime-dir .run/agents/run-2026-08-18-round-0001
```

## Scoring

The feedback service accepts prediction sets at:

```text
POST http://127.0.0.1:6430/score/feedback
```

For example:

```json
{
  "run_id": "run-2026-08-18",
  "round_id": "round-0002",
  "rule_id": "pathway-rule-17",
  "predictions": [
    {
      "subject_id": "CHEBI:6801",
      "object_id": "MONDO:0005148"
    }
  ]
}
```

It returns only aggregate counts, lower-bound precision, recall, and F0.5. It
never returns pair identities or examples. Feedback submissions are accepted
only for the active sealed round. At least five predictions must remain after
visible training labels are removed; this threshold affects feedback only, and
smaller or empty rules remain valid recorded candidates. The operator releases
final scoring only after `close-run`:

```text
POST http://127.0.0.1:6430/score/final
X-Final-Token: <operator-only token>
```

## Rule Portfolio Selection

After a round is complete, construct coverage-aware rule portfolios across all
rules accumulated through that round:

```bash
uv run miner-select-rule-sets \
  --run-dir runs/run-2026-08-21-0915
```

This writes post-mining derived artifacts under
`results/rule-sets/<run-id>/`, outside the sealed append-only run checkpoint:

- `overlap.json` records exact duplicate and strict-subset relationships between
  complete prediction sets.
- `rule-sets.jsonl` records an ordered sequence of portfolio prefixes for both
  the treats-included and treats-excluded surfaces.

The selector does not discard a precise rule merely because its predictions
are a subset of a broader rule. It greedily adds the rule that produces the
strongest precision-skewed F0.5 estimate on predictions not already covered by
the selected set. Each prefix reports exact union size and training recall, plus
estimated feedback precision and recall. These feedback estimates apply a
rule's aggregate precision uniformly to its newly added pairs and are explicitly
heuristic because the scorer does not reveal which individual held-out pairs
were hits. Rules marked `rejected` by the mining agent are reported but are not
selected.

Use aggregate union scoring to measure a promising prefix without exposing
held-out pair identities:

```bash
uv run miner-submit-rule-set \
  --run-dir runs/run-2026-08-21-0915 \
  --rule-set treats-included-p005 \
  --partition feedback
```

The scorer reconstructs the prediction union from the append-only run itself
and verifies the exact recorded member order. Rule-set feedback scoring is
available only at a completed round boundary and consumes the same bounded
feedback budget as individual-rule scoring. Final rule-set scoring remains
operator-gated and is available only after the run is closed.

The schema-driven dashboard for the current run is available at
`http://127.0.0.1:6431/benchmark/run/run-2026-08-21-0915`.
Each run page summarizes research-event types and recent activity. The
**View the complete chronological research log** link shows every event with
readable structured details and the original JSON. The **Examine portfolio
selection and rule overlap** link shows both portfolio surfaces, their ordered
members, marginal coverage, exclusions, estimates, and any aggregate union
evaluations.

## Query Stores

The benchmark builds two query stores from the filtered graph:

- Gandalf mmap/CSR for fast TRAPI path queries.
- Neo4j Community for arbitrary Cypher and rule-mining exploration.

Gandalf is pinned to commit
`82a1fb2e1bcaac6aaa899f3ff4864fc4501c7879`. Its Biolink Model `4.3.2`
schema and predicate map are downloaded once, verified by SHA-256, and then
used locally for builds and server restarts.

The runtime wrapper also supplies the OpenAPI configuration omitted from the
pinned Gandalf Python source distribution.

## Data Model

Neo4j nodes have the base label `Entity` and one additional label for each
Biolink category, with the `biolink:` prefix removed. For example:

```cypher
MATCH (d:Disease)<-[r:TREATS]-(c:SmallMolecule)
RETURN c.id, c.name, d.id, d.name, r.edge_id
LIMIT 25;
```

Relationships use an uppercase form of their Biolink predicate as the Neo4j
relationship type. The exact predicate remains in `r.predicate`.

## Biolink And TRAPI Semantics

TRAPI query-edge predicates use Biolink descendant expansion. A query for
`biolink:affects`, for example, matches `biolink:affects` and every predicate
below it in Biolink Model 4.3.2. This applies to every edge in a rule body, not
only to the treatment target.

Gandalf performs that expansion. Neo4j does not, so Neo4j rule queries must use
the expanded values of `r.predicate`:

```bash
uv run miner-expand-predicate biolink:affects
```

```cypher
MATCH (subject)-[relationship]->(object)
WHERE relationship.predicate IN $expanded_predicates
RETURN subject.id AS subject_id, object.id AS object_id
```

Each rule edge records its authored predicates, full pinned descendant closure,
and any explicit exclusions. Run validation and the feedback scorer recompute
the closure from the local Biolink 4.3.2 schema and reject mismatches. Rules
that exclude descendants must explain the exclusion, use the filtered set for
their statistics, report a full-closure ablation, and mark TRAPI expressibility
as partial or none because an ordinary parent-predicate qedge cannot impose the
exclusion.

Broad parent predicates require care. Their descendants may include treatment
assertions even when the authored predicate does not say `treats`; the
`uses_treatment_edges` flag is validated against the effective expanded set.
The treatment-evidence family is the descendant closure of
`biolink:treats_or_applied_or_studied_to_treat`, so applied-treatment,
clinical-trial, preclinical, and beneficial-in-model predicates count as
treatment edges as well as the target `treats` family.

Every evaluation partition has two independently computed Pareto surfaces:

- **Treats included:** all rules compete, including both treatment-free and
  treatment-using rules.
- **Treats excluded:** only rules with `uses_treatment_edges=false` compete.

The dashboard switches between these surfaces without changing the underlying
evaluation labels. A treatment-free rule can therefore be dominated on the
all-rule surface while remaining Pareto-optimal among treatment-free rules.

The benchmark dashboard defaults to **All rounds**, computing the frontier
across the entire run. The **Compare** controls can explicitly limit the
comparison to one round; the page labels that frontier as round-local.
The selected round is retained when changing evaluation partition, treatment
surface, or the all-rules/Pareto-only view.

Rule pages lead with a graph of the recorded pattern. Select a node or
numbered relationship to inspect its role, direction, qualifiers, source
constraints, and predicate expansion. Amber asterisks mark relationships
with additional qualifiers, sources, exclusions, or predicate scope; selecting
one opens its keyed `R1*`, `R2*`, etc. legend entry. A whole-rule notes strip
links `C1`, `C2`, etc. to conditions and `F1`, `F2`, etc. to derived features,
including formulas and construction details. Free-text conditions are not
assigned to particular nodes or edges without explicit schema attachments.
Additional conditions remain visible in the legend below the graph.
Arrows represent required relationships, not proof of
causation; the predicted treatment relationship is shown separately.
Zoom controls and horizontal scrolling support small screens. The complete
rule, derived features, Cypher, TRAPI, and raw JSON remain available in
collapsed technical sections. This visualization does not alter stored rules
or scoring.

TRAPI provenance is available through:

- `r.primary_knowledge_sources`
- `r.aggregator_knowledge_sources`
- `r.upstream_resource_ids`
- `r.sources_json`

All original node and edge records are retained in `raw_json`. Common
attributes and every qualifier represented in the build metadata are also
materialized as typed Neo4j properties.

## Target Semantics

The target is exactly `biolink:treats`, including its configured Biolink
predicate descendants:

- `biolink:treats`
- `biolink:ameliorates_condition`
- `biolink:preventative_for_condition`

Gandalf applies predicate inheritance during TRAPI queries. Neo4j does not, so
the setup and scoring code explicitly uses the complete target-predicate set.
The same descendant-expansion requirement applies to every body predicate used
to generate rule statistics and predictions.
Unknown chemical-disease pairs remain unlabeled, so reported precision is a
lower bound against known held-out labels.

Derived edges and properties may be created after the filtered stores are
built, but every rule using one must define its inputs, construction,
deduplication policy, formula, interpretation, and limitations in its
schema-valid rule record.

Every persistent Neo4j addition must also be recorded once in the run's
append-only `neo4j-artifacts.jsonl`. The record identifies the exact property,
label, relationship, node, index, or constraint; defines units and value
semantics; provides creation, verification, and cleanup Cypher; and reports
observed population counts and distributions. Materialized rule features refer
to this inventory through `neo4j_artifact_id`.

The dashboard lists these artifacts separately from rules. Selecting an
artifact shows its full semantic definition, dependencies, observed statistics,
and executable Cypher.

## Store Endpoints

- Gandalf TRAPI: `http://localhost:6429/query`
- Gandalf documentation: `http://localhost:6429/docs`
- Benchmark dashboard: `http://127.0.0.1:6431/benchmark/run/run-2026-08-21-0915`
- Aggregate scorer: `http://localhost:6430`
- Neo4j Browser: `http://localhost:7474`
- Neo4j Bolt: `bolt://localhost:7687`

The local default Neo4j credentials are `neo4j` / `translator-local`. Override
them in `.env`.

## Operations

```bash
docker compose ps
curl --fail http://127.0.0.1:6430/health
make gandalf-stop
make neo4j-stop
```

On macOS, Gandalf is managed as the user launch service
`io.renci.miner2049er.gandalf`; Neo4j is managed by Docker Compose.
