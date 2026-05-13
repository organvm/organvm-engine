"""CLI handler for `organvm subatomic decompose`.

Decomposes a session memory into candidate sub-atoms by parsing narrative
breaks, commit-count groupings, and decision points. Output is YAML
(or JSON) — proposed sub-atoms with title, description, source-commit,
parent-session. NOT auto-claimed as DONE-IDs; human/Claude reviews.

Built as part of DIWS Stream Τ. Per wave-particle / micro-element-multiversality
principle: every session memory is one coarse atom AND N sub-atoms; this
tool surfaces the sub-atoms.

Usage:
    organvm subatomic decompose <session-id-or-path>
    organvm subatomic decompose <path> --json
    organvm subatomic decompose <path> --min-segment-bytes 200
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

MEMORY_DIR = Path.home() / ".claude" / "projects" / "-Users-4jp" / "memory"


@dataclass
class SubAtomCandidate:
    """One proposed sub-atom from a session memory."""

    parent_session: str
    title: str
    description: str
    segment_bytes: int
    source_lines: tuple[int, int]  # (start, end) line numbers in memory file
    commit_refs: list[str]  # commit SHAs detected in segment
    decision_signals: list[str]  # imperative / decision-marker words found


# Heuristics for narrative-break detection.
HEADER_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$")
COMMIT_RE = re.compile(r"\b([0-9a-f]{7,40})\b")  # commit SHA-like
DECISION_RE = re.compile(
    r"\b(decision|chose|shipped|done|landed|deployed|"
    r"fixed|completed|merged|approved|"
    r"committed|pushed|verified|closed)\b",
    re.IGNORECASE,
)
TRANSITION_RE = re.compile(r"^\s*\*\*(then|next|after that|step \d+)[^*]*\*\*", re.IGNORECASE)


def _resolve_input(arg: str) -> Path:
    """Accept either a session id or a path to a memory file."""
    p = Path(arg)
    if p.exists():
        return p
    # Try as session id
    candidates = [
        MEMORY_DIR / f"project_session_{arg}.md",
        MEMORY_DIR / f"project_artifact_{arg}.md",
        MEMORY_DIR / f"project_{arg}.md",
    ]
    for c in candidates:
        if c.exists():
            return c
    msg = f"Could not resolve session input: {arg!r}"
    raise FileNotFoundError(msg)


def _segments(text: str) -> list[tuple[int, int, str]]:
    """Split text on h2/h3 headers; return list of (start_line, end_line, segment_text)."""
    lines = text.splitlines()
    headers: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = HEADER_RE.match(line)
        if m:
            headers.append((i, line.strip()))

    if not headers:
        return [(0, len(lines) - 1, text)]

    segments: list[tuple[int, int, str]] = []
    for idx, (lineno, _header) in enumerate(headers):
        end = headers[idx + 1][0] - 1 if idx + 1 < len(headers) else len(lines) - 1
        segment_text = "\n".join(lines[lineno : end + 1])
        segments.append((lineno + 1, end + 1, segment_text))  # 1-indexed
    return segments


def _candidate_title(segment: str) -> str:
    """Extract a title from a segment — the first header line, trimmed."""
    for line in segment.splitlines():
        m = HEADER_RE.match(line)
        if m:
            return m.group(2).strip()
    # Fallback: first non-empty line up to 80 chars
    for line in segment.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s[:80]
    return "(untitled segment)"


def _detect_decisions(segment: str) -> list[str]:
    """Return unique decision-signal words found in the segment."""
    found = {m.group(1).lower() for m in DECISION_RE.finditer(segment)}
    return sorted(found)


def _detect_commits(segment: str) -> list[str]:
    """Return unique commit-SHA-like strings (7+ hex chars)."""
    found = set()
    for m in COMMIT_RE.finditer(segment):
        token = m.group(1)  # allow-secret: regex-extracted SHA candidate, not a credential
        if not token.isdigit() and len(token) >= 7:
            found.add(token)
    return sorted(found)


def _decompose(text: str, parent_session: str, min_bytes: int) -> list[SubAtomCandidate]:
    candidates: list[SubAtomCandidate] = []
    for start, end, segment in _segments(text):
        size = len(segment.encode("utf-8"))
        if size < min_bytes:
            continue
        title = _candidate_title(segment)
        description = segment.strip()
        if len(description) > 600:
            description = description[:600] + "…"
        candidates.append(
            SubAtomCandidate(
                parent_session=parent_session,
                title=title,
                description=description,
                segment_bytes=size,
                source_lines=(start, end),
                commit_refs=_detect_commits(segment),
                decision_signals=_detect_decisions(segment),
            )
        )
    return candidates


def cmd_subatomic_decompose(args) -> int:
    """Decompose a session memory into sub-atom candidates."""
    arg = getattr(args, "session", None)
    if not arg:
        sys.stderr.write("usage: organvm subatomic decompose <session-id-or-path>\n")
        return 2
    try:
        path = _resolve_input(arg)
    except FileNotFoundError as e:
        sys.stderr.write(f"{e}\n")
        return 1

    text = path.read_text(errors="replace")
    parent_session = path.stem.removeprefix("project_session_").removeprefix("project_")
    min_bytes = int(getattr(args, "min_segment_bytes", 200))

    candidates = _decompose(text, parent_session, min_bytes)

    as_json = getattr(args, "json", False)
    as_yaml = getattr(args, "yaml", False) or (not as_json)

    if as_json:
        sys.stdout.write(
            json.dumps(
                {
                    "parent_session": parent_session,
                    "source_path": str(path),
                    "min_segment_bytes": min_bytes,
                    "candidate_count": len(candidates),
                    "candidates": [asdict(c) for c in candidates],
                },
                indent=2,
            )
            + "\n"
        )
        return 0

    if as_yaml:
        # Hand-roll lightweight YAML so we don't add a runtime dep
        out: list[str] = []
        out.append(f"parent_session: {parent_session}")
        out.append(f"source_path: {path}")
        out.append(f"min_segment_bytes: {min_bytes}")
        out.append(f"candidate_count: {len(candidates)}")
        out.append("candidates:")
        for c in candidates:
            out.append(f"  - title: {json.dumps(c.title)}")
            out.append(f"    parent_session: {c.parent_session}")
            out.append(f"    segment_bytes: {c.segment_bytes}")
            out.append(f"    source_lines: [{c.source_lines[0]}, {c.source_lines[1]}]")
            out.append(f"    commit_refs: {json.dumps(c.commit_refs)}")
            out.append(f"    decision_signals: {json.dumps(c.decision_signals)}")
            out.append(f"    description: {json.dumps(c.description)}")
        sys.stdout.write("\n".join(out) + "\n")
        return 0

    # Default: human table
    print(f"Sub-atom candidates from {path.name}")
    print(f"Parent session: {parent_session}")
    print(f"Total candidates: {len(candidates)}")
    print()
    for i, c in enumerate(candidates, start=1):
        print(f"#{i}  {c.title}")
        print(f"    lines {c.source_lines[0]}–{c.source_lines[1]} | {c.segment_bytes} bytes")
        if c.commit_refs:
            print(f"    commits: {', '.join(c.commit_refs[:3])}")
        if c.decision_signals:
            print(f"    decision signals: {', '.join(c.decision_signals)}")
        print()
    return 0
