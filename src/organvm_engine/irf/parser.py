"""IRF parser — parse INST-INDEX-RERUM-FACIENDARUM.md into typed items.

The Index Rerum Faciendarum is a Markdown governance document with pipe-delimited
tables. Active items use a 6-column format; completed items use a 4- or 5-column format.
Section headers (## ...) determine item status:
  - Under '## Completed'  → status = "completed"
  - Under '## Blocked'    → status = "blocked"
  - Under '## Archived'   → status = "archived"
  - Elsewhere             → status = "open"
DONE-NNN ledger rows are treated as completed wherever they appear, because
recent closeout ledgers live under the Statistics section.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class IRFItem:
    """A single item parsed from the Index Rerum Faciendarum."""

    id: str                  # e.g. IRF-SYS-001 or DONE-003
    priority: str            # P0 / P1 / P2 / P3 (empty string for completed items)
    domain: str              # extracted from ID: IRF-SYS-001 → SYS, DONE-003 → DONE
    action: str              # human-readable description
    owner: str               # Agent / Human / Agent+Human
    source: str              # session IDs, want-list refs, etc.
    blocker: str             # None / free text
    status: str              # open / completed / blocked / archived
    section: str             # the ## header text under which the row appears


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches a ## section header (## or ###, not ####)
_SECTION_RE = re.compile(r"^(#{2,3})\s+(.+)$")

# Matches a pipe-delimited table row with at least 4 non-separator cells.
# We accept rows like:  | cell | cell | cell | cell |
# A trailing pipe is optional — hand-appended rows sometimes lack it.
_ROW_RE = re.compile(r"^\|(.+?)\|?$")

# A separator row contains only hyphens, pipes, colons, and spaces.
_SEPARATOR_RE = re.compile(r"^[\|\-\:\s]+$")

# Canonical item-ID shape. Letter suffixes (IRF-VAC-001a, DONE-145b) are the
# sub-item convention used by session "Discovered Items" blocks — they are
# first-class IDs, not markup noise (was the bulk of the IRF-SYS-182 blind spot).
_ID_RE = re.compile(r"^(IRF-(?:[A-Z]+-)+\d+[a-z]?|DONE-\d+[a-z]?)$")

# A DONE-ledger reference appearing in the *priority* column marks a row that
# was completed in place inside an active table (e.g. `| IRF-SKL-004 | DONE-525 | …`).
_DONE_REF_RE = re.compile(r"^DONE-\d+[a-z]?$")


def _cells(raw_row: str) -> list[str]:
    """Split a raw markdown table row into stripped cell strings."""
    return [c.strip() for c in raw_row.strip("|").split("|")]


def _strip_cell_markup(value: str) -> str:
    """Strip lightweight Markdown wrappers from identifier-like cells."""
    cleaned = value.strip()
    for marker in ("**", "~~", "`"):
        cleaned = cleaned.replace(marker, "")
    return cleaned.strip()


def _clean_priority(value: str) -> str:
    """Return the first P0-P4 token from a priority cell, ignoring markup."""
    cleaned = _strip_cell_markup(value)
    match = re.search(r"\bP[0-4]\b", cleaned)
    return match.group(0) if match else cleaned


def _section_status(section: str) -> str:
    """Map a section header text to a status string."""
    lower = section.lower()
    if "completed" in lower:
        return "completed"
    if "blocked" in lower:
        return "blocked"
    if "archived" in lower:
        return "archived"
    return "open"


def _extract_domain(item_id: str) -> str:
    """Extract domain code from an IRF item ID.

    Examples:
        IRF-SYS-001 → SYS
        IRF-OBJ-007 → OBJ
        DONE-003    → DONE
    """
    parts = item_id.split("-")
    if len(parts) >= 3 and parts[0] == "IRF":
        return parts[1]
    if len(parts) >= 2 and parts[0] == "DONE":
        return "DONE"
    # Fallback: return second segment or entire ID
    return parts[1] if len(parts) > 1 else item_id


def _parse_active_row(cells: list[str], status: str, section: str) -> IRFItem | None:
    """Parse an active item row.

    Expected columns: ID | Priority | Action | Owner | Source | Blocker.
    Hand-appended tail rows sometimes stop after the Action cell; owner,
    source, and blocker are optional for parse/stat purposes.
    """
    if len(cells) < 3:
        return None
    raw_item_id = cells[0]
    raw_priority = cells[1]
    action = cells[2]
    owner = cells[3] if len(cells) > 3 else ""
    source = cells[4] if len(cells) > 4 else ""
    blocker = cells[5] if len(cells) > 5 else ""
    item_id = _strip_cell_markup(raw_item_id)
    priority = _clean_priority(raw_priority)
    # ID must look like IRF-XXX-NNN[a] or DONE-NNN[a]
    if not _ID_RE.match(item_id):
        return None
    row_status = status
    if _DONE_REF_RE.match(priority):
        # Completed in place inside an active table: the priority column holds
        # the DONE-ledger reference instead of a P-level.
        row_status = "completed"
        source = f"{priority}; {source}" if source else priority
        priority = ""
    elif not re.match(r"^P[0-4]$", priority):
        # Priority must be P0–P4 (active rows) or a DONE-ref (completed in place)
        return None
    if "~~" in raw_item_id or "~~" in raw_priority or _strip_cell_markup(blocker).lower().startswith("completed"):
        row_status = "completed"

    return IRFItem(
        id=item_id,
        priority=priority,
        domain=_extract_domain(item_id),
        action=action,
        owner=owner,
        source=source,
        blocker=blocker,
        status=row_status,
        section=section,
    )


def _parse_completed_row(cells: list[str], section: str) -> IRFItem | None:
    """Parse a completed/ledger item row.

    Expected columns: ID | What | Session | Date — but short-form rows
    (ID | What | Date, or even ID | What) appear in hand-appended ledgers,
    so anything with an ID and at least one more cell is accepted.
    """
    if len(cells) < 2:
        return None
    item_id = _strip_cell_markup(cells[0])
    if len(cells) >= 5 and re.match(r"^[A-Z]{2,5}$", _strip_cell_markup(cells[1])):
        what, session = cells[2], cells[3]
    elif len(cells) >= 3:
        what, session = cells[1], cells[2]
    else:
        what, session = cells[1], ""
    if not _ID_RE.match(item_id):
        return None
    return IRFItem(
        id=item_id,
        priority="",
        domain=_extract_domain(item_id),
        action=what,
        owner="",
        source=session,
        blocker="",
        status="completed",
        section=section,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_irf(path: Path) -> list[IRFItem]:
    """Parse an IRF Markdown file into a list of IRFItem objects.

    Returns an empty list if the file does not exist.
    """
    items, _skipped = parse_irf_diagnostics(path)
    return items


def parse_irf_diagnostics(path: Path) -> tuple[list[IRFItem], list[tuple[int, str]]]:
    """Parse an IRF Markdown file, also reporting ID-bearing rows that were dropped.

    Returns ``(items, skipped)`` where ``skipped`` is a list of
    ``(line_number, line_text)`` for table rows whose first cell carries an
    IRF/DONE id but which produced no item. A non-empty ``skipped`` means the
    parse is NOT authoritative — callers gating on completeness (stats
    regeneration, closeout) must refuse until it is empty (IRF-OPS-088).
    """
    if not path.exists():
        return [], []

    items: list[IRFItem] = []
    skipped: list[tuple[int, str]] = []
    current_section = "Preamble"
    current_status = "open"
    parent_status = "open"

    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.rstrip()

        # Detect ## or ### section headers
        section_match = _SECTION_RE.match(line)
        if section_match:
            level = len(section_match.group(1))
            current_section = section_match.group(2).strip()
            section_status = _section_status(current_section)
            if level == 2:
                parent_status = section_status
                current_status = section_status
            elif section_status == "open" and parent_status in {"completed", "blocked", "archived"}:
                current_status = parent_status
            else:
                current_status = section_status
            continue

        # Detect table rows
        row_match = _ROW_RE.match(line)
        if not row_match:
            continue

        # Skip separator rows
        if _SEPARATOR_RE.match(line):
            continue

        cells = _cells(line)

        # Skip header rows (first cell is "ID")
        if cells and cells[0].lower() == "id":
            continue

        first_cell = _strip_cell_markup(cells[0]) if cells else ""

        # Try to parse as active (6+ cols) or completed ledger format,
        # falling back to the other shape — section status alone does not
        # determine row shape (4-cell ledger rows appear in open/blocked
        # sections, 6-cell rows appear under Completed).
        if current_status == "completed" or _DONE_REF_RE.match(first_cell):
            item = _parse_completed_row(cells, current_section)
            if item is None:
                item = _parse_active_row(cells, current_status, current_section)
        else:
            item = _parse_active_row(cells, current_status, current_section)
            if item is None:
                item = _parse_completed_row(cells, current_section)
                # A short ledger-shaped row outside a Completed section:
                # completed only if it is a DONE row or struck through;
                # otherwise inherit the section status.
                if (
                    item is not None
                    and current_status != "completed"
                    and not (_DONE_REF_RE.match(item.id) or "~~" in cells[0])
                ):
                    item = dataclasses.replace(item, status=current_status)

        if item is not None:
            items.append(item)
        elif _ID_RE.match(first_cell):
            skipped.append((lineno, line))

    return items, skipped


def irf_stats(items: list[IRFItem]) -> dict:
    """Compute summary statistics for a list of IRFItem objects.

    Returns a dict with keys:
        total, open, completed, blocked, archived, completion_rate,
        by_priority (dict P0–P3 → count),
        by_domain  (dict domain → count)
    """
    total = len(items)
    open_count = sum(1 for i in items if i.status == "open")
    completed = sum(1 for i in items if i.status == "completed")
    blocked = sum(1 for i in items if i.status == "blocked")
    archived = sum(1 for i in items if i.status == "archived")

    completion_rate = round(completed / total, 4) if total else 0.0

    by_priority: dict[str, int] = {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "P4": 0}
    by_domain: dict[str, int] = {}

    for item in items:
        if item.priority in by_priority:
            by_priority[item.priority] += 1
        domain = item.domain
        by_domain[domain] = by_domain.get(domain, 0) + 1

    return {
        "total": total,
        "open": open_count,
        "completed": completed,
        "blocked": blocked,
        "archived": archived,
        "completion_rate": completion_rate,
        "by_priority": by_priority,
        "by_domain": by_domain,
    }
