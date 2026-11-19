"""Builds real Gandalf stores from a tiny graph and checks them over TRAPI."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from miner2049er.gandalf_holdout_check import check_holdout, sample_pairs

PREDICATES = [
    "biolink:treats",
    "biolink:ameliorates_condition",
    "biolink:preventative_for_condition",
]
TRAINING = {("CHEBI:1", "MONDO:1")}
FEEDBACK = {("CHEBI:1", "MONDO:2")}
FINAL = {("CHEBI:2", "MONDO:3")}


def _edge(index: int, subject: str, predicate: str, object_: str) -> dict:
    return {
        "id": f"edge-{index}",
        "category": ["biolink:Association"],
        "subject": subject,
        "predicate": predicate,
        "object": object_,
        "sources": [{"resource_id": "infores:test", "resource_role": "primary_knowledge_source"}],
        "knowledge_level": "knowledge_assertion",
        "agent_type": "manual_agent",
    }


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return path


@pytest.fixture
def graph_files(tmp_path):
    nodes = [
        {"id": node_id, "category": [category], "name": node_id}
        for node_id, category in [
            ("CHEBI:1", "biolink:SmallMolecule"),
            ("CHEBI:2", "biolink:SmallMolecule"),
            ("MONDO:1", "biolink:Disease"),
            ("MONDO:2", "biolink:Disease"),
            ("MONDO:3", "biolink:Disease"),
        ]
    ]
    edges = [
        _edge(1, "CHEBI:1", "biolink:treats", "MONDO:1"),
        _edge(2, "CHEBI:1", "biolink:treats", "MONDO:2"),
        _edge(3, "CHEBI:2", "biolink:ameliorates_condition", "MONDO:3"),
        _edge(4, "CHEBI:2", "biolink:related_to", "MONDO:1"),
    ]
    labels = tmp_path / "labels"
    labels.mkdir()
    for name, pairs in [("feedback", FEEDBACK), ("final", FINAL)]:
        _write_jsonl(
            labels / f"{name}.jsonl",
            [{"subject_id": s, "object_id": o} for s, o in sorted(pairs)],
        )
    return {
        "nodes": _write_jsonl(tmp_path / "nodes.jsonl", nodes),
        "edges": _write_jsonl(tmp_path / "edges.jsonl", edges),
        "labels": labels,
    }


def _build(graph_files: dict, output: Path, *, exclude: bool) -> Path:
    command = [
        str(Path(sys.executable).parent / "miner-build-gandalf"),
        "--nodes", str(graph_files["nodes"]),
        "--edges", str(graph_files["edges"]),
        "--output", str(output),
    ]
    if exclude:
        for name in ("feedback", "final"):
            command += ["--exclude-labels", str(graph_files["labels"] / f"{name}.jsonl")]
        command += [arg for predicate in PREDICATES for arg in ("--target-predicate", predicate)]
    subprocess.run(command, check=True, env={**os.environ, "TMPDIR": str(output.parent)})
    return output


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def serve():
    servers: list[subprocess.Popen] = []

    def start(graph: Path) -> str:
        port = _free_port()
        server = subprocess.Popen(
            [
                str(Path(sys.executable).parent / "uvicorn"),
                "miner2049er.gandalf_server:APP",
                "--host", "127.0.0.1", "--port", str(port),
            ],
            env={
                **os.environ,
                "GANDALF_GRAPH_PATH": str(graph),
                "GANDALF_GRAPH_FORMAT": "mmap",
                "GANDALF_OTEL_ENABLED": "false",
            },
        )
        servers.append(server)
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError(f"Gandalf exited with {server.returncode}")
            try:
                if httpx.get(f"{url}/metadata", timeout=2).is_success:
                    return url
            except httpx.TransportError:
                pass
            time.sleep(0.5)
        raise TimeoutError("Gandalf did not become ready")

    yield start
    for server in servers:
        server.terminate()
        server.wait(timeout=30)


def _check(url: str) -> dict:
    return check_holdout(
        gandalf_url=url,
        holdout={"feedback": FEEDBACK, "final": FINAL},
        training=TRAINING,
        predicates=PREDICATES,
        sample_size=10,
        seed="test",
    )


def test_filtered_store_hides_holdout_and_keeps_training(tmp_path, graph_files, serve):
    url = serve(_build(graph_files, tmp_path / "filtered", exclude=True))

    summary = _check(url)

    assert summary["feedback"] == {"sampled": 1, "found": 0}
    assert summary["final"] == {"sampled": 1, "found": 0}
    assert summary["training"] == {"sampled": 1, "found": 1}


def test_unfiltered_store_fails_the_check(tmp_path, graph_files, serve):
    url = serve(_build(graph_files, tmp_path / "unfiltered", exclude=False))

    with pytest.raises(AssertionError, match="Held-out pairs visible"):
        _check(url)


def test_missing_training_pairs_fail_the_check(tmp_path, graph_files, serve):
    url = serve(_build(graph_files, tmp_path / "filtered", exclude=True))

    with pytest.raises(AssertionError, match="Training pairs missing"):
        check_holdout(
            gandalf_url=url,
            holdout={"feedback": FEEDBACK},
            training={("CHEBI:2", "MONDO:2")},
            predicates=PREDICATES,
            sample_size=10,
            seed="test",
        )


def test_sample_is_deterministic_and_bounded():
    pairs = {(f"CHEBI:{i}", f"MONDO:{i}") for i in range(100)}

    first = sample_pairs(pairs, 10, "seed")

    assert first == sample_pairs(pairs, 10, "seed")
    assert len(first) == 10
    assert len(sample_pairs(pairs, 1000, "seed")) == 100
    with pytest.raises(ValueError):
        sample_pairs(set(), 10, "seed")
