from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import orjson
from jsonschema import Draft202012Validator, FormatChecker

from miner2049er.settings import ROOT

SCHEMA_DIR = ROOT / "schemas"


def load_schema(name: str) -> dict[str, Any]:
    path = SCHEMA_DIR / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_document(value: dict[str, Any], schema_name: str) -> None:
    validator = Draft202012Validator(
        load_schema(schema_name),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise ValueError(f"{schema_name}:{location}: {error.message}")


def read_jsonl(path: Path, schema_name: str) -> Iterator[dict[str, Any]]:
    with path.open("rb") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                value = orjson.loads(line)
                validate_document(value, schema_name)
            except Exception as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
            yield value
