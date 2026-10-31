from __future__ import annotations

from pathlib import Path

import yaml
from bmt.toolkit import Toolkit
from linkml_runtime.utils.schemaview import SchemaView

from miner2049er.settings import ROOT

# Version used for new runs and the Gandalf server. Runs recorded under an
# earlier version are still validated against their own recorded version.
BIOLINK_VERSION = "4.4.4"
BIOLINK_ROOT = ROOT / "data" / "reference" / "biolink"
OPENAPI_CONFIG_DIR = Path(__file__).resolve().parent


def local_toolkit(version: str = BIOLINK_VERSION) -> Toolkit:
    schema = BIOLINK_ROOT / version / "biolink-model.yaml"
    predicate_map = BIOLINK_ROOT / version / "predicate_mapping.yaml"
    for path in (schema, predicate_map):
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing pinned Biolink reference file: {path}. "
                f"Run scripts/fetch_biolink.sh {version}."
            )
    toolkit = Toolkit.__new__(Toolkit)
    toolkit.view = SchemaView(str(schema))
    toolkit.pmap = yaml.safe_load(predicate_map.read_text(encoding="utf-8"))
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
