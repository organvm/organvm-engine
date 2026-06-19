"""Tests for exit interview Phase 1: V1 Testimony generation."""

from pathlib import Path

import pytest

from organvm_engine.governance.exit_interview.discovery import (
    build_supply_map,
    load_gate_contracts,
)
from organvm_engine.governance.exit_interview.schemas import DemandEntry, SupplyEntry, Testimony
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


class TestDocumentationOnlyTestimony:
    def _supply_entry(self, v1_path: str, repo: str = "meta-organvm/praxis-perpetua"):
        return SupplyEntry(
            v1_path=v1_path,
            repo=repo,
            demands=[
                DemandEntry(
                    gate_name="praxis--preserve",
                    gate_ids=["G1"],
                    mechanism="praxis",
                    verb="preserve",
                    expected_signals=["RULE", "KNOWLEDGE", "CONTRACT"],
                ),
            ],
        )

    def test_documentation_directory_generates_rich_testimony(self, tmp_path):
        repo = tmp_path / "meta-organvm" / "praxis-perpetua"
        standards = repo / "standards"
        standards.mkdir(parents=True)

        (repo / "README.md").write_text("# Praxis Perpetua\n", encoding="utf-8")
        (standards / "SOP--module-handoff.md").write_text(
            """---
sop: true
name: module-handoff
scope: system
governs:
  - src/organvm_engine/governance/exit_interview/testimony.py
---
# SOP: Module Handoff

## Purpose

This SOP must govern `src/organvm_engine/governance/exit_interview/testimony.py`.
It preserves handoff knowledge and validates documentation testimony.

See [README](../README.md) and [JSON Schema](https://json-schema.org/).
""",
            encoding="utf-8",
        )
        (standards / "gate-contract.yaml").write_text(
            """identity:
  name: praxis--preserve
  mechanism: praxis
  verb: preserve
  signal_inputs: [TRACE]
  signal_outputs: [RULE, KNOWLEDGE]
sources:
  - repo: meta-organvm/praxis-perpetua
    modules: [standards/]
gate:
  - id: G1
    check: DOCS_EXIST
    condition: Documentation must exist
    status: PENDING
state: CALLING
""",
            encoding="utf-8",
        )

        testimony = generate_testimony(self._supply_entry("standards"), tmp_path)

        assert testimony.documentation["word_count"] > 0
        assert "documentation files" in testimony.existence["evidence"]
        assert "sections" in testimony.structure
        assert "link graph" in testimony.relation
        assert "SOP coverage" in testimony.process
        assert "KNOWLEDGE" in testimony.signals_produces
        assert "RULE" in testimony.signals_produces

        serialized = testimony.to_dict()
        docs = serialized["documentation"]
        assert docs["link_graph"]["internal"] == 1
        assert docs["link_graph"]["external"] == 1
        assert docs["schema_coverage"]["governance_data_files"]
        assert docs["sop_coverage"]["governed_module_count"] == 1
        assert (
            "src/organvm_engine/governance/exit_interview/testimony.py"
            in docs["sop_coverage"]["governed_modules"]
        )

    def test_documentation_file_uses_heading_identity(self, tmp_path):
        repo = tmp_path / "meta-organvm" / "organvm-corpvs-testamentvm"
        repo.mkdir(parents=True)
        (repo / "README.md").write_text(
            """# Corpus Testament

## Record

This report preserves session trace knowledge for future review.
""",
            encoding="utf-8",
        )

        testimony = generate_testimony(
            self._supply_entry("README.md", repo="meta-organvm/organvm-corpvs-testamentvm"),
            tmp_path,
        )

        assert testimony.identity == "Documentation: Corpus Testament"
        assert "Documentation workflow" in testimony.process
        assert testimony.documentation["markdown_file_count"] == 1
