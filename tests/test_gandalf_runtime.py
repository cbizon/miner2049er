from pathlib import Path

from miner2049er.gandalf_runtime import (
    BIOLINK_VERSION,
    configure_local_biolink,
    local_toolkit,
)


def test_local_toolkit_loads_pinned_qualifiers():
    toolkit = local_toolkit()
    descendants = toolkit.get_descendants("qualifier", formatted=True)

    assert "biolink:object_aspect_qualifier" in descendants
    assert "biolink:disease_context_qualifier" in descendants


def test_runtime_repairs_missing_gandalf_openapi_package_data():
    configure_local_biolink()

    import gandalf.openapi

    config_path = Path(gandalf.openapi.__file__).parent / "openapi-config.yaml"
    assert config_path.is_file()


def test_benchmark_image_includes_the_pinned_biolink_files():
    dockerfile = Path("Dockerfile.benchmark").read_text(encoding="utf-8")

    assert (
        f"COPY data/reference/biolink/{BIOLINK_VERSION} "
        f"./data/reference/biolink/{BIOLINK_VERSION}"
    ) in dockerfile
