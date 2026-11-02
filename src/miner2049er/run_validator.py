from __future__ import annotations

import argparse
import json
from pathlib import Path

from miner2049er.run_artifacts import validate_run_directory
from miner2049er.settings import evaluations_dir as configured_evaluations_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a complete benchmark run")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--evaluations-dir",
        type=Path,
        default=configured_evaluations_dir(),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(
        json.dumps(
            validate_run_directory(args.run_dir, args.evaluations_dir),
            indent=2,
        )
    )
