"""Active handoff discovery, metadata parsing, and cleanup."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from organvm_engine.paths import additional_workspace_roots, workspace_root

HANDOFF_RELATIVE_PATH = Path(".conductor") / "active-handoff.md"
DEFAULT_STALE_AFTER = timedelta(hours=48)
DEFAULT_CLEAN_OLDER_THAN = timedelta(days=7)

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([mhdw])\s*$", re.IGNORECASE)
_INLINE_META_RE = re.compile(r"^\s*(created_at|expires_at)\s*:\s*(.+?)\s*$")
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    "node_modules",
    "venv",
}


@dataclass(frozen=True)
class HandoffEntry:
    """Parsed representation of one `.conductor/active-handoff.md` file."""

    path: Path
    repo_path: Path
    root: Path
    repo: str
    organ: str | None
    created_at: datetime | None
    expires_at: datetime | None
    modified_at: datetime
    title: str | None
    metadata_source: str
    parse_error: str | None = None

    @property
    def effective_created_at(self) -> datetime:
        """Timestamp used for age when `created_at` is absent."""
        return self.created_at or self.modified_at

    def age(self, now: datetime | None = None) -> timedelta:
        ref = _coerce_now(now)
        return max(timedelta(), ref - self.effective_created_at)

    def status(
        self,
        now: datetime | None = None,
        *,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
    ) -> str:
        ref = _coerce_now(now)
        if self.expires_at is not None and self.expires_at <= ref:
            return "expired"
        if self.age(ref) > stale_after:
            return "stale"
        return "active"

    def to_dict(
        self,
        now: datetime | None = None,
        *,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
    ) -> dict[str, Any]:
        ref = _coerce_now(now)
        return {
            "path": str(self.path),
            "repo_path": str(self.repo_path),
            "repo": self.repo,
            "organ": self.organ,
            "status": self.status(ref, stale_after=stale_after),
            "age_seconds": int(self.age(ref).total_seconds()),
            "age": format_duration(self.age(ref)),
            "created_at": format_timestamp(self.created_at),
            "expires_at": format_timestamp(self.expires_at),
            "modified_at": format_timestamp(self.modified_at),
            "title": self.title,
            "metadata_source": self.metadata_source,
            "parse_error": self.parse_error,
        }


@dataclass(frozen=True)
class CleanResult:
    """Result from removing expired or old handoff files."""

    removed: list[HandoffEntry]
    kept: list[HandoffEntry]
    errors: list[dict[str, str]]
    dry_run: bool

    def to_dict(self, now: datetime | None = None) -> dict[str, Any]:
        ref = _coerce_now(now)
        return {
            "removed": [entry.to_dict(ref) for entry in self.removed],
            "kept": [entry.to_dict(ref) for entry in self.kept],
            "errors": self.errors,
            "dry_run": self.dry_run,
        }


def parse_duration(value: str) -> timedelta:
    """Parse compact durations such as `48h`, `7d`, or `2w`."""
    match = _DURATION_RE.match(value)
    if not match:
        raise ValueError(f"Invalid duration '{value}'. Use forms like 48h, 7d, or 2w.")

    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    return timedelta(weeks=amount)


def discover_handoffs(
    workspace: Path | str | None = None,
    *,
    include_additional_roots: bool = True,
    now: datetime | None = None,
) -> list[HandoffEntry]:
    """Find active handoff files across the workspace and optional flat roots."""
    ws = Path(workspace).expanduser() if workspace is not None else workspace_root()
    roots = [ws]
    if include_additional_roots:
        roots.extend(additional_workspace_roots(workspace=ws))

    seen: set[Path] = set()
    entries: list[HandoffEntry] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in _walk_handoff_paths(root):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            entries.append(read_handoff(path, root=root, now=now))

    return sorted(entries, key=lambda item: str(item.path))


def read_handoff(
    path: Path | str,
    *,
    root: Path | str | None = None,
    now: datetime | None = None,
) -> HandoffEntry:
    """Read one handoff file and derive metadata used for staleness checks."""
    handoff_path = Path(path)
    scan_root = Path(root).expanduser() if root is not None else handoff_path.parent.parent
    repo_path, repo, organ = _derive_repo_info(handoff_path, scan_root)

    modified_at = datetime.fromtimestamp(handoff_path.stat().st_mtime, tz=timezone.utc)
    metadata: dict[str, Any] = {}
    metadata_source = "missing"
    parse_error: str | None = None
    title: str | None = None

    try:
        text = handoff_path.read_text(encoding="utf-8", errors="replace")
        metadata, metadata_source = _extract_metadata(text)
        title = _extract_title(text)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        parse_error = str(exc)

    created_at = _parse_datetime(metadata.get("created_at"))
    expires_at = _parse_datetime(metadata.get("expires_at"))

    # Touch `now` to normalize caller-provided test clocks early.
    _coerce_now(now)

    return HandoffEntry(
        path=handoff_path,
        repo_path=repo_path,
        root=scan_root,
        repo=repo,
        organ=organ,
        created_at=created_at,
        expires_at=expires_at,
        modified_at=modified_at,
        title=title,
        metadata_source=metadata_source,
        parse_error=parse_error,
    )


def clean_handoffs(
    workspace: Path | str | None = None,
    *,
    older_than: timedelta = DEFAULT_CLEAN_OLDER_THAN,
    include_additional_roots: bool = True,
    dry_run: bool = False,
    now: datetime | None = None,
) -> CleanResult:
    """Remove handoffs that are expired or older than the supplied threshold."""
    ref = _coerce_now(now)
    removed: list[HandoffEntry] = []
    kept: list[HandoffEntry] = []
    errors: list[dict[str, str]] = []

    for entry in discover_handoffs(
        workspace,
        include_additional_roots=include_additional_roots,
        now=ref,
    ):
        should_remove = (
            (entry.expires_at is not None and entry.expires_at <= ref)
            or entry.age(ref) > older_than
        )
        if not should_remove:
            kept.append(entry)
            continue

        if not dry_run:
            try:
                entry.path.unlink()
            except OSError as exc:
                errors.append({"path": str(entry.path), "error": str(exc)})
                kept.append(entry)
                continue
        removed.append(entry)

    return CleanResult(removed=removed, kept=kept, errors=errors, dry_run=dry_run)


def render_handoff_table(
    entries: list[HandoffEntry],
    *,
    now: datetime | None = None,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> str:
    """Render a workspace handoff inventory table."""
    ref = _coerce_now(now)
    if not entries:
        return "No active handoffs found."

    lines = [
        f"{'Status':<8} {'Age':>7} {'Expires':<20} {'Repo':<32} Path",
        "-" * 96,
    ]
    for entry in entries:
        status = entry.status(ref, stale_after=stale_after).upper()
        age = format_duration(entry.age(ref))
        expires = format_timestamp(entry.expires_at) or "-"
        repo = f"{entry.organ}/{entry.repo}" if entry.organ else entry.repo
        lines.append(f"{status:<8} {age:>7} {expires:<20} {repo:<32} {entry.path}")
    return "\n".join(lines)


def render_context_handoff_warning(
    entry: HandoffEntry,
    *,
    now: datetime | None = None,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> str:
    """Render a repo context warning for stale or expired handoffs."""
    ref = _coerce_now(now)
    status = entry.status(ref, stale_after=stale_after)
    if status == "active":
        return ""

    created = format_timestamp(entry.created_at) or f"missing; using mtime {format_timestamp(entry.modified_at)}"
    expires = format_timestamp(entry.expires_at) or "missing"
    return (
        "### Handoff Staleness Warning\n\n"
        f"- `.conductor/active-handoff.md` is **{status.upper()}** "
        f"(age {format_duration(entry.age(ref))}; created_at: {created}; "
        f"expires_at: {expires}).\n"
        "- Confirm the handoff is still current before treating its constraints as binding.\n"
    )


def format_duration(delta: timedelta) -> str:
    """Format a duration compactly for CLI output."""
    total_seconds = max(0, int(delta.total_seconds()))
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    days = hours // 24
    remainder_hours = hours % 24
    if remainder_hours == 0:
        return f"{days}d"
    return f"{days}d{remainder_hours}h"


def format_timestamp(value: datetime | None) -> str | None:
    """Return a UTC ISO-8601 timestamp with `Z` suffix."""
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _walk_handoff_paths(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIRS]
        current = Path(dirpath)
        if current.name == ".conductor" and HANDOFF_RELATIVE_PATH.name in filenames:
            found.append(current / HANDOFF_RELATIVE_PATH.name)
    return found


def _extract_metadata(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for idx, line in enumerate(lines[1:], start=1):
            if line.strip() in {"---", "..."}:
                raw = "\n".join(lines[1:idx]).strip()
                data = yaml.safe_load(raw) if raw else {}
                return (data or {}, "frontmatter") if isinstance(data, dict) else ({}, "frontmatter")

    inline: dict[str, str] = {}
    for line in lines[:30]:
        if line.startswith("# "):
            break
        match = _INLINE_META_RE.match(line)
        if match:
            inline[match.group(1)] = match.group(2)
    if inline:
        return inline, "inline"
    return {}, "missing"


def _extract_title(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        raw = str(value).strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _derive_repo_info(path: Path, root: Path) -> tuple[Path, str, str | None]:
    repo_path = path.parent.parent
    repo = repo_path.name
    organ: str | None = None

    try:
        rel = repo_path.relative_to(root)
    except ValueError:
        rel = repo_path

    if len(rel.parts) >= 2:
        organ = rel.parts[0]
    return repo_path, repo, organ


def _coerce_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)
