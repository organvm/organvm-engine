"""Agent handoff discovery, parsing, and staleness detection.

Multi-agent work is relayed through ``.conductor/active-handoff.md`` files
(see the Active Handoff Protocol in every repo's CLAUDE.md). When an agent
hands work to a sister agent it writes one of these files; the receiving agent
is expected to read it first and archive it once the work lands.

A handoff that lingers as ``active`` long after its timestamp is a smell: the
receiving agent either never picked it up or completed the work without
clearing the baton. This module walks the workspace for those files, parses
their header metadata, and flags stale ones so the swarm can be reconciled.

Handoff header format (markdown)::

    # Agent Handoff: claude → opencode

    **Session:** 2026-03-30-dispatch-signal-closure
    **Phase:** BUILD
    **Organ:** META-ORGANVM | **Repo:** organvm-engine
    **Scope:** Build validate_signal_closure + fix essay-pipeline CI
    **Timestamp:** 2026-03-30
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from organvm_engine.organ_config import get_organ_map
from organvm_engine.paths import workspace_root

# Default age (in days) past which an *active* handoff is considered stale.
DEFAULT_STALE_DAYS = 7

# ---------------------------------------------------------------------------
# Header regexes
# ---------------------------------------------------------------------------

# "# Agent Handoff: claude → opencode" (also accepts ->, —, =>)
_TITLE_RE = re.compile(
    r"^#\s*Agent Handoff:\s*(.+?)\s*(?:→|->|—|=>)\s*(.+?)\s*$",
    re.MULTILINE,
)
_SESSION_RE = re.compile(r"^\*\*Session:\*\*\s*(.+?)\s*$", re.MULTILINE)
_PHASE_RE = re.compile(r"^\*\*Phase:\*\*\s*(.+?)\s*$", re.MULTILINE)
_ORGAN_RE = re.compile(r"\*\*Organ:\*\*\s*([^|*\n]+?)\s*(?:\||\*\*|$)", re.MULTILINE)
_REPO_RE = re.compile(r"\*\*Repo:\*\*\s*([^|*\n]+?)\s*(?:\||\*\*|$)", re.MULTILINE)
_SCOPE_RE = re.compile(r"^\*\*Scope:\*\*\s*(.+?)\s*$", re.MULTILINE)
_TIMESTAMP_RE = re.compile(r"^\*\*Timestamp:\*\*\s*(.+?)\s*$", re.MULTILINE)
_CROSS_VERIFY = "CROSS-VERIFICATION REQUIRED"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Handoff:
    """A parsed agent handoff document."""

    path: str               # absolute path to the handoff file
    repo: str               # repo directory name (from path, fallback header)
    organ: str              # organ name/key (from header) or ""
    from_agent: str         # originating agent (from title) or ""
    to_agent: str           # receiving agent (from title) or ""
    session: str            # session identifier or ""
    phase: str              # lifecycle phase (BUILD, etc.) or ""
    scope: str              # one-line scope summary or ""
    timestamp: str          # raw timestamp string as written or ""
    handoff_date: date | None  # parsed date, or None if unparseable
    cross_verification: bool   # whether CROSS-VERIFICATION REQUIRED is set
    archived: bool          # True when found under .conductor/archive/

    def age_days(self, today: date | None = None) -> int | None:
        """Days between the handoff timestamp and *today* (None if undated)."""
        if self.handoff_date is None:
            return None
        ref = today or date.today()
        return (ref - self.handoff_date).days

    def is_stale(self, stale_days: int = DEFAULT_STALE_DAYS, today: date | None = None) -> bool:
        """True for an active handoff older than *stale_days*.

        Archived handoffs are never stale — they have been resolved. A handoff
        with no parseable timestamp is treated as stale: an undated active
        baton cannot be reasoned about and should be reviewed.
        """
        if self.archived:
            return False
        age = self.age_days(today)
        if age is None:
            return True
        return age > stale_days

    def staleness(self, stale_days: int = DEFAULT_STALE_DAYS, today: date | None = None) -> str:
        """Human-readable staleness label."""
        if self.archived:
            return "ARCHIVED"
        age = self.age_days(today)
        if age is None:
            return "UNDATED"
        if age > stale_days:
            return "STALE"
        return "ACTIVE"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_timestamp(raw: str) -> date | None:
    """Parse a handoff timestamp into a date.

    Accepts plain ISO dates (``2026-03-30``) and ISO datetimes with an
    optional trailing ``Z`` (``2026-03-30T16:26:25Z``). Returns None when the
    value cannot be parsed.
    """
    value = raw.strip()
    if not value:
        return None
    # Datetime form first — fall back to the leading date component.
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _first(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def parse_handoff(path: Path, archived: bool = False) -> Handoff | None:
    """Parse a single handoff markdown file into a :class:`Handoff`.

    Returns None if the file is unreadable. A file that exists but lacks the
    ``# Agent Handoff`` title still parses (with empty agent fields) so that
    malformed or partial handoffs remain visible to ``handoff list``.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    from_agent = to_agent = ""
    title = _TITLE_RE.search(text)
    if title:
        from_agent = title.group(1).strip()
        to_agent = title.group(2).strip()

    timestamp = _first(_TIMESTAMP_RE, text)
    repo = _first(_REPO_RE, text) or path.parent.parent.name

    return Handoff(
        path=str(path),
        repo=repo,
        organ=_first(_ORGAN_RE, text),
        from_agent=from_agent,
        to_agent=to_agent,
        session=_first(_SESSION_RE, text),
        phase=_first(_PHASE_RE, text),
        scope=_first(_SCOPE_RE, text),
        timestamp=timestamp,
        handoff_date=_parse_timestamp(timestamp),
        cross_verification=_CROSS_VERIFY in text,
        archived=archived,
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_in_repo(repo_dir: Path, include_archived: bool = False) -> list[Handoff]:
    """Find handoffs under a single repo's ``.conductor/`` directory.

    Always picks up ``.conductor/active-handoff.md``. When *include_archived*
    is set, also reads every ``.md`` file under ``.conductor/archive/``.
    """
    conductor = repo_dir / ".conductor"
    if not conductor.is_dir():
        return []

    handoffs: list[Handoff] = []
    active = conductor / "active-handoff.md"
    if active.is_file():
        parsed = parse_handoff(active, archived=False)
        if parsed is not None:
            handoffs.append(parsed)

    if include_archived:
        archive = conductor / "archive"
        if archive.is_dir():
            for md in sorted(archive.glob("*.md")):
                parsed = parse_handoff(md, archived=True)
                if parsed is not None:
                    handoffs.append(parsed)

    return handoffs


def discover_handoffs(
    workspace: Path | str | None = None,
    organ: str | None = None,
    include_archived: bool = False,
) -> list[Handoff]:
    """Walk the workspace for agent handoffs across every organ repo.

    Structure scanned: ``<workspace>/<org>/<repo>/.conductor/active-handoff.md``
    (and ``.conductor/archive/*.md`` when *include_archived* is set).

    Args:
        workspace: Root workspace directory. Defaults to the resolved
            workspace root.
        organ: Optional CLI organ key (e.g. ``"META"``, ``"I"``). When given,
            only that organ's directory is scanned.
        include_archived: Also include resolved handoffs under ``archive/``.

    Returns:
        Handoffs sorted oldest-dated first (undated last), then by path.
    """
    ws = Path(workspace) if workspace else workspace_root()
    organ_map = get_organ_map()

    if organ is not None:
        key = organ.upper()
        if key not in organ_map:
            return []
        org_dirs = [ws / organ_map[key]["dir"]]
    else:
        org_dirs = [
            ws / v["dir"] for v in organ_map.values() if v["registry_key"] != "PERSONAL"
        ]

    handoffs: list[Handoff] = []
    for org_dir in org_dirs:
        if not org_dir.is_dir():
            continue
        for repo_dir in sorted(org_dir.iterdir()):
            if repo_dir.is_dir():
                handoffs.extend(discover_in_repo(repo_dir, include_archived=include_archived))

    # Oldest-dated first so the most neglected batons surface at the top;
    # undated entries sort to the end. date.max keeps undated below any real date.
    handoffs.sort(key=lambda h: (h.handoff_date or date.max, h.path))
    return handoffs


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


def filter_stale(
    handoffs: list[Handoff],
    stale_days: int = DEFAULT_STALE_DAYS,
    today: date | None = None,
) -> list[Handoff]:
    """Return only the handoffs that are stale per :meth:`Handoff.is_stale`."""
    return [h for h in handoffs if h.is_stale(stale_days=stale_days, today=today)]
