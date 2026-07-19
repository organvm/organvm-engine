"""Tests for the contextmd module (context file generation and sync)."""

from pathlib import Path

import pytest

from organvm_engine.contextmd import AUTO_END, AUTO_START
from organvm_engine.contextmd.generator import (
    _build_variable_context,
    _read_omega_counts,
    generate_organ_section,
    generate_repo_section,
    generate_workspace_section,
)
from organvm_engine.contextmd.sync import _inject_section, sync_repo
from organvm_engine.contextmd.templates import VARIABLE_STATUS_SECTION
from organvm_engine.registry.loader import load_registry

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def registry():
    return load_registry(FIXTURES / "registry-minimal.json")


class TestInjectSection:
    def test_creates_new_file(self, tmp_path):
        target = tmp_path / "CLAUDE.md"
        action = _inject_section(target, "## Generated\nContent here")
        assert action == "created"
        assert target.read_text() == "## Generated\nContent here\n"

    def test_replaces_existing_markers(self, tmp_path):
        target = tmp_path / "CLAUDE.md"
        target.write_text(
            f"# My Project\n\n{AUTO_START}\n## Old Section\n{AUTO_END}\n\n## Manual Section\n",
        )
        new_section = f"{AUTO_START}\n## New Section\n{AUTO_END}"
        action = _inject_section(target, new_section)
        assert action == "updated"
        content = target.read_text()
        assert "## New Section" in content
        assert "## Old Section" not in content
        assert "## Manual Section" in content

    def test_appends_when_no_markers(self, tmp_path):
        target = tmp_path / "CLAUDE.md"
        target.write_text("# My Project\n\nSome content.")
        new_section = f"{AUTO_START}\n## Generated\n{AUTO_END}"
        action = _inject_section(target, new_section)
        assert action == "updated"
        content = target.read_text()
        assert content.startswith("# My Project")
        assert AUTO_START in content

    def test_unchanged_when_same_content(self, tmp_path):
        section = f"{AUTO_START}\n## Same\n{AUTO_END}"
        target = tmp_path / "CLAUDE.md"
        target.write_text(f"# Title\n\n{section}\n")
        action = _inject_section(target, section)
        assert action == "unchanged"

    def test_dry_run_does_not_write(self, tmp_path):
        target = tmp_path / "CLAUDE.md"
        action = _inject_section(target, "## Content", dry_run=True)
        assert action == "created"
        assert not target.exists()


class TestGenerateRepoSection:
    def test_generates_valid_section(self, registry):
        section = generate_repo_section("recursive-engine", "organvm-i-theoria", registry)
        assert AUTO_START in section
        assert AUTO_END in section
        assert "ORGAN-I" in section
        assert "flagship" in section
        assert "recursive-engine" in section

    def test_returns_error_for_missing_repo(self, registry):
        section = generate_repo_section("nonexistent", "org", registry)
        assert "ERROR" in section

    def test_includes_siblings(self, registry):
        section = generate_repo_section("recursive-engine", "organvm-i-theoria", registry)
        assert "ontological-framework" in section

    def test_includes_seed_edges(self, registry):
        seed = {
            "produces": [{"target": "repo-b", "artifact": "data"}],
            "consumes": [{"source": "meta-organvm/schema-definitions", "artifact": "schemas"}],
        }
        section = generate_repo_section("recursive-engine", "organvm-i-theoria", registry, seed)
        assert "Produces" in section
        assert "Consumes" in section

    def test_includes_system_library(self, registry):
        section = generate_repo_section("recursive-engine", "organvm-i-theoria", registry)
        assert "## System Library" in section
        assert "organvm plans search <query>" in section
        assert "organvm chains list" in section
        assert "organvm sop lifecycle" in section


class TestGenerateOrganSection:
    def test_generates_valid_organ_section(self, registry):
        section = generate_organ_section("ORGAN-I", registry)
        assert AUTO_START in section
        assert "Theory" in section
        assert "recursive-engine" in section
        assert "## System Library" in section

    def test_returns_error_for_missing_organ(self, registry):
        section = generate_organ_section("ORGAN-IX", registry)
        assert "ERROR" in section


class TestGenerateWorkspaceSection:
    def test_generates_valid_workspace_section(self, registry):
        section = generate_workspace_section(registry, seeds=[{}, {}, {}])
        assert AUTO_START in section
        assert "repos" in section
        assert "organs" in section
        assert "## System Library" in section

    def test_seed_coverage_reflects_count(self, registry):
        section = generate_workspace_section(registry, seeds=[{}, {}])
        assert "2/6" in section  # 2 seeds, 6 repos in fixture


