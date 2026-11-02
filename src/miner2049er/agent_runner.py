from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from miner2049er.benchmark_config import (
    DEFAULT_BENCHMARK_CONFIG,
    load_benchmark_config,
)
from miner2049er.research_log import append_research_event
from miner2049er.run_artifacts import (
    DEFAULT_EVALUATIONS_DIR,
    finish_round,
    load_run_authorization,
    record_agent_execution,
    validate_round_completion,
    validate_run_directory,
)
from miner2049er.settings import ROOT

SAFE_SERVICE_VARIABLES = (
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "GANDALF_URL",
    "SCORER_URL",
)
DEFAULT_SERVICE_VALUES = {
    "NEO4J_USER": "neo4j",
    "SCORER_URL": "http://127.0.0.1:6430",
}
SHELL_VARIABLES = (
    "HOME",
    "PATH",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "TERM",
    *SAFE_SERVICE_VARIABLES,
)
DEFAULT_MODEL = "gpt-5.6-sol"
DEFAULT_MODEL_PROVIDER = "azure"
DEFAULT_MODEL_BASE_URL = "https://renci-analytics.openai.azure.com/openai/v1/"
DEFAULT_MODEL_API_KEY_ENV = "AZURE_OPENAI_API_KEY"
DEFAULT_MODEL_CATALOG = Path("/Users/bizon/.codex/models.azure-codex.json")
DEFAULT_REASONING_EFFORT = "xhigh"
DEFAULT_AGENT_RUNTIME = "codex"
CLAUDE_BINARY = Path("/Users/bizon/.nvm/versions/node/v22.18.0/bin/claude")
# sandbox-exec: the controller confines the agent with a macOS sandbox profile and
#   seals the round itself.
# container: the pod is the boundary. The agent container mounts no sealed data
#   and holds no final-scoring token (checked at startup), Claude's token comes
#   from CLAUDE_CODE_OAUTH_TOKEN, and an operator Job seals the round afterwards.
ISOLATION_MODES = ("sandbox-exec", "container")
CONTAINER_SEALED_PATHS = (Path("/sealed"),)
CONTAINER_FORBIDDEN_VARIABLES = ("SCORER_FINAL_TOKEN", "BENCHMARK_SEALED_DIR")
CLAUDE_KEYCHAIN_SERVICE = "Claude Code-credentials"
CLAUDE_REFRESH_MODEL = "haiku"
CLAUDE_REFRESH_BUFFER_SECONDS = 600
DEFAULT_DEADLINE_POLL_SECONDS = 5
DEFAULT_RECOVERY_WRAP_UP_SECONDS = 600


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_dotenv_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid environment line {line_number} in {path}")
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip("\"'")
    return values


