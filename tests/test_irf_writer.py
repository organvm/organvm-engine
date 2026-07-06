"""Tests for organvm_engine.irf.writer and the 2026-06-07 parser drop categories.

Covers the IRF-OPS-091 undercount chain (parser regression cases A–E) and the
IRF-SYS-251 write-back tooling (add / complete / stats regeneration), including
the hardlink-inode invariant from IRF-SYS-168.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from organvm_engine.irf.parser import irf_stats, parse_irf, parse_irf_diagnostics
from organvm_engine.irf.writer import (
    IRFWriteError,
    add_item,
    complete_item,
    next_done_id,
    next_irf_id,
    regenerate_stats_block,
    write_in_place,
)

FIXTURES = Path(__file__).parent / "fixtures"
CASES = FIXTURES / "irf-parser-cases.md"


# ---------------------------------------------------------------------------
# Parser drop categories (IRF-OPS-017 / SYS-182 / OPS-088 / OPS-091)
# ---------------------------------------------------------------------------

def _ids(path: Path) -> set[str]:
    return {item.id for item in parse_irf(path)}


def test_fixture_parses_complete():
    """Every ID-bearing row in the fixture parses — zero silent drops."""
    items, skipped = parse_irf_diagnostics(CASES)
    assert skipped == []
    assert len(items) == 13


def test_letter_suffixed_ids_parse():
    """Category A — IRF-VAC-001a-style sub-item IDs (IRF-SYS-182 blind spot)."""
    ids = _ids(CASES)
    assert {"IRF-VAC-001a", "IRF-VAC-001b", "IRF-VAC-002a", "DONE-114a"} <= ids


def test_done_ref_in_priority_cell_parses_as_completed():
    """Category B — DONE-ref in the priority column means completed in place."""
    items = {i.id: i for i in parse_irf(CASES)}
    item = items["IRF-SKL-004"]
    assert item.status == "completed"
    assert item.priority == ""
    assert "DONE-525" in item.source


def test_ledger_row_in_blocked_section_parses():
    """Category C — 4-cell ledger-shaped rows outside Completed sections."""
    items = {i.id: i for i in parse_irf(CASES)}
    assert items["IRF-SYS-155"].status == "blocked"


def test_short_done_row_parses():
    """Category D — 3-cell DONE rows still land in the ledger."""
    assert "DONE-145" in _ids(CASES)


def test_row_without_trailing_pipe_parses():
    """Category E — hand-appended rows missing the trailing pipe."""
    assert "IRF-SYS-096" in _ids(CASES)


def test_short_active_row_keeps_priority_and_action():
    """Tail-added active rows may omit owner/source/blocker cells."""
    items = {i.id: i for i in parse_irf(CASES)}
    item = items["IRF-SYS-096"]
    assert item.status == "open"
    assert item.priority == "P2"
    assert "Row without trailing pipe" in item.action


def test_stats_count_short_tail_row_priority():
    """Category E rows must contribute to priority stats, not just total."""
    stats = irf_stats(parse_irf(CASES))
    assert stats["by_priority"]["P2"] == 2


def test_tail_row_without_leading_pipe_parses_and_counts(tmp_path: Path):
    """Tail-appended Markdown rows may omit the leading pipe; stats must see them."""
    path = tmp_path / "irf.md"
    path.write_text(
        CASES.read_text()
        + "\n\n### S-tail Discovered Items (2026-06-18)\n\n"
        + "ID | Priority | Action | Owner | Source | Blocker\n"
        + "---|---|---|---|---|---\n"
        + "IRF-TAIL-001 | P2 | Tail-created compact row | Agent | issue-71 | None\n",
    )

    items, skipped = parse_irf_diagnostics(path)
    stats = irf_stats(items)

    assert skipped == []
    assert stats["total"] == len(parse_irf(CASES)) + 1
    assert stats["by_domain"]["TAIL"] == 1
    assert next(i for i in items if i.id == "IRF-TAIL-001").priority == "P2"


def test_late_file_row_resolves():
    """IRF-OPS-088 — rows late in the file are reachable."""
    assert "IRF-OPS-087" in _ids(CASES)


def test_struck_rows_count_as_completed():
    items = {i.id: i for i in parse_irf(CASES)}
    assert items["IRF-SYS-003"].status == "completed"
    assert items["IRF-VAC-002a"].status == "completed"


def test_stats_tables_not_counted_as_items():
    """The embedded ## Statistics tables must not leak into the item list."""
    ids = _ids(CASES)
    assert "SYS" not in ids
    assert "P0" not in ids


# ---------------------------------------------------------------------------
# ID allocation
# ---------------------------------------------------------------------------

def test_next_done_id_skips_existing():
    items = parse_irf(CASES)
    # Highest numeric DONE in fixture is DONE-525 (priority-cell ref is not an
    # item id); ledger has DONE-145; allocator must clear the max item id.
    assert next_done_id(items) == "DONE-146"


def test_next_irf_id_per_domain():
    items = parse_irf(CASES)
    assert next_irf_id(items, "VAC") == "IRF-VAC-003"
    assert next_irf_id(items, "NEW") == "IRF-NEW-001"


# ---------------------------------------------------------------------------
# add_item
# ---------------------------------------------------------------------------

