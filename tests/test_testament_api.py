"""Tests for the testament public API (get_testament_summary) — issue #54."""

from __future__ import annotations

from pathlib import Path

from organvm_engine.testament import get_testament_summary

FIXTURES = Path(__file__).parent / "fixtures"


def test_get_testament_summary_returns_dict():
    result = get_testament_summary(
        registry_path=FIXTURES / "registry-minimal.json",
    )
    assert isinstance(result, dict)


def test_summary_has_system_section():
    result = get_testament_summary(
        registry_path=FIXTURES / "registry-minimal.json",
    )
    assert "system" in result
    sys = result["system"]
    assert "total_repos" in sys
    assert "total_organs" in sys
    assert "total_public" in sys
    assert "status_counts" in sys
    assert isinstance(sys["total_repos"], int)
    assert sys["total_repos"] >= 0


def test_summary_has_omega_section():
    result = get_testament_summary(
        registry_path=FIXTURES / "registry-minimal.json",
    )
    assert "omega" in result
    omega = result["omega"]
    assert "met_count" in omega
    assert "total" in omega
    assert "met_ratio" in omega
    assert 0 <= omega["met_ratio"] <= 1.0


def test_summary_has_densities():
    result = get_testament_summary(
        registry_path=FIXTURES / "registry-minimal.json",
    )
    assert "densities" in result
    densities = result["densities"]
    assert isinstance(densities, dict)
    # Should have organ keys
    assert len(densities) >= 1


def test_summary_has_sonic_section():
    result = get_testament_summary(
        registry_path=FIXTURES / "registry-minimal.json",
    )
    assert "sonic" in result
    sonic = result["sonic"]
    assert "voices" in sonic
    assert sonic["voices"] == 8
    assert "bpm" in sonic
    assert "master_amplitude" in sonic
    assert "time_signature" in sonic


def test_summary_has_catalog_section():
    result = get_testament_summary(
        registry_path=FIXTURES / "registry-minimal.json",
    )
    assert "catalog" in result
    cat = result["catalog"]
    assert "total" in cat
    assert "by_modality" in cat
    assert "by_organ" in cat
    assert isinstance(cat["total"], int)


def test_summary_has_network_section():
    result = get_testament_summary(
        registry_path=FIXTURES / "registry-minimal.json",
    )
    assert "network" in result
    net = result["network"]
    assert "nodes" in net
    assert "feedback_edges" in net
    assert "execution_order" in net
    assert net["nodes"] >= 8
    assert isinstance(net["execution_order"], list)


def test_summary_has_artifact_types_count():
    result = get_testament_summary(
        registry_path=FIXTURES / "registry-minimal.json",
    )
    assert "artifact_types" in result
    assert result["artifact_types"] >= 10
    assert "source_modules" in result
    assert result["source_modules"] >= 8


def test_summary_with_catalog_dir(tmp_path: Path):
    """Using a custom catalog_dir returns an empty catalog."""
    result = get_testament_summary(
        registry_path=FIXTURES / "registry-minimal.json",
        catalog_dir=tmp_path,
    )
    assert result["catalog"]["total"] == 0


def test_summary_all_keys_present():
    """Verify the complete key set for API consumers."""
    result = get_testament_summary(
        registry_path=FIXTURES / "registry-minimal.json",
    )
    expected_keys = {
        "system", "omega", "densities", "sonic",
        "catalog", "network", "artifact_types", "source_modules",
    }
    assert set(result.keys()) == expected_keys


# --- /testament/ route rendering ------------------------------------------

def _sample_summary() -> dict:
    return get_testament_summary(registry_path=FIXTURES / "registry-minimal.json")


def test_render_testament_page_is_html():
    from organvm_engine.testament.renderers.html import render_testament_page

    html = render_testament_page(_sample_summary())
    assert html.startswith("<!DOCTYPE html>")
    assert "ORGANVM Testament" in html
    assert "Organ Density" in html


def test_render_testament_page_handles_empty_summary():
    """Renderer must not crash on a minimal/empty payload."""
    from organvm_engine.testament.renderers.html import render_testament_page

    html = render_testament_page({})
    assert html.startswith("<!DOCTYPE html>")
    assert "no density data" in html


def test_render_testament_page_includes_network_order():
    from organvm_engine.testament.renderers.html import render_testament_page

    summary = _sample_summary()
    html = render_testament_page(summary)
    for node in summary["network"]["execution_order"]:
        assert node in html