def load_service_environment(env_path: Path) -> dict[str, str]:
    dotenv = _load_dotenv_values(env_path)
    values = {
        name: os.environ.get(name)
        or dotenv.get(name)
        or DEFAULT_SERVICE_VALUES.get(name, "")
        for name in SAFE_SERVICE_VARIABLES
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(f"Missing agent service variables: {', '.join(missing)}")
    return values


def load_run_context(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if manifest["status"] != "running" or not manifest["current_round_id"]:
        raise ValueError(f"Run is not active: {run_dir}")
    round_id = manifest["current_round_id"]
    round_dir = run_dir / "rounds" / round_id
    round_manifest = json.loads((round_dir / "round.json").read_text(encoding="utf-8"))
    if round_manifest["status"] != "running":
        raise ValueError(f"Round is not active: {round_id}")
    deadline_text = round_manifest["deadline"]
    if not deadline_text:
        raise ValueError("The restricted runner requires a round deadline")
    deadline = datetime.fromisoformat(deadline_text)
    if deadline.tzinfo is None or deadline.utcoffset() is None:
        raise ValueError("The round deadline must include a UTC offset")
    prompt_path = run_dir / round_manifest["agent_prompt_path"]
    if not prompt_path.is_file():
        raise FileNotFoundError(prompt_path)
    return {
        "run_id": manifest["run_id"],
        "round_id": round_id,
        "run_dir": run_dir,
        "round_dir": round_dir,
        "prompt_path": prompt_path,
        "deadline": deadline,
    }


def _sandbox_string(path: Path | str) -> str:
    return json.dumps(str(path))


def build_sandbox_profile(
    *,
    run_dir: Path,
    runtime_dir: Path,
    sealed_root: Path,
    source_root: Path,
    evaluations_dir: Path = DEFAULT_EVALUATIONS_DIR,
) -> str:
    denied_read_write_paths = (
        sealed_root.resolve(),
        source_root.resolve(),
        ROOT / ".env",
        ROOT / "data" / "scorer-state",
        ROOT / "results",
        ROOT / "rules",
        Path.home() / ".codex" / "sessions",
        Path.home() / ".codex" / "archived_sessions",
        Path.home() / ".codex" / "memories",
        Path.home() / ".codex" / "state_5.sqlite",
        Path.home() / ".codex" / "history.jsonl",
        Path.home() / ".codex" / "auth.json",
        Path.home() / ".docker" / "run" / "docker.sock",
        Path("/var/run/docker.sock"),
    )
    denied_write_paths = (evaluations_dir.resolve(),)
    socket_paths = denied_read_write_paths[-2:]
    rules = [
        "(version 1)",
        "(allow default)",
    ]
    for path in denied_read_write_paths:
        rules.append(
            f"(deny file-read* file-write* (subpath {_sandbox_string(path)}))"
        )
    for path in denied_write_paths:
        rules.append(f"(deny file-write* (subpath {_sandbox_string(path)}))")
    for socket_path in socket_paths:
        rules.append(
            "(deny network-outbound "
            f"(remote unix-socket (path {_sandbox_string(socket_path)})))"
        )
    rules.extend(
        [
            f"; Public run directory: {_sandbox_string(run_dir.resolve())}",
            f"; Controller runtime directory: {_sandbox_string(runtime_dir.resolve())}",
            "",
        ]
    )
    return "\n".join(rules)


def build_agent_environment(
    *,
    runtime_dir: Path,
    service_environment: dict[str, str],
    api_key_env: str,
    agent_runtime: str = DEFAULT_AGENT_RUNTIME,
    isolation: str = "sandbox-exec",
    evaluations_dir: Path = DEFAULT_EVALUATIONS_DIR,
) -> dict[str, str]:
    home = runtime_dir / "home"
    codex_home = runtime_dir / "codex-home"
    temporary = runtime_dir / "tmp"
    for path in (home, codex_home, temporary):
        path.mkdir(parents=True, exist_ok=True)
    path = ":".join(
        (
            str(ROOT / ".venv" / "bin"),
            "/Users/bizon/.local/bin",
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
        )
    )
    environment = {
        "HOME": str(home),
        "CODEX_HOME": str(codex_home),
        "PATH": path,
        "TMPDIR": str(temporary),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "TERM": "dumb",
        "MINER_EVALUATIONS_DIR": str(evaluations_dir),
        **service_environment,
    }
    if isolation == "container":
        # The image's venv is prebuilt and read-only to the agent's user; the
        # prompt's `uv run ...` commands must use it as is.
        environment["UV_NO_SYNC"] = "1"
    if agent_runtime == "codex":
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ValueError(
                f"Missing model credential environment variable: {api_key_env}"
            )
        environment[api_key_env] = api_key
    elif agent_runtime != "claude":
        raise ValueError(f"Unsupported agent runtime: {agent_runtime}")
    return environment


def build_codex_command(
    *,
    model: str,
    model_provider: str,
    model_base_url: str,
    api_key_env: str,
    reasoning_effort: str,
) -> list[str]:
    provider = json.dumps(model_provider)
    provider_config = (
        "{"
        f"name={json.dumps(model_provider)},"
        f"base_url={json.dumps(model_base_url)},"
        f"env_key={json.dumps(api_key_env)}"
        "}"
    )
    include_only = json.dumps(list(SHELL_VARIABLES), separators=(",", ":"))
    return [
        "/Users/bizon/.local/bin/codex",
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C",
        str(ROOT),
        "-c",
        f"model_provider={provider}",
        "-c",
        f"model={json.dumps(model)}",
        "-c",
        f"model_reasoning_effort={json.dumps(reasoning_effort)}",
        "-c",
        f"model_catalog_json={json.dumps(str(DEFAULT_MODEL_CATALOG))}",
        "-c",
        f"model_providers.{model_provider}={provider_config}",
        "-c",
        'web_search="disabled"',
        "-c",
        'memories.use_memories=false',
        "-c",
        'shell_environment_policy.inherit="all"',
        "-c",
        f"shell_environment_policy.include_only={include_only}",
        "-",
    ]


def _claude_binary(isolation: str) -> str:
    if isolation == "sandbox-exec":
        return str(CLAUDE_BINARY)
    found = shutil.which("claude")
    if not found:
        raise FileNotFoundError("claude is not on PATH in this container")
    return found


def build_claude_command(
    *,
    model: str,
    reasoning_effort: str,
    isolation: str = "sandbox-exec",
) -> list[str]:
    return [
        _claude_binary(isolation),
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        "--effort",
        reasoning_effort,
        "--no-session-persistence",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--dangerously-skip-permissions",
        "--tools",
        "Bash,Edit,Read,Write,Glob,Grep",
    ]


def build_agent_command(
    *,
    agent_runtime: str,
    model: str,
    model_provider: str,
    model_base_url: str,
    api_key_env: str,
    reasoning_effort: str,
    isolation: str = "sandbox-exec",
) -> list[str]:
    if agent_runtime == "codex":
        if isolation != "sandbox-exec":
            raise ValueError("Container isolation is implemented for Claude only")
        return build_codex_command(
            model=model,
            model_provider=model_provider,
            model_base_url=model_base_url,
            api_key_env=api_key_env,
            reasoning_effort=reasoning_effort,
        )
    if agent_runtime == "claude":
        return build_claude_command(
            model=model,
            reasoning_effort=reasoning_effort,
            isolation=isolation,
        )
    raise ValueError(f"Unsupported agent runtime: {agent_runtime}")


def _read_claude_keychain_credentials() -> dict[str, Any]:
    account = os.environ.get("USER") or getpass.getuser()
    result = subprocess.run(
        [
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            account,
            "-w",
            "-s",
            CLAUDE_KEYCHAIN_SERVICE,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            "Claude Code subscription credentials are unavailable in macOS "
            f"Keychain: {result.stderr.strip()}"
        )
    try:
        credentials = json.loads(result.stdout)["claudeAiOauth"]
        access_token = credentials["accessToken"]
        expires_at = int(credentials["expiresAt"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Claude Code Keychain credentials are malformed") from error
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("Claude Code Keychain credentials have no access token")
    return {
        "access_token": access_token,
        "expires_at": expires_at,
    }


def _refresh_claude_keychain_credentials() -> None:
    result = subprocess.run(
        [
            str(CLAUDE_BINARY),
            "-p",
            "--output-format",
            "json",
            "--model",
            CLAUDE_REFRESH_MODEL,
            "--effort",
            "low",
            "--no-session-persistence",
            "--disable-slash-commands",
            "--strict-mcp-config",
            "--tools",
            "",
        ],
        cwd=ROOT,
        input="Reply with exactly OK.",
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            "Claude Code could not refresh its subscription credential: "
            f"{result.stderr.strip()}"
        )


def _load_claude_access_token() -> str:
    credentials = _read_claude_keychain_credentials()
    refresh_at = credentials["expires_at"] / 1000 - CLAUDE_REFRESH_BUFFER_SECONDS
    if time.time() >= refresh_at:
        _refresh_claude_keychain_credentials()
        credentials = _read_claude_keychain_credentials()
        if time.time() >= credentials["expires_at"] / 1000:
            raise ValueError("Claude Code refreshed credential is already expired")
    return credentials["access_token"]


def _open_one_shot_secret_pipe(secret: str) -> int:
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, secret.encode("utf-8"))
    finally:
        os.close(write_fd)
    return read_fd


def _container_claude_token() -> str:
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if not token:
        raise ValueError("CLAUDE_CODE_OAUTH_TOKEN is not set in the agent container")
    return token


def verify_container_isolation(sealed_root: Path) -> None:
    """Fail unless this container really lacks sealed labels and the final token."""
    visible = [
        str(path)
        for path in (*CONTAINER_SEALED_PATHS, sealed_root)
        if path.exists()
    ]
    if visible:
        raise RuntimeError(f"Sealed paths are visible to the agent container: {visible}")
    present = [name for name in CONTAINER_FORBIDDEN_VARIABLES if os.environ.get(name)]
    if present:
        raise RuntimeError(f"Operator-only variables are set: {present}")


def _start_agent_process(
    *,
    command: list[str],
    agent_runtime: str,
    environment: dict[str, str],
    events: Any,
    errors: Any,
    isolation: str = "sandbox-exec",
) -> subprocess.Popen[str]:
    child_environment = dict(environment)
    credential_fd: int | None = None
    pass_fds: tuple[int, ...] = ()
    if agent_runtime == "claude":
        token = (
            _load_claude_access_token()
            if isolation == "sandbox-exec"
            else _container_claude_token()
        )
        credential_fd = _open_one_shot_secret_pipe(token)
        child_environment["CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR"] = str(
            credential_fd
        )
        pass_fds = (credential_fd,)
    try:
        return subprocess.Popen(
            command,
            cwd=ROOT,
            env=child_environment,
            stdin=subprocess.PIPE,
            stdout=events,
            stderr=errors,
            text=True,
            pass_fds=pass_fds,
        )
    finally:
        if credential_fd is not None:
            os.close(credential_fd)


def verify_sandbox(
    profile_path: Path,
    context: dict[str, Any],
    sealed_root: Path,
    evaluations_dir: Path = DEFAULT_EVALUATIONS_DIR,
) -> None:
    allowed = subprocess.run(
        [
            "/usr/bin/sandbox-exec",
            "-f",
            str(profile_path),
            "/usr/bin/head",
            "-n",
            "1",
            str(context["prompt_path"]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if allowed.returncode:
        raise RuntimeError(f"Sandbox blocked the public prompt: {allowed.stderr.strip()}")

    forbidden = (
        ROOT / ".env",
        ROOT / "results",
        ROOT / "rules",
        sealed_root,
        Path("/Users/bizon/Projects/ROBOKOP/ORION/graph-metadata.json"),
    )
    for path in forbidden:
        attempt = subprocess.run(
            [
                "/usr/bin/sandbox-exec",
                "-f",
                str(profile_path),
                "/usr/bin/stat",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if attempt.returncode == 0:
            raise RuntimeError(f"Sandbox unexpectedly allowed hidden path: {path}")

    evaluations_dir.mkdir(parents=True, exist_ok=True)
    readable = subprocess.run(
        [
            "/usr/bin/sandbox-exec",
            "-f",
            str(profile_path),
            "/usr/bin/stat",
            str(evaluations_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if readable.returncode:
        raise RuntimeError(
            "Sandbox blocked aggregate evaluations needed by the run validator: "
            f"{readable.stderr.strip()}"
        )
    write_probe = evaluations_dir / f".sandbox-write-probe-{os.getpid()}"
    writable = subprocess.run(
        [
            "/usr/bin/sandbox-exec",
            "-f",
            str(profile_path),
            "/usr/bin/touch",
            str(write_probe),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if writable.returncode == 0:
        write_probe.unlink(missing_ok=True)
        raise RuntimeError("Sandbox unexpectedly allowed evaluation-file writes")


def _state_path(runtime_dir: Path) -> Path:
    return runtime_dir / "state.json"


def _write_state(
    runtime_dir: Path,
    context: dict[str, Any],
    **updates: Any,
) -> None:
    path = _state_path(runtime_dir)
    state = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.is_file()
        else {
            "run_id": context["run_id"],
            "round_id": context["round_id"],
            "deadline": context["deadline"].isoformat(),
            "started_at": datetime.now().astimezone().isoformat(),
            "invocations": 0,
        }
    )
    state.update(updates)
    state["updated_at"] = datetime.now().astimezone().isoformat()
    _atomic_write_json(path, state)


def _stop_process(
    process: subprocess.Popen[str],
    grace_seconds: int,
) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def _communicate_until_wall_deadline(
    process: subprocess.Popen[str],
    prompt_text: str,
    deadline: datetime,
    poll_seconds: int,
    *,
    now: Callable[[], datetime] | None = None,
) -> bool:
    now = now or (lambda: datetime.now(deadline.tzinfo))
    pending_input: str | None = prompt_text
    while True:
        remaining = (deadline - now()).total_seconds()
        if remaining <= 0:
            return False
        try:
            process.communicate(
                pending_input,
                timeout=min(float(poll_seconds), remaining),
            )
            return True
        except subprocess.TimeoutExpired:
            pending_input = None


def _deadline_recovery_prompt(context: dict[str, Any], deadline: datetime) -> str:
    return f"""
# Deadline Recovery Wrap-Up

The wall-clock deadline {deadline.isoformat()} has passed after the controller
or host was suspended. Do not launch new hypotheses, query Neo4j or Gandalf,
submit feedback, or modify existing rule, prediction, evaluation, or Neo4j
artifact records.

Read the existing append-only artifacts for {context["round_id"]}. Append one
honest `final_summary` event using `uv run miner-log-research-event` that:

- states that deadline recovery interrupted the normal wrap-up;
- summarizes completed rule families, evaluations, failures, and graph gaps;
- identifies work that was not rerun or completed;
- does not claim that interrupted work succeeded.

Then run `uv run miner-validate-run {context["run_dir"]}` and exit immediately.
"""


def _append_controller_interruption_summary(
    *,
    context: dict[str, Any],
    evaluations_dir: Path,
    invocations: int,
    last_exit_code: int | None,
    reason: str,
    validation_error: str | None,
) -> dict[str, Any]:
    validation = validate_run_directory(context["run_dir"], evaluations_dir)
    return append_research_event(
        run_dir=context["run_dir"],
        event_type="final_summary",
        summary=(
            "The controller closed the round after deadline recovery because the "
            "agent did not complete its own final summary."
        ),
        details={
            "families_explored": [],
            "surviving_rule_ids": [],
            "failed_families": [],
            "pareto_summary": (
                "Not recomputed because deadline recovery interrupted the normal "
                "agent wrap-up."
            ),
            "graph_gaps": [
                (
                    "The controller cannot infer unfinished biological hypotheses "
                    "from aggregate artifact counts."
                )
            ],
            "next_round_priorities": [
                "Review unfinished hypotheses and rerun surviving rules in a new round."
            ],
            "completion_mode": "controller_interruption_fallback",
            "interrupted": True,
            "reason": reason,
            "agent_invocations": invocations,
            "last_agent_exit_code": last_exit_code,
            "pre_summary_validation": validation,
            "prior_completion_error": validation_error,
            "limitations": [
                "The agent did not complete the requested end-of-round synthesis.",
                "Existing artifacts were schema-validated but were not rerun by the controller.",
                "Start another round to continue or independently review unfinished hypotheses.",
            ],
        },
    )


def _completion_protocol(
    *,
    context: dict[str, Any],
    wrap_up_at: datetime,
    evaluations_dir: Path,
) -> str:
    return f"""

# Controller Completion Protocol

- Stop launching new hypotheses at {wrap_up_at.isoformat()} and use the
  remaining time for reruns, artifact checks, and synthesis.
- Append research events only with `uv run miner-log-research-event`; never
  write `research-log.jsonl` directly.
- Aggregate evaluator output is in {evaluations_dir} (read-only; the
  `MINER_EVALUATIONS_DIR` variable points there, so the run validator sees
  it). Ignore the relative `evaluations` path recorded in older run.json
  files. The held-out labels and scorer state remain inaccessible.
- Append one `final_summary` event for {context["round_id"]} with
  `uv run miner-log-research-event`, including plain-language
  `experiments`, at most five `questions_for_operator`, and
  `proposed_directions` for tomorrow's human review.
- Then run the final
  `uv run miner-validate-run {context["run_dir"]}`.
- Exit normally after the summary and final validation. Do not sleep merely to
  remain alive until the deadline. The controller, not the agent, seals the
  round checkpoint.
"""


def _completion_validation(
    context: dict[str, Any],
    evaluations_dir: Path,
) -> tuple[dict[str, int] | None, str | None]:
    try:
        return (
            validate_round_completion(context["run_dir"], evaluations_dir),
            None,
        )
    except (KeyError, OSError, TypeError, ValueError) as error:
        return None, f"{type(error).__name__}: {error}"


def _finish_controller_round(
    *,
    context: dict[str, Any],
    evaluations_dir: Path,
    authorization_dir: Path,
    config_path: Path,
) -> tuple[dict[str, Any], dict[str, int]]:
    config = load_benchmark_config(config_path)
    manifest = finish_round(
        run_dir=context["run_dir"],
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        config=config,
    )
    validation = validate_run_directory(context["run_dir"], evaluations_dir)
    return manifest, validation


def _authorization_directory(
    *,
    authorization_dir: Path | None,
    sealed_root: Path,
    split_id: str,
) -> Path:
    if authorization_dir:
        return authorization_dir.resolve()
    return sealed_root.resolve() / split_id / "authorized-runs"


def _controller_preflight(
    *,
    context: dict[str, Any],
    evaluations_dir: Path,
    authorization_dir: Path,
    config_path: Path,
) -> dict[str, int]:
    config = load_benchmark_config(config_path)
    validation = validate_run_directory(context["run_dir"], evaluations_dir)
    authorization = load_run_authorization(
        authorization_dir,
        context["run_id"],
    )
    expected = {
        "benchmark_id": config.benchmark_id,
        "split_id": config.split_id,
        "graph_version": config.graph_version,
        "biolink_version": config.biolink_version,
        "predicate_expansion": config.predicate_expansion,
        "status": "running",
        "current_round_id": context["round_id"],
    }
    for field, value in expected.items():
        if authorization[field] != value:
            raise ValueError(
                f"Controller authorization mismatch for {field}: "
                f"expected {value!r}, found {authorization[field]!r}"
            )
    return validation


def _validate_duration_arguments(args: argparse.Namespace) -> None:
    if args.wrap_up_seconds < 0:
        raise ValueError("--wrap-up-seconds cannot be negative")
    if args.shutdown_grace_seconds < 0:
        raise ValueError("--shutdown-grace-seconds cannot be negative")
    if args.deadline_poll_seconds <= 0:
        raise ValueError("--deadline-poll-seconds must be positive")
    if args.recovery_wrap_up_seconds < 0:
        raise ValueError("--recovery-wrap-up-seconds cannot be negative")


def _seal_controller_round(
    *,
    context: dict[str, Any],
    runtime_dir: Path,
    evaluations_dir: Path,
    authorization_dir: Path | None,
    config_path: Path,
    invocations: int,
    last_exit_code: int | None,
    validation: dict[str, int],
    completion_mode: str,
) -> int:
    if authorization_dir is None:
        # Container isolation: sealing needs the sealed authorization records,
        # so `miner-benchmark-setup finish-round` runs as a separate operator Job.
        _write_state(
            runtime_dir,
            context,
            status="awaiting_operator_seal",
            controller_pid=None,
            agent_pid=None,
            invocations=invocations,
            last_exit_code=last_exit_code,
            validation=validation,
            completion_mode=completion_mode,
        )
        return 0
    try:
        manifest, sealed_validation = _finish_controller_round(
            context=context,
            evaluations_dir=evaluations_dir,
            authorization_dir=authorization_dir,
            config_path=config_path,
        )
    except (KeyError, OSError, TypeError, ValueError) as error:
        _write_state(
            runtime_dir,
            context,
            status="finalization_failed",
            controller_pid=None,
            agent_pid=None,
            invocations=invocations,
            last_exit_code=last_exit_code,
            validation=validation,
            completion_mode=completion_mode,
            finalization_error=f"{type(error).__name__}: {error}",
        )
        return 1
    _write_state(
        runtime_dir,
        context,
        status="round_complete",
        controller_pid=None,
        agent_pid=None,
        invocations=invocations,
        last_exit_code=last_exit_code,
        run_status=manifest["status"],
        validation=sealed_validation,
        completion_mode=completion_mode,
        validation_error=None,
        finalization_error=None,
    )
    return 0


def _recover_and_finish_after_deadline(
    *,
    command: list[str],
    agent_runtime: str,
    environment: dict[str, str],
    context: dict[str, Any],
    runtime_dir: Path,
    evaluations_dir: Path,
    authorization_dir: Path | None,
    config_path: Path,
    invocations: int,
    last_exit_code: int | None,
    reason: str,
    deadline_poll_seconds: int,
    recovery_wrap_up_seconds: int,
    shutdown_grace_seconds: int,
    isolation: str = "sandbox-exec",
) -> int:
    validation, validation_error = _completion_validation(context, evaluations_dir)
    if validation is not None:
        return _seal_controller_round(
            context=context,
            runtime_dir=runtime_dir,
            evaluations_dir=evaluations_dir,
            authorization_dir=authorization_dir,
            config_path=config_path,
            invocations=invocations,
            last_exit_code=last_exit_code,
            validation=validation,
            completion_mode="agent_final_summary_after_deadline",
        )

    recovery_exit_code: int | None = None
    if recovery_wrap_up_seconds:
        recovery_started_at = datetime.now(context["deadline"].tzinfo)
        recovery_deadline = recovery_started_at + timedelta(
            seconds=recovery_wrap_up_seconds
        )
        events_path = runtime_dir / "deadline-recovery.jsonl"
        stderr_path = runtime_dir / "deadline-recovery.stderr.log"
        _write_state(
            runtime_dir,
            context,
            status="deadline_wrap_up",
            agent_pid=None,
            invocations=invocations,
            last_exit_code=last_exit_code,
            deadline_reason=reason,
            deadline_overrun_seconds=max(
                0.0,
                (recovery_started_at - context["deadline"]).total_seconds(),
            ),
            recovery_deadline=recovery_deadline.isoformat(),
            validation_error=validation_error,
        )
        with events_path.open("w", encoding="utf-8") as events, stderr_path.open(
            "w", encoding="utf-8"
        ) as errors:
            process = _start_agent_process(
                command=command,
                agent_runtime=agent_runtime,
                environment=environment,
                events=events,
                errors=errors,
                isolation=isolation,
            )
            _write_state(
                runtime_dir,
                context,
                status="deadline_wrap_up",
                agent_pid=process.pid,
                recovery_events=str(events_path),
                recovery_stderr=str(stderr_path),
            )
            exited = _communicate_until_wall_deadline(
                process,
                _deadline_recovery_prompt(context, context["deadline"]),
                recovery_deadline,
                deadline_poll_seconds,
            )
            if not exited:
                _stop_process(process, shutdown_grace_seconds)
            recovery_exit_code = process.returncode

        validation, validation_error = _completion_validation(
            context,
            evaluations_dir,
        )
        if validation is not None:
            return _seal_controller_round(
                context=context,
                runtime_dir=runtime_dir,
                evaluations_dir=evaluations_dir,
                authorization_dir=authorization_dir,
                config_path=config_path,
                invocations=invocations,
                last_exit_code=recovery_exit_code,
                validation=validation,
                completion_mode="agent_deadline_recovery",
            )

    try:
        _append_controller_interruption_summary(
            context=context,
            evaluations_dir=evaluations_dir,
            invocations=invocations,
            last_exit_code=recovery_exit_code
            if recovery_exit_code is not None
            else last_exit_code,
            reason=reason,
            validation_error=validation_error,
        )
        validation, validation_error = _completion_validation(
            context,
            evaluations_dir,
        )
        if validation is None:
            raise ValueError(validation_error or "Completion validation failed")
    except (KeyError, OSError, TypeError, ValueError) as error:
        _write_state(
            runtime_dir,
            context,
            status="finalization_failed",
            controller_pid=None,
            agent_pid=None,
            invocations=invocations,
            last_exit_code=recovery_exit_code
            if recovery_exit_code is not None
            else last_exit_code,
            completion_mode="controller_interruption_fallback",
            validation_error=validation_error,
            finalization_error=f"{type(error).__name__}: {error}",
        )
        return 1

    return _seal_controller_round(
        context=context,
        runtime_dir=runtime_dir,
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        config_path=config_path,
        invocations=invocations,
        last_exit_code=recovery_exit_code
        if recovery_exit_code is not None
        else last_exit_code,
        validation=validation,
        completion_mode="controller_interruption_fallback",
    )


def run_controller(args: argparse.Namespace) -> int:
    _validate_duration_arguments(args)
    context = load_run_context(args.run_dir)
    runtime_dir = args.runtime_dir.resolve()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    evaluations_dir = args.evaluations_dir.resolve()
    evaluations_dir.mkdir(parents=True, exist_ok=True)
    isolation = args.isolation
    if isolation == "container":
        verify_container_isolation(args.sealed_root)
        # Authorization was checked by the operator Job that started the round.
        authorization_dir = None
        preflight = validate_run_directory(context["run_dir"], evaluations_dir)
    else:
        config = load_benchmark_config(args.config)
        authorization_dir = _authorization_directory(
            authorization_dir=args.authorization_dir,
            sealed_root=args.sealed_root,
            split_id=config.split_id,
        )
        preflight = _controller_preflight(
            context=context,
            evaluations_dir=evaluations_dir,
            authorization_dir=authorization_dir,
            config_path=args.config,
        )
    service_environment = {
        name: os.environ[name]
        for name in SAFE_SERVICE_VARIABLES
        if os.environ.get(name)
    }
    # Gandalf is not deployed on the cluster yet; container rounds say so in
    # their round instruction instead of requiring GANDALF_URL.
    optional = {"GANDALF_URL"} if isolation == "container" else set()
    missing = [
        name
        for name in SAFE_SERVICE_VARIABLES
        if name not in service_environment and name not in optional
    ]
    if missing:
        raise ValueError(f"Controller is missing service variables: {', '.join(missing)}")
    environment = build_agent_environment(
        runtime_dir=runtime_dir,
        service_environment=service_environment,
        api_key_env=args.api_key_env,
        agent_runtime=args.agent_runtime,
        isolation=isolation,
        evaluations_dir=evaluations_dir,
    )
    agent_command = build_agent_command(
        agent_runtime=args.agent_runtime,
        model=args.model,
        model_provider=args.model_provider,
        model_base_url=args.model_base_url,
        api_key_env=args.api_key_env,
        reasoning_effort=args.reasoning_effort,
        isolation=isolation,
    )
    if isolation == "container":
        command = agent_command
    else:
        profile_path = runtime_dir / "sandbox.sb"
        profile_path.write_text(
            build_sandbox_profile(
                run_dir=context["run_dir"],
                runtime_dir=runtime_dir,
                sealed_root=args.sealed_root,
                source_root=args.source_root,
                evaluations_dir=evaluations_dir,
            ),
            encoding="utf-8",
        )
        verify_sandbox(
            profile_path,
            context,
            args.sealed_root,
            evaluations_dir,
        )
        command = ["/usr/bin/sandbox-exec", "-f", str(profile_path), *agent_command]
    record_agent_execution(
        run_dir=context["run_dir"],
        round_id=context["round_id"],
        model=args.model,
        model_provider=args.model_provider,
        reasoning_effort=args.reasoning_effort,
    )
    deadline = context["deadline"]
    wrap_up_at = deadline - timedelta(seconds=args.wrap_up_seconds)
    prompt = (
        context["prompt_path"].read_text(encoding="utf-8")
        + _completion_protocol(
            context=context,
            wrap_up_at=wrap_up_at,
            evaluations_dir=evaluations_dir,
        )
    )
    invocation = 0
    consecutive_failures = 0
    last_exit_code: int | None = None
    _write_state(
        runtime_dir,
        context,
        status="running",
        controller_pid=os.getpid(),
        run_dir=str(context["run_dir"]),
        evaluations_dir=str(evaluations_dir),
        authorization_dir=str(authorization_dir) if authorization_dir else None,
        wrap_up_at=wrap_up_at.isoformat(),
        agent_runtime=args.agent_runtime,
        model=args.model,
        model_provider=args.model_provider,
        reasoning_effort=args.reasoning_effort,
        validation=preflight,
    )

    while datetime.now(deadline.tzinfo) < deadline:
        invocation += 1
        if invocation > 1:
            prompt_text = (
                f"{prompt}\n\n# Controller Continuation\n\n"
                f"This is invocation {invocation} within the same active round. "
                "The earlier invocation exited before the deadline. Read all current "
                "append-only artifacts and aggregate evaluations, then continue the "
                "experiment without repeating completed work. If an earlier "
                "`final_summary` was written before the wrap-up window, treat it as "
                "provisional and append a new final summary when this invocation "
                "actually completes.\n"
            )
        else:
            prompt_text = prompt
        events_path = runtime_dir / f"invocation-{invocation:04d}.jsonl"
        stderr_path = runtime_dir / f"invocation-{invocation:04d}.stderr.log"
        with events_path.open("w", encoding="utf-8") as events, stderr_path.open(
            "w", encoding="utf-8"
        ) as errors:
            process = _start_agent_process(
                command=command,
                agent_runtime=args.agent_runtime,
                environment=environment,
                events=events,
                errors=errors,
                isolation=isolation,
            )
            _write_state(
                runtime_dir,
                context,
                status="running",
                controller_pid=os.getpid(),
                agent_pid=process.pid,
                invocations=invocation,
                current_events=str(events_path),
                current_stderr=str(stderr_path),
            )
            exited_before_deadline = _communicate_until_wall_deadline(
                process,
                prompt_text,
                deadline,
                args.deadline_poll_seconds,
            )
            if not exited_before_deadline:
                _stop_process(process, args.shutdown_grace_seconds)
                return _recover_and_finish_after_deadline(
                    command=command,
                    agent_runtime=args.agent_runtime,
                    environment=environment,
                    context=context,
                    runtime_dir=runtime_dir,
                    evaluations_dir=evaluations_dir,
                    authorization_dir=authorization_dir,
                    config_path=args.config,
                    invocations=invocation,
                    last_exit_code=process.returncode,
                    reason="wall_clock_deadline_elapsed",
                    deadline_poll_seconds=args.deadline_poll_seconds,
                    recovery_wrap_up_seconds=args.recovery_wrap_up_seconds,
                    shutdown_grace_seconds=args.shutdown_grace_seconds,
                    isolation=isolation,
                )
            last_exit_code = process.returncode

        now = datetime.now(deadline.tzinfo)
        validation, validation_error = _completion_validation(
            context,
            evaluations_dir,
        )
        if process.returncode == 0 and validation is not None and now >= wrap_up_at:
            return _seal_controller_round(
                context=context,
                runtime_dir=runtime_dir,
                evaluations_dir=evaluations_dir,
                authorization_dir=authorization_dir,
                config_path=args.config,
                invocations=invocation,
                last_exit_code=process.returncode,
                validation=validation,
                completion_mode="agent_normal",
            )

        if now >= deadline:
            return _recover_and_finish_after_deadline(
                command=command,
                agent_runtime=args.agent_runtime,
                environment=environment,
                context=context,
                runtime_dir=runtime_dir,
                evaluations_dir=evaluations_dir,
                authorization_dir=authorization_dir,
                config_path=args.config,
                invocations=invocation,
                last_exit_code=process.returncode,
                reason="agent_exited_after_wall_clock_deadline",
                deadline_poll_seconds=args.deadline_poll_seconds,
                recovery_wrap_up_seconds=args.recovery_wrap_up_seconds,
                shutdown_grace_seconds=args.shutdown_grace_seconds,
                isolation=isolation,
            )

        if process.returncode == 0:
            consecutive_failures = 0
            delay = 5
        else:
            consecutive_failures += 1
            delay = min(300, 30 * consecutive_failures)
        _write_state(
            runtime_dir,
            context,
            status="retrying",
            agent_pid=None,
            invocations=invocation,
            last_exit_code=process.returncode,
            retry_delay_seconds=delay,
            validation=validation,
            validation_error=validation_error,
        )
        remaining = (deadline - datetime.now(deadline.tzinfo)).total_seconds()
        if remaining > 0:
            time.sleep(min(delay, remaining))

    return _recover_and_finish_after_deadline(
        command=command,
        agent_runtime=args.agent_runtime,
        environment=environment,
        context=context,
        runtime_dir=runtime_dir,
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        config_path=args.config,
        invocations=invocation,
        last_exit_code=last_exit_code,
        reason="deadline_elapsed_between_invocations",
        deadline_poll_seconds=args.deadline_poll_seconds,
        recovery_wrap_up_seconds=args.recovery_wrap_up_seconds,
        shutdown_grace_seconds=args.shutdown_grace_seconds,
        isolation=isolation,
    )


def start_detached(args: argparse.Namespace) -> int:
    _validate_duration_arguments(args)
    context = load_run_context(args.run_dir)
    if datetime.now(context["deadline"].tzinfo) >= context["deadline"]:
        raise ValueError(f"Round deadline has already passed: {context['deadline'].isoformat()}")
    runtime_dir = args.runtime_dir.resolve()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    evaluations_dir = args.evaluations_dir.resolve()
    evaluations_dir.mkdir(parents=True, exist_ok=True)
    config = load_benchmark_config(args.config)
    authorization_dir = _authorization_directory(
        authorization_dir=args.authorization_dir,
        sealed_root=args.sealed_root,
        split_id=config.split_id,
    )
    _controller_preflight(
        context=context,
        evaluations_dir=evaluations_dir,
        authorization_dir=authorization_dir,
        config_path=args.config,
    )
    state_path = _state_path(runtime_dir)
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        pid = state.get("controller_pid")
        if pid and _pid_is_running(pid):
            raise ValueError(f"Agent controller is already running with PID {pid}")

    service_environment = load_service_environment(args.env_file)
    controller_environment = {
        "HOME": os.environ["HOME"],
        "PATH": os.environ["PATH"],
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
        **service_environment,
    }
    if args.agent_runtime == "codex":
        controller_environment[args.api_key_env] = os.environ.get(
            args.api_key_env,
            "",
        )
        if not controller_environment[args.api_key_env]:
            raise ValueError(
                f"Missing model credential environment variable: {args.api_key_env}"
            )
    elif args.agent_runtime != "claude":
        raise ValueError(f"Unsupported agent runtime: {args.agent_runtime}")
    profile_path = runtime_dir / "sandbox.sb"
    profile_path.write_text(
        build_sandbox_profile(
            run_dir=context["run_dir"],
            runtime_dir=runtime_dir,
            sealed_root=args.sealed_root,
            source_root=args.source_root,
            evaluations_dir=evaluations_dir,
        ),
        encoding="utf-8",
    )
    verify_sandbox(
        profile_path,
        context,
        args.sealed_root,
        evaluations_dir,
    )
    command = [
        sys.executable,
        "-m",
        "miner2049er.agent_runner",
        "run",
        "--run-dir",
        str(context["run_dir"]),
        "--runtime-dir",
        str(runtime_dir),
        "--sealed-root",
        str(args.sealed_root),
        "--source-root",
        str(args.source_root),
        "--config",
        str(args.config),
        "--evaluations-dir",
        str(evaluations_dir),
        "--wrap-up-seconds",
        str(args.wrap_up_seconds),
        "--shutdown-grace-seconds",
        str(args.shutdown_grace_seconds),
        "--deadline-poll-seconds",
        str(args.deadline_poll_seconds),
        "--recovery-wrap-up-seconds",
        str(args.recovery_wrap_up_seconds),
        "--agent-runtime",
        args.agent_runtime,
        "--model",
        args.model,
        "--model-provider",
        args.model_provider,
        "--model-base-url",
        args.model_base_url,
        "--api-key-env",
        args.api_key_env,
        "--reasoning-effort",
        args.reasoning_effort,
    ]
    command.extend(("--authorization-dir", str(authorization_dir)))
    controller_log = runtime_dir / "controller.log"
    with controller_log.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=controller_environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    _write_state(
        runtime_dir,
        context,
        status="starting",
        controller_pid=process.pid,
        controller_log=str(controller_log),
        agent_runtime=args.agent_runtime,
        model=args.model,
        model_provider=args.model_provider,
        reasoning_effort=args.reasoning_effort,
    )
    print(
        json.dumps(
            {
                "run_id": context["run_id"],
                "round_id": context["round_id"],
                "deadline": context["deadline"].isoformat(),
                "controller_pid": process.pid,
                "agent_runtime": args.agent_runtime,
                "model": args.model,
                "model_provider": args.model_provider,
                "reasoning_effort": args.reasoning_effort,
                "runtime_dir": str(runtime_dir),
                "state": str(_state_path(runtime_dir)),
            },
            indent=2,
        )
    )
    return 0


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def show_status(args: argparse.Namespace) -> int:
    state_path = _state_path(args.runtime_dir.resolve())
    if not state_path.is_file():
        raise FileNotFoundError(state_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["controller_running"] = bool(
        state.get("controller_pid") and _pid_is_running(state["controller_pid"])
    )
    state["agent_running"] = bool(
        state.get("agent_pid") and _pid_is_running(state["agent_pid"])
    )
    run_dir = Path(state["run_dir"]) if state.get("run_dir") else None
    if run_dir and (run_dir / "run.json").is_file():
        manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        state["run_status"] = manifest["status"]
        state["current_round_id"] = manifest["current_round_id"]
        if manifest["status"] == "round_complete":
            state["next_actions"] = [
                f"uv run miner-benchmark-setup start-round --run-id {manifest['run_id']}",
                f"uv run miner-benchmark-setup close-run --run-id {manifest['run_id']}",
            ]
        elif state["status"] in {"deadline_incomplete", "finalization_failed"}:
            state["next_actions"] = [
                f"uv run miner-validate-run {run_dir}",
                (
                    "Repair or complete the active round, append final_summary with "
                    "miner-log-research-event, then run miner-benchmark-setup "
                    f"finish-round --run-id {manifest['run_id']}"
                ),
            ]
    print(json.dumps(state, indent=2))
    return 0


def stop_controller(args: argparse.Namespace) -> int:
    state_path = _state_path(args.runtime_dir.resolve())
    state = json.loads(state_path.read_text(encoding="utf-8"))
    agent_pid = state.get("agent_pid")
    if agent_pid and _pid_is_running(agent_pid):
        os.kill(agent_pid, signal.SIGTERM)
    controller_pid = state.get("controller_pid")
    if controller_pid and _pid_is_running(controller_pid):
        os.kill(controller_pid, signal.SIGTERM)
    state["status"] = "stopped"
    state["agent_pid"] = None
    state["updated_at"] = datetime.now().astimezone().isoformat()
    _atomic_write_json(state_path, state)
    print(json.dumps(state, indent=2))
    return 0


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=ROOT / ".run" / "agents" / "active",
    )
    parser.add_argument(
        "--sealed-root",
        type=Path,
        default=Path("/Users/bizon/Projects/experiments/miner2049er-sealed"),
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("/Users/bizon/Projects/ROBOKOP/ORION"),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_BENCHMARK_CONFIG)
    parser.add_argument(
        "--evaluations-dir",
        type=Path,
        default=DEFAULT_EVALUATIONS_DIR,
    )
    parser.add_argument("--authorization-dir", type=Path)
    parser.add_argument("--wrap-up-seconds", type=int, default=900)
    parser.add_argument("--shutdown-grace-seconds", type=int, default=30)
    parser.add_argument(
        "--deadline-poll-seconds",
        type=int,
        default=DEFAULT_DEADLINE_POLL_SECONDS,
    )
    parser.add_argument(
        "--recovery-wrap-up-seconds",
        type=int,
        default=DEFAULT_RECOVERY_WRAP_UP_SECONDS,
    )
    parser.add_argument(
        "--agent-runtime",
        choices=("codex", "claude"),
        default=DEFAULT_AGENT_RUNTIME,
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-provider", default=DEFAULT_MODEL_PROVIDER)
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--api-key-env", default=DEFAULT_MODEL_API_KEY_ENV)
    parser.add_argument(
        "--reasoning-effort",
        default=DEFAULT_REASONING_EFFORT,
    )
    parser.add_argument(
        "--isolation",
        choices=ISOLATION_MODES,
        default="sandbox-exec",
        help="sandbox-exec on the laptop; container inside a pod",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch a blind, deadline-bound rule-mining agent process"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start")
    _add_common_arguments(start)
    start.add_argument("--env-file", type=Path, default=ROOT / ".env")
    run = subparsers.add_parser("run")
    _add_common_arguments(run)
    status = subparsers.add_parser("status")
    status.add_argument("--runtime-dir", type=Path, required=True)
    stop = subparsers.add_parser("stop")
    stop.add_argument("--runtime-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    handlers = {
        "start": start_detached,
        "run": run_controller,
        "status": show_status,
        "stop": stop_controller,
    }
    raise SystemExit(handlers[args.command](args))


if __name__ == "__main__":
    main()
