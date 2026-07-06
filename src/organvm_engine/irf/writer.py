"""IRF writer — tooled write-backs for INST-INDEX-RERUM-FACIENDARUM.md (IRF-SYS-251).

The IRF protocol requires on-close updates (add new rows, complete items, refresh
the Statistics block), but hand-editing a ~1MB markdown file is the manual-copy
surface that produces drift (IRF-SYS-250, IRF-OPS-091). These functions route
write-backs through tooling instead.

Invariants every mutation honors:

- **In-place writes only.** The registry file is hardlinked across two checkout
  paths (IRF-SYS-168); a tempfile + rename would silently sever the link, so we
  truncate-and-write the existing inode via ``Path.write_text``.
- **Additive idiom.** ``complete`` strikes through the active row in place AND
  appends a ledger row to ``## Completed`` — both idioms coexist in the file;
  nothing is deleted.
- **Parse-complete gate.** ``regenerate_stats_block`` refuses while
  ``parse_irf_diagnostics`` reports unparsed ID rows (IRF-OPS-088): stats derived
  from an incomplete parse would re-freeze drift into the document.
- **Dry-run by default** at the CLI layer; callers pass the full new text back
  through :func:`write_in_place` only when ``--write`` is given.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from organvm_engine.irf.parser import (
    IRFItem,
    irf_stats,
    parse_irf,
    parse_irf_diagnostics,
)

_ID_LINE_RE = re.compile(
    r"^\s*\|?\s*(?:\*\*|~~|`)*\s*"
    r"(IRF-(?:[A-Z]+-)+\d+[a-z]?|DONE-\d+[a-z]?)\b",
)

AUTOGEN_NOTE = (
    "<!-- AUTOGEN: regenerate via `organvm irf stats --write` — do not hand-edit"
    " (derive-don't-copy, IRF-OPS-091) -->"
)


class IRFWriteError(RuntimeError):
    """A write-back could not be performed safely."""


@dataclass
class Mutation:
    """A proposed text mutation: the new full document plus a human preview."""

    new_text: str
    preview: str


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def write_in_place(path: Path, new_text: str) -> None:
    """Overwrite ``path`` preserving its inode (the file is hardlinked, IRF-SYS-168)."""
    with path.open("w", encoding="utf-8") as fh:
        fh.write(new_text)


def next_done_id(items: list[IRFItem]) -> str:
    """Allocate the next DONE-NNN id (max existing + 1, letter suffixes ignored)."""
    highest = 0
    for item in items:
        match = re.match(r"^DONE-(\d+)", item.id)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"DONE-{highest + 1:03d}"


def next_irf_id(items: list[IRFItem], domain: str) -> str:
    """Allocate the next IRF-<DOMAIN>-NNN id (max existing + 1)."""
    domain = domain.upper()
    highest = 0
    for item in items:
        match = re.match(rf"^IRF-{re.escape(domain)}-(\d+)", item.id)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"IRF-{domain}-{highest + 1:03d}"


def _find_item_line(lines: list[str], item_id: str) -> int | None:
    """Return the index of the first non-struck table row carrying ``item_id``."""
    row_re = re.compile(rf"^\|\s*(?:\*\*|`)*\s*{re.escape(item_id)}\b")
    for idx, line in enumerate(lines):
        if row_re.match(line):
            return idx
    return None


# ---------------------------------------------------------------------------
# Mutations (pure: text in, Mutation out — caller decides whether to write)
# ---------------------------------------------------------------------------

def add_item(
    path: Path,
    domain: str,
    action: str,
    priority: str = "P2",
    owner: str = "Agent",
    source: str = "",
    blocker: str = "None",
    item_id: str | None = None,
) -> Mutation:
    """Append a new 6-column open row after the last open row of ``domain``.

    Falls back to appending directly before the ``## Completed`` section when the
    domain has no existing open rows.
    """
    domain = domain.upper()
    if not re.match(r"^P[0-4]$", priority):
        raise IRFWriteError(f"priority must be P0–P4, got {priority!r}")

    items = parse_irf(path)
    if item_id is None:
        item_id = next_irf_id(items, domain)
    elif any(i.id == item_id for i in items):
        raise IRFWriteError(f"{item_id} already exists — refusing to create a duplicate id")

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    new_row = f"| {item_id} | {priority} | {action} | {owner} | {source} | {blocker} |"

    # Find the last open-section, non-struck row of this domain — completed and
    # blocked sections must not attract new open rows.
    anchor = None
    open_row_re = re.compile(
        rf"^\|\s*(?:\*\*|`)*\s*IRF-{re.escape(domain)}-\d+[a-z]?\s*(?:\*\*|`)*\s*\|",
    )
    section_re = re.compile(r"^(#{2,3})\s+(.+)$")
    section_status = "open"
    parent_section_status = "open"
    for idx, line in enumerate(lines):
        section_match = section_re.match(line)
        if section_match:
            lowered = section_match.group(2).lower()
            this_status = next(
                (s for s in ("completed", "blocked", "archived") if s in lowered), "open",
            )
            if len(section_match.group(1)) == 2:
                parent_section_status = this_status
                section_status = this_status
            else:
                section_status = (
                    parent_section_status if this_status == "open" else this_status
                )
            continue
        if section_status == "open" and open_row_re.match(line):
            anchor = idx
    if anchor is None:
        # Fall back: insert before ## Completed (or at EOF if absent).
        anchor = next(
            (i for i, ln in enumerate(lines) if ln.startswith("## Completed")),
            len(lines),
        ) - 1
        while anchor > 0 and not lines[anchor].strip():
            anchor -= 1

    lines.insert(anchor + 1, new_row)
    new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    preview = f"+ L{anchor + 2}: {new_row}"
    return Mutation(new_text=new_text, preview=preview)


def complete_item(
    path: Path,
    item_id: str,
    note: str,
    session: str,
    date: str,
    done_id: str | None = None,
) -> Mutation:
    """Complete an open item: strike through its active row and append a ledger row.

    ``date`` is YYYY-MM-DD (passed in by the CLI — the writer takes no clock).
    """
    items = parse_irf(path)
    target = next((i for i in items if i.id == item_id), None)
    if target is None:
        raise IRFWriteError(f"{item_id} not found in {path.name}")
    if target.status == "completed":
        raise IRFWriteError(f"{item_id} is already completed")

    if done_id is None:
        done_id = next_done_id(items)
    elif any(i.id == done_id for i in items):
        raise IRFWriteError(
            f"{done_id} already allocated — refusing to repeat the duplicate-DONE-id failure",
        )

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    row_idx = _find_item_line(lines, item_id)
    if row_idx is None:
        raise IRFWriteError(f"could not locate the table row for {item_id}")

    # Strike through ID + priority cells and stamp the resolution on the row.
    cells = [c.strip() for c in lines[row_idx].strip().strip("|").split("|")]
    cells[0] = f"~~{cells[0]}~~"
    if len(cells) > 1 and cells[1]:
        cells[1] = f"~~{cells[1]}~~"
    if len(cells) > 2:
        cells[2] = f"~~{cells[2]}~~ — **{done_id}** ({date}): {note}"
    struck = "| " + " | ".join(cells) + " |"
    lines[row_idx] = struck

    # Append the ledger row at the end of the last DONE-ledger table.
    ledger_row = f"| {done_id} | **{item_id} closed:** {note} | {session} | {date} |"
    ledger_idx = None
    for idx, line in enumerate(lines):
        if re.match(r"^\|\s*(?:\*\*|`)*\s*DONE-\d+", line):
            ledger_idx = idx
    if ledger_idx is None:
        raise IRFWriteError("no DONE ledger table found to append the completion row")
    lines.insert(ledger_idx + 1, ledger_row)

    new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    preview = (
        f"~ L{row_idx + 1}: {struck[:120]}\n"
        f"+ L{ledger_idx + 2}: {ledger_row[:120]}"
    )
    return Mutation(new_text=new_text, preview=preview)


def regenerate_stats_block(path: Path, date: str) -> Mutation:
    """Regenerate the ``## Statistics`` section from a complete parse.

    Refuses while the parse is incomplete (IRF-OPS-088) and refuses to replace
    any region that contains ID-bearing rows (ledgers must never be clobbered).
    """
    items, skipped = parse_irf_diagnostics(path)
    if skipped:
        listing = "\n".join(f"  L{n}: {line[:100]}" for n, line in skipped[:10])
        raise IRFWriteError(
            f"parse is incomplete — {len(skipped)} ID-bearing row(s) unparsed; "
            f"stats would re-freeze drift (IRF-OPS-088). Fix the parser first.\n{listing}",
        )

    stats = irf_stats(items)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    start = next((i for i, ln in enumerate(lines) if ln.strip() == "## Statistics"), None)
    if start is None:
        raise IRFWriteError("no `## Statistics` section found")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )

    # Safety: never clobber ledger rows that may live inside the section.
    guarded = [ln for ln in lines[start:end] if _ID_LINE_RE.match(ln)]
    if guarded:
        raise IRFWriteError(
            f"refusing to regenerate: {len(guarded)} ID-bearing row(s) inside the "
            "Statistics section would be destroyed — move them out first.",
        )

    block: list[str] = [
        "## Statistics",
        "",
        AUTOGEN_NOTE,
        "",
        f"**Last updated:** {date}",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Items | {stats['total']} |",
        f"| Open Items | {stats['open']} |",
        f"| Completed Items | {stats['completed']} |",
        f"| Blocked Items | {stats['blocked']} |",
        f"| Archived Items | {stats['archived']} |",
        f"| Completion Rate | {stats['completion_rate'] * 100:.1f}% |",
        "",
        "### Items by Priority",
        "",
        "| Priority | Count |",
        "|----------|-------|",
    ]
    block += [f"| {pri} | {count} |" for pri, count in sorted(stats["by_priority"].items())]
    block += [
        "",
        "### Items by Domain",
        "",
        "| Domain | Count |",
        "|--------|-------|",
    ]
    block += [
        f"| {domain} | {count} |"
        for domain, count in sorted(stats["by_domain"].items(), key=lambda x: (-x[1], x[0]))
    ]

    new_lines = lines[:start] + block + lines[end:]
    new_text = "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")
    preview = (
        f"regenerated ## Statistics (L{start + 1}–{end}): total={stats['total']} "
        f"open={stats['open']} completed={stats['completed']} blocked={stats['blocked']}"
    )
    return Mutation(new_text=new_text, preview=preview)
