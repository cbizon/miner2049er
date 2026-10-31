import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from miner2049er.benchmark_config import load_benchmark_config
from miner2049er.benchmark_setup import main as benchmark_setup_main
from miner2049er.research_log import main as research_log_main
from miner2049er.run_validator import main as run_validator_main

FINAL_SUMMARY_DETAILS = json.dumps(
    {
        "families_explored": [],
        "surviving_rule_ids": [],
        "failed_families": [],
        "pareto_summary": "No scored rules were produced in the CLI lifecycle test.",
        "graph_gaps": [],
        "next_round_priorities": [],
    }
)


def test_cli_lifecycle_from_initialization_through_close(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = load_benchmark_config()
    runs_dir = tmp_path / "runs"
    evaluations_dir = tmp_path / "evaluations"
    sealed_dir = tmp_path / "sealed"
    sealed_manifest = sealed_dir / config.split_id / "sealed-manifest.json"
    sealed_manifest.parent.mkdir(parents=True)
    sealed_manifest.write_text("{}\n", encoding="utf-8")
    first_deadline = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "miner-benchmark-setup",
            "init-run",
            "--run-id",
            "cli-run",
            "--deadline",
            first_deadline,
            "--runs-dir",
            str(runs_dir),
            "--evaluations-dir",
            str(evaluations_dir),
            "--sealed-dir",
            str(sealed_dir),
        ],
    )
    benchmark_setup_main()
    run_dir = runs_dir / "cli-run"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "miner-log-research-event",
            "--run-dir",
            str(run_dir),
            "--event-type",
            "final_summary",
            "--summary",
            "Completed the first CLI lifecycle round.",
            "--details-json",
            FINAL_SUMMARY_DETAILS,
        ],
    )
    research_log_main()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "miner-validate-run",
            str(run_dir),
            "--evaluations-dir",
            str(evaluations_dir),
        ],
    )
    run_validator_main()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "miner-benchmark-setup",
            "finish-round",
            "--run-id",
            "cli-run",
            "--runs-dir",
            str(runs_dir),
            "--evaluations-dir",
            str(evaluations_dir),
            "--sealed-dir",
            str(sealed_dir),
        ],
    )
    benchmark_setup_main()

    second_deadline = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "miner-benchmark-setup",
            "start-round",
            "--run-id",
            "cli-run",
            "--deadline",
            second_deadline,
            "--runs-dir",
            str(runs_dir),
            "--evaluations-dir",
            str(evaluations_dir),
            "--sealed-dir",
            str(sealed_dir),
        ],
    )
    benchmark_setup_main()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "miner-log-research-event",
            "--run-dir",
            str(run_dir),
            "--event-type",
            "final_summary",
            "--summary",
            "Completed the second CLI lifecycle round.",
            "--details-json",
            FINAL_SUMMARY_DETAILS,
        ],
    )
    research_log_main()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "miner-benchmark-setup",
            "finish-round",
            "--run-id",
            "cli-run",
            "--runs-dir",
            str(runs_dir),
            "--evaluations-dir",
            str(evaluations_dir),
            "--sealed-dir",
            str(sealed_dir),
        ],
    )
    benchmark_setup_main()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "miner-benchmark-setup",
            "close-run",
            "--run-id",
            "cli-run",
            "--runs-dir",
            str(runs_dir),
            "--evaluations-dir",
            str(evaluations_dir),
            "--sealed-dir",
            str(sealed_dir),
        ],
    )
    benchmark_setup_main()

    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["round_count"] == 2
    assert manifest["current_round_id"] is None
