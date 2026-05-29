"""CLI handler for `organvm memory triangulate`.

Cross-references atoms / IRF / git / GH for items in a time window. Reports
items present in 1 location but missing from others (single-location risk).
Universal rule #2 (nothing local-only) + axiom #23 (identity = convergence
across ≥3 locations) enforcement.

Built as part of DIWS Stream Τ.

Usage:
    organvm memory triangulate --since 72h
    organvm memory triangulate --since 7d --json
    organvm memory triangulate --since 72h --strict
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

# Identifier patterns for entities we're tracking.
ID_PATTERNS = [
    re.compile(r"\b(IRF-[A-Z]+-\d+)\b"),
    re.compile(r"\b(PRT-\d+)\b"),
    re.compile(r"\b(SYS-\d+)\b"),
    re.compile(r"\b(DONE-\d+)\b"),
    re.compile(r"\b(GH#\d+)\b"),
]


@dataclass
class TriangulationEntry:
    """One identified entity and where it appears."""

    identifier: str
    in_memory: bool
    in_irf: bool
    in_git: bool
    location_count: int
    risk_level: str  # "OK" / "WATCH" / "STALE"
    locations: list[str]


def _parse_window(args) -> tuple[datetime, datetime]:
    end = datetime.now()
    since = getattr(args, "since", "72h") or "72h"
    m = re.match(r"^(\d+)\s*([hdw])$", since.strip())
    if not m:
        msg = f"invalid --since value: {since!r}"
        raise ValueError(msg)
    n, unit = int(m.group(1)), m.group(2)
    delta = {"h": timedelta(hours=n), "d": timedelta(days=n), "w": timedelta(weeks=n)}[unit]
    return end - delta, end


def _scan_text(text: str) -> set[str]:
    """Return unique identifiers found in text."""
    found: set[str] = set()
    for pattern in ID_PATTERNS:
        for m in pattern.finditer(text):
            found.add(m.group(1))
    return found


def _scan_memory_dir(start: datetime, end: datetime) -> dict[str, set[str]]:
    """Return {identifier: {memory_file_paths}} for files in window."""
    result: dict[str, set[str]] = {}
    if not MEMORY_DIR.exists():
        return result
    for p in MEMORY_DIR.glob("*.md"):
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
        except OSError:
            continue
        if not (start <= mtime <= end):
            continue
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        for ident in _scan_text(text):
            result.setdefault(ident, set()).add(str(p))
    return result


def _scan_irf() -> set[str]:
    if not IRF_PATH.exists():
        return set()
    try:
        text = IRF_PATH.read_text(errors="replace")
    except OSError:
        return set()
    return _scan_text(text)


def _scan_git_log(start: datetime, end: datetime) -> set[str]:
    """Scan corpvs + a-i--skills git logs for identifiers within window."""
    found: set[str] = set()
    repos = [
        IRF_PATH.parent,
        Path.home() / "Workspace" / "organvm" / "a-i--skills",
        Path.home() / "Workspace" / "4444J99" / "domus-semper-palingenesis",
    ]
    for repo in repos:
        if not (repo / ".git").exists():
            continue
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
                    "--pretty=format:%s%n%b",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if result.returncode != 0:
            continue
        found.update(_scan_text(result.stdout))
    return found


def _classify(in_memory: bool, in_irf: bool, in_git: bool) -> tuple[int, str]:
    count = sum([in_memory, in_irf, in_git])
    if count >= 3:
        return count, "OK"
    if count == 2:
        return count, "WATCH"
    return count, "STALE"


def cmd_memory_triangulate(args) -> int:
    """Cross-ref atoms/IRF/git for entities in a time window."""
    start, end = _parse_window(args)

    memory_hits = _scan_memory_dir(start, end)
    irf_hits = _scan_irf()
    git_hits = _scan_git_log(start, end)

    all_ids = set(memory_hits.keys()) | irf_hits | git_hits

    entries: list[TriangulationEntry] = []
    for ident in sorted(all_ids):
        in_memory = ident in memory_hits
        in_irf = ident in irf_hits
        in_git = ident in git_hits
        count, risk = _classify(in_memory, in_irf, in_git)
        locations: list[str] = []
        if in_memory:
            locations.extend(sorted(memory_hits[ident]))
        if in_irf:
            locations.append(str(IRF_PATH))
        if in_git:
            locations.append("(git log)")
        entries.append(
            TriangulationEntry(
                identifier=ident,
                in_memory=in_memory,
                in_irf=in_irf,
                in_git=in_git,
                location_count=count,
                risk_level=risk,
                locations=locations,
            ),
        )

    strict = bool(getattr(args, "strict", False))
    if strict:
        entries = [e for e in entries if e.risk_level != "OK"]

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

    print(f"Memory triangulation — window {start.date()} → {end.date()}")
    print(f"Strict mode: {strict}")
    print()

    if not entries:
        print("No entities found (or all triple-referenced if --strict).")
        return 0

    col_id = 18
    col_risk = 7
    print(f"{'identifier':<{col_id}} {'risk':<{col_risk}} mem irf git  count")
    print(f"{'─' * col_id} {'─' * col_risk} ─── ─── ───  ─────")
    for e in entries:
        mem = "✓" if e.in_memory else "·"
        irf = "✓" if e.in_irf else "·"
        git = "✓" if e.in_git else "·"
        print(
            f"{e.identifier:<{col_id}} {e.risk_level:<{col_risk}}  {mem}   {irf}   {git}    {e.location_count}",
        )

    ok = sum(1 for e in entries if e.risk_level == "OK")
    watch = sum(1 for e in entries if e.risk_level == "WATCH")
    stale = sum(1 for e in entries if e.risk_level == "STALE")
    print()
    print(f"Total: {len(entries)} | OK: {ok} | WATCH: {watch} | STALE: {stale}")
    return 0