@pytest.fixture
def working_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "irf.md"
    dst.write_text(CASES.read_text())
    return dst


def test_add_item_appends_after_domain(working_copy: Path):
    mutation = add_item(working_copy, domain="SYS", action="New synthetic item", priority="P3")
    write_in_place(working_copy, mutation.new_text)
    items = {i.id: i for i in parse_irf(working_copy)}
    new = items["IRF-SYS-156"]  # max SYS is 155 → next is 156
    assert new.status == "open"
    assert new.priority == "P3"


def test_add_item_rejects_duplicate_id(working_copy: Path):
    with pytest.raises(IRFWriteError, match="duplicate"):
        add_item(working_copy, domain="SYS", action="dup", item_id="IRF-SYS-001")


def test_add_item_rejects_bad_priority(working_copy: Path):
    with pytest.raises(IRFWriteError, match="priority"):
        add_item(working_copy, domain="SYS", action="x", priority="P9")


def test_add_item_keeps_parse_complete(working_copy: Path):
    mutation = add_item(working_copy, domain="OPS", action="Another item")
    write_in_place(working_copy, mutation.new_text)
    _, skipped = parse_irf_diagnostics(working_copy)
    assert skipped == []


# ---------------------------------------------------------------------------
# complete_item
# ---------------------------------------------------------------------------

def test_complete_item_strikes_and_ledgers(working_copy: Path):
    mutation = complete_item(
        working_copy,
        item_id="IRF-SYS-001",
        note="closed by test",
        session="S-test",
        date="2026-06-07",
    )
    write_in_place(working_copy, mutation.new_text)
    items = {i.id: i for i in parse_irf(working_copy)}
    assert items["IRF-SYS-001"].status == "completed"
    # Ledger row appended with the allocated DONE id
    assert "DONE-146" in items
    assert "IRF-SYS-001" in items["DONE-146"].action


def test_complete_item_rejects_duplicate_done(working_copy: Path):
    with pytest.raises(IRFWriteError, match="already allocated"):
        complete_item(
            working_copy,
            item_id="IRF-SYS-001",
            note="x",
            session="S",
            date="2026-06-07",
            done_id="DONE-145",
        )


def test_complete_item_rejects_already_completed(working_copy: Path):
    with pytest.raises(IRFWriteError, match="already completed"):
        complete_item(
            working_copy,
            item_id="IRF-SKL-004",
            note="x",
            session="S",
            date="2026-06-07",
        )


def test_complete_item_rejects_unknown_id(working_copy: Path):
    with pytest.raises(IRFWriteError, match="not found"):
        complete_item(
            working_copy, item_id="IRF-NOPE-999", note="x", session="S", date="2026-06-07",
        )


def test_complete_is_additive(working_copy: Path):
    """Nothing is deleted: total item count grows by one (the ledger row)."""
    before = len(parse_irf(working_copy))
    mutation = complete_item(
        working_copy, item_id="IRF-SYS-001", note="n", session="S", date="2026-06-07",
    )
    write_in_place(working_copy, mutation.new_text)
    assert len(parse_irf(working_copy)) == before + 1


# ---------------------------------------------------------------------------
# regenerate_stats_block
# ---------------------------------------------------------------------------

def test_stats_regeneration_reflects_parse(working_copy: Path):
    mutation = regenerate_stats_block(working_copy, date="2026-06-07")
    write_in_place(working_copy, mutation.new_text)
    text = working_copy.read_text()
    stats = irf_stats(parse_irf(working_copy))
    assert f"| Total Items | {stats['total']} |" in text
    assert "999" not in text  # stale hand-edited values replaced
    assert "AUTOGEN" in text


def test_stats_regeneration_preserves_items(working_copy: Path):
    before = {i.id for i in parse_irf(working_copy)}
    mutation = regenerate_stats_block(working_copy, date="2026-06-07")
    write_in_place(working_copy, mutation.new_text)
    assert {i.id for i in parse_irf(working_copy)} == before


def test_stats_regeneration_is_idempotent(working_copy: Path):
    first = regenerate_stats_block(working_copy, date="2026-06-07")
    write_in_place(working_copy, first.new_text)
    second = regenerate_stats_block(working_copy, date="2026-06-07")
    assert second.new_text == first.new_text


def test_stats_regeneration_guards_compact_tail_rows(working_copy: Path):
    write_in_place(
        working_copy,
        working_copy.read_text()
        + "\nIRF-TAIL-001 | P2 | Tail-created compact row | Agent | issue-71 | None\n",
    )

    with pytest.raises(IRFWriteError, match="ID-bearing"):
        regenerate_stats_block(working_copy, date="2026-06-18")


# ---------------------------------------------------------------------------
# Hardlink invariant (IRF-SYS-168)
# ---------------------------------------------------------------------------

def test_write_in_place_preserves_inode(tmp_path: Path):
    original = tmp_path / "irf.md"
    original.write_text(CASES.read_text())
    twin = tmp_path / "twin.md"
    os.link(original, twin)
    inode_before = original.stat().st_ino

    mutation = add_item(original, domain="SYS", action="inode test")
    write_in_place(original, mutation.new_text)

    assert original.stat().st_ino == inode_before
    assert twin.read_text() == original.read_text()
