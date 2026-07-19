"""Session debrief — tiered task extraction and session analysis.

Implements: SPEC-015, ESCL-005 (session debrief and escalation)

Produces a structured close-out deliverable at session end:
- Session analysis (what happened, areas touched, accomplishments)
- Tiered to-dos: Big (multi-session), Medium (single-session), Small (quick fixes)

The debrief extracts signals from tool usage, file paths, and human prompts
to classify work done and surface remaining tasks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FileTouch:
    """A file touched during the session."""

    path: str
    action: str  # read, write, edit
    count: int = 1


@dataclass
class SessionDebrief:
    """Structured session close-out."""

    session_id: str
    agent: str
    project: str
    duration_minutes: int | None
    date: str

    # Analysis
    files_written: list[str] = field(default_factory=list)
    files_edited: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    repos_touched: list[str] = field(default_factory=list)
    tool_summary: dict[str, int] = field(default_factory=dict)
    bash_commands: list[str] = field(default_factory=list)
    human_prompts: list[str] = field(default_factory=list)
    test_runs: int = 0
    commits_made: int = 0

    # Tiered to-dos (populated by classify_todos)
    big_todos: list[str] = field(default_factory=list)
    medium_todos: list[str] = field(default_factory=list)
    small_todos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent": self.agent,
            "project": self.project,
            "duration_minutes": self.duration_minutes,
            "date": self.date,
            "files_written": self.files_written,
            "files_edited": self.files_edited,
            "files_read_count": len(self.files_read),
            "repos_touched": self.repos_touched,
            "tool_summary": self.tool_summary,
            "test_runs": self.test_runs,
            "commits_made": self.commits_made,
            "prompt_count": len(self.human_prompts),
            "big_todos": self.big_todos,
            "medium_todos": self.medium_todos,
            "small_todos": self.small_todos,
        }


def build_debrief(jsonl_path: Path) -> SessionDebrief | None:
    """Build a session debrief from a Claude Code JSONL transcript.

    Extracts tool usage, file touches, bash commands, and human prompts
    to construct a structured analysis of what happened.
    """
    from organvm_engine.session.parser import detect_agent, parse_any_session

    meta = parse_any_session(jsonl_path)
    if not meta:
        return None

    agent = detect_agent(jsonl_path)
    debrief = SessionDebrief(
        session_id=meta.session_id,
        agent=agent,
        project=meta.project_dir or meta.cwd,
        duration_minutes=meta.duration_minutes,
        date=meta.date_str,
        tool_summary=dict(meta.tools_used),
    )

    # Parse JSONL for detailed file/command extraction
    _extract_details(jsonl_path, agent, debrief)

    # Derive repos from file paths
    debrief.repos_touched = _derive_repos(
        debrief.files_written + debrief.files_edited,
    )

    return debrief


def _extract_details(
    jsonl_path: Path,
    agent: str,
    debrief: SessionDebrief,
) -> None:
    """Extract file touches, bash commands, and prompts from session JSONL."""
    if agent != "claude":
        # Only Claude JSONL has the detailed tool_use blocks we need
        return

    seen_writes: set[str] = set()
    seen_edits: set[str] = set()
    seen_reads: set[str] = set()

    try:
        with jsonl_path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                # Extract human prompts
                if msg_type == "user":
                    text = _msg_to_text(msg)
                    if text and len(text) > 10:
                        debrief.human_prompts.append(text)
                    continue

                # Extract tool uses from assistant messages
                if msg_type != "assistant":
                    continue

                content = msg.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue

                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue

                    name = block.get("name", "")
                    inp = block.get("input", {})

                    if name in ("Write", "write_file"):
                        fp = inp.get("file_path", inp.get("path", ""))
                        if fp and fp not in seen_writes:
                            seen_writes.add(fp)
                            debrief.files_written.append(fp)

                    elif name == "Edit":
                        fp = inp.get("file_path", "")
                        if fp and fp not in seen_edits:
                            seen_edits.add(fp)
                            debrief.files_edited.append(fp)

                    elif name in ("Read", "read_file"):
                        fp = inp.get("file_path", inp.get("path", ""))
                        if fp and fp not in seen_reads:
                            seen_reads.add(fp)
                            debrief.files_read.append(fp)

                    elif name == "Bash":
                        cmd = inp.get("command", "")
                        if cmd:
                            debrief.bash_commands.append(cmd)
                            if _is_test_command(cmd):
                                debrief.test_runs += 1
                            if _is_commit_command(cmd):
                                debrief.commits_made += 1

    except OSError:
        pass


def _msg_to_text(msg: dict) -> str:
    """Extract plain text from a user message."""
    content = msg.get("message", {}).get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts).strip()
    return ""


def _is_test_command(cmd: str) -> bool:
    """Check if a bash command is a test invocation."""
    return bool(re.search(r"\bpytest\b|\bnpm\s+test\b|\bvitest\b|\bjest\b", cmd))


def _is_commit_command(cmd: str) -> bool:
    """Check if a bash command is a git commit."""
    return bool(re.search(r"\bgit\s+commit\b", cmd))


def _derive_repos(file_paths: list[str]) -> list[str]:
    """Derive repo names from file paths.

    Looks for patterns like .../meta-organvm/organvm-engine/... and extracts
    the repo-level directory.
    """
    repos: set[str] = set()
    for fp in file_paths:
        parts = Path(fp).parts
        # Look for known workspace markers
        for i, part in enumerate(parts):
            if part in ("meta-organvm", "Workspace") and i + 1 < len(parts):
                # Next part after meta-organvm is the repo
                if part == "meta-organvm" and i + 1 < len(parts):
                    repos.add(parts[i + 1])
                    break
                # Next two parts after Workspace: org/repo
                if part == "Workspace" and i + 2 < len(parts):
                    repos.add(parts[i + 2])
                    break
    return sorted(repos)


def classify_todos(debrief: SessionDebrief) -> None:
    """Classify remaining work into big/medium/small tiers.

    Uses heuristics from the session's prompts, tool usage, and file patterns
    to identify what was started but not finished, and what naturally follows.
    """
    # Analyze prompt content for explicit TODO signals
    for prompt in debrief.human_prompts:
        lower = prompt.lower()

        # Look for explicit future-work language
        for pattern in (
            r"(?:later|next|todo|follow[- ]?up|eventually|should also)\b[^.]*",
            r"(?:we still need|we need to|still need to|don't forget)\b[^.]*",
            r"(?:after this|once .+ is done)\b[^.]*",
        ):
            matches = re.findall(pattern, lower)
            for m in matches:
                cleaned = m.strip().rstrip(".,;")
                if len(cleaned) > 15:
                    debrief.medium_todos.append(cleaned)

    # Infer todos from session patterns
    _infer_structural_todos(debrief)

    # Deduplicate
    debrief.big_todos = _dedupe(debrief.big_todos)
    debrief.medium_todos = _dedupe(debrief.medium_todos)
    debrief.small_todos = _dedupe(debrief.small_todos)


def _infer_structural_todos(debrief: SessionDebrief) -> None:
    """Infer todos from structural patterns in the session."""
    # If tests were written but not run (or run and failed)
    has_test_files = any("test_" in f for f in debrief.files_written + debrief.files_edited)
    if has_test_files and debrief.test_runs == 0:
        debrief.small_todos.append("Run tests for newly written test files")

    # If files were written but never committed
    if (debrief.files_written or debrief.files_edited) and debrief.commits_made == 0:
        debrief.small_todos.append("Commit uncommitted changes from this session")

    # If multiple repos were touched, suggest integration verification
    if len(debrief.repos_touched) > 2:
        debrief.medium_todos.append(
            f"Verify integration across {len(debrief.repos_touched)} repos: "
            + ", ".join(debrief.repos_touched),
        )

    # If CLAUDE.md or MEMORY.md was not updated but significant work was done
    significant = len(debrief.files_written) + len(debrief.files_edited) >= 5
    touched_memory = any("MEMORY" in f or "CLAUDE.md" in f for f in debrief.files_edited)
    if significant and not touched_memory:
        debrief.small_todos.append("Update MEMORY.md with session outcomes")

    # If new tool files were created, suggest MCP server wiring check
    new_tools = [f for f in debrief.files_written if "/tools/" in f]
    if new_tools:
        debrief.small_todos.append("Verify new tool files are wired into server.py dispatch")

    # If governance/audit files were touched, suggest full audit run
    governance_files = [
        f for f in debrief.files_written + debrief.files_edited
        if "governance" in f or "audit" in f
    ]
    if governance_files:
        debrief.medium_todos.append("Run full governance audit: organvm governance audit")


def _dedupe(items: list[str]) -> list[str]:
    """Deduplicate while preserving order."""
    seen: set[str] = set()
    result = []
    for item in items:
        normalized = item.lower().strip()
        if normalized not in seen:
            seen.add(normalized)
            result.append(item)
    return result


def render_debrief(debrief: SessionDebrief) -> str:
    """Render a session debrief as markdown."""
    lines = [
        f"# Session Debrief: {debrief.date}",
        "",
        f"**Agent:** {debrief.agent} | **Duration:** {debrief.duration_minutes or '?'} min | "
        f"**Session:** `{debrief.session_id[:8]}`",
        f"**Project:** {debrief.project}",
        "",
    ]

    # Session analysis
    lines.append("## Analysis")
    lines.append("")

    if debrief.repos_touched:
        lines.append(f"**Repos touched:** {', '.join(debrief.repos_touched)}")

    lines.append(f"**Files written:** {len(debrief.files_written)}")
    lines.append(f"**Files edited:** {len(debrief.files_edited)}")
    lines.append(f"**Files read:** {len(debrief.files_read)}")
    lines.append(f"**Test runs:** {debrief.test_runs}")
    lines.append(f"**Commits:** {debrief.commits_made}")
    lines.append(f"**Prompts:** {len(debrief.human_prompts)}")
    lines.append("")

    # Tool breakdown
    if debrief.tool_summary:
        lines.append("### Tool Usage")
        for tool, count in sorted(
            debrief.tool_summary.items(), key=lambda x: -x[1],
        )[:10]:
            lines.append(f"- {tool}: {count}")
        lines.append("")

    # Files written/edited
    if debrief.files_written:
        lines.append("### Files Created")
        for f in debrief.files_written:
            lines.append(f"- `{_short_path(f)}`")
        lines.append("")

    if debrief.files_edited:
        lines.append("### Files Modified")
        for f in debrief.files_edited:
            lines.append(f"- `{_short_path(f)}`")
        lines.append("")

    # Tiered to-dos
    lines.append("## To-Dos")
    lines.append("")

    if debrief.big_todos:
        lines.append("### Big (multi-session, architectural)")
        for todo in debrief.big_todos:
            lines.append(f"- [ ] {todo}")
        lines.append("")

    if debrief.medium_todos:
        lines.append("### Medium (single-session, contained)")
        for todo in debrief.medium_todos:
            lines.append(f"- [ ] {todo}")
        lines.append("")

    if debrief.small_todos:
        lines.append("### Small (quick fixes, polish)")
        for todo in debrief.small_todos:
            lines.append(f"- [ ] {todo}")
        lines.append("")

    if not (debrief.big_todos or debrief.medium_todos or debrief.small_todos):
        lines.append("*No to-dos extracted. Add manually if needed.*")
        lines.append("")

    return "\n".join(lines)


def _short_path(path: str) -> str:
    """Shorten a file path for display."""
    parts = Path(path).parts
    # Find the repo-level directory and show from there
    for i, part in enumerate(parts):
        if part == "meta-organvm" and i + 1 < len(parts):
            return "/".join(parts[i + 1 :])
        if part == "Workspace" and i + 2 < len(parts):
            return "/".join(parts[i + 2 :])
    # Fallback: last 3 parts
    return "/".join(parts[-3:]) if len(parts) >= 3 else path
