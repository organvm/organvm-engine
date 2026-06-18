"""Discover and parse ``.conductor/active-handoff.md`` files.

Handoff files have no rigid schema — they are written by agents in
free-form markdown. The parser is therefore tolerant: it extracts a title,
a timestamp, the originating agent, and the cross-verification flag using a
cascade of patterns, falling back to file mtime when no timestamp is
embedded.

Staleness is the age of the handoff relative to "now". The default
threshold is 24 hours: past that, an open handoff with locked files is more
likely an abandoned session than active work.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from organvm_engine.organ_config import organ_org_dirs
from organvm_engine.paths import workspace_root

# Location of a handoff inside a repo working tree.
HANDOFF_RELPATH = Path(".conductor") / "active-handoff.md"

# A handoff older than this many hours is considered stale.
DEFAULT_STALE_HOURS = 24.0

_CROSS_VERIFICATION_RE = re.compile(r"CROSS-VERIFICATION\s+REQUIRED", re.IGNORECASE)

# ISO 8601 timestamp (date, or date + time, optionally zoned).
_ISO_TS_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?",
)

# Bold metadata markers like ``**Created:** 2026-06-18T12:00:00Z``.
_META_TS_RE = re.compile(
    r"\*\*\s*(?:created|updated|timestamp|date|generated|started)\s*:?\s*\*\*\s*(.+)",
    re.IGNORECASE,
)

# Bold originating-agent markers like ``**Agent:** jules-3``.
_AGENT_RE = re.compile(
    r"\*\*\s*(?:agent|from|originating agent|author|by)\s*:?\s*\*\*\s*(.+)",
    re.IGNORECASE,
)

# YAML-frontmatter keys carrying a timestamp, in priority order.
_FRONTMATTER_TS_KEYS = ("timestamp", "updated", "created", "date", "generated", "started")


def _parse_iso(value: str) -> datetime | None:
    """Parse an ISO 8601 string into a timezone-aware UTC datetime."""
    match = _ISO_TS_RE.search(value)
    if not match:
        return None
    raw = match.group(0).replace("Z", "+00:00").replace(" ", "T")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_frontmatter(text: str) -> dict[str, str]:
    """Return the leading YAML frontmatter as a flat key→value mapping."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip().strip("\"'")
    return fields


def _extract_timestamp(text: str) -> datetime | None:
    """Find the most authoritative embedded timestamp, if any.

    Priority: frontmatter keys → bold metadata markers → first ISO string.
    """
    frontmatter = _extract_frontmatter(text)
    for key in _FRONTMATTER_TS_KEYS:
        if key in frontmatter:
            dt = _parse_iso(frontmatter[key])
            if dt is not None:
                return dt

    for match in _META_TS_RE.finditer(text):
        dt = _parse_iso(match.group(1))
        if dt is not None:
            return dt

    return _parse_iso(text)


def _extract_title(text: str) -> str:
    """Return the first markdown heading or non-empty line as the title."""
    in_frontmatter = False
    for index, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if index == 0 and line == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if line == "---":
                in_frontmatter = False
            continue
        if not line:
            continue
        if line.startswith("#"):
            return line.lstrip("#").strip()
        return line
    return "(untitled handoff)"


def _extract_agent(text: str) -> str | None:
    """Return the originating agent if a marker is present."""
    frontmatter = _extract_frontmatter(text)
    for key in ("agent", "from", "author", "by"):
        if frontmatter.get(key):
            return frontmatter[key]
    match = _AGENT_RE.search(text)
    if match:
        return match.group(1).strip()
    return None


@dataclass
class Handoff:
    """A parsed ``active-handoff.md`` file and its staleness metadata."""

    path: Path
    org: str
    repo: str
    title: str
    timestamp: datetime
    timestamp_source: str  # "embedded" | "mtime"
    cross_verification: bool
    agent: str | None = None

    def age_hours(self, now: datetime | None = None) -> float:
        """Hours elapsed between the handoff timestamp and *now* (UTC)."""
        ref = now or datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        return (ref - self.timestamp).total_seconds() / 3600.0

    def is_stale(
        self,
        threshold_hours: float = DEFAULT_STALE_HOURS,
        now: datetime | None = None,
    ) -> bool:
        """True if the handoff is at least *threshold_hours* old."""
        return self.age_hours(now) >= threshold_hours

    @property
    def slug(self) -> str:
        """Human-readable ``org/repo`` location."""
        return f"{self.org}/{self.repo}" if self.repo else self.org


