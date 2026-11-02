from __future__ import annotations

import json
import re
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any

import orjson
from jsonschema import Draft202012Validator, FormatChecker

from miner2049er.settings import ROOT

SCHEMA_DIR = ROOT / "schemas"
PREDICTION_SCHEMA = "prediction.schema.json"
_ROUND_ID = re.compile(r"round-[0-9]{4}")
_PREDICTION_REQUIRED = ("run_id", "round_id", "rule_id", "subject_id", "object_id")
_PREDICTION_KEYS = {
    "schema_version",
    *_PREDICTION_REQUIRED,
    "support_count",
    "evidence_bindings",
}


def load_schema(name: str) -> dict[str, Any]:
    path = SCHEMA_DIR / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def _validator(schema_name: str) -> Draft202012Validator:
    # Built once per schema: reading the file and constructing a validator for
    # every JSONL row was a large share of full-run validation time.
    return Draft202012Validator(load_schema(schema_name), format_checker=FormatChecker())


def prediction_is_valid(value: Any) -> bool:
    """Exact hand-written equivalent of prediction.schema.json.

    Runs accumulate millions of prediction rows, and generic schema validation
    of each one dominated full-run validation (and so every rule recording).
    tests/test_schema_validation.py pins the schema and checks this agrees with
    jsonschema, so a schema change fails the tests until this is updated.
    """
    if not isinstance(value, dict) or value.keys() - _PREDICTION_KEYS:
        return False
    if value.get("schema_version") != "1.0":
        return False
    for key in _PREDICTION_REQUIRED:
        item = value.get(key)
        if not isinstance(item, str) or not item:
            return False
    if not _ROUND_ID.fullmatch(value["round_id"]):
        return False
    if "support_count" in value:
        count = value["support_count"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return False
    if "evidence_bindings" in value:
        bindings = value["evidence_bindings"]
        if not isinstance(bindings, list) or not all(isinstance(b, str) for b in bindings):
            return False
    return True


def validate_document(value: dict[str, Any], schema_name: str) -> None:
    if schema_name == PREDICTION_SCHEMA and prediction_is_valid(value):
        return
    errors = sorted(
        _validator(schema_name).iter_errors(value),
        key=lambda error: list(error.path),
    )
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
