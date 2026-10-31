import json
from pathlib import Path

from miner2049er.benchmark_config import load_benchmark_config
from miner2049er.feedback_submitter import build_feedback_payload, submit_feedback
from miner2049er.run_artifacts import initialize_run
from tests.benchmark_examples import benchmark_rule


def _prepared_run(tmp_path: Path) -> Path:
    run_dir = initialize_run(
        runs_dir=tmp_path / "runs",
        evaluations_dir=tmp_path / "evaluations",
        authorization_dir=tmp_path / "sealed" / "authorized-runs",
        run_id="test-run",
        config=load_benchmark_config(),
        prompt_path=Path("prompts/treats-rule-mining.md"),
        deadline=None,
    )
    (run_dir / "rules.jsonl").write_text(
        json.dumps(benchmark_rule()) + "\n",
        encoding="utf-8",
    )
    predictions = [
        {
            "schema_version": "1.0",
            "run_id": "test-run",
            "round_id": "round-0001",
            "rule_id": "test-rule",
            "subject_id": f"CHEBI:{index}",
            "object_id": f"MONDO:{index}",
        }
        for index in range(1, 21)
    ]
    (run_dir / "predictions.jsonl").write_text(
        "".join(json.dumps(prediction) + "\n" for prediction in predictions),
        encoding="utf-8",
    )
    return run_dir


def test_build_feedback_payload_uses_the_active_round(tmp_path: Path):
    payload = build_feedback_payload(_prepared_run(tmp_path), "test-rule")

    assert payload["run_id"] == "test-run"
    assert payload["round_id"] == "round-0001"
    assert payload["rule_id"] == "test-rule"
    assert len(payload["predictions"]) == 20
    assert set(payload["predictions"][0]) == {"subject_id", "object_id"}


def test_submit_feedback_posts_to_the_aggregate_endpoint(monkeypatch, tmp_path: Path):
    captured = {}

    class Response:
        is_success = True
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"metrics": {"precision_lower_bound": 0.5}}

    def fake_post(url, *, json, timeout):
        captured.update({"url": url, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr("miner2049er.feedback_submitter.httpx.post", fake_post)
    result = submit_feedback(
        run_dir=_prepared_run(tmp_path),
        rule_id="test-rule",
        scorer_url="http://scorer.example",
        timeout_seconds=12.0,
    )

    assert captured["url"] == "http://scorer.example/score/feedback"
    assert captured["json"]["round_id"] == "round-0001"
    assert captured["timeout"] == 12.0
    assert result["metrics"]["precision_lower_bound"] == 0.5
