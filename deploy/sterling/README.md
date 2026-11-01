# Sterling deployment: Translator 1.0.2 query stores

Builds the benchmark's Neo4j store on Sterling (namespace `bizon`). Gandalf,
the scorer, the dashboard and the nightly agent CronJob come later.

## Storage

| PVC | Class | Size | Holds | Mounted by |
| --- | --- | --- | --- | --- |
| `miner-source` | basic | 10Gi | `nodes.jsonl.zst`, `edges.jsonl.zst`, metadata | build Job |
| `miner-sealed` | encrypted | 1Gi | feedback and final labels | build Job, later the scorer only |
| `miner-work` | basic | 10Gi | public split, runs, evaluations | build Job, later agent and scorer |
| `miner-import` | basic | 10Gi | Parquet for `neo4j-admin` | build Job; delete after import |
| `miner-neo4j-data` | basic-noatime | 60Gi | Neo4j store | build Job, Neo4j |

The `ssd` class is blocked for new volumes by Sterling's Gatekeeper policy.
The namespace quota is 128Gi; this requests 91Gi.

The source stays zstd-compressed (`SOURCE_COMPRESSION=zstd`), so the 28GB
uncompressed graph is never written. The Neo4j export drops the per-record
`raw_json` and `sources_json` copies, which nothing reads; every field they
held is exported on its own.

## Prerequisites

1. Push the image (needs Docker running locally) and pin it:

   ```bash
   docker build -f Dockerfile.benchmark -t ghcr.io/cbizon/miner2049er:1.0.2 .
   docker push ghcr.io/cbizon/miner2049er:1.0.2
   ```

   Replace `IMAGE_TAG` in `build-stores-job.yaml` with the pushed tag, or
   better its `@sha256:` digest. The existing `registry-credentials` pull
   secret covers `ghcr.io/cbizon`.

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

The Job runs fetch, split, Parquet export and `neo4j-admin import` in
order. Each step skips work a previous attempt finished, so after a failure
delete the Job and apply it again. The import refuses to overwrite an
existing database.

When the Job succeeds, read the store size from its last log line, set
`NEO4J_server_memory_pagecache_size` in `neo4j.yaml` to fit, then:

```bash
kubectl delete pvc miner-import
kubectl apply -f neo4j.yaml
kubectl logs -f job/miner-neo4j-indexes
```
