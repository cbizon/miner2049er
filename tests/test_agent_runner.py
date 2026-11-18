from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from miner2049er.agent_runner import (
    SAFE_SERVICE_VARIABLES,
    _append_controller_interruption_summary,
    _communicate_until_wall_deadline,
    _completion_protocol,
    _completion_validation,
    _controller_preflight,
    _deadline_recovery_prompt,
    _finish_controller_round,
    build_agent_command,
    build_agent_environment,
    build_claude_command,
    build_codex_command,
    build_sandbox_profile,
    load_run_context,
    load_service_environment,
)
from miner2049er.benchmark_config import DEFAULT_BENCHMARK_CONFIG, load_benchmark_config
from miner2049er.research_log import append_research_event
from miner2049er.run_artifacts import initialize_run, load_run_authorization
from miner2049er.settings import ROOT


def _checkpoint_details() -> dict:
    return {
        "progress": ["Recorded a checkpoint."],
        "active_hypotheses": [],
        "completed_hypotheses": [],
        "next_actions": ["Continue the active round."],
        "resource_summary": None,
    }


def _final_summary_details() -> dict:
    return {
        "families_explored": [],
        "surviving_rule_ids": [],
        "failed_families": [],
        "pareto_summary": "No scored rules were available in this test.",
        "graph_gaps": [],
        "next_round_priorities": [],
    }


def test_load_service_environment_only_returns_safe_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        """NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=local
GANDALF_URL=http://localhost:6429
SCORER_URL=http://localhost:6430
SCORER_FINAL_TOKEN=must-not-leak
""",
        encoding="utf-8",
    )
    for name in (*SAFE_SERVICE_VARIABLES, "SCORER_FINAL_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    values = load_service_environment(env_file)

    assert set(values) == set(SAFE_SERVICE_VARIABLES)
    assert "SCORER_FINAL_TOKEN" not in values


def test_load_service_environment_supplies_nonsecret_local_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        """NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=local
GANDALF_URL=http://localhost:6429
""",
        encoding="utf-8",
    )
    for name in SAFE_SERVICE_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    values = load_service_environment(env_file)

    assert values["NEO4J_USER"] == "neo4j"
    assert values["SCORER_URL"] == "http://127.0.0.1:6430"


