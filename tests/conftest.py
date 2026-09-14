"""Shared test fixtures for organvm-engine."""

import os
from pathlib import Path

import pytest

from organvm_engine.registry.loader import load_registry

FIXTURES = Path(__file__).parent / "fixtures"


def replace_with_nonregular(path: Path, kind: str, outside: Path) -> None:
    """Replace a regular fixture with a requested non-regular filesystem object."""
    path.unlink()
    if kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("FIFO creation is unavailable")
        os.mkfifo(path)
    elif kind == "symlink":
        path.symlink_to(outside)
    elif kind == "directory":
        path.mkdir()
    else:  # pragma: no cover - callers use closed parametrizations
        raise AssertionError(f"unknown replacement kind: {kind}")


# Sentinel path that should never exist — any test accidentally resolving
# the production path will fail fast instead of silently corrupting data.
_BLOCKED = Path("/nonexistent/organvm-test-guard")


@pytest.fixture(autouse=True)
def _block_production_paths(monkeypatch):
    """Redirect all production path defaults to /nonexistent.

    This autouse fixture ensures no test can accidentally read from or
    write to the real registry, governance rules, or corpus directory.
    Tests that need file I/O must use tmp_path or the FIXTURES directory.
    """
    import organvm_engine.paths as paths_mod
    import organvm_engine.registry.loader as loader_mod

    monkeypatch.setattr(paths_mod, "_DEFAULT_WORKSPACE", _BLOCKED)
    # corpus_dir() also probes the Code-root fallback; block it so the
    # content-based probe can never resolve the real corpus during tests.
    monkeypatch.setattr(paths_mod, "_DEFAULT_CODE_ROOT", _BLOCKED)
    monkeypatch.setattr(
        loader_mod, "_default_registry_path", lambda: _BLOCKED / "repo-registry.json",
    )
    # Block env vars that bypass _DEFAULT_WORKSPACE, ensuring tests never
    # touch production corpus/governance files.
    monkeypatch.delenv("ORGANVM_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("ORGANVM_CORPUS_DIR", raising=False)


@pytest.fixture
def registry():
    return load_registry(FIXTURES / "registry-minimal.json")
