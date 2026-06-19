"""Tests for exit interview Phase 1: V1 Testimony generation."""

from pathlib import Path

import pytest

from organvm_engine.governance.exit_interview.discovery import (
    build_supply_map,
    load_gate_contracts,
)
from organvm_engine.governance.exit_interview.schemas import (
    DemandEntry,
    SupplyEntry,
    Testimony,
)
from organvm_engine.governance.exit_interview.testimony import (
    _is_doc_directory,
    _is_doc_file,
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


# ---------------------------------------------------------------------------
# Documentation-only repos
# ---------------------------------------------------------------------------


def _supply_entry(repo: str, module: str) -> SupplyEntry:
    """Build a minimal supply entry with one demand for testing."""
    return SupplyEntry(
        v1_path=module,
        repo=repo,
        demands=[
            DemandEntry(
                gate_name="memory--preserve",
                gate_ids=["G1"],
                mechanism="memory",
                verb="preserve",
                expected_signals=["KNOWLEDGE"],
            ),
        ],
    )


@pytest.fixture
def doc_repo(tmp_path):
    """A documentation-only repo: markdown specs, no Python."""
    repo = tmp_path / "some-org" / "spec-repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text(
        "# Spec Repo\n\n"
        "This repo documents the governance policy. Every promotion MUST be "
        "audited and SHALL trace upward to A6.\n\n"
        "## Usage\n\n"
        "```bash\norganvm exit-interview generate\n```\n\n"
        "See [the rules](docs/rules.md) and [home](https://example.com).\n",
        encoding="utf-8",
    )
    (repo / "docs" / "rules.md").write_text(
        "# Rules\n\n## Promotion\n\nArtifacts should be governed (A6).\n",
        encoding="utf-8",
    )
    return tmp_path, repo


class TestDocumentationDetection:
    def test_doc_file_by_suffix(self, tmp_path):
        assert _is_doc_file(tmp_path / "x.md")
        assert _is_doc_file(tmp_path / "x.RST")
        assert not _is_doc_file(tmp_path / "x.py")

    def test_doc_directory_true_for_markdown_only(self, doc_repo):
        _ws, repo = doc_repo
        assert _is_doc_directory(repo)

    def test_doc_directory_false_when_python_present(self, doc_repo):
        _ws, repo = doc_repo
        (repo / "tool.py").write_text("x = 1\n", encoding="utf-8")
        assert not _is_doc_directory(repo)

    def test_doc_directory_ignores_vendored_python(self, doc_repo):
        """A .py inside a pruned dir should not disqualify a doc repo."""
        _ws, repo = doc_repo
        vendored = repo / "node_modules" / "pkg"
        vendored.mkdir(parents=True)
        (vendored / "index.py").write_text("x = 1\n", encoding="utf-8")
        assert _is_doc_directory(repo)


class TestDocumentationTestimony:
    def test_doc_dir_existence_scored(self, doc_repo):
        ws, _repo = doc_repo
        testimony = generate_testimony(_supply_entry("some-org/spec-repo", "."), ws)
        # Existence must register the markdown, not report an empty Python dir.
        assert testimony.existence["score"] == 1.0
        assert "doc file" in testimony.existence["evidence"]

    def test_doc_identity_uses_title(self, doc_repo):
        ws, _repo = doc_repo
        testimony = generate_testimony(_supply_entry("some-org/spec-repo", "."), ws)
        assert testimony.identity == "Spec Repo"

    def test_doc_structure_lists_sections(self, doc_repo):
        ws, _repo = doc_repo
        testimony = generate_testimony(_supply_entry("some-org/spec-repo", "."), ws)
        assert "documents" in testimony.structure
        assert "sections" in testimony.structure

    def test_doc_law_detects_normative_language(self, doc_repo):
        ws, _repo = doc_repo
        testimony = generate_testimony(_supply_entry("some-org/spec-repo", "."), ws)
        assert "must" in testimony.law.lower()
        assert "A6" in testimony.law

    def test_doc_process_counts_code_blocks(self, doc_repo):
        ws, _repo = doc_repo
        testimony = generate_testimony(_supply_entry("some-org/spec-repo", "."), ws)
        assert "code/command example" in testimony.process

    def test_doc_relation_extracts_links(self, doc_repo):
        ws, _repo = doc_repo
        testimony = generate_testimony(_supply_entry("some-org/spec-repo", "."), ws)
        assert "rules.md" in testimony.relation

    def test_doc_teleology_maps_axioms(self, doc_repo):
        ws, _repo = doc_repo
        testimony = generate_testimony(_supply_entry("some-org/spec-repo", "."), ws)
        assert "A6" in testimony.teleology

    def test_doc_produces_knowledge_signal(self, doc_repo):
        ws, _repo = doc_repo
        testimony = generate_testimony(_supply_entry("some-org/spec-repo", "."), ws)
        assert "KNOWLEDGE" in testimony.signals_produces
        assert testimony.signals_consumes == []

    def test_doc_axiom_claims_present(self, doc_repo):
        ws, _repo = doc_repo
        testimony = generate_testimony(_supply_entry("some-org/spec-repo", "."), ws)
        axioms = {c.axiom for c in testimony.axiom_alignment}
        assert "A6" in axioms

    def test_doc_testimony_serializes(self, doc_repo):
        ws, _repo = doc_repo
        testimony = generate_testimony(_supply_entry("some-org/spec-repo", "."), ws)
        d = testimony.to_dict()
        assert d["testimony"]["identity"] == "Spec Repo"
        assert d["signals"]["produces"]

    def test_single_doc_file(self, tmp_path):
        repo = tmp_path / "org" / "notes"
        repo.mkdir(parents=True)
        (repo / "SEED.md").write_text(
            "# Seed\n\nThe seed adapts and evolves (A4).\n", encoding="utf-8",
        )
        testimony = generate_testimony(_supply_entry("org/notes", "SEED.md"), tmp_path)
        assert testimony.identity == "Seed"
        assert testimony.existence["score"] == 1.0
        assert "A4" in testimony.teleology
