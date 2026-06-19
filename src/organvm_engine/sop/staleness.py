"""Cross-reference SOPs against the code paths they govern."""

from __future__ import annotations

import contextlib
import glob
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path

from organvm_engine.sop.discover import SOPEntry

STALE = "stale"
FRESH = "fresh"
MISSING = "missing"
UNKNOWN = "unknown"

_SKIP_DIRS = frozenset({
    ".git",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "site-packages",
    "vendor",
})

_CODE_SUFFIXES = frozenset({
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".jsx",
    ".json",
    ".kt",
    ".mjs",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
})


@dataclass(frozen=True)
class GovernedPathCheck:
    """Staleness result for one SOP governed path."""

    sop: SOPEntry
    declared_path: str
    status: str
    reason: str
    resolved_paths: list[Path] = field(default_factory=list)
    newest_path: Path | None = None
    sop_reviewed_at: datetime | None = None
    code_updated_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "sop": self.sop.filename,
            "sop_name": self.sop.sop_name,
            "org": self.sop.org,
            "repo": self.sop.repo,
            "declared_path": self.declared_path,
            "status": self.status,
            "reason": self.reason,
            "resolved_paths": [str(p) for p in self.resolved_paths],
            "newest_path": str(self.newest_path) if self.newest_path else None,
            "sop_reviewed_at": _format_dt(self.sop_reviewed_at),
            "code_updated_at": _format_dt(self.code_updated_at),
        }


@dataclass
class SOPStalenessReport:
    """Aggregate staleness report for a discovered SOP set."""

    checks: list[GovernedPathCheck] = field(default_factory=list)
    unmapped: list[SOPEntry] = field(default_factory=list)

    @property
    def stale(self) -> list[GovernedPathCheck]:
        return [c for c in self.checks if c.status == STALE]

    @property
    def missing(self) -> list[GovernedPathCheck]:
        return [c for c in self.checks if c.status == MISSING]

    @property
    def unknown(self) -> list[GovernedPathCheck]:
        return [c for c in self.checks if c.status == UNKNOWN]

    @property
    def fresh(self) -> list[GovernedPathCheck]:
        return [c for c in self.checks if c.status == FRESH]

    @property
    def passed(self) -> bool:
        return not self.stale and not self.missing and not self.unknown

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "summary": {
                "checked": len(self.checks),
                "fresh": len(self.fresh),
                "stale": len(self.stale),
                "missing": len(self.missing),
                "unknown": len(self.unknown),
                "unmapped": len(self.unmapped),
            },
            "checks": [c.to_dict() for c in self.checks],
            "unmapped": [
                {
                    "sop": e.filename,
                    "sop_name": e.sop_name,
                    "org": e.org,
                    "repo": e.repo,
                    "path": str(e.path),
                }
                for e in self.unmapped
            ],
        }


def audit_sop_staleness(
    entries: list[SOPEntry],
    workspace: Path | str | None = None,
) -> SOPStalenessReport:
    """Check SOP review freshness against declared governed code paths.

    SOPs opt in by declaring ``governed_paths``/``governed_code``/``code_paths``
    frontmatter. Each path is resolved against the SOP's repo root; if the
    newest governed code file is newer than the SOP's review timestamp, the SOP
    is stale.
    """
    ws = Path(workspace).resolve() if workspace is not None else None
    report = SOPStalenessReport()

    for entry in entries:
        if not entry.governed_paths:
            report.unmapped.append(entry)
            continue

        repo_root = _repo_root_for_entry(entry, ws)
        sop_reviewed_at = _sop_reviewed_at(entry, repo_root)
        for declared_path in entry.governed_paths:
            report.checks.append(
                _check_governed_path(
                    entry=entry,
                    repo_root=repo_root,
                    workspace=ws,
                    declared_path=declared_path,
                    sop_reviewed_at=sop_reviewed_at,
                ),
            )

    return report


