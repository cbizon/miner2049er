import json

import pytest

from miner2049er.benchmark_setup import validate_source


def test_validate_source_requires_matching_graph_metadata(tmp_path):
    (tmp_path / "nodes.jsonl").touch()
    (tmp_path / "edges.jsonl").touch()
    (tmp_path / "graph-metadata.json").write_text(
        json.dumps({"version": "2026_06_21"}),
        encoding="utf-8",
    )

    assert validate_source(tmp_path, "2026_06_21")["version"] == "2026_06_21"
    with pytest.raises(ValueError, match="does not match"):
        validate_source(tmp_path, "different")
