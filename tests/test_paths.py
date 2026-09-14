"""Tests for workspace path resolution."""

from pathlib import Path

import pytest
from conftest import replace_with_nonregular

from organvm_engine import paths


class TestPaths:
    def test_workspace_root_uses_blocked_default(self, monkeypatch):
        # autouse fixture sets _DEFAULT_WORKSPACE to /nonexistent/...
        # Clear env var so the blocked default is actually used
        monkeypatch.delenv("ORGANVM_WORKSPACE_DIR", raising=False)
        result = paths.workspace_root()
        assert "nonexistent" in str(result)

    def test_workspace_root_env_override(self, monkeypatch):
        monkeypatch.setenv("ORGANVM_WORKSPACE_DIR", "/tmp/test-workspace")
        assert paths.workspace_root() == Path("/tmp/test-workspace")

    def test_corpus_dir_default(self):
        result = paths.corpus_dir()
        assert result == paths._DEFAULT_CODE_ROOT / "organvm-corpvs-testamentvm"

    def test_corpus_dir_env_override(self, monkeypatch):
        monkeypatch.setenv("ORGANVM_CORPUS_DIR", "/tmp/test-corpus")
        assert paths.corpus_dir() == Path("/tmp/test-corpus")

    def test_additional_workspace_roots_env_override(self, monkeypatch):
        monkeypatch.setenv(
            "ORGANVM_ADDITIONAL_WORKSPACE_ROOTS",
            "/tmp/flat-one:/tmp/flat-two",
        )
        assert paths.additional_workspace_roots() == [
            Path("/tmp/flat-one"),
            Path("/tmp/flat-two"),
        ]

    def test_additional_workspace_roots_from_governance_config(self, tmp_path):
        config_dir = tmp_path / "meta-organvm" / "organvm-corpvs-testamentvm"
        config_dir.mkdir(parents=True)
        (config_dir / "governance-config.yaml").write_text(
            "additional_workspace_roots:\n"
            "  - ~/Code/organvm\n"
            "  - /tmp/other-root\n",
        )
        assert paths.additional_workspace_roots(workspace=tmp_path) == [
            Path.home() / "Code" / "organvm",
            Path("/tmp/other-root"),
        ]

    @pytest.mark.parametrize("replacement_kind", ["fifo", "symlink", "directory"])
    def test_governance_config_nonregular_swap_never_blocks(
        self,
        tmp_path,
        monkeypatch,
        replacement_kind,
    ):
        config_dir = tmp_path / "meta-organvm" / "organvm-corpvs-testamentvm"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "governance-config.yaml"
        config_path.write_text(
            "additional_workspace_roots: [/tmp/foreign]\n",
            encoding="utf-8",
        )
        outside = tmp_path / "outside.yaml"
        outside.write_text(
            "additional_workspace_roots: [/tmp/outside]\n",
            encoding="utf-8",
        )
        real_read = paths.read_stable_regular_bytes
        swapped = False

        def swap_after_is_file(path, *args, **kwargs):
            nonlocal swapped
            if Path(path) == config_path and not swapped:
                replace_with_nonregular(
                    config_path,
                    replacement_kind,
                    outside,
                )
                swapped = True
            return real_read(path, *args, **kwargs)

        monkeypatch.setattr(paths, "read_stable_regular_bytes", swap_after_is_file)

        assert paths.additional_workspace_roots(workspace=tmp_path) == []
        assert swapped is True

    def test_corpus_dir_skips_husk_and_probes_code_root(self, tmp_path, monkeypatch):
        # Legacy location exists but holds no registry (relocation husk);
        # the Code-root candidate holds the canonical registry and wins.
        monkeypatch.delenv("ORGANVM_WORKSPACE_DIR", raising=False)
        husk = tmp_path / "ws" / "meta-organvm" / "organvm-corpvs-testamentvm"
        husk.mkdir(parents=True)
        (husk / "CLAUDE.md").write_text("husk")
        code_root = tmp_path / "code-organvm"
        corpus = code_root / "organvm-corpvs-testamentvm"
        corpus.mkdir(parents=True)
        (corpus / "repo-registry.json").write_text("{}")
        monkeypatch.setattr(paths, "_DEFAULT_WORKSPACE", tmp_path / "ws")
        monkeypatch.setattr(paths, "_DEFAULT_CODE_ROOT", code_root)
        assert paths.corpus_dir() == corpus

    def test_corpus_dir_prefers_canonical_code_root_over_legacy(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ORGANVM_WORKSPACE_DIR", raising=False)
        legacy = tmp_path / "ws" / "meta-organvm" / "organvm-corpvs-testamentvm"
        legacy.mkdir(parents=True)
        (legacy / "repo-registry.json").write_text("{}")
        code_root = tmp_path / "code-organvm"
        other = code_root / "organvm-corpvs-testamentvm"
        other.mkdir(parents=True)
        (other / "repo-registry.json").write_text("{}")
        monkeypatch.setattr(paths, "_DEFAULT_WORKSPACE", tmp_path / "ws")
        monkeypatch.setattr(paths, "_DEFAULT_CODE_ROOT", code_root)
        assert paths.corpus_dir() == other

    def test_corpus_dir_uses_legacy_only_as_fallback(self, tmp_path, monkeypatch):
        legacy = tmp_path / "ws" / "meta-organvm" / "organvm-corpvs-testamentvm"
        legacy.mkdir(parents=True)
        (legacy / "repo-registry.json").write_text("{}")
        monkeypatch.setattr(paths, "_DEFAULT_WORKSPACE", tmp_path / "ws")
        monkeypatch.setattr(paths, "_DEFAULT_CODE_ROOT", tmp_path / "missing-code-root")
        assert paths.corpus_dir() == legacy

    def test_registry_path(self):
        result = paths.registry_path()
        assert result.name == "repo-registry.json"
        assert "organvm-corpvs-testamentvm" in str(result)

    def test_registry_path_prefers_canonical_name(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORGANVM_CORPUS_DIR", str(tmp_path))
        (tmp_path / "repo-registry.json").write_text("{}")
        (tmp_path / "registry-v2.json").write_text("{}")
        assert paths.registry_path().name == "repo-registry.json"

    def test_registry_path_does_not_select_breadcrumb(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORGANVM_CORPUS_DIR", str(tmp_path))
        (tmp_path / "registry-v2.json").write_text("{}")
        assert paths.registry_path().name == "repo-registry.json"

    def test_governance_rules_path(self):
        result = paths.governance_rules_path()
        assert result.name == "governance-rules.json"

    def test_soak_dir(self):
        result = paths.soak_dir()
        assert result.name == "soak-test"
        assert "data" in str(result)
