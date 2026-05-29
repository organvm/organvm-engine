"""CLI handler for the sessions audit command group.

Surfaces session memories and verifies triple-reference (memory + IRF + git/GH)
across a configurable time window. Built as part of DIWS Stream Τ to close
the dark-matter gap identified in the 72h audit (2026-04-23 → 2026-04-25).

Usage:
    organvm sessions audit --since 72h
    organvm sessions audit --since 7d --json
    organvm sessions audit --window-start 2026-04-23 --window-end 2026-04-25
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_DIR = Path.home() / ".claude" / "projects" / "-Users-4jp" / "memory"
IRF_PATH = (
    Path.home()
    / "Workspace"
    / "organvm"
    / "organvm-corpvs-testamentvm"
    / "INST-INDEX-RERUM-FACIENDARUM.md"
)
SESSION_FILE_PATTERN = "project_session_*.md"


@dataclass
class SessionAuditEntry:
    """One row in the sessions-audit report."""

    memory_file: str
    session_id: str
    mtime: str
    has_irf_reference: bool
    has_git_evidence: bool
    triple_ref_status: str  # "OK" / "STALE" / "PARTIAL"
    notes: str


def _parse_window(args) -> tuple[datetime, datetime]:
    """Resolve --since / --window-start / --window-end into (start, end) datetimes."""
    end = datetime.now()
    if getattr(args, "window_end", None):
        end = datetime.fromisoformat(args.window_end)

    if getattr(args, "window_start", None):
        start = datetime.fromisoformat(args.window_start)
        return start, end

    since = getattr(args, "since", "72h") or "72h"
    match = re.match(r"^(\d+)\s*([hdw])$", since.strip())
    if not match:
        raise ValueError(f"invalid --since value: {since!r} (expected like '72h', '7d', '4w')")
    n, unit = int(match.group(1)), match.group(2)
    delta = {"h": timedelta(hours=n), "d": timedelta(days=n), "w": timedelta(weeks=n)}[unit]
    return end - delta, end


def _list_session_memories(start: datetime, end: datetime) -> list[Path]:
    if not MEMORY_DIR.exists():
        return []
    out: list[Path] = []
    for p in MEMORY_DIR.glob(SESSION_FILE_PATTERN):
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
        except OSError:
            continue
        if start <= mtime <= end:
            out.append(p)
    return sorted(out)


def _check_irf_reference(session_id: str) -> bool:
    """Look for the session id in the IRF text."""
    if not IRF_PATH.exists():
        return False
    try:
        text = IRF_PATH.read_text(errors="replace")
    except OSError:
        return False
    # Session ids are typically slugs; match either bare slug or quoted.
    return session_id.lower() in text.lower()


def _check_git_evidence(session_id: str, start: datetime, end: datetime) -> bool:
    """Look in the corpvs git log for the session id within window."""
    repo = IRF_PATH.parent
    if not (repo / ".git").exists():
        return False
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "log",
                f"--since={start.isoformat()}",
                f"--until={end.isoformat()}",
                "--all",
                "--pretty=format:%H %s",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    if result.returncode != 0:
        return False
    return session_id.lower() in result.stdout.lower()


def _session_id_from_path(path: Path) -> str:
    # project_session_2026-04-25_catch_all_titan_keeper.md → 2026-04-25_catch_all_titan_keeper
    name = path.stem
    return name.removeprefix("project_session_")


def _audit_one(path: Path, start: datetime, end: datetime) -> SessionAuditEntry:
    session_id = _session_id_from_path(path)
    mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    has_irf = _check_irf_reference(session_id)
    has_git = _check_git_evidence(session_id, start, end)

    refs = sum([has_irf, has_git])
    if refs >= 2:
        status, notes = "OK", "memory + IRF + git all present"
    elif refs == 1:
        status, notes = "PARTIAL", (
            "missing IRF reference" if not has_irf else "missing git evidence"
        )
    else:
        status, notes = "STALE", "memory only — no IRF or git evidence"

    return SessionAuditEntry(
        memory_file=str(path),
        session_id=session_id,
        mtime=mtime,
        has_irf_reference=has_irf,
        has_git_evidence=has_git,
        triple_ref_status=status,
        notes=notes,
    )


def cmd_sessions_audit(args) -> int:
    """Audit session memories within a time window for triple-reference status."""
    start, end = _parse_window(args)
    memories = _list_session_memories(start, end)

    if not memories:
        if getattr(args, "json", False):
            sys.stdout.write(json.dumps({"window_start": start.isoformat(), "window_end": end.isoformat(), "entries": []}, indent=2) + "\n")
        else:
            print(f"No session memories in window {start.date()} → {end.date()}.")
        return 0

    entries = [_audit_one(p, start, end) for p in memories]

    if getattr(args, "json", False):
        sys.stdout.write(
            json.dumps(
                {
                    "window_start": start.isoformat(),
                    "window_end": end.isoformat(),
                    "count": len(entries),
                    "entries": [asdict(e) for e in entries],
                },
                indent=2,
            )
            + "\n",
        )
        return 0

    print(f"Sessions audit — window {start.date()} → {end.date()}")
    print(f"Memory dir: {MEMORY_DIR}")
    print(f"IRF: {IRF_PATH}")
    print()

    col_id = 50
    col_status = 9
    print(f"{'session_id':<{col_id}} {'status':<{col_status}} notes")
    print(f"{'─' * col_id} {'─' * col_status} {'─' * 40}")
    for e in entries:
        sid = e.session_id if len(e.session_id) <= col_id else e.session_id[: col_id - 1] + "…"
        print(f"{sid:<{col_id}} {e.triple_ref_status:<{col_status}} {e.notes}")

    ok = sum(1 for e in entries if e.triple_ref_status == "OK")
    partial = sum(1 for e in entries if e.triple_ref_status == "PARTIAL")
    stale = sum(1 for e in entries if e.triple_ref_status == "STALE")
    print()
    print(f"Total: {len(entries)} | OK: {ok} | PARTIAL: {partial} | STALE: {stale}")
    return 0