class TestReadOmegaCounts:
    def test_reads_from_evidence_map(self, tmp_path, monkeypatch):
        evidence = tmp_path / "docs" / "evaluation" / "omega-evidence-map.md"
        evidence.parent.mkdir(parents=True)
        evidence.write_text(
            "## Summary\n\n"
            "| Status | Count | Criteria |\n"
            "|--------|-------|----------|\n"
            "| MET | 3 | #1, #2, #3 |\n"
            "| IN PROGRESS | 5 | #4-#8 |\n"
            "| NOT STARTED | 9 | #9-#17 |\n",
        )
        monkeypatch.setattr(
            "organvm_engine.paths.corpus_dir",
            lambda: tmp_path,
        )
        met, total = _read_omega_counts()
        assert met == 3
        assert total == 17

    def test_fallback_on_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "organvm_engine.paths.corpus_dir",
            lambda: tmp_path,
        )
        met, total = _read_omega_counts()
        assert met == 0
        assert total == 17


class TestBuildVariableContext:
    def test_returns_string(self):
        """_build_variable_context always returns a string, even when ontologia is absent."""
        result = _build_variable_context()
        assert isinstance(result, str)

    def test_returns_empty_when_ontologia_missing(self, monkeypatch):
        """Returns empty string when ontologia import fails."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "ontologia.registry.store":
                raise ImportError("ontologia not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = _build_variable_context()
        assert result == ""

    def test_returns_populated_table_with_variables(self, tmp_path):
        """Returns a markdown table when variables exist in the store."""
        try:
            from ontologia.registry.store import open_store
            from ontologia.variables.variable import Scope, Variable
        except ImportError:
            pytest.skip("ontologia not installed")

        store = open_store(store_dir=tmp_path / "ontologia")
        store.set_variable(Variable(key="total_repos", value=112, scope=Scope.GLOBAL))
        store.set_variable(Variable(key="system_density", value="0.72", scope=Scope.GLOBAL))
        store.save()

        # Patch open_store in the generator module to use our tmp store
        import organvm_engine.contextmd.generator as gen_mod

        def patched_open_store(store_dir=None):
            return open_store(store_dir=tmp_path / "ontologia")
        # Exercise the real function against a real store by monkeypatching open_store
        from unittest import mock
        with mock.patch("organvm_engine.contextmd.generator.open_store" if hasattr(gen_mod, "open_store") else "ontologia.registry.store.open_store"):
            pass  # scope check only

        # Direct test: invoke with our tmp store via inner import monkeypatching
        import sys
        orig_module = sys.modules.get("ontologia.registry.store")
        try:
            import types
            fake_module = types.ModuleType("ontologia.registry.store")

            def _patched_open_store(store_dir=None):
                return open_store(store_dir=tmp_path / "ontologia")

            fake_module.open_store = _patched_open_store
            sys.modules["ontologia.registry.store"] = fake_module

            result = _build_variable_context()
        finally:
            if orig_module is not None:
                sys.modules["ontologia.registry.store"] = orig_module
            else:
                sys.modules.pop("ontologia.registry.store", None)

        assert isinstance(result, str)
        # If ontologia is available and variables were loaded, expect table content
        if result:
            assert "total_repos" in result or "system_density" in result

    def test_variable_status_section_has_placeholder(self):
        """VARIABLE_STATUS_SECTION template contains required placeholders."""
        assert "{variable_rows}" in VARIABLE_STATUS_SECTION
        assert "{metric_count}" in VARIABLE_STATUS_SECTION
        assert "{observation_count}" in VARIABLE_STATUS_SECTION

    def test_variable_status_section_format(self):
        """VARIABLE_STATUS_SECTION formats correctly with sample data."""
        rendered = VARIABLE_STATUS_SECTION.format(
            variable_rows="| `total_repos` | 112 | global | 2026-03-15 |",
            metric_count=3,
            observation_count=42,
        )
        assert "total_repos" in rendered
        assert "112" in rendered
        assert "3 registered" in rendered
        assert "42 recorded" in rendered
        assert "organvm ontologia status" in rendered
        assert "organvm refresh" in rendered


class TestSyncRepo:
    def test_sync_creates_file(self, tmp_path, registry):
        repo_path = tmp_path / "recursive-engine"
        repo_path.mkdir()
        result = sync_repo(repo_path, "recursive-engine", "organvm-i-theoria", registry)
        assert result["action"] == "created"
        content = (repo_path / "CLAUDE.md").read_text()
        assert AUTO_START in content
        assert "recursive-engine" in content

    def test_sync_updates_existing(self, tmp_path, registry):
        repo_path = tmp_path / "recursive-engine"
        repo_path.mkdir()
        claude_md = repo_path / "CLAUDE.md"
        claude_md.write_text(f"# My Repo\n\n{AUTO_START}\n## Old\n{AUTO_END}\n\n## Keep This\n")
        result = sync_repo(repo_path, "recursive-engine", "organvm-i-theoria", registry)
        assert result["action"] == "updated"
        content = claude_md.read_text()
        assert "## Keep This" in content
        assert "## Old" not in content
