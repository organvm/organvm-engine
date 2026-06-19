"""Cross-reference SOPs against the code they govern."""

from __future__ import annotations

import glob
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from organvm_engine.sop.discover import SOPEntry

_GLOB_CHARS = frozenset("*?[]")
_EXCLUDED_SEGMENTS = frozenset({
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
})
_CODE_SUFFIXES = frozenset({
    ".bash",
    ".c",
    ".cc",
    ".cfg",
    ".clj",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".lua",
    ".mjs",
    ".php",
    ".pl",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".scss",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".xml",
    ".yaml",
    ".yml",
    ".zsh",
})
_CODE_FILENAMES = frozenset({
    "Dockerfile",
    "Makefile",
    "Procfile",
    "docker-compose.yml",
    "go.mod",
    "go.sum",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
})


@dataclass(frozen=True)
class SOPStalenessIssue:
    """A stale, missing, or unlinked SOP/code reference."""

    status: str
    sop_name: str
    sop_path: Path
    pattern: str | None = None
    code_path: Path | None = None
    sop_changed_at: datetime | None = None
    code_changed_at: datetime | None = None
    days_stale: int | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation."""
        return {
            "status": self.status,
            "sop_name": self.sop_name,
            "sop_path": str(self.sop_path),
            "pattern": self.pattern,
            "code_path": str(self.code_path) if self.code_path else None,
            "sop_changed_at": _dt_to_iso(self.sop_changed_at),
            "code_changed_at": _dt_to_iso(self.code_changed_at),
            "days_stale": self.days_stale,
            "detail": self.detail,
        }


@dataclass
class SOPStalenessReport:
    """Aggregate report for SOP staleness checks."""

    checked_sops: int = 0
    linked_sops: int = 0
    checked_refs: int = 0
    fresh_refs: int = 0
    issues: list[SOPStalenessIssue] = field(default_factory=list)

    @property
    def stale(self) -> list[SOPStalenessIssue]:
        return [issue for issue in self.issues if issue.status == "stale"]

    @property
    def missing(self) -> list[SOPStalenessIssue]:
        return [issue for issue in self.issues if issue.status == "missing"]

    @property
    def unlinked(self) -> list[SOPStalenessIssue]:
        return [issue for issue in self.issues if issue.status == "unlinked"]

    def has_failures(self, require_governs: bool = False) -> bool:
        """Return True when strict mode should fail."""
        statuses = {"stale", "missing"}
        if require_governs:
            statuses.add("unlinked")
        return any(issue.status in statuses for issue in self.issues)

    def to_dict(self) -> dict:
        """Return a JSON-serializable report."""
        return {
            "checked_sops": self.checked_sops,
            "linked_sops": self.linked_sops,
            "unlinked_sops": len(self.unlinked),
            "checked_refs": self.checked_refs,
            "fresh_refs": self.fresh_refs,
            "stale_refs": len(self.stale),
            "missing_refs": len(self.missing),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def audit_sop_staleness(
    entries: list[SOPEntry],
    *,
    workspace: Path | str | None = None,
    repo_root: Path | str | None = None,
    include_unlinked: bool = True,
) -> SOPStalenessReport:
    """Cross-reference SOP ``governs`` metadata against governed code files."""
    report = SOPStalenessReport()
    timestamp_resolver = _TimestampResolver()
    ws = Path(workspace) if workspace is not None else None
    root_override = Path(repo_root) if repo_root is not None else None

    for entry in entries:
        report.checked_sops += 1
        sop_name = entry.sop_name or entry.filename
        root = _entry_repo_root(entry, workspace=ws, repo_root=root_override)

        if not entry.governs:
            if include_unlinked:
                report.issues.append(SOPStalenessIssue(
                    status="unlinked",
                    sop_name=sop_name,
                    sop_path=entry.path,
                    detail="SOP has no governs/code reference metadata.",
                ))
            continue

        report.linked_sops += 1
        sop_changed_at = timestamp_resolver.changed_at(entry.path, root)
        seen_code_paths: set[Path] = set()

        for pattern in entry.governs:
            matches = _resolve_governed_paths(root, pattern)
            if not matches:
                report.issues.append(SOPStalenessIssue(
                    status="missing",
                    sop_name=sop_name,
                    sop_path=entry.path,
                    pattern=pattern,
                    sop_changed_at=sop_changed_at,
                    detail=f"No governed code matched {pattern!r}.",
                ))
                continue

            for code_path in matches:
                stable_code_path = code_path.resolve(strict=False)
                if stable_code_path in seen_code_paths:
                    continue
                seen_code_paths.add(stable_code_path)
                report.checked_refs += 1
                code_changed_at = timestamp_resolver.changed_at(code_path, root)
                if (
                    sop_changed_at is not None
                    and code_changed_at is not None
                    and _is_stale(sop_changed_at, code_changed_at)
                ):
                    report.issues.append(SOPStalenessIssue(
                        status="stale",
                        sop_name=sop_name,
                        sop_path=entry.path,
                        pattern=pattern,
                        code_path=code_path,
                        sop_changed_at=sop_changed_at,
                        code_changed_at=code_changed_at,
                        days_stale=max(0, (code_changed_at - sop_changed_at).days),
                        detail="Governed code changed after the SOP.",
                    ))
                else:
                    report.fresh_refs += 1

    return report


def _entry_repo_root(
    entry: SOPEntry,
    *,
    workspace: Path | None,
    repo_root: Path | None,
) -> Path:
    if repo_root is not None:
        return repo_root

    if entry.path.parent.name == ".sops":
        return entry.path.parent.parent

    if workspace is not None:
        if entry.scope == "organ" or entry.repo == entry.org:
            return workspace / entry.org
        return workspace / entry.org / entry.repo

    return entry.path.parent


def _resolve_governed_paths(repo_root: Path, pattern: str) -> list[Path]:
    pattern = pattern.strip()
    if not pattern or "://" in pattern:
        return []

    raw = Path(pattern).expanduser()
    has_glob = any(ch in pattern for ch in _GLOB_CHARS)
    candidates: list[Path]

    if raw.is_absolute():
        candidates = [Path(p) for p in glob.glob(pattern)] if has_glob else [raw]
    elif has_glob:
        candidates = list(repo_root.glob(pattern))
    else:
        candidates = [repo_root / raw]

    resolved: list[Path] = []
    for candidate in candidates:
        resolved.extend(_expand_candidate(candidate, explicit=not has_glob))

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in resolved:
        stable = path.resolve(strict=False)
        if stable not in seen:
            seen.add(stable)
            unique.append(path)
    return sorted(unique)


def _expand_candidate(path: Path, *, explicit: bool) -> list[Path]:
    if _should_skip(path):
        return []
    if path.is_file():
        if explicit or _is_code_file(path):
            return [path]
        return []
    if not path.is_dir():
        return []

    files: list[Path] = []
    for item in path.rglob("*"):
        if _should_skip(item):
            continue
        if item.is_file() and _is_code_file(item):
            files.append(item)
    return files


def _is_code_file(path: Path) -> bool:
    return path.suffix in _CODE_SUFFIXES or path.name in _CODE_FILENAMES


def _should_skip(path: Path) -> bool:
    return any(part in _EXCLUDED_SEGMENTS for part in path.parts)


def _is_stale(sop_changed_at: datetime | None, code_changed_at: datetime | None) -> bool:
    return sop_changed_at is not None and code_changed_at is not None and code_changed_at > sop_changed_at


def _dt_to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class _TimestampResolver:
    def __init__(self) -> None:
        self._git_repos: dict[Path, bool] = {}
        self._dirty_paths: dict[tuple[Path, Path], bool] = {}
        self._cache: dict[tuple[Path, Path], datetime | None] = {}

    def changed_at(self, path: Path, repo_root: Path) -> datetime | None:
        key = (path.resolve(strict=False), repo_root.resolve(strict=False))
        if key in self._cache:
            return self._cache[key]

        changed_at = self._git_changed_at(path, repo_root)
        if changed_at is None:
            changed_at = self._mtime_changed_at(path)

        self._cache[key] = changed_at
        return changed_at

    def _git_changed_at(self, path: Path, repo_root: Path) -> datetime | None:
        root = repo_root.resolve(strict=False)
        if not self._is_git_repo(root):
            return None

        try:
            rel = path.resolve(strict=False).relative_to(root)
        except ValueError:
            return None
        if self._is_dirty(root, rel):
            return None

        try:
            proc = subprocess.run(
                ["git", "-C", str(root), "log", "-1", "--format=%ct", "--", str(rel)],
                capture_output=True,
                check=False,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        raw = proc.stdout.strip()
        if proc.returncode != 0 or not raw.isdigit():
            return None
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)

    def _is_dirty(self, repo_root: Path, rel: Path) -> bool:
        key = (repo_root, rel)
        if key in self._dirty_paths:
            return self._dirty_paths[key]

        try:
            proc = subprocess.run(
                ["git", "-C", str(repo_root), "status", "--porcelain", "--", str(rel)],
                capture_output=True,
                check=False,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            self._dirty_paths[key] = False
            return False

        dirty = proc.returncode == 0 and bool(proc.stdout.strip())
        self._dirty_paths[key] = dirty
        return dirty

    def _is_git_repo(self, repo_root: Path) -> bool:
        if repo_root in self._git_repos:
            return self._git_repos[repo_root]

        try:
            proc = subprocess.run(
                ["git", "-C", str(repo_root), "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                check=False,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            self._git_repos[repo_root] = False
            return False

        is_repo = proc.returncode == 0 and proc.stdout.strip() == "true"
        self._git_repos[repo_root] = is_repo
        return is_repo

    @staticmethod
    def _mtime_changed_at(path: Path) -> datetime | None:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return None
