from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from miner2049er.benchmark_config import (
    DEFAULT_BENCHMARK_CONFIG,
    load_benchmark_config,
)
from miner2049er.partitioning import (
    DEFAULT_PUBLIC_DIR,
    DEFAULT_SEALED_DIR,
    build_partition_artifacts,
)
from miner2049er.run_artifacts import (
    DEFAULT_CONTINUATION_INSTRUCTION,
    DEFAULT_EVALUATIONS_DIR,
    DEFAULT_INITIAL_INSTRUCTION,
    DEFAULT_RUNS_DIR,
    close_run,
    finish_round,
    initialize_run,
    start_round,
)
from miner2049er.settings import ROOT, source_file

STORES = ("neo4j", "gandalf")

def validate_source(source_dir: Path, expected_version: str) -> dict:
    required = {
        "nodes": source_file(source_dir, "nodes"),
        "edges": source_file(source_dir, "edges"),
        "metadata": source_dir / "graph-metadata.json",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing source graph files: {', '.join(missing)}")
    metadata = json.loads(required["metadata"].read_text(encoding="utf-8"))
    actual_version = metadata.get("version")
    if actual_version != expected_version:
        raise ValueError(
            f"Graph metadata version {actual_version!r} does not match "
            f"benchmark version {expected_version!r}"
        )
    return metadata


def _sealed_manifest(sealed_root: Path, split_id: str) -> Path:
    path = sealed_root / split_id / "sealed-manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Run the prepare phase first: {path}")
    return path


