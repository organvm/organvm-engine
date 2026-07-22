"""Tests for sop.discover module."""

from pathlib import Path

from organvm_engine.sop.discover import (
    _derive_sop_name,
    _infer_scope,
    _parse_frontmatter,
    discover_sops,
)


def _make_sop(tmp_path: Path, org: str, repo: str, filename: str, content: str = "") -> Path:
    """Create a SOP file in the expected workspace structure."""
    d = tmp_path / org / repo
    d.mkdir(parents=True, exist_ok=True)
    f = d / filename
    f.write_text(content or f"# SOP: {filename}\n\nContent here.\n")
    return f


def _make_sops_dir(
    tmp_path: Path, org: str, repo_or_none: str | None, filename: str, content: str = "",
) -> Path:
    """Create a .sops/ file at organ or repo level."""
    d = tmp_path / org / repo_or_none / ".sops" if repo_or_none else tmp_path / org / ".sops"
    d.mkdir(parents=True, exist_ok=True)
    f = d / filename
    f.write_text(content or f"# {filename}\n\nContent.\n")
    return f


class TestDiscoverSops:
    def test_finds_double_hyphen_sop(self, tmp_path):
        _make_sop(tmp_path, "meta-organvm", "praxis-perpetua", "SOP--foo.md")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1
        assert entries[0].filename == "SOP--foo.md"
        assert entries[0].doc_type == "SOP"
        assert entries[0].org == "meta-organvm"
        assert entries[0].repo == "praxis-perpetua"

    def test_finds_single_hyphen_sop(self, tmp_path):
        _make_sop(tmp_path, "organvm-v-logos", "public-process", "sop-doctoral-dissertation.md")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1
        assert entries[0].doc_type == "SOP"

    def test_finds_metadoc(self, tmp_path):
        _make_sop(tmp_path, "meta-organvm", "praxis-perpetua", "METADOC--research-standards.md")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1
        assert entries[0].doc_type == "METADOC"

    def test_finds_appendix(self, tmp_path):
        _make_sop(tmp_path, "meta-organvm", "praxis-perpetua", "APPENDIX--bibliography.md")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1
        assert entries[0].doc_type == "APPENDIX"

    def test_extracts_title(self, tmp_path):
        _make_sop(
            tmp_path,
            "meta-organvm",
            "praxis-perpetua",
            "SOP--test.md",
            "> **Canonical location:** elsewhere\n\n# SOP: My Great Procedure\n\nBody.\n",
        )
        entries = discover_sops(workspace=tmp_path)
        assert entries[0].title == "SOP: My Great Procedure"

    def test_detects_canonical_header(self, tmp_path):
        _make_sop(
            tmp_path,
            "meta-organvm",
            "corpus",
            "sop--pitch-deck-rollout.md",
            "> **Canonical location:** `praxis-perpetua/standards/SOP--pitch-deck-rollout.md`\n",
        )
        entries = discover_sops(workspace=tmp_path)
        assert entries[0].has_canonical_header is True

    def test_no_canonical_header(self, tmp_path):
        _make_sop(tmp_path, "meta-organvm", "praxis-perpetua", "SOP--test.md")
        entries = discover_sops(workspace=tmp_path)
        assert entries[0].has_canonical_header is False

    def test_canonical_flag_for_praxis_standards(self, tmp_path):
        d = tmp_path / "meta-organvm" / "praxis-perpetua" / "standards"
        d.mkdir(parents=True)
        (d / "SOP--test.md").write_text("# SOP: Test\n")
        entries = discover_sops(workspace=tmp_path)
        assert entries[0].canonical is True

    def test_not_canonical_outside_praxis(self, tmp_path):
        _make_sop(tmp_path, "organvm-v-logos", "public-process", "sop-test.md")
        entries = discover_sops(workspace=tmp_path)
        assert entries[0].canonical is False

    def test_skips_node_modules(self, tmp_path):
        d = tmp_path / "meta-organvm" / "repo" / "node_modules" / "pkg"
        d.mkdir(parents=True)
        (d / "SOP--hidden.md").write_text("# SOP: Hidden\n")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 0

    def test_skips_dot_git(self, tmp_path):
        d = tmp_path / "meta-organvm" / "repo" / ".git"
        d.mkdir(parents=True)
        (d / "SOP--hidden.md").write_text("# SOP: Hidden\n")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 0

    def test_skips_archive_dir(self, tmp_path):
        d = tmp_path / "meta-organvm" / "repo" / "archive"
        d.mkdir(parents=True)
        (d / "SOP--old.md").write_text("# SOP: Old\n")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 0

    def test_skips_intake_dir(self, tmp_path):
        d = tmp_path / "meta-organvm" / "repo" / "intake"
        d.mkdir(parents=True)
        (d / "SOP--unsorted.md").write_text("# SOP: Unsorted\n")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 0

    def test_skips_vault_backup(self, tmp_path):
        d = tmp_path / "organvm-i-theoria" / "repo" / "vault_backup_2025"
        d.mkdir(parents=True)
        (d / "SOP_INDEX.md").write_text("# SOP Index\n")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 0

    def test_organ_filter(self, tmp_path):
        _make_sop(tmp_path, "meta-organvm", "praxis", "SOP--a.md")
        _make_sop(tmp_path, "organvm-v-logos", "pub", "SOP--b.md")
        entries = discover_sops(workspace=tmp_path, organ="META")
        assert len(entries) == 1
        assert entries[0].org == "meta-organvm"

    def test_organ_filter_invalid(self, tmp_path):
        entries = discover_sops(workspace=tmp_path, organ="NONEXISTENT")
        assert entries == []

    def test_finds_in_subdirectory(self, tmp_path):
        d = tmp_path / "meta-organvm" / "corpus" / "docs" / "operations"
        d.mkdir(parents=True)
        (d / "sop--cicd-resilience.md").write_text("# SOP: CI/CD\n")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1
        assert entries[0].filename == "sop--cicd-resilience.md"

    def test_finds_personal_org(self, tmp_path):
        _make_sop(tmp_path, "4444J99", "app-pipeline", "sop--diagnostic.md")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1
        assert entries[0].org == "4444J99"

    def test_sorted_output(self, tmp_path):
        _make_sop(tmp_path, "organvm-v-logos", "repo-b", "SOP--z.md")
        _make_sop(tmp_path, "meta-organvm", "repo-a", "SOP--a.md")
        entries = discover_sops(workspace=tmp_path)
        assert entries[0].org == "meta-organvm"
        assert entries[1].org == "organvm-v-logos"

    def test_empty_workspace(self, tmp_path):
        entries = discover_sops(workspace=tmp_path)
        assert entries == []

    def test_ignores_non_md_files(self, tmp_path):
        d = tmp_path / "meta-organvm" / "repo"
        d.mkdir(parents=True)
        (d / "SOP--test.txt").write_text("not markdown\n")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 0

    def test_case_insensitive_match(self, tmp_path):
        _make_sop(tmp_path, "meta-organvm", "repo", "Sop--Mixed-Case.md")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1

    def test_discovers_repo_sops_dir(self, tmp_path):
        """Files in .sops/ at repo level are discovered as SOP-SKILL."""
        _make_sops_dir(tmp_path, "meta-organvm", "organvm-engine", "cli-pattern.md")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1
        assert entries[0].doc_type == "SOP-SKILL"
        assert entries[0].scope == "repo"
        assert entries[0].repo == "organvm-engine"

    def test_discovers_organ_sops_dir(self, tmp_path):
        """Files in .sops/ at org level are discovered as SOP-SKILL."""
        _make_sops_dir(tmp_path, "meta-organvm", None, "sync-protocol.md")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1
        assert entries[0].doc_type == "SOP-SKILL"
        assert entries[0].scope == "organ"
        assert entries[0].repo == "meta-organvm"  # repo == org_name for organ-level

    def test_sops_dir_ignores_non_md(self, tmp_path):
        d = tmp_path / "meta-organvm" / "repo" / ".sops"
        d.mkdir(parents=True)
        (d / "notes.txt").write_text("not markdown\n")
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 0

    def test_sops_dir_with_frontmatter(self, tmp_path):
        content = (
            "---\nsop: true\nname: my-sop\nscope: repo\n"
            "triggers:\n  - context:deploy\n"
            "complements:\n  - verification-loop\n"
            "overrides: null\n---\n# My SOP\n"
        )
        _make_sops_dir(tmp_path, "meta-organvm", "engine", "my-sop.md", content)
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1
        e = entries[0]
        assert e.sop_name == "my-sop"
        assert e.scope == "repo"
        assert e.triggers == ["context:deploy"]
        assert e.complements == ["verification-loop"]
        assert e.overrides is None

    def test_sops_dir_with_governed_paths(self, tmp_path):
        content = (
            "---\nsop: true\nname: code-sop\nscope: repo\n"
            "last_reviewed: 2026-06-01\n"
            "governed_paths:\n  - src/organvm_engine/cli/\n  - tests/test_cli.py\n"
            "---\n# Code SOP\n"
        )
        _make_sops_dir(tmp_path, "meta-organvm", "engine", "code-sop.md", content)
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1
        assert entries[0].last_reviewed == "2026-06-01"
        assert entries[0].governed_paths == ["src/organvm_engine/cli/", "tests/test_cli.py"]

    def test_discovers_local_repo_sops_dir(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "sample-repo"\n')
        _make_sops_dir(
            tmp_path,
            "",
            None,
            "local-pattern.md",
            "---\nsop: true\nname: local-pattern\nscope: repo\n---\n# Local Pattern\n",
        )
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1
        assert entries[0].repo == "sample-repo"
        assert entries[0].scope == "repo"

    def test_parses_phase_from_frontmatter(self, tmp_path):
        content = (
            "---\nsop: true\nname: deploy-check\nscope: repo\n"
            "phase: hardening\ntriggers: []\ncomplements: []\n"
            "overrides: null\n---\n# Deploy Check\n"
        )
        _make_sops_dir(tmp_path, "meta-organvm", "engine", "deploy-check.md", content)
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1
        assert entries[0].phase == "hardening"

    def test_phase_defaults_to_any(self, tmp_path):
        content = (
            "---\nsop: true\nname: no-phase\nscope: repo\n"
            "triggers: []\ncomplements: []\n"
            "overrides: null\n---\n# No Phase\n"
        )
        _make_sops_dir(tmp_path, "meta-organvm", "engine", "no-phase.md", content)
        entries = discover_sops(workspace=tmp_path)
        assert len(entries) == 1
        assert entries[0].phase == "any"


class TestParseFrontmatter:
    def test_valid_frontmatter(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\nname: foo\nscope: system\n---\n# Title\n")
        result = _parse_frontmatter(f)
        assert result["name"] == "foo"
        assert result["scope"] == "system"

    def test_no_frontmatter(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Title\n\nBody.\n")
        assert _parse_frontmatter(f) == {}

    def test_missing_closing_marker(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\nname: foo\n# No closing marker\n")
        assert _parse_frontmatter(f) == {}

    def test_empty_frontmatter(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\n---\n# Title\n")
        assert _parse_frontmatter(f) == {}

    def test_with_lists(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\ntriggers:\n  - a\n  - b\ncomplements:\n  - c\n---\n# T\n")
        result = _parse_frontmatter(f)
        assert result["triggers"] == ["a", "b"]
        assert result["complements"] == ["c"]


class TestInferScope:
    def test_system_in_praxis(self, tmp_path):
        f = tmp_path / "meta-organvm" / "praxis-perpetua" / "standards" / "SOP--test.md"
        f.parent.mkdir(parents=True)
        f.touch()
        assert _infer_scope(f, tmp_path) == "system"

    def test_organ_sops_dir(self, tmp_path):
        f = tmp_path / "meta-organvm" / ".sops" / "sync.md"
        f.parent.mkdir(parents=True)
        f.touch()
        assert _infer_scope(f, tmp_path) == "organ"

    def test_repo_sops_dir(self, tmp_path):
        f = tmp_path / "meta-organvm" / "engine" / ".sops" / "cli.md"
        f.parent.mkdir(parents=True)
        f.touch()
        assert _infer_scope(f, tmp_path) == "repo"

    def test_unknown_for_legacy(self, tmp_path):
        f = tmp_path / "meta-organvm" / "repo" / "docs" / "SOP--old.md"
        f.parent.mkdir(parents=True)
        f.touch()
        assert _infer_scope(f, tmp_path) == "unknown"


class TestDeriveSopName:
    def test_strips_sop_prefix(self):
        assert _derive_sop_name("SOP--structural-integrity-audit.md") == "structural-integrity-audit"

    def test_strips_metadoc_prefix(self):
        assert _derive_sop_name("METADOC--research-standards.md") == "research-standards"

    def test_no_prefix(self):
        assert _derive_sop_name("registry-update-protocol.md") == "registry-update-protocol"

    def test_single_hyphen_sop(self):
        assert _derive_sop_name("sop-doctoral-dissertation.md") == "doctoral-dissertation"
