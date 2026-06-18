"""Workspace path resolution.

Resolves canonical paths to ORGANVM data sources. Uses environment
variables when available, falls back to conventional defaults.

Environment variables:
    ORGANVM_WORKSPACE_DIR — workspace root (default: ~/Workspace)
    ORGANVM_CORPUS_DIR — corpus repo (default: probe of
        <workspace>/meta-organvm/organvm-corpvs-testamentvm then
        ~/Code/organvm/organvm-corpvs-testamentvm; a candidate qualifies
        only if it contains the repo registry)
    ORGANVM_ADDITIONAL_WORKSPACE_ROOTS — colon-separated flat workspace roots
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_WORKSPACE = Path.home() / "Workspace"
_DEFAULT_CORPUS_SUBPATH = "meta-organvm/organvm-corpvs-testamentvm"
# Corpus relocated to the Code root (2026-06 consolidation). Bare launchd
# daemons do not inherit shell-profile env vars, so corpus_dir() must be able
# to find the real corpus without ORGANVM_CORPUS_DIR. A directory only counts
# as the corpus if it actually holds the repo registry — the legacy
# <workspace> location can persist as a husk of auto-generated context files.
_DEFAULT_CODE_ROOT = Path.home() / "Code" / "organvm"
_CORPUS_REPO_NAME = "organvm-corpvs-testamentvm"
# Canonical registry filename first; registry-v2.json is the retained breadcrumb.
_REGISTRY_FILENAMES = ("repo-registry.json", "registry-v2.json")


@dataclass(frozen=True)
class PathConfig:
    """Explicit workspace/corpus path configuration.

    When unset, values fall back to the environment and conventional defaults.
    """

    workspace_dir: Path | str | None = None
    corpus_root: Path | str | None = None
    additional_workspace_roots: tuple[Path | str, ...] | None = None

    def workspace_root(self) -> Path:
        raw = self.workspace_dir
        if raw is not None:
            return _coerce_path(raw)
        return _coerce_path(os.environ.get("ORGANVM_WORKSPACE_DIR", str(_DEFAULT_WORKSPACE)))

    def corpus_dir(self) -> Path:
        raw = self.corpus_root
        if raw is not None:
            return _coerce_path(raw)
        env = os.environ.get("ORGANVM_CORPUS_DIR")
        if env:
            return _coerce_path(env)
        legacy = self.workspace_root() / _DEFAULT_CORPUS_SUBPATH
        for candidate in (legacy, _DEFAULT_CODE_ROOT / _CORPUS_REPO_NAME):
            if _holds_registry(candidate):
                return candidate
        return legacy

    def additional_roots(self) -> list[Path]:
        raw = self.additional_workspace_roots
        if raw is not None:
            return [_coerce_path(p) for p in raw]
        return additional_workspace_roots(workspace=self.workspace_root())

    def registry_path(self) -> Path:
        corpus = self.corpus_dir()
        for name in _REGISTRY_FILENAMES:
            candidate = corpus / name
            if candidate.is_file():
                return candidate
        # Nothing on disk (e.g. test sandbox): keep the legacy name so
        # callers and fixtures see the historical default.
        return corpus / _REGISTRY_FILENAMES[-1]

    def governance_rules_path(self) -> Path:
        return self.corpus_dir() / "governance-rules.json"

    def registry_dir(self) -> Path:
        """Return the path for per-organ split registry directory."""
        return self.corpus_dir() / "registry"

    def soak_dir(self) -> Path:
        return self.corpus_dir() / "data" / "soak-test"

    def atoms_dir(self) -> Path:
        return self.corpus_dir() / "data" / "atoms"

    def irf_path(self) -> Path:
        """Path to INST-INDEX-RERUM-FACIENDARUM.md."""
        return self.corpus_dir() / "INST-INDEX-RERUM-FACIENDARUM.md"

    def content_dir(self) -> Path:
        """Content pipeline posts directory in praxis-perpetua."""
        return self.corpus_dir().parent / "praxis-perpetua" / "content-pipeline" / "posts"


def _coerce_path(value: Path | str) -> Path:
    return Path(value).expanduser()


def _holds_registry(path: Path) -> bool:
    """True if *path* contains the repo registry (canonical or breadcrumb name).

    Content-based validation: directory existence alone is not enough,
    because relocated repos can leave husk directories behind.
    """
    return any((path / name).is_file() for name in _REGISTRY_FILENAMES)


def _split_path_list(value: str) -> list[Path]:
    return [_coerce_path(p) for p in value.split(":") if p]


def _governance_config_path(workspace: Path) -> Path:
    return workspace / "meta-organvm" / "organvm-corpvs-testamentvm" / "governance-config.yaml"


def _load_governance_config_paths(workspace: Path) -> list[Path]:
    config_path = _governance_config_path(workspace)
    if not config_path.is_file():
        return []

    try:
        import yaml

        data = yaml.safe_load(config_path.read_text()) or {}
    except Exception:
        return []

    roots = data.get("additional_workspace_roots", [])
    if isinstance(roots, str):
        return _split_path_list(roots)
    if isinstance(roots, list):
        return [_coerce_path(p) for p in roots if isinstance(p, str)]
    return []


def resolve_path_config(config: PathConfig | None = None) -> PathConfig:
    """Return an explicit path configuration object."""
    return config if config is not None else PathConfig()


def additional_workspace_roots(
    config: PathConfig | None = None,
    workspace: Path | str | None = None,
) -> list[Path]:
    """Return additive flat workspace roots from env/config.

    Environment configuration takes precedence over governance-config.yaml.
    """
    if config is not None and config.additional_workspace_roots is not None:
        return [_coerce_path(p) for p in config.additional_workspace_roots]

    env = os.environ.get("ORGANVM_ADDITIONAL_WORKSPACE_ROOTS")
    if env:
        return _split_path_list(env)

    ws = _coerce_path(workspace) if workspace is not None else resolve_path_config(config).workspace_root()
    return _load_governance_config_paths(ws)


def workspace_root(config: PathConfig | None = None) -> Path:
    """Return the workspace root directory."""
    return resolve_path_config(config).workspace_root()


def corpus_dir(config: PathConfig | None = None) -> Path:
    """Return the path to organvm-corpvs-testamentvm."""
    return resolve_path_config(config).corpus_dir()


def registry_path(config: PathConfig | None = None) -> Path:
    """Return the path to registry-v2.json."""
    return resolve_path_config(config).registry_path()


def irf_path(config: PathConfig | None = None) -> Path:
    """Return the path to INST-INDEX-RERUM-FACIENDARUM.md."""
    return resolve_path_config(config).irf_path()


def registry_dir(config: PathConfig | None = None) -> Path:
    """Return the path to the per-organ registry directory."""
    return resolve_path_config(config).registry_dir()


def governance_rules_path(config: PathConfig | None = None) -> Path:
    """Return the path to governance-rules.json."""
    return resolve_path_config(config).governance_rules_path()


def soak_dir(config: PathConfig | None = None) -> Path:
    """Return the path to the soak-test data directory."""
    return resolve_path_config(config).soak_dir()


def atoms_dir(config: PathConfig | None = None) -> Path:
    """Return the path to the centralized atoms output directory."""
    return resolve_path_config(config).atoms_dir()


def content_dir(config: PathConfig | None = None) -> Path:
    """Return the path to the content pipeline posts directory."""
    return resolve_path_config(config).content_dir()


def context_sync_dir(config: PathConfig | None = None) -> Path:
    """Directory for context-sync changelog artifacts."""
    return corpus_dir(config) / "data" / "context-sync"


def context_sync_changelog_path(config: PathConfig | None = None) -> Path:
    """Path to the context-sync changelog.jsonl file."""
    return context_sync_dir(config) / "changelog.jsonl"


def fossil_dir(config: PathConfig | None = None) -> Path:
    """Directory for fossil record artifacts."""
    return corpus_dir(config) / "data" / "fossil"


def fossil_record_path(config: PathConfig | None = None) -> Path:
    """Path to the fossil-record.jsonl file."""
    return fossil_dir(config) / "fossil-record.jsonl"


def resolve_workspace(
    args: "argparse.Namespace | None" = None,
    config: PathConfig | None = None,
) -> Path | None:
    """Resolve workspace from CLI args, env, or default."""
    if args is not None:
        raw = getattr(args, "workspace", None)
        if raw:
            return _coerce_path(raw).resolve()
    cfg = resolve_path_config(config)
    if cfg.workspace_dir is not None:
        return cfg.workspace_root().resolve()
    env = os.environ.get("ORGANVM_WORKSPACE_DIR")
    if env:
        return _coerce_path(env).resolve()
    default = _DEFAULT_WORKSPACE
    return default if default.is_dir() else None
