from __future__ import annotations

from pathlib import Path

import yaml
from bmt.toolkit import Toolkit
from linkml_runtime.utils.schemaview import SchemaView

from miner2049er.settings import ROOT

BIOLINK_VERSION = "4.3.2"
BIOLINK_DIR = ROOT / "data" / "reference" / "biolink" / BIOLINK_VERSION
BIOLINK_SCHEMA = BIOLINK_DIR / "biolink-model.yaml"
PREDICATE_MAP = BIOLINK_DIR / "predicate_mapping.yaml"
OPENAPI_CONFIG_DIR = Path(__file__).resolve().parent


def local_toolkit() -> Toolkit:
    for path in (BIOLINK_SCHEMA, PREDICATE_MAP):
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing pinned Biolink reference file: {path}. "
                "Run scripts/fetch_biolink.sh."
            )
    toolkit = Toolkit.__new__(Toolkit)
    toolkit.view = SchemaView(str(BIOLINK_SCHEMA))
    toolkit.pmap = yaml.safe_load(PREDICATE_MAP.read_text(encoding="utf-8"))
    return toolkit


def configure_local_biolink() -> None:
    import gandalf.biolink
    import gandalf.normalize
    import gandalf.openapi
    import gandalf.search.lookup
    import gandalf.validation

    gandalf.biolink.make_toolkit = local_toolkit
    gandalf.normalize.make_toolkit = local_toolkit
    gandalf.openapi.__file__ = str(OPENAPI_CONFIG_DIR / "_openapi_module.py")
    gandalf.search.lookup.make_toolkit = local_toolkit
    gandalf.validation.make_toolkit = local_toolkit
