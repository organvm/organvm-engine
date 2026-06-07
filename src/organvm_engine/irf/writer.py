"""IRF writer — functions to safely mutate the INST-INDEX-RERUM-FACIENDARUM.md document."""

from __future__ import annotations

import re
from pathlib import Path

from organvm_engine.irf.parser import _cells, _strip_cell_markup


def add_irf_item(
    path: Path,
    item_id: str,
    priority: str,
    action: str,
    owner: str,
    source: str,
    blocker: str = "None",
    section: str = "Backlog",
) -> bool:
    """Appends a new active row to the specified section.

    Returns True if successfully added, False if the section was not found.
    """
    if not path.exists():
        return False

    lines = path.read_text(encoding="utf-8").splitlines()
    target_section_regex = re.compile(rf"^(#{{2,3}})\s+{re.escape(section)}$", re.IGNORECASE)

    insert_idx = -1
    in_section = False

    for i, line in enumerate(lines):
        if target_section_regex.match(line.rstrip()):
            in_section = True
            continue

        if in_section:
            if line.startswith("## ") or line.startswith("### "):
                insert_idx = i
                break

    if in_section and insert_idx == -1:
        insert_idx = len(lines)

    if not in_section:
        return False

    # Walk backwards to find the last table row in this section
    last_row_idx = -1
    for i in range(insert_idx - 1, -1, -1):
        if lines[i].startswith("|"):
            last_row_idx = i
            break
        if lines[i].startswith("##"):
            break

    if last_row_idx != -1:
        insert_idx = last_row_idx + 1
    else:
        # If no table exists, maybe we should add headers?
        # But we assume the section already has a table. If not, just insert.
        pass

    new_row = f"| {item_id} | {priority} | {action} | {owner} | {source} | {blocker} |"
    lines.insert(insert_idx, new_row)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def complete_irf_item(path: Path, item_id: str, session: str, date: str) -> bool:
    """Moves an item to the ## Completed section and changes its format.

    Returns True if successfully moved, False if item not found or section not found.
    """
    if not path.exists():
        return False

    lines = path.read_text(encoding="utf-8").splitlines()
    item_row_idx = -1
    item_action = ""

    # 1. Find and remove the active row
    for i, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cells = _cells(line)
        if not cells:
            continue
        # Skip header rows
        if cells[0].lower() == "id":
            continue

        cell_id = _strip_cell_markup(cells[0])
        if cell_id == item_id:
            # Expecting 6 columns for an active item
            if len(cells) >= 6:
                item_row_idx = i
                item_action = cells[2]
                break
            elif len(cells) >= 4:
                # Might already be completed or a different format, but let's grab the action
                # If it's already 4 columns, action is at idx 1 or 2 depending on if it has a priority column empty
                # In active it's idx 2
                item_row_idx = i
                item_action = cells[2] if len(cells) >= 6 else cells[1]
                break

    if item_row_idx == -1:
        return False

    del lines[item_row_idx]

    # 2. Find ## Completed section
    completed_regex = re.compile(r"^(#{2,3})\s+Completed", re.IGNORECASE)
    insert_idx = -1
    in_completed = False

    for i, line in enumerate(lines):
        if completed_regex.match(line.rstrip()):
            in_completed = True
            continue

        if in_completed:
            if line.startswith("## ") or line.startswith("### "):
                insert_idx = i
                break

    if in_completed and insert_idx == -1:
        insert_idx = len(lines)

    if not in_completed:
        return False

    # Insert at the end of the completed table
    last_row_idx = -1
    for i in range(insert_idx - 1, -1, -1):
        if lines[i].startswith("|"):
            last_row_idx = i
            break
        if lines[i].startswith("##"):
            break

    if last_row_idx != -1:
        insert_idx = last_row_idx + 1

    # Bold the item ID and the action text if it's not already?
    # In the corpus, we saw:
    # | IRF-SYS-182 | **`organvm irf list` / `irf status` / `irf stats` parser blind spot...** | S-2026-06-07... | 2026-06-07 |
    # But some don't bold the action. We'll leave action as is (maybe the user bolds it, or we just copy it).
    
    new_row = f"| {item_id} | {item_action} | {session} | {date} |"
    lines.insert(insert_idx, new_row)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True
