"""Parse AI agent session transcripts into structured metadata.

Supports Claude Code (.jsonl), Gemini CLI (.json), and Codex (.jsonl).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


@dataclass
class SessionMeta:
    """Metadata extracted from a Claude Code session transcript."""

    session_id: str
    file_path: Path
    slug: str
    cwd: str
    git_branch: str
    started: datetime | None
    ended: datetime | None
    message_count: int
    human_messages: int
    assistant_messages: int
    tools_used: dict[str, int]
    first_human_message: str
    project_dir: str

    @property
    def date_str(self) -> str:
        if self.started:
            return self.started.strftime("%Y-%m-%d")
        return "unknown"

    @property
    def duration_minutes(self) -> int | None:
        if self.started and self.ended:
            delta = self.ended - self.started
            return int(delta.total_seconds() / 60)
        return None


def _read_cwd_from_project(proj_dir: Path) -> str:
    """Read actual cwd from the first session file in a project directory.

    The encoded directory name is lossy (hyphens in paths are not escaped),
    so we extract the real path from session metadata.
    """
    for jsonl in proj_dir.glob("*.jsonl"):
        try:
            with jsonl.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        cwd = msg.get("cwd")
                        if cwd:
                            return cwd
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
    return proj_dir.name  # fallback to encoded name


def list_projects() -> list[dict]:
    """List all Claude Code project directories with session counts."""
    if not CLAUDE_PROJECTS_DIR.exists():
        return []

    results = []
    for proj_dir in sorted(CLAUDE_PROJECTS_DIR.iterdir()):
        if not proj_dir.is_dir():
            continue
        sessions = list(proj_dir.glob("*.jsonl"))
        if not sessions:
            continue

        decoded = _read_cwd_from_project(proj_dir)
        results.append({
            "project_dir": proj_dir.name,
            "decoded_path": decoded,
            "session_count": len(sessions),
            "path": str(proj_dir),
        })

    return results


def list_sessions(project_dir: str | None = None) -> list[SessionMeta]:
    """List all sessions, optionally filtered to a project directory."""
    if project_dir:
        search_dir = CLAUDE_PROJECTS_DIR / project_dir
        if not search_dir.exists():
            return []
        jsonl_files = sorted(search_dir.glob("*.jsonl"))
    else:
        jsonl_files = sorted(CLAUDE_PROJECTS_DIR.rglob("*.jsonl"))

    results = []
    for f in jsonl_files:
        meta = parse_session(f)
        if meta:
            results.append(meta)

    # Sort by start time, newest first
    results.sort(key=lambda m: m.started or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return results


def parse_session(jsonl_path: Path) -> SessionMeta | None:
    """Parse a session .jsonl file into structured metadata."""
    if not jsonl_path.exists():
        return None

    session_id = jsonl_path.stem
    slug = cwd = git_branch = ""
    project_dir = jsonl_path.parent.name
    timestamps: list[datetime] = []
    human_count = assistant_count = total = 0
    tools: dict[str, int] = {}
    first_human = ""

    try:
        with jsonl_path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                # Extract session metadata from first user/assistant message
                if not slug and msg.get("slug"):
                    slug = msg["slug"]
                if not cwd and msg.get("cwd"):
                    cwd = msg["cwd"]
                if not git_branch and msg.get("gitBranch"):
                    git_branch = msg["gitBranch"]

                # Track timestamps
                ts_str = msg.get("timestamp")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        timestamps.append(ts)
                    except (ValueError, TypeError):
                        pass

                if msg_type == "user":
                    total += 1
                    human_count += 1
                    if not first_human:
                        content = msg.get("message", {}).get("content", "")
                        if isinstance(content, str):
                            first_human = content[:300]
                        elif isinstance(content, list):
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    text = part.get("text", "")
                                    if text and len(text) > 20:
                                        first_human = text[:300]
                                        break

                elif msg_type == "assistant":
                    total += 1
                    assistant_count += 1
                    # Extract tool usage
                    content = msg.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                name = block.get("name", "unknown")
                                tools[name] = tools.get(name, 0) + 1

    except OSError:
        return None

    if total == 0:
        return None

    started = min(timestamps) if timestamps else None
    ended = max(timestamps) if timestamps else None

    return SessionMeta(
        session_id=session_id,
        file_path=jsonl_path,
        slug=slug,
        cwd=cwd,
        git_branch=git_branch,
        started=started,
        ended=ended,
        message_count=total,
        human_messages=human_count,
        assistant_messages=assistant_count,
        tools_used=tools,
        first_human_message=first_human,
        project_dir=project_dir,
    )


@dataclass
class SessionExport:
    """A session exported as a praxis-perpetua session review."""

    meta: SessionMeta
    slug: str
    output_path: Path

    def render(self) -> str:
        """Render as a session review markdown file with referential wires."""
        duration = f"~{self.meta.duration_minutes} min" if self.meta.duration_minutes else "unknown"
        date = self.meta.date_str
        short_id = self.meta.session_id[:8]

        # Top tools
        top_tools = sorted(self.meta.tools_used.items(), key=lambda x: x[1], reverse=True)[:10]
        tools_table = "\n".join(f"| {name} | {count} |" for name, count in top_tools)

        first_msg = self.meta.first_human_message
        if len(first_msg) > 200:
            first_msg = first_msg[:200] + "..."

        return f"""# Session Review: {date} -- {self.slug}

