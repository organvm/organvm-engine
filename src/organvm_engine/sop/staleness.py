"""Detect SOP staleness against governed repository code."""

from __future__ import annotations

import glob
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from organvm_engine.seed.discover import discover_seeds
from organvm_engine.sop.discover import SOPEntry

_MAPPING_FILENAMES = ("sop-governance.yaml", "sop-governance.yml")
_MAPPING_KEYS = ("sop_governance", "sop-governance", "sop_mappings", "sops")
_PATH_KEYS = ("paths", "governs", "governed_paths", "code", "code_paths")
_SOP_KEYS = ("sop", "name", "sop_name", "filename")
_SKIP_SEGMENTS = frozenset({
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
})
_SCOPE_PRIORITY = {"repo": 0, "organ": 1, "system": 2, "unknown": 3}


@dataclass(frozen=True)
class SOPCodeMapping:
    """A declaration that an SOP governs one or more code paths."""

    sop_name: str
    paths: tuple[str, ...]
    source: Path
    base_dir: Path
    org: str | None = None
    repo: str | None = None


@dataclass
class SOPStalenessResult:
    """Result for one SOP-to-code mapping."""

    mapping: SOPCodeMapping
    status: str
    sop_entry: SOPEntry | None = None
    sop_mtime: float | None = None
    code_mtime: float | None = None
    newest_code_path: Path | None = None
    governed_files: list[Path] = field(default_factory=list)
    missing_paths: list[Path] = field(default_factory=list)

    @property
    def is_stale(self) -> bool:
        return self.status == "stale"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sop": self.mapping.sop_name,
            "status": self.status,
            "sop_path": str(self.sop_entry.path) if self.sop_entry else None,
            "sop_mtime": self.sop_mtime,
            "sop_modified": _format_timestamp(self.sop_mtime),
            "code_mtime": self.code_mtime,
            "code_modified": _format_timestamp(self.code_mtime),
            "newest_code_path": str(self.newest_code_path) if self.newest_code_path else None,
            "governed_paths": list(self.mapping.paths),
            "governed_files": [str(path) for path in self.governed_files],
            "missing_paths": [str(path) for path in self.missing_paths],
            "mapping_source": str(self.mapping.source),
            "repo": self.mapping.repo,
            "org": self.mapping.org,
        }


def load_sop_code_mappings(
    workspace: Path | str | None = None,
    mapping_path: Path | str | None = None,
) -> list[SOPCodeMapping]:
    """Load SOP-code mappings from seed.yaml and sop-governance.yaml files.

    Supported seed.yaml shape::

        sop_governance:
          - sop: cli-module-pattern
            paths:
              - src/organvm_engine/cli/

    Dedicated ``sop-governance.yaml`` files may use the same top-level key or a
    top-level ``sops`` list. Relative paths resolve from the file containing the
    mapping, which makes repo-local seed declarations portable.
    """
    if mapping_path is not None:
        path = Path(mapping_path).expanduser()
        return _load_mapping_file(path)

    ws = Path(workspace).expanduser() if workspace is not None else Path.cwd()
    candidates = _mapping_candidates(ws)

    mappings: list[SOPCodeMapping] = []
    for candidate in candidates:
        mappings.extend(_load_mapping_file(candidate))
    return mappings


def audit_sop_staleness(
    discovered: list[SOPEntry],
    mappings: list[SOPCodeMapping],
) -> list[SOPStalenessResult]:
    """Compare mapped SOP mtimes against the newest governed code mtime."""
    results: list[SOPStalenessResult] = []
    for mapping in mappings:
        sop_entry = _select_sop_entry(mapping, discovered)
        if sop_entry is None:
            results.append(SOPStalenessResult(mapping=mapping, status="missing-sop"))
            continue

        try:
            sop_mtime = sop_entry.path.stat().st_mtime
        except OSError:
            results.append(
                SOPStalenessResult(
                    mapping=mapping,
                    status="missing-sop",
                    sop_entry=sop_entry,
                ),
            )
            continue

        governed_files, missing_paths = _resolve_governed_files(mapping)
        if not governed_files:
            results.append(
                SOPStalenessResult(
                    mapping=mapping,
                    status="missing-code",
                    sop_entry=sop_entry,
                    sop_mtime=sop_mtime,
                    missing_paths=missing_paths,
                ),
            )
            continue

        newest_code_path = max(governed_files, key=lambda path: path.stat().st_mtime)
        code_mtime = newest_code_path.stat().st_mtime
        status = "stale" if code_mtime > sop_mtime else "fresh"
        results.append(
            SOPStalenessResult(
                mapping=mapping,
                status=status,
                sop_entry=sop_entry,
                sop_mtime=sop_mtime,
                code_mtime=code_mtime,
                newest_code_path=newest_code_path,
                governed_files=governed_files,
                missing_paths=missing_paths,
            ),
        )
    return results


def stale_results(results: list[SOPStalenessResult]) -> list[SOPStalenessResult]:
    """Return results that need operator attention."""
    return [r for r in results if r.status != "fresh"]


def _mapping_candidates(workspace: Path) -> list[Path]:
    candidates: list[Path] = []

    for name in _MAPPING_FILENAMES:
        candidates.append(workspace / name)

    root_seed = workspace / "seed.yaml"
    candidates.append(root_seed)

    for seed_path in discover_seeds(workspace=workspace):
        candidates.append(seed_path)
        for name in _MAPPING_FILENAMES:
            candidates.append(seed_path.parent / name)

    seen: set[Path] = set()
    existing: list[Path] = []
    for candidate in candidates:
        try:
            key = candidate.resolve()
        except OSError:
            key = candidate
        if key in seen or not candidate.is_file():
            continue
        seen.add(key)
        existing.append(candidate)
    return existing


