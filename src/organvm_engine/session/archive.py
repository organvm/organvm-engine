"""Per-project session archival.

Routes conversation transcripts from ~/.claude/projects/ (and other agent
storage locations) into the project repos they belong to, preserving the
complete intellectual record: dialogue, reasoning, plans, and raw session data.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from organvm_engine.session.parser import (
    SessionExport,
    SessionMeta,
    parse_any_session,
    render_any_prompts,
    render_any_transcript,
)


@dataclass
class ArchiveResult:
    """Result of archiving a single session."""

    session_id: str
    project_path: Path
    archive_dir: Path
    files_written: list[str]
    skipped: bool = False
    skip_reason: str = ""
    error: str = ""


def load_archive_state(project_path: Path) -> dict:
    """Load archive state from project's .claude/sessions/.archive-state.json."""
    state_path = project_path / ".claude" / "sessions" / ".archive-state.json"
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_archive_state(project_path: Path, state: dict) -> None:
    """Write archive state back to disk."""
    state_path = project_path / ".claude" / "sessions" / ".archive-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def resolve_project_path(meta: SessionMeta) -> Path | None:
    """Resolve the actual project directory from session metadata.

    Uses meta.cwd (most reliable) with validation that the path exists.
    Returns None if the project directory cannot be resolved.
    """
    if not meta.cwd:
        return None

    project = Path(meta.cwd)
    if project.is_dir():
        return project

    # cwd might be a subdirectory that was removed — try parent
    if project.parent.is_dir():
        return project.parent

    return None


def _build_meta_json(meta: SessionMeta) -> str:
    """Build machine-readable session metadata as JSON."""
    data = {
        "session_id": meta.session_id,
        "slug": meta.slug,
        "cwd": meta.cwd,
        "git_branch": meta.git_branch,
        "project_dir": meta.project_dir,
        "started": meta.started.isoformat() if meta.started else None,
        "ended": meta.ended.isoformat() if meta.ended else None,
        "duration_minutes": meta.duration_minutes,
        "message_count": meta.message_count,
        "human_messages": meta.human_messages,
        "assistant_messages": meta.assistant_messages,
        "tools_used": meta.tools_used,
        "first_human_message": meta.first_human_message[:300],
        "source_file": str(meta.file_path),
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }
    return json.dumps(data, indent=2, default=str) + "\n"


def _session_slug(meta: SessionMeta) -> str:
    """Derive a filesystem-safe slug for the session archive directory.

    Uses the session's own slug if available, otherwise a truncated
    version of the first human message.
    """
    slug = meta.slug or ""
    if slug and slug != meta.project_dir:
        # Clean the slug for filesystem use
        safe = slug.replace(" ", "-").replace("/", "-").replace("\\", "-")
        safe = "".join(c for c in safe if c.isalnum() or c in "-_")
        return safe[:60]

    # Derive from first human message
    words = meta.first_human_message.split()[:6]
    slug = "-".join(w.lower() for w in words)
    safe = "".join(c for c in slug if c.isalnum() or c in "-_")
    return safe[:60] or meta.session_id[:12]


def archive_session(
    session_path: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    include_raw: bool = True,
) -> ArchiveResult:
    """Archive a single session to its project directory.

    Creates:
      <project>/.claude/sessions/YYYY-MM-DD--<slug>/
        transcript.md   - Dialogue (summary mode)
        prompts.md      - Human prompts only
        review.md       - 5-phase review scaffold
        meta.json       - Machine-readable metadata
        session.jsonl   - Raw canonical data (if include_raw=True)

    Args:
        session_path: Path to the .jsonl session file.
        dry_run: Preview without writing.
        force: Re-archive even if already processed.
        include_raw: Copy the raw .jsonl file (can be large).

    Returns:
        ArchiveResult with details of what was written.
    """
    meta = parse_any_session(session_path)
    if not meta:
        return ArchiveResult(
            session_id=session_path.stem,
            project_path=Path(),
            archive_dir=Path(),
            files_written=[],
            error=f"Could not parse session: {session_path}",
        )

    project_path = resolve_project_path(meta)
    if not project_path:
        return ArchiveResult(
            session_id=meta.session_id,
            project_path=Path(meta.cwd or "."),
            archive_dir=Path(),
            files_written=[],
            skipped=True,
            skip_reason=f"Project directory not found: {meta.cwd}",
        )

    # Check archive state
    if not force:
        state = load_archive_state(project_path)
        if meta.session_id in state:
            return ArchiveResult(
                session_id=meta.session_id,
                project_path=project_path,
                archive_dir=Path(state[meta.session_id].get("archive_dir", "")),
                files_written=[],
                skipped=True,
                skip_reason="Already archived",
            )

    # Build archive directory name
    slug = _session_slug(meta)
    dir_name = f"{meta.date_str}--{slug}"
    archive_dir = project_path / ".claude" / "sessions" / dir_name

    if dry_run:
        files = ["transcript.md", "prompts.md", "review.md", "meta.json"]
        if include_raw:
            files.append("session.jsonl")
        return ArchiveResult(
            session_id=meta.session_id,
            project_path=project_path,
            archive_dir=archive_dir,
            files_written=files,
        )

    # Create archive directory
    archive_dir.mkdir(parents=True, exist_ok=True)

    files_written: list[str] = []

    # Transcript (summary mode — dialogue + reasoning, filtered tool output)
    transcript = render_any_transcript(session_path, unabridged=False)
    if transcript:
        (archive_dir / "transcript.md").write_text(transcript, encoding="utf-8")
        files_written.append("transcript.md")

    # Prompts extract
    prompts = render_any_prompts(session_path)
    if prompts:
        (archive_dir / "prompts.md").write_text(prompts, encoding="utf-8")
        files_written.append("prompts.md")

    # Review scaffold
    review_path = archive_dir / "review.md"
    export = SessionExport(meta=meta, slug=slug, output_path=review_path)
    review_content = export.render()
    review_path.write_text(review_content, encoding="utf-8")
    files_written.append("review.md")

    # Machine-readable metadata
    meta_json = _build_meta_json(meta)
    (archive_dir / "meta.json").write_text(meta_json, encoding="utf-8")
    files_written.append("meta.json")

    # Raw session data
    if include_raw and session_path.exists():
        raw_dest = archive_dir / "session.jsonl"
        shutil.copy2(session_path, raw_dest)
        files_written.append("session.jsonl")

    # Copy subagent data if present
    subagent_dir = session_path.parent / session_path.stem / "subagents"
    if subagent_dir.is_dir():
        dest_subagents = archive_dir / "subagents"
        dest_subagents.mkdir(exist_ok=True)
        for f in subagent_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, dest_subagents / f.name)
                files_written.append(f"subagents/{f.name}")

    # Update archive state
    state = load_archive_state(project_path)
    state[meta.session_id] = {
        "slug": slug,
        "archive_dir": str(archive_dir),
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "files": files_written,
        "date": meta.date_str,
    }
    _save_archive_state(project_path, state)

    return ArchiveResult(
        session_id=meta.session_id,
        project_path=project_path,
        archive_dir=archive_dir,
        files_written=files_written,
    )