**Date:** {date}
**Agent(s):** Claude Code
**Session ID:** `{self.meta.session_id}`
**Slug:** `{self.meta.slug}`
**Duration:** {duration}
**Working directory:** `{self.meta.cwd}`
**Branch:** `{self.meta.git_branch}`
**Messages:** {self.meta.message_count} ({self.meta.human_messages} human, {self.meta.assistant_messages} assistant)

### Source & Render Commands

```bash
# Transcript (conversation summary)
organvm session transcript {short_id}

# Unabridged audit trail (thinking, full tool I/O, generated code)
organvm session transcript {short_id} --unabridged

# Prompts only (drift detection, pattern analysis)
organvm session prompts {short_id}
```

**Source JSONL:** `{self.meta.file_path}`

---

## Opening Prompt

> {first_msg}

---

## Tool Usage

| Tool | Count |
|------|-------|
{tools_table}

---

## Phase I: Inventory

### Goals
- [ ] [TODO: summarize goals from opening prompt]

### Files Produced/Modified
<!-- TODO: fill from git log or session content -->

| File | Action | Repo | Tracked? |
|------|--------|------|----------|
| — | — | — | — |

---

## Phase II: Structural Triage

- [ ] Git tracking: all files tracked
- [ ] File placement: correct repos and directories
- [ ] Naming conventions: followed
- [ ] Data integrity: no protected files modified
- [ ] Cross-references: all links resolve
- [ ] Version integrity: no destructive overwrites

---

## Phase III: Content Audit

| Deliverable | Standard | Compliance | Gaps |
|-------------|----------|------------|------|
| — | — | — | — |

---

## Phase IV: Lessons Extracted

1. [TODO: extract lessons]

---

## Phase V: Reconciliation

- [ ] Structural issues fixed
- [ ] Content gaps expanded
- [ ] Session log written
- [ ] `derived-principles.md` updated
- [ ] Fixes committed

---

## Outcome

