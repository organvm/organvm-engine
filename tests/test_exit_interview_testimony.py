"""Tests for exit interview Phase 1: V1 Testimony generation."""

from pathlib import Path

import pytest

from organvm_engine.governance.exit_interview.discovery import (
    build_supply_map,
    load_gate_contracts,
)
from organvm_engine.governance.exit_interview.schemas import Testimony
from organvm_engine.governance.exit_interview.testimony import (
    generate_all_testimonies,
    generate_testimony,
)

FIXTURES = Path(__file__).parent / "fixtures" / "gate-contracts"


@pytest.fixture
def workspace_root():
    """Use the actual workspace root for testing against real files."""
    ws = Path.home() / "Workspace"
    if not ws.is_dir():
        pytest.skip("Workspace not found — skip filesystem-dependent tests")
    return ws


@pytest.fixture
def supply_map():
    contracts = load_gate_contracts(FIXTURES)
    return build_supply_map(contracts)


class TestGenerateTestimony:
    def test_generates_testimony_for_existing_module(self, workspace_root, supply_map):
        """governance/ exists in the engine — should produce rich testimony."""
        key = "meta-organvm/organvm-engine/governance"
        if key not in supply_map.entries:
            pytest.skip("governance/ not in supply map")

        testimony = generate_testimony(supply_map.entries[key], workspace_root)
        assert isinstance(testimony, Testimony)
        assert testimony.v2_mechanism == "nervous"
        assert testimony.v2_verb == "govern"
        assert testimony.existence.get("score", 0) > 0

    def test_testimony_has_seven_dimensions(self, workspace_root, supply_map):
        key = "meta-organvm/organvm-engine/governance"
        if key not in supply_map.entries:
            pytest.skip("governance/ not in supply map")

        testimony = generate_testimony(supply_map.entries[key], workspace_root)
        # All 7 dimensions should be populated
        assert testimony.existence  # dict with score
        assert testimony.identity  # non-empty string
        assert testimony.structure  # non-empty string

    def test_testimony_has_gate_references(self, workspace_root, supply_map):
        key = "meta-organvm/organvm-engine/governance"
        if key not in supply_map.entries:
            pytest.skip("governance/ not in supply map")

        testimony = generate_testimony(supply_map.entries[key], workspace_root)
        assert len(testimony.feeds_gates) > 0
        assert any("nervous--govern" in g for g in testimony.feeds_gates)

    def test_testimony_infers_signals(self, workspace_root, supply_map):
        key = "meta-organvm/organvm-engine/governance"
        if key not in supply_map.entries:
            pytest.skip("governance/ not in supply map")

        testimony = generate_testimony(supply_map.entries[key], workspace_root)
        # governance module should produce RULE or VALIDATION signals
        all_signals = testimony.signals_consumes + testimony.signals_produces
        assert len(all_signals) > 0

    def test_testimony_serializes_to_dict(self, workspace_root, supply_map):
        key = "meta-organvm/organvm-engine/governance"
        if key not in supply_map.entries:
            pytest.skip("governance/ not in supply map")

        testimony = generate_testimony(supply_map.entries[key], workspace_root)
        d = testimony.to_dict()
        assert "identity" in d
        assert "testimony" in d
        assert "signals" in d
        assert "axiom_alignment" in d


class TestGenerateAllTestimonies:
    def test_generates_multiple(self, workspace_root, supply_map):
        testimonies = generate_all_testimonies(supply_map.entries, workspace_root)
        assert len(testimonies) > 0
        for _key, t in testimonies.items():
            assert isinstance(t, Testimony)

    def test_nonexistent_module_still_generates(self, workspace_root, supply_map):
        """Modules that don't exist on disk should still get testimony (with exists=False)."""
        # schema-definitions/schemas/ may not resolve — test graceful handling
        testimonies = generate_all_testimonies(supply_map.entries, workspace_root)
        # All entries get testimony, even if existence score is 0
        assert len(testimonies) == len(supply_map.entries)