def test_load_run_context_requires_offset_deadline(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    round_dir = run_dir / "rounds" / "round-0001"
    round_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "status": "running",
                "current_round_id": "round-0001",
                "run_id": "test-run",
            }
        ),
        encoding="utf-8",
    )
    (round_dir / "agent-prompt.md").write_text("prompt", encoding="utf-8")
    (round_dir / "round.json").write_text(
        json.dumps(
            {
                "status": "running",
                "deadline": "2026-08-18T21:00:00",
                "agent_prompt_path": "rounds/round-0001/agent-prompt.md",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="UTC offset"):
        load_run_context(run_dir)


def test_agent_environment_does_not_inherit_operator_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "model-key")
    monkeypatch.setenv("SCORER_FINAL_TOKEN", "final-token")
    services = {name: f"value-{name}" for name in SAFE_SERVICE_VARIABLES}

    environment = build_agent_environment(
        runtime_dir=tmp_path,
        service_environment=services,
        api_key_env="AZURE_OPENAI_API_KEY",
    )

    assert environment["AZURE_OPENAI_API_KEY"] == "model-key"
    assert "SCORER_FINAL_TOKEN" not in environment
    assert all(environment[name] == services[name] for name in SAFE_SERVICE_VARIABLES)


def test_claude_agent_environment_does_not_require_or_inherit_model_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    services = {name: f"value-{name}" for name in SAFE_SERVICE_VARIABLES}

    environment = build_agent_environment(
        runtime_dir=tmp_path,
        service_environment=services,
        api_key_env="AZURE_OPENAI_API_KEY",
        agent_runtime="claude",
    )

    assert "AZURE_OPENAI_API_KEY" not in environment
    assert environment["HOME"] == str(tmp_path / "home")
    assert all(environment[name] == services[name] for name in SAFE_SERVICE_VARIABLES)


def test_codex_shell_environment_excludes_model_key() -> None:
    command = build_codex_command(
        model="test-model",
        model_provider="azure",
        model_base_url="https://example.test/",
        api_key_env="AZURE_OPENAI_API_KEY",
        reasoning_effort="high",
    )
    include_argument = next(
        value for value in command if value.startswith("shell_environment_policy.include_only=")
    )

    assert "NEO4J_PASSWORD" in include_argument
    assert "AZURE_OPENAI_API_KEY" not in include_argument
    assert "--ignore-user-config" in command
    assert "--dangerously-bypass-approvals-and-sandbox" in command
    assert 'model_reasoning_effort="high"' in command


def test_claude_command_uses_requested_model_effort_and_bounded_tools() -> None:
    command = build_claude_command(
        model="opus",
        reasoning_effort="low",
    )

    assert command[:2] == [
        "/Users/bizon/.nvm/versions/node/v22.18.0/bin/claude",
        "-p",
    ]
    assert command[command.index("--model") + 1] == "opus"
    assert command[command.index("--effort") + 1] == "low"
    assert command[command.index("--tools") + 1] == "Bash,Edit,Read,Write,Glob,Grep"
    assert "WebSearch" not in command
    assert "WebFetch" not in command
    assert "--no-session-persistence" in command


def test_agent_command_dispatches_to_claude() -> None:
    command = build_agent_command(
        agent_runtime="claude",
        model="sonnet",
        model_provider="anthropic",
        model_base_url="ignored",
        api_key_env="ignored",
        reasoning_effort="low",
    )

    assert command == build_claude_command(
        model="sonnet",
        reasoning_effort="low",
    )


def test_sandbox_profile_denies_hidden_inputs(tmp_path: Path) -> None:
    evaluations_dir = tmp_path / "evaluations"
    profile = build_sandbox_profile(
        run_dir=tmp_path / "runs" / "test",
        runtime_dir=tmp_path / ".run",
        sealed_root=tmp_path / "sealed",
        source_root=tmp_path / "source",
        evaluations_dir=evaluations_dir,
    )

    assert f'(subpath "{tmp_path / "sealed"}")' in profile
    assert f'(subpath "{tmp_path / "source"}")' in profile
    assert f'(subpath "{Path.home() / ".codex" / "sessions"}")' in profile
    assert f'(subpath "{ROOT / "results"}")' in profile
    assert f'(subpath "{ROOT / "rules"}")' in profile
    assert f'(deny file-write* (subpath "{evaluations_dir}"))' in profile
    assert (
        f'(deny file-read* file-write* (subpath "{evaluations_dir}"))'
        not in profile
    )
    assert "unix-socket" in profile


def test_completion_protocol_requires_summary_then_official_validation() -> None:
    deadline = datetime.now(UTC) + timedelta(hours=1)
    protocol = _completion_protocol(
        context={
            "run_dir": Path("/tmp/test-run"),
            "round_id": "round-0001",
        },
        wrap_up_at=deadline - timedelta(minutes=15),
        evaluations_dir=Path("/work/evaluations"),
    )

    assert protocol.index("final_summary") < protocol.index("miner-validate-run")
    assert "Do not sleep" in protocol
    assert "/work/evaluations" in protocol


def test_process_wait_rechecks_wall_clock_after_host_sleep() -> None:
    deadline = datetime(2026, 8, 19, 2, tzinfo=UTC)
    observed_times = iter(
        (
            deadline - timedelta(minutes=30),
            deadline - timedelta(minutes=10),
            deadline + timedelta(hours=2),
        )
    )

    class SuspendedProcess:
        def __init__(self) -> None:
            self.inputs: list[str | None] = []

        def communicate(self, value: str | None, timeout: float) -> None:
            self.inputs.append(value)
            raise subprocess.TimeoutExpired("codex", timeout)

    process = SuspendedProcess()

    exited = _communicate_until_wall_deadline(
        process,  # type: ignore[arg-type]
        "prompt",
        deadline,
        poll_seconds=5,
        now=lambda: next(observed_times),
    )

    assert exited is False
    assert process.inputs == ["prompt", None]


def test_deadline_recovery_prompt_forbids_more_research() -> None:
    deadline = datetime(2026, 8, 19, 2, tzinfo=UTC)
    prompt = _deadline_recovery_prompt(
        {
            "run_dir": Path("/tmp/test-run"),
            "round_id": "round-0001",
        },
        deadline,
    )

    assert "Do not launch new hypotheses" in prompt
    assert "Do not" in prompt and "query Neo4j or Gandalf" in prompt
    assert "final_summary" in prompt
    assert "interrupted work succeeded" in prompt


def test_controller_fallback_summary_makes_valid_run_finishable(
    tmp_path: Path,
) -> None:
    config = load_benchmark_config()
    evaluations_dir = tmp_path / "evaluations"
    authorization_dir = tmp_path / "sealed" / config.split_id / "authorized-runs"
    run_dir = initialize_run(
        runs_dir=tmp_path / "runs",
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        run_id="test-run",
        config=config,
        prompt_path=ROOT / "prompts" / "treats-rule-mining.md",
        deadline=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )

    event = _append_controller_interruption_summary(
        context={
            "run_id": "test-run",
            "round_id": "round-0001",
            "run_dir": run_dir,
        },
        evaluations_dir=evaluations_dir,
        invocations=2,
        last_exit_code=1,
        reason="wall_clock_deadline_elapsed",
        validation_error="ValueError: missing final_summary",
    )
    validation, error = _completion_validation({"run_dir": run_dir}, evaluations_dir)

    assert event["event_type"] == "final_summary"
    assert event["details"]["completion_mode"] == "controller_interruption_fallback"
    assert event["details"]["interrupted"] is True
    assert validation is not None
    assert error is None


def test_controller_finalization_seals_a_valid_round_boundary(tmp_path: Path) -> None:
    config = load_benchmark_config()
    evaluations_dir = tmp_path / "evaluations"
    authorization_dir = tmp_path / "sealed" / config.split_id / "authorized-runs"
    run_dir = initialize_run(
        runs_dir=tmp_path / "runs",
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        run_id="test-run",
        config=config,
        prompt_path=ROOT / "prompts" / "treats-rule-mining.md",
        deadline=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )
    append_research_event(
        run_dir=run_dir,
        event_type="final_summary",
        summary="The round completed and its artifacts were rerun.",
        details=_final_summary_details(),
    )
    context = {"run_dir": run_dir}

    preflight = _controller_preflight(
        context={
            **context,
            "run_id": "test-run",
            "round_id": "round-0001",
        },
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        config_path=DEFAULT_BENCHMARK_CONFIG,
    )
    validation, error = _completion_validation(context, evaluations_dir)
    manifest, sealed_validation = _finish_controller_round(
        context=context,
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        config_path=DEFAULT_BENCHMARK_CONFIG,
    )

    assert error is None
    assert preflight == validation
    assert validation is not None
    assert manifest["status"] == "round_complete"
    assert manifest["current_round_id"] is None
    assert sealed_validation == validation
    authorization = load_run_authorization(authorization_dir, "test-run")
    assert authorization["status"] == "round_complete"
    assert authorization["current_round_id"] is None


def test_controller_refuses_to_seal_out_of_order_research_events(
    tmp_path: Path,
) -> None:
    config = load_benchmark_config()
    evaluations_dir = tmp_path / "evaluations"
    authorization_dir = tmp_path / "sealed" / config.split_id / "authorized-runs"
    run_dir = initialize_run(
        runs_dir=tmp_path / "runs",
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        run_id="test-run",
        config=config,
        prompt_path=ROOT / "prompts" / "treats-rule-mining.md",
        deadline=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )
    first = append_research_event(
        run_dir=run_dir,
        event_type="checkpoint",
        summary="Recorded a checkpoint.",
        details=_checkpoint_details(),
    )
    second = append_research_event(
        run_dir=run_dir,
        event_type="final_summary",
        summary="Recorded the final summary.",
        details=_final_summary_details(),
    )
    first["timestamp"] = "2026-08-18T18:01:24-04:00"
    second["timestamp"] = "2026-08-18T18:00:11-04:00"
    (run_dir / "research-log.jsonl").write_text(
        f"{json.dumps(first)}\n{json.dumps(second)}\n",
        encoding="utf-8",
    )

    validation, error = _completion_validation({"run_dir": run_dir}, evaluations_dir)

    assert validation is None
    assert error == "ValueError: Research event timestamps must be nondecreasing"


def test_container_isolation_refuses_visible_sealed_data(tmp_path, monkeypatch):
    from miner2049er.agent_runner import verify_container_isolation

    monkeypatch.delenv("SCORER_FINAL_TOKEN", raising=False)
    monkeypatch.delenv("BENCHMARK_SEALED_DIR", raising=False)
    absent = tmp_path / "not-mounted"
    verify_container_isolation(absent)

    sealed = tmp_path / "sealed"
    sealed.mkdir()
    with pytest.raises(RuntimeError, match="Sealed paths are visible"):
        verify_container_isolation(sealed)


def test_container_isolation_refuses_operator_token(tmp_path, monkeypatch):
    from miner2049er.agent_runner import verify_container_isolation

    monkeypatch.setenv("SCORER_FINAL_TOKEN", "operator-only")
    with pytest.raises(RuntimeError, match="Operator-only variables"):
        verify_container_isolation(tmp_path / "not-mounted")


def test_container_claude_token_comes_from_environment(monkeypatch):
    from miner2049er.agent_runner import _container_claude_token

    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    with pytest.raises(ValueError, match="CLAUDE_CODE_OAUTH_TOKEN"):
        _container_claude_token()
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token")
    assert _container_claude_token() == "token"


SERVICE_ENVIRONMENT = {
    "NEO4J_URI": "bolt://miner-neo4j:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "secret",
    "GANDALF_URL": "http://miner-gandalf:6429",
    "SCORER_URL": "http://miner-scorer:6430",
}


def test_controller_passes_only_service_variables():
    from miner2049er.agent_runner import controller_service_environment

    environment = controller_service_environment({**SERVICE_ENVIRONMENT, "OTHER": "x"})

    assert environment == SERVICE_ENVIRONMENT


@pytest.mark.parametrize("value", [None, ""])
def test_controller_requires_gandalf_url(value):
    from miner2049er.agent_runner import controller_service_environment

    environ = {**SERVICE_ENVIRONMENT}
    if value is None:
        del environ["GANDALF_URL"]
    else:
        environ["GANDALF_URL"] = value
    with pytest.raises(ValueError, match="GANDALF_URL"):
        controller_service_environment(environ)


def test_container_mode_leaves_sealing_to_the_operator(tmp_path):
    from miner2049er.agent_runner import _seal_controller_round

    context = {
        "run_id": "run",
        "round_id": "round-0001",
        "run_dir": tmp_path,
        "deadline": datetime.now(UTC) + timedelta(hours=1),
    }
    status = _seal_controller_round(
        context=context,
        runtime_dir=tmp_path,
        evaluations_dir=tmp_path,
        authorization_dir=None,
        config_path=tmp_path / "unused.json",
        invocations=1,
        last_exit_code=0,
        validation={"rules": 0},
        completion_mode="agent_normal",
    )

    assert status == 0
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["status"] == "awaiting_operator_seal"