def _load_mapping_file(path: Path) -> list[SOPCodeMapping]:
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(data, dict):
        return []

    block = _mapping_block(data)
    if block is None:
        return []

    default_org = _optional_str(data.get("org") or data.get("organ"))
    default_repo = _optional_str(data.get("repo"))
    return _parse_mapping_block(
        block,
        source=path,
        base_dir=path.parent,
        default_org=default_org,
        default_repo=default_repo,
    )


def _mapping_block(data: dict[str, Any]) -> Any:
    for key in _MAPPING_KEYS:
        if key in data:
            block = data[key]
            if isinstance(block, dict):
                for nested_key in ("mappings", "sops"):
                    if nested_key in block:
                        return block[nested_key]
            return block
    return None


def _parse_mapping_block(
    block: Any,
    *,
    source: Path,
    base_dir: Path,
    default_org: str | None,
    default_repo: str | None,
) -> list[SOPCodeMapping]:
    if isinstance(block, list):
        entries = [(None, item) for item in block]
    elif isinstance(block, dict):
        entries = [
            (key, value)
            for key, value in block.items()
            if key not in {"schema_version", "version", "metadata"}
        ]
    else:
        return []

    mappings: list[SOPCodeMapping] = []
    for key, value in entries:
        mapping = _parse_mapping_entry(
            key,
            value,
            source=source,
            base_dir=base_dir,
            default_org=default_org,
            default_repo=default_repo,
        )
        if mapping is not None:
            mappings.append(mapping)
    return mappings


def _parse_mapping_entry(
    key: str | None,
    value: Any,
    *,
    source: Path,
    base_dir: Path,
    default_org: str | None,
    default_repo: str | None,
) -> SOPCodeMapping | None:
    if isinstance(value, dict):
        sop_name = _first_str(value, _SOP_KEYS) or key
        raw_paths = _first_present(value, _PATH_KEYS)
        org = _optional_str(value.get("org") or value.get("organ")) or default_org
        repo = _optional_str(value.get("repo")) or default_repo
        entry_base = _entry_base_dir(value, base_dir)
    else:
        sop_name = key
        raw_paths = value
        org = default_org
        repo = default_repo
        entry_base = base_dir

    if not sop_name:
        return None

    paths = _coerce_paths(raw_paths)
    if not paths:
        return None

    return SOPCodeMapping(
        sop_name=sop_name,
        paths=paths,
        source=source,
        base_dir=entry_base,
        org=org,
        repo=repo,
    )


def _entry_base_dir(value: dict[str, Any], fallback: Path) -> Path:
    raw = _optional_str(value.get("base_dir") or value.get("root"))
    if not raw:
        return fallback
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return fallback / path


def _resolve_governed_files(mapping: SOPCodeMapping) -> tuple[list[Path], list[Path]]:
    governed_files: list[Path] = []
    missing_paths: list[Path] = []
    for raw in mapping.paths:
        matches = _expand_mapping_path(mapping.base_dir, raw)
        if not matches:
            missing_paths.append(_absolute_mapping_path(mapping.base_dir, raw))
            continue
        for match in matches:
            if match.is_file() and not _should_skip(match):
                governed_files.append(match)
            elif match.is_dir():
                governed_files.extend(_iter_governed_files(match))

    seen: set[Path] = set()
    unique_files: list[Path] = []
    for path in sorted(governed_files):
        try:
            key = path.resolve()
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        unique_files.append(path)
    return unique_files, missing_paths


def _expand_mapping_path(base_dir: Path, raw_path: str) -> list[Path]:
    if _has_glob(raw_path):
        pattern = str(_absolute_mapping_path(base_dir, raw_path))
        return sorted(Path(path) for path in glob.glob(pattern, recursive=True))

    path = _absolute_mapping_path(base_dir, raw_path)
    return [path] if path.exists() else []


def _absolute_mapping_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return base_dir / path


def _iter_governed_files(root: Path) -> list[Path]:
    files: list[Path] = []
    try:
        children = sorted(root.iterdir())
    except OSError:
        return files

    for child in children:
        if _should_skip(child):
            continue
        if child.is_file():
            files.append(child)
        elif child.is_dir():
            files.extend(_iter_governed_files(child))
    return files


def _should_skip(path: Path) -> bool:
    return any(part in _SKIP_SEGMENTS for part in path.parts)


def _select_sop_entry(mapping: SOPCodeMapping, discovered: list[SOPEntry]) -> SOPEntry | None:
    matches = [
        entry for entry in discovered
        if entry.sop_name == mapping.sop_name or entry.filename == mapping.sop_name
    ]
    if not matches:
        return None

    def sort_key(entry: SOPEntry) -> tuple[int, int, int, int, str]:
        repo_mismatch = int(bool(mapping.repo) and entry.repo != mapping.repo)
        org_mismatch = int(bool(mapping.org) and entry.org != mapping.org)
        reference_copy = int(entry.has_canonical_header)
        scope_priority = _SCOPE_PRIORITY.get(entry.scope, 99)
        return (repo_mismatch, org_mismatch, reference_copy, scope_priority, str(entry.path))

    return sorted(matches, key=sort_key)[0]


def _coerce_paths(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str) and item)
    return ()


def _first_str(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _has_glob(value: str) -> bool:
    return any(ch in value for ch in "*?[")


def _format_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")
