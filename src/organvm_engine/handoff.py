"""Active handoff discovery, metadata parsing, and cleanup."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HANDOFF_RELATIVE_PATH = Path(".conductor") / "active-handoff.md"
DEFAULT_STALE_AFTER = timedelta(hours=48)

_SKIP_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
}


@dataclass(frozen=True)
class HandoffInfo:
    """Parsed state for one `.conductor/active-handoff.md` file."""

    path: Path
    repo_path: Path
    root: Path
    created_at: datetime | None
    expires_at: datetime | None
    mtime: datetime
    age: timedelta
    status: str
    reasons: tuple[str, ...]
    metadata_source: str
    size_bytes: int

    @property
    def repo(self) -> str:
        return self.repo_path.name

    @property
    def metadata_complete(self) -> bool:
        return self.created_at is not None and self.expires_at is not None

    @property
    def effective_created_at(self) -> datetime:
        return self.created_at or self.mtime

    @property
    def relative_path(self) -> str:
        try:
            return self.path.relative_to(self.root).as_posix()
        except ValueError:
            return self.path.as_posix()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "relative_path": self.relative_path,
            "repo": self.repo,
            "repo_path": str(self.repo_path),
            "root": str(self.root),
            "created_at": _format_datetime(self.created_at),
            "expires_at": _format_datetime(self.expires_at),
            "mtime": _format_datetime(self.mtime),
            "age_seconds": int(self.age.total_seconds()),
            "age": format_age(self.age),
            "status": self.status,
            "reasons": list(self.reasons),
            "metadata_source": self.metadata_source,
            "metadata_complete": self.metadata_complete,
            "size_bytes": self.size_bytes,
        }


def list_handoffs(
    workspace: Path | str | None = None,
    *,
    additional_roots: list[Path | str] | None = None,
    include_additional_roots: bool = True,
    now: datetime | None = None,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> list[HandoffInfo]:
    """Return all active handoff files under the workspace and configured roots."""

    roots = _workspace_roots(
        workspace,
        additional_roots=additional_roots,
        include_additional_roots=include_additional_roots,
    )
    current = _normalize_datetime(now or datetime.now(timezone.utc))
    handoffs: list[HandoffInfo] = []

    for root in roots:
        for path in _discover_handoff_paths(root):
            try:
                handoffs.append(
                    read_handoff(
                        path,
                        root=root,
                        now=current,
                        stale_after=stale_after,
                    ),
                )
            except OSError:
                continue

    return sorted(handoffs, key=lambda h: (h.status != "expired", h.status != "stale", h.relative_path))


def read_handoff(
    path: Path | str,
    *,
    root: Path | str | None = None,
    now: datetime | None = None,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> HandoffInfo:
    """Parse a single active handoff file."""

    handoff_path = Path(path).expanduser()
    stat = handoff_path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    current = _normalize_datetime(now or datetime.now(timezone.utc))
    text = handoff_path.read_text(encoding="utf-8", errors="replace")
    metadata, metadata_source = _extract_metadata(text)

    created_at = _parse_datetime(metadata.get("created_at"))
    expires_at = _parse_datetime(metadata.get("expires_at"))
    effective_created = created_at or mtime
    age = max(current - effective_created, timedelta())

    reasons: list[str] = []
    if created_at is None:
        reasons.append("created_at missing; using file mtime")
    if expires_at is None:
        reasons.append("expires_at missing")
    if created_at and created_at > current:
        reasons.append("created_at is in the future")
    if expires_at and expires_at <= current:
        status = "expired"
        reasons.append("expires_at has passed")
    elif age > stale_after:
        status = "stale"
        reasons.append(f"age exceeds {format_age(stale_after)} stale threshold")
    else:
        status = "active"

    repo_path = handoff_path.parent.parent
    root_path = Path(root).expanduser() if root is not None else repo_path

    return HandoffInfo(
        path=handoff_path,
        repo_path=repo_path,
        root=root_path,
        created_at=created_at,
        expires_at=expires_at,
        mtime=mtime,
        age=age,
        status=status,
        reasons=tuple(reasons),
        metadata_source=metadata_source,
        size_bytes=stat.st_size,
    )


def inspect_repo_handoff(
    repo_path: Path | str,
    *,
    now: datetime | None = None,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> HandoffInfo | None:
    """Return parsed handoff state for a repo, or None when no handoff exists."""

    repo = Path(repo_path).expanduser()
    handoff_path = repo / HANDOFF_RELATIVE_PATH
    if not handoff_path.is_file():
        return None
    return read_handoff(
        handoff_path,
        root=repo,
        now=now,
        stale_after=stale_after,
    )


def clean_handoffs(
    workspace: Path | str | None = None,
    *,
    older_than: timedelta | None = None,
    dry_run: bool = True,
    additional_roots: list[Path | str] | None = None,
    include_additional_roots: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Remove expired handoff files, and optionally files older than a threshold."""

    current = _normalize_datetime(now or datetime.now(timezone.utc))
    handoffs = list_handoffs(
        workspace,
        additional_roots=additional_roots,
        include_additional_roots=include_additional_roots,
        now=current,
    )

    removed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for info in handoffs:
        reason = _clean_reason(info, older_than=older_than)
        if reason is None:
            kept.append(info.to_dict())
            continue

        entry = info.to_dict()
        entry["clean_reason"] = reason
        if not dry_run:
            try:
                info.path.unlink()
            except OSError as exc:
                errors.append({"path": str(info.path), "error": str(exc)})
                continue
        removed.append(entry)

    return {
        "removed": removed,
        "kept": kept,
        "errors": errors,
        "dry_run": dry_run,
        "older_than": format_age(older_than) if older_than else None,
    }


