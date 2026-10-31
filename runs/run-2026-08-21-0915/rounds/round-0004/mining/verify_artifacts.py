"""Verify existing run-owned graph artifacts without changing their ledgers."""

import json
import math
import os
import time

from neo4j import GraphDatabase, Query, READ_ACCESS

from audit import records
from probe import REQUIRED, RUN, log_event


def main():
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing service variables: " + ", ".join(missing))
    failed = []
    with GraphDatabase.driver(
        os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        max_transaction_retry_time=0, connection_timeout=15,
    ) as driver:
        for artifact in records(RUN / "neo4j-artifacts.jsonl"):
            query = artifact["execution"]["verification_cypher"]
            started = time.monotonic()
            try:
                with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                    rows = [r.data() for r in session.run(Query(query, timeout=90))]
                if len(rows) != 1:
                    raise RuntimeError("Expected a single aggregate verification row")
                row = rows[0]
                expected = artifact["observed"]
                checks = {
                    key: row.get(key) == expected[key]
                    for key in ("values_populated", "values_missing", "distinct_values", "minimum", "maximum")
                }
                checks["relationships"] = row.get("relationships") == expected["relationships_created"]
                checks["mean"] = math.isclose(row["mean"], expected["mean"], rel_tol=1e-9, abs_tol=1e-9)
                for key, value in expected["quantiles"].items():
                    checks[key] = math.isclose(row[key], value, rel_tol=1e-9, abs_tol=1e-9)
                for key in ("missing_member_lists", "inconsistent_counts"):
                    if key in row:
                        checks[key] = row[key] == 0
                matches = all(checks.values())
                log_event("query", "Verify documented graph artifact: " + artifact["artifact_id"], {
                    "purpose": "Check that all run-owned quantities retain their recorded statistics.",
                    "query_language": "cypher", "query_text": query, "outcome": "completed",
                    "result_summary": json.dumps({"observed": row, "checks": checks, "matches": matches}),
                    "runtime_seconds": time.monotonic() - started,
                    "artifact_id": artifact["artifact_id"],
                    "next_action": "Preserve matching artifacts; investigate mismatches without rewriting the append-only inventory.",
                })
                if not matches:
                    raise RuntimeError("Artifact statistics differ from the immutable inventory")
            except Exception as error:
                failed.append(artifact["artifact_id"])
                log_event("failure", "Graph artifact did not verify: " + artifact["artifact_id"], {
                    "stage": "artifact verification", "error": str(error),
                    "diagnosis": "The existing inventory has not been changed; this artifact lacks a successful current verification.",
                    "next_action": "Report the verification gap and inspect affected rules before claiming reproduction.",
                    "hypothesis_status": "blocked", "artifact_id": artifact["artifact_id"],
                })
    if failed:
        raise RuntimeError("Unverified artifacts: " + ", ".join(failed))
    print("All existing run-owned graph artifact statistics match.")


if __name__ == "__main__":
    main()
