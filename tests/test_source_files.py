from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pyarrow as pa
import pytest

from miner2049er.settings import source_file
from miner2049er.source_files import open_source, split_release


def _release(tmp_path: Path, version: str = "1.0.2") -> Path:
    members = {
        "nodes.jsonl": b'{"id": "A"}\n{"id": "B"}\n',
        "edges.jsonl": b'{"subject": "A", "object": "B"}\n',
        "graph-metadata.json": json.dumps({"version": version}).encode(),
    }
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    archive = tmp_path / "release.tar.zst"
    with pa.output_stream(str(archive), compression="zstd") as output:
        output.write(raw.getvalue())
    return archive


def test_split_release_writes_streamable_zstd_members(tmp_path: Path):
    output = tmp_path / "source"
    output.mkdir()

    written = split_release(_release(tmp_path), output)

    assert set(written) == {"nodes.jsonl.zst", "edges.jsonl.zst", "graph-metadata.json"}
    with open_source(output / "nodes.jsonl.zst") as stream:
        assert [json.loads(line)["id"] for line in stream] == ["A", "B"]
    assert json.loads((output / "graph-metadata.json").read_text())["version"] == "1.0.2"


def test_open_source_reads_plain_jsonl(tmp_path: Path):
    path = tmp_path / "edges.jsonl"
    path.write_bytes(b'{"a": 1}\n{"a": 2}\n')

    with open_source(path) as stream:
        assert len(list(stream)) == 2


def test_source_compression_is_explicit(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SOURCE_COMPRESSION", "zstd")
    assert source_file(tmp_path, "edges").name == "edges.jsonl.zst"
    monkeypatch.setenv("SOURCE_COMPRESSION", "gzip")
    with pytest.raises(ValueError, match="SOURCE_COMPRESSION"):
        source_file(tmp_path, "edges")
