import pytest

freshforge = pytest.importorskip("freshforge")

from wbi_birds.forge import NODE_TYPES, provider_factory  # noqa: E402


def test_provider_metadata() -> None:
    metadata = provider_factory().metadata()
    assert metadata.id == "wbi"
    assert metadata.node_types == NODE_TYPES
    assert len(metadata.node_types) >= 8


def test_provider_declares_pipeline_node_types() -> None:
    ids = {node_type.id for node_type in NODE_TYPES}
    expected = {
        "ingest_ebd",
        "fit_antifunction",
        "compile_instance",
        "build_model",
        "run_scenarios",
        "compute_frontiers",
        "verify_parity",
        "analyze_frontiers",
    }
    assert expected <= ids
