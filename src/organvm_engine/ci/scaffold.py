"""CI workflow scaffolding — generate lint/test/typecheck YAML for repos.

Drives issues #58 (linting), #59 (testing), #60 (type-checking) of the
Descent Protocol cross-repo infrastructure rollout.

Given a repo path, detects the project stack (Python, TypeScript, or hybrid)
and generates GitHub Actions workflow YAML snippets for each requested
capability.  Works standalone or via ``organvm ci scaffold <repo>``.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from textwrap import dedent


class Stack(str, Enum):
    """Detected project technology stack."""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


@dataclass
class ScaffoldResult:
    """Generated CI scaffold for a repository."""

    repo_name: str
    stack: Stack
    lint_yaml: str | None = None
    test_yaml: str | None = None
    typecheck_yaml: str | None = None

    def combined_yaml(self) -> str:
        """Return a single workflow file incorporating all requested steps."""
        steps: list[str] = []
        if self.lint_yaml:
            steps.append(self.lint_yaml)
        if self.test_yaml:
            steps.append(self.test_yaml)
        if self.typecheck_yaml:
            steps.append(self.typecheck_yaml)
        if not steps:
            return ""
        return _wrap_workflow(
            self.repo_name,
            self.stack,
            "\n".join(steps),
            workflow_name=self.workflow_name(),
        )

    def workflow_name(self) -> str:
        """Return the display name for the generated workflow."""
        if self.typecheck_yaml and not self.lint_yaml and not self.test_yaml:
            return "Type Check"
        if self.lint_yaml and not self.test_yaml and not self.typecheck_yaml:
            return "Lint"
        if self.test_yaml and not self.lint_yaml and not self.typecheck_yaml:
            return "Test"
        return "CI"

    def workflow_filename(self) -> str:
        """Return a safe default filename for the generated workflow."""
        if self.typecheck_yaml and not self.lint_yaml and not self.test_yaml:
            return "type-check.yml"
        if self.lint_yaml and not self.test_yaml and not self.typecheck_yaml:
            return "lint.yml"
        if self.test_yaml and not self.lint_yaml and not self.typecheck_yaml:
            return "test.yml"
        return "ci.yml"


# ---------------------------------------------------------------------------
# Stack detection
# ---------------------------------------------------------------------------

def detect_stack(repo_path: Path) -> Stack:
    """Detect the technology stack of a repository from on-disk markers.

    Returns Stack.PYTHON, Stack.TYPESCRIPT, Stack.HYBRID, or Stack.UNKNOWN.
    """
    has_python = (
        (repo_path / "pyproject.toml").is_file()
        or (repo_path / "setup.py").is_file()
        or (repo_path / "setup.cfg").is_file()
        or (repo_path / "requirements.txt").is_file()
    )
    has_ts = (
        (repo_path / "package.json").is_file()
        or (repo_path / "tsconfig.json").is_file()
    )

    if has_python and has_ts:
        return Stack.HYBRID
    if has_python:
        return Stack.PYTHON
    if has_ts:
        return Stack.TYPESCRIPT
    return Stack.UNKNOWN


# ---------------------------------------------------------------------------
# Step generators — each returns an indented YAML snippet for one job step
# ---------------------------------------------------------------------------

_PYTHON_LINT_STEP = """\
      - name: Lint (ruff)
        run: |
          pip install ruff
          ruff check src/"""

_TS_LINT_STEP = """\
      - name: Lint (eslint)
        run: |
          npm ci
          npm run lint"""

_PYTHON_TEST_STEP = """\
      - name: Test (pytest)
        run: |
          pip install -e ".[dev]"
          pytest tests/ -v"""

_TS_TEST_STEP = """\
      - name: Test
        run: |
          npm ci
          npm test"""

def _python_typecheck_target(repo_path: Path) -> str:
    """Return the pyright target for a Python repository.

    Src-layout packages should check ``src/``.  Flat-layout packages should
    check the repository root; otherwise repos with package directories beside
    ``pyproject.toml`` are silently skipped.
    """
    src_dir = repo_path / "src"
    if not src_dir.is_dir():
        return "."

    if _pyproject_uses_src_layout(repo_path / "pyproject.toml"):
        return "src/"

    if _pyproject_declares_flat_layout(repo_path / "pyproject.toml"):
        return "."

    if _has_flat_layout_python_sources(repo_path):
        return "."

    return "src/"


def _pyproject_uses_src_layout(pyproject_path: Path) -> bool:
    """Return True when pyproject explicitly declares src package discovery."""
    data = _load_pyproject(pyproject_path)
    if data is None:
        return False

    tool = data.get("tool")
    if not isinstance(tool, dict):
        return False

    setuptools = tool.get("setuptools")
    if isinstance(setuptools, dict):
        packages = setuptools.get("packages")
        if isinstance(packages, dict):
            find = packages.get("find")
            if isinstance(find, dict):
                where = find.get("where")
                if _is_src_layout_value(where):
                    return True

    hatch = tool.get("hatch")
    if isinstance(hatch, dict):
        build = hatch.get("build")
        if isinstance(build, dict):
            targets = build.get("targets")
            if isinstance(targets, dict):
                wheel = targets.get("wheel")
                if isinstance(wheel, dict):
                    packages = wheel.get("packages")
                    if _is_src_layout_value(packages):
                        return True

    return False


def _pyproject_declares_flat_layout(pyproject_path: Path) -> bool:
    """Return True when pyproject explicitly points packaging at repo root."""
    data = _load_pyproject(pyproject_path)
    if data is None:
        return False

    tool = data.get("tool")
    if not isinstance(tool, dict):
        return False

    setuptools = tool.get("setuptools")
    if isinstance(setuptools, dict):
        py_modules = setuptools.get("py-modules")
        packages = setuptools.get("packages")
        if _is_non_empty_string_list(py_modules) or _is_non_empty_string_list(packages):
            return True
        if isinstance(packages, dict):
            find = packages.get("find")
            if isinstance(find, dict) and _is_flat_layout_value(find.get("where")):
                return True

    hatch = tool.get("hatch")
    if isinstance(hatch, dict):
        build = hatch.get("build")
        if isinstance(build, dict):
            targets = build.get("targets")
            if isinstance(targets, dict):
                wheel = targets.get("wheel")
                if isinstance(wheel, dict):
                    packages = wheel.get("packages")
                    only_include = wheel.get("only-include")
                    if (
                        _is_flat_package_value(packages)
                        or _is_flat_package_value(only_include)
                    ):
                        return True

    return False


def _load_pyproject(pyproject_path: Path) -> dict[str, object] | None:
    """Load pyproject TOML data, returning None when unavailable or invalid."""
    if not pyproject_path.is_file():
        return None

    try:
        data = tomllib.loads(pyproject_path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None

    return data if isinstance(data, dict) else None


def _is_src_layout_value(value: object) -> bool:
    """Return True for common pyproject spellings of a src layout."""
    if value == "src":
        return True
    return isinstance(value, list) and value == ["src"]


def _is_flat_layout_value(value: object) -> bool:
    """Return True for common pyproject spellings of repo-root discovery."""
    if value == ".":
        return True
    return isinstance(value, list) and value == ["."]


def _is_non_empty_string_list(value: object) -> bool:
    """Return True when value is a non-empty list of strings."""
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) for item in value)
    )


def _is_flat_package_value(value: object) -> bool:
    """Return True for hatch package lists that point outside src."""
    if isinstance(value, str):
        return not value.startswith("src/")
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        return any(not item.startswith("src/") for item in value)
    return False


_IGNORED_FLAT_SOURCE_DIRS = {
    ".git",
    ".github",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "dist",
    "docs",
    "htmlcov",
    "node_modules",
    "site",
    "src",
    "test",
    "tests",
    "venv",
}


def _has_flat_layout_python_sources(repo_path: Path) -> bool:
    """Return True when Python sources live directly under the repo root."""
    for child in repo_path.iterdir():
        if child.is_file() and child.suffix == ".py":
            return True
        if (
            child.is_dir()
            and child.name not in _IGNORED_FLAT_SOURCE_DIRS
            and not child.name.startswith(".")
            and _contains_python_file(child)
        ):
            return True
    return False


def _contains_python_file(path: Path) -> bool:
    """Return True when a directory contains any Python source file."""
    return any(child.is_file() and child.suffix == ".py" for child in path.rglob("*.py"))


def _python_typecheck_step(repo_path: Path) -> str:
    target = _python_typecheck_target(repo_path)
    return f"""\
      - name: Type check (pyright)
        run: |
          pip install pyright
          pyright {target}"""

_TS_TYPECHECK_STEP = """\
      - name: Type check (tsc)
        run: |
          npm ci
          npx tsc --noEmit"""


def _lint_step(stack: Stack) -> str | None:
    """Generate lint step YAML for the given stack."""
    if stack == Stack.PYTHON:
        return _PYTHON_LINT_STEP
    if stack == Stack.TYPESCRIPT:
        return _TS_LINT_STEP
    if stack == Stack.HYBRID:
        return f"{_PYTHON_LINT_STEP}\n{_TS_LINT_STEP}"
    return None


def _test_step(stack: Stack) -> str | None:
    """Generate test step YAML for the given stack."""
    if stack == Stack.PYTHON:
        return _PYTHON_TEST_STEP
    if stack == Stack.TYPESCRIPT:
        return _TS_TEST_STEP
    if stack == Stack.HYBRID:
        return f"{_PYTHON_TEST_STEP}\n{_TS_TEST_STEP}"
    return None


def _typecheck_step(stack: Stack, repo_path: Path) -> str | None:
    """Generate type-check step YAML for the given stack."""
    if stack == Stack.PYTHON:
        return _python_typecheck_step(repo_path)
    if stack == Stack.TYPESCRIPT:
        return _TS_TYPECHECK_STEP
    if stack == Stack.HYBRID:
        return f"{_python_typecheck_step(repo_path)}\n{_TS_TYPECHECK_STEP}"
    return None


# ---------------------------------------------------------------------------
# Workflow wrapper
# ---------------------------------------------------------------------------

_PYTHON_VERSION = "3.11"
_NODE_VERSION = "20"


def _wrap_workflow(
    repo_name: str,
    stack: Stack,
    steps_block: str,
    *,
    workflow_name: str = "CI",
) -> str:
    """Wrap step snippets in a complete GitHub Actions workflow."""
    setup_lines: list[str] = []

    if stack in (Stack.PYTHON, Stack.HYBRID):
        setup_lines.append(f"""\
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "{_PYTHON_VERSION}"
      - name: Install Python dependencies
        run: pip install -e ".[dev]" """.rstrip())

    if stack in (Stack.TYPESCRIPT, Stack.HYBRID):
        setup_lines.append(f"""\
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "{_NODE_VERSION}"
      - name: Install Node dependencies
        run: npm ci""")

    setup_block = "\n".join(setup_lines)

    return dedent(f"""\
# CI workflow for {repo_name}
# Generated by: organvm ci scaffold {repo_name}
name: {workflow_name}

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
{setup_block}
{steps_block}
""")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scaffold_repo(
    repo_path: Path,
    repo_name: str,
    *,
    lint: bool = True,
    test: bool = True,
    typecheck: bool = True,
) -> ScaffoldResult:
    """Generate CI workflow snippets for a repository.

    Args:
        repo_path: Filesystem path to the repo root.
        repo_name: Repository name (for labeling output).
        lint: Include linting step.
        test: Include testing step.
        typecheck: Include type-checking step.

    Returns:
        ScaffoldResult with the requested YAML snippets and a combined workflow.
    """
    stack = detect_stack(repo_path)

    result = ScaffoldResult(repo_name=repo_name, stack=stack)

    if lint:
        result.lint_yaml = _lint_step(stack)
    if test:
        result.test_yaml = _test_step(stack)
    if typecheck:
        result.typecheck_yaml = _typecheck_step(stack, repo_path)

    return result