def parse_duration(value: str) -> timedelta:
    """Parse compact durations like `48h`, `7d`, or `2w`."""

    match = re.fullmatch(r"\s*(\d+)\s*([mhdwMHDW])\s*", value)
    if not match:
        raise ValueError("duration must look like 30m, 48h, 7d, or 2w")
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    return timedelta(weeks=amount)


def format_age(delta: timedelta | None) -> str:
    """Format a timedelta for compact CLI/context display."""

    if delta is None:
        return "unknown"
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 3600:
        minutes = max(seconds // 60, 0)
        return f"{minutes}m"
    if seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h" if minutes == 0 else f"{hours}h{minutes}m"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    return f"{days}d" if hours == 0 else f"{days}d{hours}h"


def _workspace_roots(
    workspace: Path | str | None,
    *,
    additional_roots: list[Path | str] | None,
    include_additional_roots: bool,
) -> list[Path]:
    from organvm_engine.paths import additional_workspace_roots, workspace_root

    ws = Path(workspace).expanduser() if workspace else workspace_root()
    roots = [ws]
    if additional_roots is not None:
        roots.extend(Path(p).expanduser() for p in additional_roots)
    elif include_additional_roots:
        roots.extend(additional_workspace_roots(workspace=ws))

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _discover_handoff_paths(root: Path) -> list[Path]:
    if not root.is_dir():
        return []

    paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        current = Path(dirpath)
        if current.name != ".conductor":
            continue
        if "active-handoff.md" in filenames:
            paths.append(current / "active-handoff.md")
        dirnames[:] = []
    return paths


def _extract_metadata(text: str) -> tuple[dict[str, Any], str]:
    front_matter = _extract_front_matter(text)
    inline = _extract_inline_metadata(text)
    metadata = {**inline, **front_matter}

    if front_matter:
        source = "front_matter"
    elif inline:
        source = "inline"
    else:
        source = "mtime"
    return metadata, source


def _extract_front_matter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    match = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", text, flags=re.DOTALL)
    if not match:
        return {}

    try:
        import yaml

        data = yaml.safe_load(match.group(1)) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k).strip(): v for k, v in data.items()}


def _extract_inline_metadata(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    key_pattern = r"(created_at|expires_at|created at|expires at|created|expires)"
    pattern = re.compile(rf"^\s*(?:[-*]\s*)?{key_pattern}\s*:\s*(.+?)\s*$", re.IGNORECASE)
    for line in text.splitlines()[:80]:
        match = pattern.match(line)
        if not match:
            continue
        raw_key = match.group(1).lower().replace(" ", "_")
        key = {"created": "created_at", "expires": "expires_at"}.get(raw_key, raw_key)
        if key in {"created_at", "expires_at"}:
            metadata[key] = match.group(2).strip().strip("'\"")
    return metadata


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _normalize_datetime(value)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed_date = date.fromisoformat(raw)
        except ValueError:
            return None
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=timezone.utc)
    return _normalize_datetime(parsed)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _normalize_datetime(value).isoformat().replace("+00:00", "Z")


def _clean_reason(info: HandoffInfo, *, older_than: timedelta | None) -> str | None:
    if info.status == "expired":
        return "expired"
    if older_than is not None and info.age > older_than:
        return f"older-than {format_age(older_than)}"
    return None