def _resolve_since(since: str | None) -> str | None:
    """Resolve a since value to an absolute YYYY-MM-DD date string.

    Accepts:
      - YYYY-MM-DD (passthrough)
      - Nd (N days ago, e.g., 7d)
      - Nh (N hours ago, e.g., 24h)
    """
    if not since:
        return None

    # Already a date
    if re.match(r"^\d{4}-\d{2}-\d{2}$", since):
        return since

    # Relative: Nd or Nh
    m = re.match(r"^(\d+)([dh])$", since)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=n) if unit == "d" else now - timedelta(hours=n)
        return cutoff.strftime("%Y-%m-%d")

    return since  # fallback: pass through and hope it's comparable


def discover_unarchived_sessions(
    *,
    project_filter: str | None = None,
    since: str | None = None,
    agent: str | None = None,
    force: bool = False,
) -> list[tuple[Path, SessionMeta]]:
    """Find sessions that have not yet been archived to their project repos.

    Returns list of (session_path, meta) tuples for unarchived sessions,
    sorted by date (newest first).

    With ``force=True`` the already-archived filter is dropped, so every
    session matching the filters is returned for re-archiving (refreshing a
    stale snapshot of a resumed-then-continued session).
    """
    from organvm_engine.session.agents import discover_all_sessions

    all_sessions = discover_all_sessions(
        agent=agent,
        project_filter=project_filter,
    )

    # Build a set of already-archived session IDs per project

    # Check archive states for known projects
    seen_projects: dict[str, dict] = {}

    since_resolved = _resolve_since(since)

    unarchived: list[tuple[Path, SessionMeta]] = []

    for session_info in all_sessions:
        session_path = session_info.file_path

        meta = parse_any_session(session_path)
        if not meta:
            continue

        # Apply date filter
        if since_resolved and meta.date_str < since_resolved:
            continue

        project_path = resolve_project_path(meta)
        if not project_path:
            continue

        project_key = str(project_path)
        if project_key not in seen_projects:
            seen_projects[project_key] = load_archive_state(project_path)

        state = seen_projects[project_key]
        if force or meta.session_id not in state:
            unarchived.append((session_path, meta))

    return unarchived


def archive_all(
    *,
    project_filter: str | None = None,
    since: str | None = None,
    agent: str | None = None,
    dry_run: bool = False,
    include_raw: bool = True,
    force: bool = False,
) -> list[ArchiveResult]:
    """Archive all unprocessed sessions to their project directories.

    Args:
        project_filter: Only archive sessions matching this project path substring.
        since: Only archive sessions on or after this date (YYYY-MM-DD).
        agent: Only archive sessions from this agent (claude/gemini/codex).
        dry_run: Preview without writing.
        include_raw: Copy raw .jsonl files.
        force: Re-archive sessions even if already archived (refresh stale snapshots).

    Returns:
        List of ArchiveResult for each session processed.
    """
    unarchived = discover_unarchived_sessions(
        project_filter=project_filter,
        since=since,
        agent=agent,
        force=force,
    )

    results: list[ArchiveResult] = []
    for session_path, _meta in unarchived:
        result = archive_session(
            session_path,
            dry_run=dry_run,
            include_raw=include_raw,
            force=force,
        )
        results.append(result)

    return results
