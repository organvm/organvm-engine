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

    new_row = f"| {item_id} | {item_action} | {session} | {date} |"
    lines.insert(insert_idx, new_row)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def update_irf_stats(path: Path, stats: dict) -> bool:
    """Regenerates the ## Statistics section in the IRF file."""
    if not path.exists():
        return False

    lines = path.read_text(encoding="utf-8").splitlines()
    start_idx = -1
    end_idx = -1

    for i, line in enumerate(lines):
        if line.strip().startswith("## Statistics"):
            start_idx = i
            continue
        if start_idx != -1 and line.strip().startswith("## "):
            end_idx = i
            break

    if start_idx == -1:
        # If no statistics section, append to end
        start_idx = len(lines)
        end_idx = len(lines)
        lines.append("\n## Statistics")
        start_idx = len(lines) - 1

    if end_idx == -1:
        end_idx = len(lines)

    new_stats_block = [
        "## Statistics",
        "",
        f"**Last updated:** {Path(path).stat().st_mtime}",  # Placeholder, will use current time
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
    
    import datetime
    new_stats_block[2] = f"**Last updated:** {datetime.date.today().isoformat()}"

    for pri, count in sorted(stats["by_priority"].items()):
        new_stats_block.append(f"| {pri} | {count} |")

    new_stats_block.append("")
    new_stats_block.append("### Items by Domain")
    new_stats_block.append("")
    new_stats_block.append("| Domain | Count |")
    new_stats_block.append("|--------|-------|")

    for domain, count in sorted(stats["by_domain"].items(), key=lambda x: -x[1]):
        new_stats_block.append(f"| {domain} | {count} |")

    new_stats_block.append("")

    lines[start_idx:end_idx] = new_stats_block
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True
