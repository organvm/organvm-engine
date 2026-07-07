"""CI workflow scaffolding — generate lint/test/typecheck YAML for repos.

Drives issues #58 (linting), #59 (testing), #60 (type-checking) of the
Descent Protocol cross-repo infrastructure rollout.

Given a repo path, detects the project stack (Python, TypeScript, or hybrid)
and generates GitHub Actions workflow YAML snippets for each requested
capability.  Works standalone or via ``organvm ci scaffold <repo>``.
"""

from __future__ import annotations

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
        return _wrap_workflow(self.repo_name, self.stack, "\n".join(steps))


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

_PYTHON_LINT_STEP = dedent("""\
      - name: Lint (ruff)
        run: |
          pip install ruff
          ruff check src/""")

_TS_LINT_STEP = dedent("""\
      - name: Lint (eslint)
        run: |
          npm ci
          npm run lint""")

_PYTHON_TEST_STEP = dedent("""\
      - name: Test (pytest)
        run: |
          pip install -e ".[dev]"
          pytest tests/ -v""")

_TS_TEST_STEP = dedent("""\
      - name: Test
        run: |
          npm ci
          npm test""")

_PYTHON_TYPECHECK_STEP = dedent("""\
      - name: Type check (pyright)
        run: |
          pip install pyright
          pyright src/""")

_TS_TYPECHECK_STEP = dedent("""\
      - name: Type check (tsc)
        run: |
          npm ci
          npx tsc --noEmit""")


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


def _typecheck_step(stack: Stack) -> str | None:
    """Generate type-check step YAML for the given stack."""
    if stack == Stack.PYTHON:
        return _PYTHON_TYPECHECK_STEP
    if stack == Stack.TYPESCRIPT:
        return _TS_TYPECHECK_STEP
    if stack == Stack.HYBRID:
        return f"{_PYTHON_TYPECHECK_STEP}\n{_TS_TYPECHECK_STEP}"
    return None


# ---------------------------------------------------------------------------
# Workflow wrapper
# ---------------------------------------------------------------------------

_PYTHON_VERSION = "3.11"
_NODE_VERSION = "20"


def _wrap_workflow(repo_name: str, stack: Stack, steps_block: str) -> str:
    """Wrap step snippets in a complete GitHub Actions workflow."""
    setup_lines: list[str] = []

    if stack in (Stack.PYTHON, Stack.HYBRID):
        setup_lines.append(dedent(f"""\
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "{_PYTHON_VERSION}"
      - name: Install Python dependencies
        run: pip install -e ".[dev]" """))

    if stack in (Stack.TYPESCRIPT, Stack.HYBRID):
        setup_lines.append(dedent(f"""\
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "{_NODE_VERSION}"
      - name: Install Node dependencies
        run: npm ci"""))

    setup_block = "\n".join(setup_lines)

    return dedent(f"""\
# CI workflow for {repo_name}
# Generated by: organvm ci scaffold {repo_name}
name: CI

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
        result.typecheck_yaml = _typecheck_step(stack)

    return result
