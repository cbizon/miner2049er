# Sterling deployment: Translator 1.0.2 query stores

Builds the benchmark's Neo4j and Gandalf stores on Sterling (namespace
`bizon`) and runs the scorer, the dashboard and the nightly agent CronJob.

## Storage

| Volume | Class | Size | Holds | Mounted by |
| --- | --- | --- | --- | --- |
| `miner-source` | basic | 10Gi | `nodes.jsonl.zst`, `edges.jsonl.zst`, metadata | build Job |
| `miner-sealed` | encrypted | 1Gi | feedback and final labels | build Job, later the scorer only |
| `miner-work` | basic | 10Gi | public split, runs, evaluations | build Job, later agent and scorer |
| `miner-import` | basic | 10Gi | Parquet the Neo4j pod imports from | build Job, Neo4j (read-only) |
| Neo4j `/data` | emptyDir, memory | 36Gi | Neo4j store (~31GB) | Neo4j |
| `miner-gandalf` | basic | 75Gi | Gandalf mmap store (~35-40GB) and, during a build, its temp files | Gandalf build Job, Gandalf (read-only) |

Every storage class available to `bizon` is NetApp `ontap-nas` (NFS). Neo4j
doesn't support NFS for its store: `neo4j-admin import` onto `basic-noatime`
failed with spurious "missing node" errors, while the identical import on local
disk succeeds. Until the namespace has `nvme-ephemeral` quota (requested), the
store lives in RAM: each Neo4j pod start re-imports from `miner-import`, so
keep that volume, and expect writes made through Neo4j to be lost on restart.
The `ssd` class is blocked for new volumes by Sterling's Gatekeeper policy.

The source stays zstd-compressed (`SOURCE_COMPRESSION=zstd`), so the 28GB
uncompressed graph is never written. The Neo4j export drops the per-record
`raw_json` and `sources_json` copies, which nothing reads; every field they
held is exported on its own.

## Prerequisites

1. Build for amd64, push, and pin the digest in `build-stores-job.yaml`:

   ```bash
   docker buildx build --platform linux/amd64 -f Dockerfile.benchmark \
     -t ghcr.io/cbizon/miner2049er:1.0.2-$(git rev-parse --short HEAD) --push .
   ```

   The existing `registry-credentials` pull secret covers `ghcr.io/cbizon`.

2. Create the Neo4j password Secret and the index ConfigMap:

   ```bash
   kubectl create secret generic miner-neo4j-auth \
     --from-literal=NEO4J_AUTH="neo4j/$(openssl rand -hex 16)"
   kubectl create configmap miner-neo4j-indexes --from-file=../../cypher/indexes.cypher
   ```

## Apply

```bash
kubectl apply -f pvcs.yaml
kubectl apply -f build-stores-job.yaml
kubectl logs -f job/miner-build-stores --all-containers
```

The Job runs fetch, split and Parquet export in order. Each step skips work
a previous attempt finished, so after a failure delete the Job and apply it
again. When it succeeds:

```bash
kubectl apply -f neo4j.yaml
kubectl logs -f miner-neo4j-0 -c import
kubectl logs -f job/miner-neo4j-indexes
```

## Gandalf

Needs `pvcs.yaml` applied (for `miner-gandalf`) and the split prepared by
`miner-build-stores`.

```bash
kubectl apply -f build-gandalf-job.yaml
kubectl logs -f job/miner-build-gandalf --all-containers
kubectl apply -f gandalf.yaml
```

The build uses the same held-out split as Neo4j (`build-stores --stores
gandalf`, filtering through `graph_filter.edge_is_visible`). It builds in place
on `miner-gandalf`, then serves the result on localhost and requires over TRAPI
that sampled feedback and final pairs are absent and sampled training pairs
present (`miner-check-gandalf-holdout`, counts only). Only a store that passes
is renamed to the path the server loads.

Storage notes: the build peaks at ~65-70G because Gandalf keeps the unsorted
(31G) and sorted (~30G) edge-property LMDBs at once, hence the 75Gi volume,
which cannot shrink afterwards. `nvme-ephemeral` was tried first: the namespace
has 60Gi of quota, but Sterling's single NVMe node refused even a 10Gi claim
(2026-11-05). LMDB writes on NFS worked for this build; only Neo4j's import is
known to fail on NFS. Agents reach it at
`http://miner-gandalf:6429`; `GANDALF_URL` is required by the agent controller.

## Scorer and agent rounds

`scorer.yaml` runs the feedback scorer (`miner-scorer:6430`). It and the
operator Jobs are the only workloads that mount `miner-sealed`, and only the
scorer holds the final-scoring token (Secret `miner-scorer-final`).

A round is three steps:

```bash
# 1. Operator: create the run and authorize round 1 (or start-round for later rounds)
sed -e "s/@JOB@/miner-op-init-RUN/" \
    -e "s|@ARGS@|init-run --run-id RUN --deadline 2026-11-02T07:00:00-05:00 --instruction '...'|" \
    operator-job.yaml | kubectl apply -f -

# 2. Agent: no sealed volume, evaluations read-only, Claude token from a Secret
sed -e "s/@RUN@/RUN/g" -e "s/@ROUND@/round-0001/g" \
    -e "s/@MODEL@/claude-opus-5-5/" -e "s/@EFFORT@/high/" \
    agent-job.yaml | kubectl apply -f -

# 3. Operator: seal the round once the agent Job finishes
sed -e "s/@JOB@/miner-op-finish-RUN-round-0001/" -e "s|@ARGS@|finish-round --run-id RUN|" \
    operator-job.yaml | kubectl apply -f -
```

The agent runs `miner-run-agent run --isolation container`: the controller
refuses to start if a sealed path or an operator-only variable is visible, and
ends at `awaiting_operator_seal` instead of sealing.

## Daily loop

- `nightly.yaml` (+ `nightly-settings.yaml`, applied once): at 11 pm New York time a CronJob seals the previous round
  (`next-round`) and runs tonight's agent with a 7-hour deadline. Its
  settings (run, model, effort, instruction) are in the `miner-nightly`
  ConfigMap.
- The agent ends each night with a final summary that includes questions for
  the operator and ranked proposed directions.
- Morning: `scripts/sterling_debrief.sh` prints the digest (or `--check` for a
  one-line "needs you?"); the `/miner` Claude Code skill wraps the debrief,
  the discussion, and setting tonight's instruction with
  `scripts/sterling_set_instruction.sh`.
- Instructions are dated. A night without a fresh one runs the ConfigMap's
  `fallback.md`: follow the agent's top proposed direction and its defaults.
- Dashboard: `kubectl -n bizon port-forward svc/miner-dashboard 6431:6431`,
  then http://localhost:6431/benchmark.

Not yet done: a NetworkPolicy limiting the agent's egress (it can currently reach the
internet, so "no external information" is enforced only by the prompt), and
the morning checker and taste-file judge.