**Summary:** [TODO]
**Net quality delta:** [TODO]
"""


def _extract_human_text(msg: dict) -> str:
    """Extract readable text from a human message."""
    content = msg.get("message", {}).get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text", "")
                if text:
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _extract_assistant_actions(msg: dict) -> list[str]:
    """Extract tool calls from an assistant message as concise action summaries."""
    content = msg.get("message", {}).get("content", [])
    actions = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name", "unknown")
                inp = block.get("input", {})
                # Build a concise summary of the action
                if name in ("Read", "read_file"):
                    actions.append(f"Read `{inp.get('file_path', inp.get('path', '?'))}`")
                elif name in ("Write", "write_file"):
                    actions.append(f"Write `{inp.get('file_path', inp.get('path', '?'))}`")
                elif name == "Edit":
                    actions.append(f"Edit `{inp.get('file_path', '?')}`")
                elif name == "Bash":
                    cmd = inp.get("command", "")
                    if len(cmd) > 120:
                        cmd = cmd[:120] + "..."
                    actions.append(f"Bash: `{cmd}`")
                elif name == "Grep":
                    actions.append(f"Grep `{inp.get('pattern', '?')}` in {inp.get('path', '.')}")
                elif name == "Glob":
                    actions.append(f"Glob `{inp.get('pattern', '?')}`")
                elif name == "Agent":
                    actions.append(f"Agent: {str(inp.get('prompt', ''))[:100]}")
                else:
                    actions.append(f"{name}")
    return actions


def render_prompts(jsonl_path: Path) -> str:
    """Extract human prompts with assistant action summaries for audit.

    Produces a clean prompts-only view with:
    - Numbered, timestamped human messages (full text)
    - Elapsed time between prompts
    - Condensed assistant actions (tool calls only, no prose)
    - Summary statistics at the end
    """
    meta = parse_session(jsonl_path)
    if not meta:
        return ""

    lines: list[str] = []
    duration = f"~{meta.duration_minutes} min" if meta.duration_minutes else "unknown"

    lines.append(f"# Session Prompts: {meta.date_str}")
    lines.append("")
    lines.append(f"**Session ID:** `{meta.session_id}`")
    lines.append(f"**Duration:** {duration}")
    lines.append(f"**Working directory:** `{meta.cwd}`")
    lines.append(f"**Prompts:** {meta.human_messages} human messages")
    lines.append("")
    lines.append("---")
    lines.append("")

    prompt_num = 0
    last_human_ts: datetime | None = None
    pending_actions: list[str] = []
    prompt_texts: list[str] = []  # for pattern summary

    with jsonl_path.open(encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                msg = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "assistant":
                pending_actions.extend(_extract_assistant_actions(msg))

            elif msg_type == "user":
                text = _extract_human_text(msg)

                # Skip tool results and system noise
                if not text or len(text.strip()) < 5:
                    continue
                # Skip tool_result-only messages (user turn carrying tool output back)
                msg_content = msg.get("message", {}).get("content", "")
                if isinstance(msg_content, list):
                    has_text = any(
                        isinstance(p, dict) and p.get("type") == "text" and len(p.get("text", "").strip()) > 5
                        for p in msg_content
                    )
                    has_tool_result = any(
                        isinstance(p, dict) and p.get("type") == "tool_result"
                        for p in msg_content
                    )
                    if has_tool_result and not has_text:
                        continue

                # Emit prior assistant actions before next prompt
                if pending_actions and prompt_num > 0:
                    lines.append("**Actions taken:**")
                    for a in pending_actions:
                        lines.append(f"- {a}")
                    lines.append("")
                    lines.append("---")
                    lines.append("")
                pending_actions = []

                prompt_num += 1

                # Timestamp and elapsed
                ts_str = msg.get("timestamp", "")
                ts_short = ts_str[:19].replace("T", " ") if ts_str else ""
                elapsed = ""
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if last_human_ts:
                            delta = ts - last_human_ts
                            mins = int(delta.total_seconds() / 60)
                            if mins > 0:
                                elapsed = f" (+{mins}m)"
                        last_human_ts = ts
                    except (ValueError, TypeError):
                        pass

                lines.append(f"### P{prompt_num} — {ts_short}{elapsed}")
                lines.append("")
                lines.append(text)
                lines.append("")

                prompt_texts.append(text)

    # Emit final assistant actions
    if pending_actions:
        lines.append("**Actions taken:**")
        for a in pending_actions:
            lines.append(f"- {a}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Summary section
    lines.append("---")
    lines.append("")
    lines.append("## Prompt Summary")
    lines.append("")
    lines.append(f"**Total prompts:** {prompt_num}")
    lines.append(f"**Session duration:** {duration}")
    if prompt_num > 0 and meta.duration_minutes:
        avg = meta.duration_minutes / prompt_num
        lines.append(f"**Avg time between prompts:** ~{avg:.1f} min")
    lines.append("")

    # Categorize prompts by rough type
    plan_count = sum(1 for t in prompt_texts if any(
        kw in t.lower() for kw in ["implement", "plan", "build", "create", "add", "write"]
    ))
    question_count = sum(1 for t in prompt_texts if "?" in t)
    fix_count = sum(1 for t in prompt_texts if any(
        kw in t.lower() for kw in ["fix", "error", "bug", "broken", "fail", "wrong"]
    ))
    review_count = sum(1 for t in prompt_texts if any(
        kw in t.lower() for kw in ["check", "verify", "review", "audit", "look at", "show"]
    ))

    lines.append("### Prompt Categories (heuristic)")
    lines.append("")
    lines.append(f"- **Directives** (implement/build/create/add/write): {plan_count}")
    lines.append(f"- **Questions**: {question_count}")
    lines.append(f"- **Fixes** (fix/error/bug/broken/fail): {fix_count}")
    lines.append(f"- **Reviews** (check/verify/review/audit): {review_count}")
    lines.append("")

    return "\n".join(lines)


def render_transcript(jsonl_path: Path) -> str:
    """Render a full session transcript as readable markdown."""
    meta = parse_session(jsonl_path)
    if not meta:
        return ""

    lines: list[str] = []
    duration = f"~{meta.duration_minutes} min" if meta.duration_minutes else "unknown"

    lines.append(f"# Session Transcript: {meta.date_str}")
    lines.append("")
    lines.append(f"**Session ID:** `{meta.session_id}`")
    lines.append(f"**Slug:** `{meta.slug}`")
    lines.append(f"**Duration:** {duration}")
    lines.append(f"**Working directory:** `{meta.cwd}`")
    lines.append(f"**Branch:** `{meta.git_branch}`")
    lines.append(f"**Messages:** {meta.message_count} ({meta.human_messages} human, {meta.assistant_messages} assistant)")
    lines.append("")
    lines.append("---")
    lines.append("")

    turn = 0
    with jsonl_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "user":
                turn += 1
                ts = msg.get("timestamp", "")
                ts_short = ts[:19].replace("T", " ") if ts else ""
                lines.append(f"## [{turn}] Human — {ts_short}")
                lines.append("")

                content = msg.get("message", {}).get("content", "")
                if isinstance(content, str):
                    lines.append(content)
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                lines.append(part.get("text", ""))
                            elif part.get("type") == "tool_result":
                                tool_id = part.get("tool_use_id", "")
                                lines.append(f"*Tool result for `{tool_id}`*")
                                result_content = part.get("content", "")
                                if isinstance(result_content, str):
                                    lines.append(f"```\n{result_content[:2000]}\n```")
                                elif isinstance(result_content, list):
                                    for rc in result_content:
                                        if isinstance(rc, dict) and rc.get("type") == "text":
                                            lines.append(f"```\n{rc.get('text', '')[:2000]}\n```")
                lines.append("")
                lines.append("---")
                lines.append("")

            elif msg_type == "assistant":
                turn += 1
                ts = msg.get("timestamp", "")
                ts_short = ts[:19].replace("T", " ") if ts else ""
                lines.append(f"## [{turn}] Assistant — {ts_short}")
                lines.append("")

                content = msg.get("message", {}).get("content", [])
                if isinstance(content, str):
                    lines.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                lines.append(block.get("text", ""))
                                lines.append("")
                            elif block.get("type") == "tool_use":
                                name = block.get("name", "unknown")
                                inp = block.get("input", {})
                                lines.append(f"**Tool: `{name}`**")
                                # Render key input params concisely
                                if isinstance(inp, dict):
                                    for k, v in inp.items():
                                        v_str = str(v)
                                        if len(v_str) > 500:
                                            v_str = v_str[:500] + "..."
                                        lines.append(f"- `{k}`: {v_str}")
                                lines.append("")
                lines.append("---")
                lines.append("")

    return "\n".join(lines)


def _fence(content: str, lang: str = "") -> str:
    """Wrap content in a fenced code block, escaping inner triple backticks."""
    safe = content.replace("```", "~~~")
    return f"```{lang}\n{safe}\n```"


def _render_tool_use_unabridged(block: dict) -> str:
    """Render a single tool_use block with full inputs for audit trail."""
    name = block.get("name", "unknown")
    tid = block.get("id", "?")
    inp = block.get("input", {})

    parts = [f"### Tool: {name}", "", f"**ID:** `{tid[:16]}...`"]

    if name in ("Read", "read_file"):
        parts.append(f"**File:** `{inp.get('file_path', inp.get('path', '?'))}`")
        if inp.get("offset"):
            parts.append(f"**Offset:** {inp['offset']}")
        if inp.get("limit"):
            parts.append(f"**Limit:** {inp['limit']}")
    elif name == "Edit":
        parts.append(f"**File:** `{inp.get('file_path', '?')}`")
        old = inp.get("old_string", "")
        new = inp.get("new_string", "")
        parts.append(f"**old_string:**\n{_fence(old)}")
        parts.append(f"**new_string:**\n{_fence(new)}")
    elif name in ("Write", "write_file"):
        parts.append(f"**File:** `{inp.get('file_path', inp.get('path', '?'))}`")
        content = inp.get("content", "")
        parts.append(f"**Content ({len(content)} chars):**\n{_fence(content)}")
    elif name == "Bash":
        cmd = inp.get("command", "?")
        desc = inp.get("description", "")
        if desc:
            parts.append(f"**Description:** {desc}")
        parts.append(f"**Command:**\n{_fence(cmd, 'bash')}")
    elif name == "Glob":
        parts.append(f"**Pattern:** `{inp.get('pattern', '?')}`")
        if inp.get("path"):
            parts.append(f"**Path:** `{inp['path']}`")
    elif name == "Grep":
        parts.append(f"**Pattern:** `{inp.get('pattern', '?')}`")
        if inp.get("path"):
            parts.append(f"**Path:** `{inp['path']}`")
        if inp.get("output_mode"):
            parts.append(f"**Mode:** {inp['output_mode']}")
    elif name == "ToolSearch":
        parts.append(f"**Query:** `{inp.get('query', '?')}`")
    elif name == "Agent":
        parts.append(f"**Prompt:** {str(inp.get('prompt', ''))[:500]}")
    else:
        parts.append(f"**Input:**\n{_fence(json.dumps(inp, indent=2))}")

    return "\n\n".join(parts)


_SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)

TOOL_RESULT_CAP = 8000


def render_transcript_unabridged(jsonl_path: Path) -> str:
    """Render a full unabridged session transcript as an audit trail.

    Includes thinking blocks, full tool inputs (Write/Edit content),
    and tool results. System reminders are stripped from human entries.
    """
    meta = parse_session(jsonl_path)
    if not meta:
        return ""

    lines: list[str] = []
    duration = f"~{meta.duration_minutes} min" if meta.duration_minutes else "unknown"

    lines.append(f"# Full Transcript (Unabridged): {meta.date_str}")
    lines.append("")
    lines.append(f"**Session ID:** `{meta.session_id}`")
    lines.append(f"**Slug:** `{meta.slug}`")
    lines.append(f"**Duration:** {duration}")
    lines.append(f"**Working directory:** `{meta.cwd}`")
    lines.append(f"**Branch:** `{meta.git_branch}`")
    lines.append(f"**Messages:** {meta.message_count} ({meta.human_messages} human, {meta.assistant_messages} assistant)")
    lines.append("")
    lines.append("> This is the unabridged audit trail. Thinking blocks, tool inputs,")
    lines.append("> tool outputs, and all generated code are included verbatim.")
    lines.append("> Render command: `organvm session transcript {meta.session_id[:8]} --unabridged`")
    lines.append("")
    lines.append("---")
    lines.append("")

    msg_num = 0
    with jsonl_path.open(encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            etype = entry.get("type", "")
            ts_str = entry.get("timestamp", "")
            ts_short = ts_str[11:19] if len(ts_str) >= 19 else ""

            if etype == "system":
                msg_num += 1
                lines.append(f"## [{msg_num}] System — {ts_short}")
                lines.append("")
                msg = entry.get("message", {})
                content_parts = msg.get("content", [])
                if isinstance(content_parts, str):
                    lines.append(content_parts.strip())
                elif isinstance(content_parts, list):
                    for part in content_parts:
                        if isinstance(part, dict) and part.get("type") == "text":
                            lines.append(part.get("text", "").strip())
                lines.append("")
                lines.append("---")
                lines.append("")

            elif etype == "user":
                msg = entry.get("message", {})
                content_parts = msg.get("content", "")

                text_pieces: list[str] = []
                if isinstance(content_parts, str):
                    text_pieces.append(content_parts)
                elif isinstance(content_parts, list):
                    for part in content_parts:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_pieces.append(part.get("text", ""))
                        elif isinstance(part, dict) and part.get("type") == "tool_result":
                            tid = part.get("tool_use_id", "?")
                            result_content = part.get("content", "")
                            if isinstance(result_content, list):
                                result_texts = []
                                for rc in result_content:
                                    if isinstance(rc, dict) and rc.get("type") == "text":
                                        result_texts.append(rc.get("text", ""))
                                result_content = "\n".join(result_texts)
                            if isinstance(result_content, str) and result_content.strip():
                                capped = result_content[:TOOL_RESULT_CAP]
                                if len(result_content) > TOOL_RESULT_CAP:
                                    capped += f"\n[TRUNCATED at {TOOL_RESULT_CAP} chars]"
                                text_pieces.append(
                                    f"**Tool Result** (`{tid[:12]}...`):\n{_fence(capped)}",
                                )

                text = "\n\n".join(text_pieces)
                # Strip system reminders
                text = _SYSTEM_REMINDER_RE.sub("", text).strip()
                if not text:
                    continue

                msg_num += 1
                lines.append(f"## [{msg_num}] Human — {ts_short}")
                lines.append("")
                lines.append(text)
                lines.append("")
                lines.append("---")
                lines.append("")

            elif etype == "assistant":
                msg = entry.get("message", {})
                content_parts = msg.get("content", [])
                sections: list[str] = []
                has_content = False

                if isinstance(content_parts, list):
                    for part in content_parts:
                        if not isinstance(part, dict):
                            continue
                        ptype = part.get("type")

                        if ptype == "thinking":
                            thinking = part.get("thinking", "").strip()
                            if thinking:
                                has_content = True
                                sections.append(f"### Thinking\n\n{_fence(thinking)}")

                        elif ptype == "text":
                            text = part.get("text", "").strip()
                            if text:
                                has_content = True
                                sections.append(text)

                        elif ptype == "tool_use":
                            has_content = True
                            sections.append(_render_tool_use_unabridged(part))

                elif isinstance(content_parts, str):
                    text = content_parts.strip()
                    if text:
                        has_content = True
                        sections.append(text)

                if not has_content:
                    continue

                msg_num += 1
                lines.append(f"## [{msg_num}] Assistant — {ts_short}")
                lines.append("")
                lines.append("\n\n".join(sections))
                lines.append("")
                lines.append("---")
                lines.append("")

    return "\n".join(lines)


# ── Gemini rendering ───────────────────────────────────────────────


def parse_gemini_session(json_path: Path) -> SessionMeta | None:
    """Parse a Gemini CLI session JSON into SessionMeta."""
    try:
        with json_path.open(encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    messages = data.get("messages", [])
    if not messages:
        return None

    session_id = data.get("sessionId", json_path.stem)
    started = _parse_iso_ts(data.get("startTime"))
    ended = _parse_iso_ts(data.get("lastUpdated"))

    human_count = sum(1 for m in messages if m.get("type") == "user")
    agent_count = sum(1 for m in messages if m.get("type") == "gemini")

    tools: dict[str, int] = {}
    for m in messages:
        for tc in m.get("toolCalls", []):
            name = tc.get("name", "unknown")
            tools[name] = tools.get(name, 0) + 1

    first_human = ""
    for m in messages:
        if m.get("type") == "user":
            content = m.get("content", "")
            if isinstance(content, str):
                first_human = content[:300]
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("text"):
                        first_human = part["text"][:300]
                        break
            if first_human:
                break

    # Gemini doesn't store cwd in the session — use parent dir name
    project_slug = json_path.parent.parent.name if json_path.parent.name == "chats" else json_path.parent.name

    return SessionMeta(
        session_id=session_id,
        file_path=json_path,
        slug=project_slug,
        cwd="",  # Gemini doesn't store cwd
        git_branch="",  # Not available
        started=started,
        ended=ended,
        message_count=human_count + agent_count,
        human_messages=human_count,
        assistant_messages=agent_count,
        tools_used=tools,
        first_human_message=first_human,
        project_dir=project_slug,
    )


def render_gemini_transcript(json_path: Path, unabridged: bool = False) -> str:
    """Render a Gemini session as readable markdown."""
    try:
        with json_path.open(encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ""

    messages = data.get("messages", [])
    if not messages:
        return ""

    session_id = data.get("sessionId", json_path.stem)
    started = data.get("startTime", "")
    ended = data.get("lastUpdated", "")
    project_slug = json_path.parent.parent.name if json_path.parent.name == "chats" else json_path.parent.name

    title = "Full Transcript (Unabridged)" if unabridged else "Session Transcript"
    lines = [
        f"# {title}: Gemini — {project_slug}",
        "",
        "**Agent:** Gemini CLI",
        f"**Session ID:** `{session_id}`",
        f"**Project:** `{project_slug}`",
        f"**Started:** {started}",
        f"**Last updated:** {ended}",
        f"**Messages:** {len(messages)}",
        "",
        "---",
        "",
    ]

    msg_num = 0
    for msg in messages:
        mtype = msg.get("type", "")
        ts = msg.get("timestamp", "")
        ts_short = ts[11:19] if len(ts) >= 19 else ""

        if mtype == "info":
            msg_num += 1
            lines.append(f"## [{msg_num}] Info — {ts_short}")
            lines.append("")
            lines.append(msg.get("content", ""))
            lines.append("")
            lines.append("---")
            lines.append("")

        elif mtype == "user":
            msg_num += 1
            lines.append(f"## [{msg_num}] Human — {ts_short}")
            lines.append("")
            content = msg.get("content", "")
            if isinstance(content, str):
                lines.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("text"):
                        lines.append(part["text"])
            lines.append("")
            lines.append("---")
            lines.append("")

        elif mtype == "gemini":
            msg_num += 1
            lines.append(f"## [{msg_num}] Gemini — {ts_short}")
            lines.append("")

            # Thinking (thoughts)
            thoughts = msg.get("thoughts", [])
            if unabridged and thoughts and isinstance(thoughts, list):
                lines.append("### Thinking")
                lines.append("")
                for thought in thoughts:
                    if isinstance(thought, dict):
                        subject = thought.get("subject", "")
                        desc = thought.get("description", "")
                        lines.append(f"**{subject}:** {desc}")
                        lines.append("")

            # Main content
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                lines.append(content)
                lines.append("")
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("text"):
                        lines.append(part["text"])
                        lines.append("")

            # Display content (sometimes separate)
            display = msg.get("displayContent", "")
            if display and display != content:
                lines.append(display)
                lines.append("")

            # Tool calls
            tool_calls = msg.get("toolCalls", [])
            if tool_calls:
                for tc in tool_calls:
                    name = tc.get("name", "?")
                    args = tc.get("args", {})
                    lines.append(f"### Tool: {name}")
                    lines.append("")

                    if unabridged:
                        lines.append(f"**Args:**\n{_fence(json.dumps(args, indent=2))}")
                        lines.append("")
                        # Tool results are inline in Gemini
                        result = tc.get("result", [])
                        if result:
                            for r in result:
                                if isinstance(r, dict):
                                    fr = r.get("functionResponse", {})
                                    output = fr.get("response", {}).get("output", "")
                                    if output:
                                        capped = str(output)[:TOOL_RESULT_CAP]
                                        if len(str(output)) > TOOL_RESULT_CAP:
                                            capped += f"\n[TRUNCATED at {TOOL_RESULT_CAP} chars]"
                                        lines.append(f"**Result:**\n{_fence(capped)}")
                                        lines.append("")
                    else:
                        # Summary only
                        args_summary = ", ".join(f"{k}={str(v)[:80]}" for k, v in args.items())
                        lines.append(f"Args: {args_summary}")
                        lines.append("")

            # Token usage
            tokens = msg.get("tokens")
            if unabridged and tokens and isinstance(tokens, dict):
                parts = [f"{k}={v}" for k, v in tokens.items() if v]
                if parts:
                    lines.append(f"*Tokens: {', '.join(parts)}*")
                    lines.append("")

            lines.append("---")
            lines.append("")

    return "\n".join(lines)


def render_gemini_prompts(json_path: Path) -> str:
    """Extract prompts from a Gemini session."""
    meta = parse_gemini_session(json_path)
    if not meta:
        return ""

    try:
        with json_path.open(encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ""

    messages = data.get("messages", [])
    lines: list[str] = [
        f"# Session Prompts: Gemini — {meta.project_dir}",
        "",
        "**Agent:** Gemini CLI",
        f"**Session ID:** `{meta.session_id}`",
        f"**Duration:** ~{meta.duration_minutes} min" if meta.duration_minutes else "",
        "",
        "---",
        "",
    ]

    prompt_num = 0
    last_ts: datetime | None = None
    pending_actions: list[str] = []
    prompt_texts: list[str] = []

    for msg in messages:
        mtype = msg.get("type", "")

        if mtype == "gemini":
            for tc in msg.get("toolCalls", []):
                pending_actions.append(f"{tc.get('name', '?')}")

        elif mtype == "user":
            content = msg.get("content", "")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "\n".join(
                    p.get("text", "") for p in content if isinstance(p, dict) and p.get("text")
                )

            if not text or len(text.strip()) < 5:
                continue

            if pending_actions and prompt_num > 0:
                lines.append("**Actions taken:**")
                for a in pending_actions:
                    lines.append(f"- {a}")
                lines.append("")
                lines.append("---")
                lines.append("")
            pending_actions = []

            prompt_num += 1
            ts_str = msg.get("timestamp", "")
            ts_short = ts_str[:19].replace("T", " ") if ts_str else ""
            elapsed = ""
            ts = _parse_iso_ts(ts_str)
            if ts and last_ts:
                mins = int((ts - last_ts).total_seconds() / 60)
                if mins > 0:
                    elapsed = f" (+{mins}m)"
            if ts:
                last_ts = ts

            lines.append(f"### P{prompt_num} — {ts_short}{elapsed}")
            lines.append("")
            lines.append(text)
            lines.append("")
            prompt_texts.append(text)

    # Final actions
    if pending_actions:
        lines.append("**Actions taken:**")
        for a in pending_actions:
            lines.append(f"- {a}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Prompt Summary")
    lines.append("")
    lines.append(f"**Total prompts:** {prompt_num}")
    lines.append("")

    return "\n".join(lines)


# ── Codex rendering ───────────────────────────────────────────────


def parse_codex_session(jsonl_path: Path) -> SessionMeta | None:
    """Parse a Codex rollout JSONL into SessionMeta."""
    session_id = cwd = ""
    timestamps: list[datetime] = []
    human_count = assistant_count = 0
    tools: dict[str, int] = {}
    first_human = ""

    try:
        with jsonl_path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts_str = entry.get("timestamp")
                if ts_str:
                    ts = _parse_iso_ts(ts_str)
                    if ts:
                        timestamps.append(ts)

                etype = entry.get("type", "")

                if etype == "session_meta":
                    payload = entry.get("payload", {})
                    session_id = payload.get("id", jsonl_path.stem)
                    cwd = payload.get("cwd", "")

                elif etype == "response_item":
                    payload = entry.get("payload", {})
                    role = payload.get("role", "")
                    ptype = payload.get("type", "")

                    if role == "user" and ptype == "message":
                        human_count += 1
                        if not first_human:
                            content = payload.get("content", [])
                            if isinstance(content, list):
                                for c in content:
                                    if isinstance(c, dict) and c.get("type") == "input_text":
                                        text = c.get("text", "")
                                        if text and len(text) > 20:
                                            first_human = text[:300]
                                            break
                    elif role == "assistant" and ptype == "message":
                        assistant_count += 1
                    elif ptype == "function_call":
                        name = payload.get("name", "unknown")
                        tools[name] = tools.get(name, 0) + 1
    except OSError:
        return None

    if not timestamps:
        return None

    return SessionMeta(
        session_id=session_id or jsonl_path.stem,
        file_path=jsonl_path,
        slug="",
        cwd=cwd,
        git_branch="",
        started=min(timestamps),
        ended=max(timestamps),
        message_count=human_count + assistant_count,
        human_messages=human_count,
        assistant_messages=assistant_count,
        tools_used=tools,
        first_human_message=first_human,
        project_dir=cwd or jsonl_path.parent.name,
    )


def render_codex_transcript(jsonl_path: Path, unabridged: bool = False) -> str:
    """Render a Codex session as readable markdown."""
    meta = parse_codex_session(jsonl_path)
    if not meta:
        return ""

    title = "Full Transcript (Unabridged)" if unabridged else "Session Transcript"
    lines = [
        f"# {title}: Codex — {meta.cwd or meta.project_dir}",
        "",
        "**Agent:** Codex (OpenAI)",
        f"**Session ID:** `{meta.session_id}`",
        f"**Working directory:** `{meta.cwd}`",
        f"**Messages:** {meta.message_count} ({meta.human_messages} human, {meta.assistant_messages} assistant)",
        "",
        "---",
        "",
    ]

    msg_num = 0
    with jsonl_path.open(encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            etype = entry.get("type", "")
            ts_str = entry.get("timestamp", "")
            ts_short = ts_str[11:19] if len(ts_str) >= 19 else ""

            if etype == "response_item":
                payload = entry.get("payload", {})
                role = payload.get("role", "")
                ptype = payload.get("type", "")

                if role == "user" and ptype == "message":
                    content = payload.get("content", [])
                    text_parts = []
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "input_text":
                                text_parts.append(c.get("text", ""))
                    text = "\n".join(text_parts).strip()
                    if not text:
                        continue
                    msg_num += 1
                    lines.append(f"## [{msg_num}] Human — {ts_short}")
                    lines.append("")
                    lines.append(text)
                    lines.append("")
                    lines.append("---")
                    lines.append("")

                elif role == "assistant" and ptype == "message":
                    content = payload.get("content", [])
                    text_parts = []
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "output_text":
                                text_parts.append(c.get("text", ""))
                    text = "\n".join(text_parts).strip()
                    if not text:
                        continue
                    msg_num += 1
                    lines.append(f"## [{msg_num}] Codex — {ts_short}")
                    lines.append("")
                    lines.append(text)
                    lines.append("")
                    lines.append("---")
                    lines.append("")

                elif ptype == "function_call":
                    msg_num += 1
                    name = payload.get("name", "?")
                    args_str = payload.get("arguments", "{}")
                    call_id = payload.get("call_id", "?")

                    lines.append(f"## [{msg_num}] Tool Call — {ts_short}")
                    lines.append("")
                    lines.append(f"### Tool: {name}")
                    lines.append(f"**Call ID:** `{call_id[:16]}...`")
                    lines.append("")
                    if unabridged:
                        try:
                            args = json.loads(args_str) if isinstance(args_str, str) else args_str
                            lines.append(f"**Args:**\n{_fence(json.dumps(args, indent=2))}")
                        except (json.JSONDecodeError, TypeError):
                            lines.append(f"**Args:** `{str(args_str)[:500]}`")
                    else:
                        lines.append(f"**Args:** `{str(args_str)[:200]}`")
                    lines.append("")
                    lines.append("---")
                    lines.append("")

                elif ptype == "function_call_output":
                    if unabridged:
                        msg_num += 1
                        output = payload.get("output", "")
                        call_id = payload.get("call_id", "?")
                        lines.append(f"## [{msg_num}] Tool Result — {ts_short}")
                        lines.append("")
                        lines.append(f"**Call ID:** `{call_id[:16]}...`")
                        capped = str(output)[:TOOL_RESULT_CAP]
                        if len(str(output)) > TOOL_RESULT_CAP:
                            capped += f"\n[TRUNCATED at {TOOL_RESULT_CAP} chars]"
                        lines.append(f"\n{_fence(capped)}")
                        lines.append("")
                        lines.append("---")
                        lines.append("")

                elif ptype == "reasoning":
                    if unabridged:
                        msg_num += 1
                        lines.append(f"## [{msg_num}] Reasoning — {ts_short}")
                        lines.append("")
                        summary = payload.get("summary", [])
                        if summary:
                            for s in summary:
                                if isinstance(s, dict):
                                    lines.append(f"- {s.get('text', str(s))}")
                                else:
                                    lines.append(f"- {s}")
                        else:
                            lines.append("*Reasoning content encrypted — summary not available*")
                        lines.append("")
                        lines.append("---")
                        lines.append("")

    return "\n".join(lines)


# ── Dispatch by agent ──────────────────────────────────────────────


def detect_agent(file_path: Path) -> str:
    """Detect which agent produced a session file."""
    path_str = str(file_path)
    if "/.claude/" in path_str:
        return "claude"
    if "/.gemini/" in path_str:
        return "gemini"
    if "/.codex/" in path_str:
        return "codex"
    # Fallback: check file format
    if file_path.suffix == ".json":
        return "gemini"
    return "claude"


def parse_any_session(file_path: Path) -> SessionMeta | None:
    """Parse a session file from any supported agent."""
    agent = detect_agent(file_path)
    if agent == "gemini":
        return parse_gemini_session(file_path)
    if agent == "codex":
        return parse_codex_session(file_path)
    return parse_session(file_path)


def render_any_transcript(file_path: Path, unabridged: bool = False) -> str:
    """Render a transcript from any supported agent."""
    agent = detect_agent(file_path)
    if agent == "gemini":
        return render_gemini_transcript(file_path, unabridged=unabridged)
    if agent == "codex":
        return render_codex_transcript(file_path, unabridged=unabridged)
    if unabridged:
        return render_transcript_unabridged(file_path)
    return render_transcript(file_path)


def render_any_prompts(file_path: Path) -> str:
    """Render prompts extract from any supported agent."""
    agent = detect_agent(file_path)
    if agent == "gemini":
        return render_gemini_prompts(file_path)
    # Codex prompts use the same structure as the generic one
    # but we need a codex-specific parser — for now fall through to Claude
    return render_prompts(file_path)


def _parse_iso_ts(ts_str: str | None) -> datetime | None:
    """Parse an ISO timestamp, tolerant of Z suffix."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def find_session(session_id: str) -> Path | None:
    """Find a session by full or partial ID across all agents."""
    from organvm_engine.session.agents import (
        CODEX_ARCHIVED_DIR,
        CODEX_SESSIONS_DIR,
        GEMINI_TMP_DIR,
    )

    candidates: list[Path] = []

    # Claude
    if CLAUDE_PROJECTS_DIR.exists():
        for jsonl in CLAUDE_PROJECTS_DIR.rglob("*.jsonl"):
            if jsonl.stem == session_id or jsonl.stem.startswith(session_id):
                candidates.append(jsonl)

    # Gemini — session ID is in the JSON, but filename contains a short hash
    if GEMINI_TMP_DIR.exists():
        for json_file in GEMINI_TMP_DIR.rglob("session-*.json"):
            if session_id in json_file.stem:
                candidates.append(json_file)

    # Codex — session ID is in the JSONL payload, filename contains UUID
    for codex_dir in (CODEX_SESSIONS_DIR, CODEX_ARCHIVED_DIR):
        if codex_dir.exists():
            for jsonl in codex_dir.rglob("rollout-*.jsonl"):
                if session_id in jsonl.stem:
                    candidates.append(jsonl)

    # Deduplicate exact matches
    exact = [c for c in candidates if c.stem == session_id]
    if len(exact) == 1:
        return exact[0]

    if len(candidates) == 1:
        return candidates[0]

    return None  # Not found or ambiguous


def extract_human_texts(jsonl_path: Path) -> list[str]:
    """Extract clean human prompt texts from a Claude Code session JSONL.

    Uses _extract_human_text() and applies the same filtering as render_prompts()
    (skips tool_result-only messages and messages shorter than 5 chars).

    Returns list of human message strings in chronological order.
    """
    texts: list[str] = []

    try:
        fh = jsonl_path.open(encoding="utf-8", errors="replace")
    except OSError:
        return texts

    with fh as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                msg = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            if msg.get("type") != "user":
                continue

            text = _extract_human_text(msg)
            if not text or len(text.strip()) < 5:
                continue

            # Skip tool_result-only messages
            msg_content = msg.get("message", {}).get("content", "")
            if isinstance(msg_content, list):
                has_text = any(
                    isinstance(p, dict)
                    and p.get("type") == "text"
                    and len(p.get("text", "").strip()) > 5
                    for p in msg_content
                )
                has_tool_result = any(
                    isinstance(p, dict) and p.get("type") == "tool_result"
                    for p in msg_content
                )
                if has_tool_result and not has_text:
                    continue

            texts.append(text)

    return texts
