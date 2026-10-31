"""Bounded, serial graph probes; research persistence is owned by the official CLI."""

import argparse
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import time

from neo4j import GraphDatabase, Query, READ_ACCESS


RUN = Path(__file__).resolve().parents[3]
REQUIRED = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "GANDALF_URL", "SCORER_URL")


class MissingDescendantTypeFilter(logging.Filter):
    def filter(self, record):
        # Absent descendant types must remain in queries but need not flood the console.
        return "UnknownRelationshipTypeWarning" not in record.getMessage()


logging.getLogger("neo4j.notifications").addFilter(MissingDescendantTypeFilter())


def log_event(event_type, summary, details):
    result = subprocess.run(
        [
            "uv", "run", "miner-log-research-event",
            "--run-dir", str(RUN),
            "--event-type", event_type,
            "--summary", summary,
            "--details-json", json.dumps(details),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(
            "Official research-event command failed with status "
            + str(result.returncode) + ": " + result.stderr + "\n" + result.stdout
        )
    print("Research event", json.loads(result.stdout)["sequence"], flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("batch", type=Path)
    args = parser.parse_args()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing service variables: " + ", ".join(missing))
    probes = json.loads(args.batch.read_text())
    with GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        max_transaction_retry_time=0,
        connection_timeout=15,
    ) as driver:
        for probe in probes:
            free = shutil.disk_usage(RUN).free
            if free < 5 * 1024**3:
                log_event("failure", "Disk reserve prevents further probing.", {
                    "stage": "resource preflight",
                    "error": f"Only {free} free bytes remain.",
                    "diagnosis": "The operator requires at least five GiB free.",
                    "next_action": "Stop launching queries and summarize the blocker.",
                    "hypothesis_status": "blocked",
                })
                raise RuntimeError("Disk reserve breached")
            query = probe["query"]
            parameters = probe.get("parameters", {})
            timeout = probe.get("timeout_seconds", 60)
            print("\nSTART", probe["purpose"], "timeout", timeout, flush=True)
            started = time.monotonic()
            rows = []
            try:
                with driver.session(database="neo4j", default_access_mode=READ_ACCESS) as session:
                    result = session.run(Query(query, timeout=timeout), parameters)
                    for record in result:
                        rows.append(record.data())
                        if len(rows) > probe.get("maximum_rows", 200):
                            raise RuntimeError("Probe output bound exceeded; use graph aggregation.")
                    summary = result.consume()
                elapsed = time.monotonic() - started
                print(json.dumps({"seconds": elapsed, "rows": rows}, default=str), flush=True)
                details = {
                    "purpose": probe["purpose"],
                    "query_language": "cypher",
                    "query_text": query,
                    "parameters": parameters,
                    "runtime_seconds": elapsed,
                    "timeout_seconds": timeout,
                    "outcome": "completed" if rows else "empty",
                    "result_summary": json.dumps(rows, default=str),
                    "next_action": probe["next_action"],
                }
                if summary.plan is not None:
                    details["query_plan"] = summary.plan
                if summary.profile is not None:
                    details["query_profile"] = summary.profile
                log_event("query", probe["purpose"], details)
            except Exception as error:
                elapsed = time.monotonic() - started
                print(type(error).__name__, str(error), flush=True)
                log_event("query", "Bounded probe did not complete: " + probe["purpose"], {
                    "purpose": probe["purpose"],
                    "query_language": "cypher",
                    "query_text": query,
                    "parameters": parameters,
                    "runtime_seconds": elapsed,
                    "timeout_seconds": timeout,
                    "outcome": "failed",
                    "result_summary": type(error).__name__ + ": " + str(error),
                    "next_action": "Inspect the failure before any larger formulation.",
                })
                log_event("failure", "Bounded query failure retained without automatic retry.", {
                    "stage": probe["purpose"],
                    "error": type(error).__name__ + ": " + str(error),
                    "diagnosis": "This is an execution failure, not biological evidence.",
                    "next_action": probe["next_action"],
                    "hypothesis_status": "active",
                })
                if "ServiceUnavailable" in type(error).__name__:
                    raise


if __name__ == "__main__":
    main()
