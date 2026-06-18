"""Context sync diff/changelog — track what changes between sync runs.

Each ``organvm context sync`` run can capture a per-file unified diff of the
auto-generated section it replaces. Those diffs are accumulated into a
``SyncChange`` list, rendered for the terminal, and (on ``--write``) appended as
one entry to ``corpus_dir/data/context-sync/changelog.jsonl``. The changelog
gives an audit trail of how each context file's AUTO block has drifted over
time, run after run.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from organvm_engine.contextmd import AUTO_END, AUTO_START


@dataclass
class SyncChange:
    """A single context file's change during one sync run."""

    path: str
    action: str  # "created" | "updated" | "unchanged"
    added: int = 0
    removed: int = 0
    diff: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunChangelog:
    """The set of changes produced by one sync run."""

    timestamp: str | None = None
    dry_run: bool = False
    changes: list[SyncChange] = field(default_factory=list)

    @property
    def updated(self) -> list[SyncChange]:
        return [c for c in self.changes if c.action == "updated"]

    @property
    def created(self) -> list[SyncChange]:
        return [c for c in self.changes if c.action == "created"]

    def with_diffs(self) -> list[SyncChange]:
        """Changes that carry a non-empty diff (created or updated)."""
        return [c for c in self.changes if c.diff]

    def to_entry(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "dry_run": self.dry_run,
            "counts": {
                "created": len(self.created),
                "updated": len(self.updated),
                "total_added": sum(c.added for c in self.changes),
                "total_removed": sum(c.removed for c in self.changes),
            },
            "changes": [c.to_dict() for c in self.with_diffs()],
        }


def _extract_auto_section(content: str) -> str:
    """Return the AUTO block (inclusive of markers) from *content*, or ""."""
    start = content.find(AUTO_START)
    end = content.find(AUTO_END)
    if start == -1 or end == -1 or end < start:
        return ""
    return content[start : end + len(AUTO_END)]


def compute_change(
    file_path: Path | str,
    old_content: str | None,
    new_section: str,
    action: str,
) -> SyncChange:
    """Build a :class:`SyncChange` describing a sync edit.

    *old_content* is the full prior file content (None for a brand-new file).
    The diff compares only the AUTO block — manual content outside the markers
    is never part of the sync and so never part of the changelog.
    """
    path = str(file_path)
    if action == "created":
        new_lines = new_section.splitlines()
        diff = "\n".join(f"+{line}" for line in new_lines)
        return SyncChange(
            path=path, action="created", added=len(new_lines), removed=0, diff=diff,
        )

    if action != "updated":
        return SyncChange(path=path, action=action)

    old_section = _extract_auto_section(old_content or "")
    old_lines = old_section.splitlines()
    new_lines = new_section.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        ),
    )
    added = sum(
        1 for line in diff_lines if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1 for line in diff_lines if line.startswith("-") and not line.startswith("---")
    )
    return SyncChange(
        path=path,
        action="updated",
        added=added,
        removed=removed,
        diff="\n".join(diff_lines),
    )


def render_changes(changelog: RunChangelog, show_diff: bool = False) -> str:
    """Human-readable rendering of a run's changes."""
    diffable = changelog.with_diffs()
    if not diffable:
        return "No context sections changed since the last sync."

    lines: list[str] = []
    lines.append("Context Sync Changelog")
    lines.append("─" * 40)
    for change in diffable:
        marker = "NEW" if change.action == "created" else "MOD"
        lines.append(f"  [{marker}] {change.path}  (+{change.added} -{change.removed})")
        if show_diff and change.diff:
            for diff_line in change.diff.splitlines():
                lines.append(f"      {diff_line}")
    total_added = sum(c.added for c in changelog.changes)
    total_removed = sum(c.removed for c in changelog.changes)
    lines.append("─" * 40)
    lines.append(
        f"  {len(changelog.created)} created, {len(changelog.updated)} updated "
        f"(+{total_added} -{total_removed} lines)",
    )
    return "\n".join(lines)


def append_changelog(
    changelog: RunChangelog,
    changelog_path: Path | str | None = None,
) -> Path | None:
    """Append this run as one JSONL entry to the changelog file.

    Returns the path written, or None if there was nothing to record.
    """
    if not changelog.with_diffs():
        return None
    if changelog_path is None:
        from organvm_engine.paths import context_sync_changelog_path

        changelog_path = context_sync_changelog_path()
    changelog_path = Path(changelog_path)
    changelog_path.parent.mkdir(parents=True, exist_ok=True)
    entry = changelog.to_entry()
    with changelog_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return changelog_path


def load_changelog(changelog_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Read all recorded run entries from the changelog file."""
    if changelog_path is None:
        from organvm_engine.paths import context_sync_changelog_path

        changelog_path = context_sync_changelog_path()
    changelog_path = Path(changelog_path)
    if not changelog_path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line in changelog_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def render_changelog(entries: list[dict[str, Any]], limit: int | None = None) -> str:
    """Render recorded run history (most recent last)."""
    if not entries:
        return "No context-sync history recorded yet."
    shown = entries[-limit:] if limit else entries
    lines: list[str] = []
    lines.append("Context Sync History")
    lines.append("─" * 40)
    for entry in shown:
        ts = entry.get("timestamp") or "(no timestamp)"
        counts = entry.get("counts", {})
        dry = " [dry-run]" if entry.get("dry_run") else ""
        lines.append(
            f"  {ts}{dry}: "
            f"{counts.get('created', 0)} created, {counts.get('updated', 0)} updated "
            f"(+{counts.get('total_added', 0)} -{counts.get('total_removed', 0)})",
        )
    if limit and len(entries) > limit:
        lines.append(f"  … {len(entries) - limit} earlier run(s) not shown")
    return "\n".join(lines)