def parse_handoff(path: Path | str, org: str = "", repo: str = "") -> Handoff:
    """Parse a single handoff file into a :class:`Handoff`.

    Falls back to the file's modification time when no timestamp is embedded
    in the document.
    """
    path = Path(path)
    text = path.read_text(errors="replace")

    timestamp = _extract_timestamp(text)
    if timestamp is not None:
        source = "embedded"
    else:
        timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        source = "mtime"

    return Handoff(
        path=path,
        org=org,
        repo=repo,
        title=_extract_title(text),
        timestamp=timestamp,
        timestamp_source=source,
        cross_verification=bool(_CROSS_VERIFICATION_RE.search(text)),
        agent=_extract_agent(text),
    )


def discover_handoffs(
    workspace: Path | str | None = None,
    orgs: list[str] | None = None,
) -> list[Handoff]:
    """Discover and parse every active handoff across the workspace.

    Scans ``<workspace>/<org>/.conductor/active-handoff.md`` (organ
    superprojects) and ``<workspace>/<org>/<repo>/.conductor/active-handoff.md``
    (member repos).

    Args:
        workspace: Workspace root. Defaults to the resolved workspace.
        orgs: Org directory names to scan. Defaults to all organ dirs.

    Returns:
        Handoffs sorted oldest-first (most stale at the top).
    """
    ws = Path(workspace) if workspace else workspace_root()
    scan_orgs = orgs if orgs is not None else organ_org_dirs()

    handoffs: list[Handoff] = []
    for org_name in scan_orgs:
        org_dir = ws / org_name
        if not org_dir.is_dir():
            continue

        # Organ superproject-level handoff.
        org_handoff = org_dir / HANDOFF_RELPATH
        if org_handoff.is_file():
            handoffs.append(parse_handoff(org_handoff, org=org_name, repo=""))

        # Member-repo handoffs.
        for repo_dir in sorted(org_dir.iterdir()):
            if not repo_dir.is_dir():
                continue
            repo_handoff = repo_dir / HANDOFF_RELPATH
            if repo_handoff.is_file():
                handoffs.append(
                    parse_handoff(repo_handoff, org=org_name, repo=repo_dir.name),
                )

    handoffs.sort(key=lambda h: h.timestamp)
    return handoffs


def filter_stale(
    handoffs: list[Handoff],
    threshold_hours: float = DEFAULT_STALE_HOURS,
    now: datetime | None = None,
) -> list[Handoff]:
    """Return only the handoffs that are stale at *threshold_hours*."""
    return [h for h in handoffs if h.is_stale(threshold_hours, now)]


def format_handoffs(
    handoffs: list[Handoff],
    threshold_hours: float = DEFAULT_STALE_HOURS,
    now: datetime | None = None,
) -> str:
    """Format a handoff list for terminal output."""
    if not handoffs:
        return "  No active handoffs found."

    lines = [
        f"  {'Location':<40} {'Age':<10} {'State':<8} {'XV':<4} Title",
        f"  {'─' * 90}",
    ]
    for h in handoffs:
        age = h.age_hours(now)
        age_str = f"{age:.0f}h" if age < 48 else f"{age / 24:.1f}d"  # noqa: PLR2004
        state = "STALE" if h.is_stale(threshold_hours, now) else "fresh"
        approx = "~" if h.timestamp_source == "mtime" else " "
        xv = "✓" if h.cross_verification else " "
        lines.append(
            f"  {h.slug[:39]:<40} {approx}{age_str:<9} {state:<8} {xv:<4} {h.title[:40]}",
        )
    return "\n".join(lines)