def _run(command: list[str], env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def _console_script(name: str) -> str:
    """The entry point installed beside the running interpreter (same venv)."""
    path = Path(sys.executable).parent / name
    if not path.is_file():
        raise FileNotFoundError(f"Console script {name} not found at {path}")
    return str(path)


def build_store_artifacts(
    *,
    source_dir: Path,
    public_root: Path,
    sealed_root: Path,
    config_path: Path,
    overwrite: bool,
    stores: tuple[str, ...] = STORES,
    store_root: Path | None = None,
) -> dict[str, str]:
    config = load_benchmark_config(config_path)
    sealed_manifest_path = _sealed_manifest(sealed_root, config.split_id)
    sealed = json.loads(sealed_manifest_path.read_text(encoding="utf-8"))
    store_root = store_root or public_root / config.split_id / "stores"
    neo4j_output = store_root / "neo4j-import"
    gandalf_output = store_root / "gandalf"
    predicate_args = [
        argument
        for predicate in config.target_predicates
        for argument in ("--target-predicate", predicate)
    ]
    exclusion_args = [
        "--exclude-labels",
        str(sealed_manifest_path.parent / sealed["feedback_labels"]),
        "--exclude-labels",
        str(sealed_manifest_path.parent / sealed["final_labels"]),
    ]
    overwrite_args = ["--overwrite"] if overwrite else []
    built = {"store_root": str(store_root)}
    if "neo4j" in stores:
        _run(
            [
                _console_script("miner-export-neo4j"),
                "--nodes",
                str(source_file(source_dir, "nodes")),
                "--edges",
                str(source_file(source_dir, "edges")),
                "--output",
                str(neo4j_output),
                *exclusion_args,
                *predicate_args,
                *overwrite_args,
            ]
        )
        built["neo4j_import"] = str(neo4j_output)
    if "gandalf" in stores:
        _run(
            [
                _console_script("miner-build-gandalf"),
                "--nodes",
                str(source_file(source_dir, "nodes")),
                "--edges",
                str(source_file(source_dir, "edges")),
                "--output",
                str(gandalf_output),
                *exclusion_args,
                *predicate_args,
                *overwrite_args,
            ]
        )
        built["gandalf"] = str(gandalf_output)
    return built


def start_services(
    *,
    public_root: Path,
    sealed_root: Path,
    config_path: Path,
) -> None:
    config = load_benchmark_config(config_path)
    split_root = public_root / config.split_id
    store_root = split_root / "stores"
    environment = {
        **os.environ,
        "BENCHMARK_CONFIG": str(config_path),
        "BENCHMARK_SEALED_DIR": str(sealed_root / config.split_id),
        "BENCHMARK_SPLIT_ID": config.split_id,
        "NEO4J_DATA_DIR": str(store_root / "neo4j-data"),
        "NEO4J_IMPORT_DIR": str(store_root / "neo4j-import"),
        "GANDALF_GRAPH_PATH": str(store_root / "gandalf"),
    }
    neo4j_data = Path(environment["NEO4J_DATA_DIR"])
    if not neo4j_data.exists() or not any(neo4j_data.iterdir()):
        _run([str(ROOT / "scripts" / "import_neo4j.sh")], environment)
    else:
        print(f"Using existing benchmark Neo4j data: {neo4j_data}")
    _run(["docker", "compose", "up", "-d", "neo4j", "scorer", "dashboard"], environment)
    _run([str(ROOT / "scripts" / "index_neo4j.sh")], environment)
    _run([_console_script("miner-build-rule-features")], environment)
    _run([str(ROOT / "scripts" / "start_gandalf.sh")], environment)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare the treats rule-mining benchmark")
    parser.add_argument(
        "phase",
        choices=(
            "prepare",
            "build-stores",
            "start",
            "all",
            "init-run",
            "finish-round",
            "start-round",
            "close-run",
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_BENCHMARK_CONFIG)
    parser.add_argument("--source-dir", type=Path, required=False)
    parser.add_argument("--public-dir", type=Path, default=DEFAULT_PUBLIC_DIR)
    parser.add_argument(
        "--sealed-dir",
        type=Path,
        default=Path(os.environ.get("BENCHMARK_SEALED_DIR", DEFAULT_SEALED_DIR)),
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--stores",
        nargs="+",
        choices=STORES,
        default=list(STORES),
        help="Which query stores build-stores produces",
    )
    parser.add_argument(
        "--store-root",
        type=Path,
        help="Where build-stores writes; defaults to <public-dir>/<split>/stores",
    )
    parser.add_argument("--run-id")
    parser.add_argument("--deadline")
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument(
        "--evaluations-dir",
        type=Path,
        default=DEFAULT_EVALUATIONS_DIR,
    )
    instruction_group = parser.add_mutually_exclusive_group()
    instruction_group.add_argument("--instruction")
    instruction_group.add_argument("--instruction-file", type=Path)
    return parser.parse_args()


def _round_instruction(args: argparse.Namespace, default: str) -> str:
    if args.instruction_file:
        return args.instruction_file.read_text(encoding="utf-8")
    return args.instruction or default


def main() -> None:
    args = parse_args()
    config = load_benchmark_config(args.config)
    source_dir = args.source_dir or Path(
        os.environ.get("SOURCE_DIR", "/Users/bizon/Projects/ROBOKOP/ORION")
    )
    if args.phase in {"prepare", "build-stores", "all"}:
        validate_source(source_dir, config.graph_version)
    if args.phase in {"prepare", "all"}:
        manifest = build_partition_artifacts(
            source_file(source_dir, "edges"),
            config,
            args.public_dir,
            args.sealed_dir,
        )
        print(json.dumps(manifest, indent=2))
    if args.phase in {"build-stores", "all"}:
        print(
            json.dumps(
                build_store_artifacts(
                    source_dir=source_dir,
                    public_root=args.public_dir,
                    sealed_root=args.sealed_dir,
                    config_path=args.config,
                    overwrite=args.overwrite,
                    stores=tuple(args.stores),
                    store_root=args.store_root,
                ),
                indent=2,
            )
        )
    if args.phase in {"start", "all"}:
        start_services(
            public_root=args.public_dir,
            sealed_root=args.sealed_dir,
            config_path=args.config,
        )
    if args.phase in {"init-run", "finish-round", "start-round", "close-run"}:
        if not args.run_id:
            raise ValueError(f"--run-id is required for {args.phase}")
        _sealed_manifest(args.sealed_dir, config.split_id)
    authorization_dir = (
        args.sealed_dir / config.split_id / "authorized-runs"
    )
    if args.phase == "init-run":
        run_dir = initialize_run(
            runs_dir=args.runs_dir,
            evaluations_dir=args.evaluations_dir,
            authorization_dir=authorization_dir,
            run_id=args.run_id,
            config=config,
            prompt_path=ROOT / "prompts" / "treats-rule-mining.md",
            deadline=args.deadline,
            instruction=_round_instruction(args, DEFAULT_INITIAL_INSTRUCTION),
        )
        print(
            json.dumps(
                {
                    "run_dir": str(run_dir),
                    "round_id": "round-0001",
                    "agent_prompt": str(
                        run_dir / "rounds" / "round-0001" / "agent-prompt.md"
                    ),
                },
                indent=2,
            )
        )
    if args.phase == "start-round":
        run_dir = args.runs_dir / args.run_id
        agent_prompt = start_round(
            run_dir=run_dir,
            evaluations_dir=args.evaluations_dir,
            authorization_dir=authorization_dir,
            config=config,
            deadline=args.deadline,
            instruction=_round_instruction(
                args,
                DEFAULT_CONTINUATION_INSTRUCTION,
            ),
        )
        round_manifest = json.loads(
            (agent_prompt.parent / "round.json").read_text(encoding="utf-8")
        )
        print(
            json.dumps(
                {
                    "run_dir": str(run_dir),
                    "round_id": round_manifest["round_id"],
                    "agent_prompt": str(agent_prompt),
                },
                indent=2,
            )
        )
    if args.phase == "finish-round":
        manifest = finish_round(
            run_dir=args.runs_dir / args.run_id,
            evaluations_dir=args.evaluations_dir,
            authorization_dir=authorization_dir,
            config=config,
        )
        print(json.dumps(manifest, indent=2))
    if args.phase == "close-run":
        manifest = close_run(
            run_dir=args.runs_dir / args.run_id,
            evaluations_dir=args.evaluations_dir,
            authorization_dir=authorization_dir,
            config=config,
        )
        print(json.dumps(manifest, indent=2))