def _check_governed_path(
    entry: SOPEntry,
    repo_root: Path,
    workspace: Path | None,
    declared_path: str,
    sop_reviewed_at: datetime | None,
) -> GovernedPathCheck:
    resolved_paths = _resolve_governed_paths(declared_path, repo_root, workspace)
    if not resolved_paths:
        return GovernedPathCheck(
            sop=entry,
            declared_path=declared_path,
            status=MISSING,
            reason="declared governed path does not exist",
            sop_reviewed_at=sop_reviewed_at,
        )

    newest_path, code_updated_at = _newest_code_timestamp(resolved_paths, repo_root)
    if code_updated_at is None:
        return GovernedPathCheck(
            sop=entry,
            declared_path=declared_path,
            status=UNKNOWN,
            reason="no governed code files with timestamps found",
            resolved_paths=resolved_paths,
            sop_reviewed_at=sop_reviewed_at,
        )

    if sop_reviewed_at is None:
        return GovernedPathCheck(
            sop=entry,
            declared_path=declared_path,
            status=UNKNOWN,
            reason="SOP has no review timestamp and file timestamp is unavailable",
            resolved_paths=resolved_paths,
            newest_path=newest_path,
            code_updated_at=code_updated_at,
        )

    status = STALE if code_updated_at > sop_reviewed_at else FRESH
    reason = (
        "governed code changed after SOP review"
        if status == STALE
        else "SOP review is current with governed code"
    )
    return GovernedPathCheck(
        sop=entry,
        declared_path=declared_path,
        status=status,
        reason=reason,
        resolved_paths=resolved_paths,
        newest_path=newest_path,
        sop_reviewed_at=sop_reviewed_at,
        code_updated_at=code_updated_at,
    )


def _repo_root_for_entry(entry: SOPEntry, workspace: Path | None) -> Path:
    if workspace is not None:
        with contextlib.suppress(ValueError):
            rel = entry.path.resolve().relative_to(workspace)
            parts = rel.parts
            if parts and parts[0] == ".sops":
                return workspace
            if len(parts) >= 2:
                candidate = workspace / parts[0] / parts[1]
                if candidate.is_dir():
                    return candidate
    return _nearest_git_root(entry.path.parent) or entry.path.parent


def _resolve_governed_paths(
    declared_path: str,
    repo_root: Path,
    workspace: Path | None,
) -> list[Path]:
    raw = Path(declared_path).expanduser()
    candidates: list[Path] = []

    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(repo_root / raw)
        if workspace is not None:
            candidates.append(workspace / raw)

    resolved: list[Path] = []
    for candidate in candidates:
        matches = _expand_candidate(candidate)
        if matches:
            resolved.extend(matches)
            break

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in resolved:
        normalized = path.resolve()
        if normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped


def _expand_candidate(candidate: Path) -> list[Path]:
    candidate_str = str(candidate)
    if any(token in candidate_str for token in ("*", "?", "[")):
        return [Path(p) for p in glob.glob(candidate_str, recursive=True) if Path(p).exists()]
    return [candidate] if candidate.exists() else []


def _newest_code_timestamp(paths: list[Path], repo_root: Path) -> tuple[Path | None, datetime | None]:
    newest_path: Path | None = None
    newest_at: datetime | None = None

    for path in paths:
        files = list(_iter_code_files(path))
        for file_path in files:
            updated_at = _path_updated_at(file_path, repo_root)
            if updated_at is not None and (newest_at is None or updated_at > newest_at):
                newest_at = updated_at
                newest_path = file_path

    return newest_path, newest_at


def _iter_code_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if _is_code_file(path) else []
    if not path.is_dir():
        return []

    files: list[Path] = []
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        rel_parts = child.relative_to(path).parts
        if any(part in _SKIP_DIRS or part.startswith(".") for part in rel_parts):
            continue
        if _is_code_file(child):
            files.append(child)
    return files


def _is_code_file(path: Path) -> bool:
    return path.suffix.lower() in _CODE_SUFFIXES or path.name in {"Makefile", "Dockerfile"}


def _sop_reviewed_at(entry: SOPEntry, repo_root: Path) -> datetime | None:
    if entry.last_reviewed:
        parsed = _parse_datetime(entry.last_reviewed)
        if parsed is not None:
            return parsed
    return _path_updated_at(entry.path, repo_root)


def _path_updated_at(path: Path, repo_root: Path) -> datetime | None:
    git_time = _git_last_commit_time(path, repo_root)
    if git_time is not None:
        return git_time
    with contextlib.suppress(OSError):
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return None


def _git_last_commit_time(path: Path, repo_root: Path) -> datetime | None:
    if not (repo_root / ".git").exists():
        return None
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return None

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "log", "-1", "--format=%ct", "--", str(rel)],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    with contextlib.suppress(ValueError):
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    return None


def _nearest_git_root(path: Path) -> Path | None:
    current = path.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _parse_datetime(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None

    with contextlib.suppress(ValueError):
        parsed_date = date.fromisoformat(raw)
        return datetime.combine(parsed_date, time.max, tzinfo=timezone.utc)

    normalized = raw.replace("Z", "+00:00")
    with contextlib.suppress(ValueError):
        parsed_dt = datetime.fromisoformat(normalized)
        if parsed_dt.tzinfo is None:
            return parsed_dt.replace(tzinfo=timezone.utc)
        return parsed_dt.astimezone(timezone.utc)
    return None


def _format_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
