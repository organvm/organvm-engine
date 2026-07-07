"""Tests for ci/scaffold.py — CI workflow YAML generation."""

from pathlib import Path

import pytest

from organvm_engine.ci.scaffold import (
    Stack,
    detect_stack,
    scaffold_repo,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def python_repo(tmp_path: Path) -> Path:
    """Create a Python project directory."""
    repo = tmp_path / "my-python-repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "test"')
    (repo / "src").mkdir()
    return repo


@pytest.fixture()
def ts_repo(tmp_path: Path) -> Path:
    """Create a TypeScript project directory."""
    repo = tmp_path / "my-ts-repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"name": "test"}')
    (repo / "tsconfig.json").write_text('{"compilerOptions": {}}')
    return repo


@pytest.fixture()
def hybrid_repo(tmp_path: Path) -> Path:
    """Create a hybrid Python + TypeScript project directory."""
    repo = tmp_path / "my-hybrid-repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "test"')
    (repo / "package.json").write_text('{"name": "test"}')
    return repo


@pytest.fixture()
def empty_repo(tmp_path: Path) -> Path:
    """Create an empty project directory (unknown stack)."""
    repo = tmp_path / "my-empty-repo"
    repo.mkdir()
    return repo


# ---------------------------------------------------------------------------
# Stack detection
# ---------------------------------------------------------------------------

class TestDetectStack:
    def test_python_pyproject(self, python_repo: Path):
        assert detect_stack(python_repo) == Stack.PYTHON

    def test_python_setup_py(self, tmp_path: Path):
        repo = tmp_path / "setup-repo"
        repo.mkdir()
        (repo / "setup.py").write_text("from setuptools import setup")
        assert detect_stack(repo) == Stack.PYTHON

    def test_python_requirements_txt(self, tmp_path: Path):
        repo = tmp_path / "req-repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("flask\n")
        assert detect_stack(repo) == Stack.PYTHON

    def test_typescript_package_json(self, ts_repo: Path):
        assert detect_stack(ts_repo) == Stack.TYPESCRIPT

    def test_typescript_tsconfig_only(self, tmp_path: Path):
        repo = tmp_path / "ts-only"
        repo.mkdir()
        (repo / "tsconfig.json").write_text("{}")
        assert detect_stack(repo) == Stack.TYPESCRIPT

    def test_hybrid(self, hybrid_repo: Path):
        assert detect_stack(hybrid_repo) == Stack.HYBRID

    def test_unknown(self, empty_repo: Path):
        assert detect_stack(empty_repo) == Stack.UNKNOWN


# ---------------------------------------------------------------------------
# Scaffold generation
# ---------------------------------------------------------------------------

class TestScaffoldRepo:
    def test_python_all_steps(self, python_repo: Path):
        result = scaffold_repo(python_repo, "my-python-repo")
        assert result.stack == Stack.PYTHON
        assert result.lint_yaml is not None
        assert "ruff check" in result.lint_yaml
        assert result.test_yaml is not None
        assert "pytest" in result.test_yaml
        assert result.typecheck_yaml is not None
        assert "pyright" in result.typecheck_yaml

    def test_typescript_all_steps(self, ts_repo: Path):
        result = scaffold_repo(ts_repo, "my-ts-repo")
        assert result.stack == Stack.TYPESCRIPT
        assert result.lint_yaml is not None
        assert "eslint" in result.lint_yaml
        assert result.test_yaml is not None
        assert "npm test" in result.test_yaml
        assert result.typecheck_yaml is not None
        assert "tsc --noEmit" in result.typecheck_yaml

    def test_hybrid_includes_both(self, hybrid_repo: Path):
        result = scaffold_repo(hybrid_repo, "my-hybrid-repo")
        assert result.stack == Stack.HYBRID
        assert "ruff check" in result.lint_yaml
        assert "eslint" in result.lint_yaml
        assert "pytest" in result.test_yaml
        assert "npm test" in result.test_yaml

    def test_lint_only(self, python_repo: Path):
        result = scaffold_repo(
            python_repo, "test", lint=True, test=False, typecheck=False,
        )
        assert result.lint_yaml is not None
        assert result.test_yaml is None
        assert result.typecheck_yaml is None

    def test_test_only(self, python_repo: Path):
        result = scaffold_repo(
            python_repo, "test", lint=False, test=True, typecheck=False,
        )
        assert result.lint_yaml is None
        assert result.test_yaml is not None
        assert result.typecheck_yaml is None

    def test_typecheck_only(self, python_repo: Path):
        result = scaffold_repo(
            python_repo, "test", lint=False, test=False, typecheck=True,
        )
        assert result.lint_yaml is None
        assert result.test_yaml is None
        assert result.typecheck_yaml is not None

    def test_unknown_stack_returns_none_steps(self, empty_repo: Path):
        result = scaffold_repo(empty_repo, "empty")
        assert result.stack == Stack.UNKNOWN
        assert result.lint_yaml is None
        assert result.test_yaml is None
        assert result.typecheck_yaml is None

    def test_no_steps_requested(self, python_repo: Path):
        result = scaffold_repo(
            python_repo, "test", lint=False, test=False, typecheck=False,
        )
        assert result.lint_yaml is None
        assert result.test_yaml is None
        assert result.typecheck_yaml is None


# ---------------------------------------------------------------------------
# Combined workflow output
# ---------------------------------------------------------------------------

class TestCombinedYaml:
    def test_python_combined_is_valid_yaml_structure(self, python_repo: Path):
        result = scaffold_repo(python_repo, "test-repo")
        combined = result.combined_yaml()
        assert "name: CI" in combined
        assert "actions/checkout@v4" in combined
        assert "setup-python@v5" in combined
        assert "ruff check" in combined
        assert "pytest" in combined
        assert "pyright" in combined

    def test_typescript_combined_has_node_setup(self, ts_repo: Path):
        result = scaffold_repo(ts_repo, "test-repo")
        combined = result.combined_yaml()
        assert "setup-node@v4" in combined
        assert "npm ci" in combined

    def test_hybrid_combined_has_both_setups(self, hybrid_repo: Path):
        result = scaffold_repo(hybrid_repo, "test-repo")
        combined = result.combined_yaml()
        assert "setup-python@v5" in combined
        assert "setup-node@v4" in combined

    def test_empty_combined_for_unknown_stack(self, empty_repo: Path):
        result = scaffold_repo(empty_repo, "empty")
        assert result.combined_yaml() == ""

    def test_combined_includes_repo_name(self, python_repo: Path):
        result = scaffold_repo(python_repo, "my-special-repo")
        combined = result.combined_yaml()
        assert "my-special-repo" in combined

    def test_combined_has_push_and_pr_triggers(self, python_repo: Path):
        result = scaffold_repo(python_repo, "test-repo")
        combined = result.combined_yaml()
        assert "push:" in combined
        assert "pull_request:" in combined
        assert "branches: [main]" in combined
