"""Tests for organvm_engine.irf.parser — parse_irf() and irf_stats()."""

from __future__ import annotations

from pathlib import Path

import pytest

from organvm_engine.irf.parser import IRFItem, irf_stats, parse_irf

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "irf-sample.md"


# ---------------------------------------------------------------------------
# parse_irf — basic smoke tests
# ---------------------------------------------------------------------------

def test_parse_returns_list():
    result = parse_irf(SAMPLE)
    assert isinstance(result, list)


def test_parse_returns_irf_items():
    result = parse_irf(SAMPLE)
    assert all(isinstance(item, IRFItem) for item in result)


def test_parse_missing_file_returns_empty():
    result = parse_irf(Path("/nonexistent/path/irf.md"))
    assert result == []


def test_parse_correct_total_count():
    # Sample has 8 active/blocked/archived items + 4 completed = 12 total
    result = parse_irf(SAMPLE)
    assert len(result) == 12


# ---------------------------------------------------------------------------
# parse_irf — field correctness
# ---------------------------------------------------------------------------

def test_parse_active_item_fields():
    items = parse_irf(SAMPLE)
    sys001 = next(i for i in items if i.id == "IRF-SYS-001")
    assert sys001.priority == "P1"
    assert sys001.domain == "SYS"
    assert sys001.status == "open"
    assert "CONSTITUTION.md" in sys001.action
    assert sys001.owner == "Agent"
    assert sys001.blocker == "None"


def test_parse_p0_item_fields():
    items = parse_irf(SAMPLE)
    mon001 = next(i for i in items if i.id == "IRF-MON-001")
    assert mon001.priority == "P0"
    assert mon001.domain == "MON"
    assert mon001.status == "open"


def test_parse_p3_item_fields():
    items = parse_irf(SAMPLE)
    mon002 = next(i for i in items if i.id == "IRF-MON-002")
    assert mon002.priority == "P3"
    assert mon002.status == "open"


def test_parse_completed_items_have_completed_status():
    items = parse_irf(SAMPLE)
    completed = [i for i in items if i.status == "completed"]
    assert len(completed) == 4


def test_parse_completed_item_fields():
    items = parse_irf(SAMPLE)
    done001 = next(i for i in items if i.id == "DONE-001")
    assert done001.status == "completed"
    assert done001.priority == ""
    assert done001.domain == "DONE"
    assert "Application pipeline" in done001.action


def test_parse_completed_subsection_five_column_row():
    items = parse_irf(SAMPLE)
    done004 = next(i for i in items if i.id == "DONE-004")
    assert done004.status == "completed"
    assert done004.domain == "DONE"
    assert "Parser-visible closeout row" in done004.action
    assert done004.source == "S-sample-closeout"


def test_parse_completed_items_are_all_done():
    items = parse_irf(SAMPLE)
    completed = [i for i in items if i.status == "completed"]
    assert all(i.id.startswith("DONE-") for i in completed)


def test_parse_domain_extraction_irf():
    items = parse_irf(SAMPLE)
    obj = next(i for i in items if i.id == "IRF-OBJ-001")
    assert obj.domain == "OBJ"


def test_parse_domain_extraction_crp():
    items = parse_irf(SAMPLE)
    crp = next(i for i in items if i.id == "IRF-CRP-001")
    assert crp.domain == "CRP"


def test_parse_section_tracked():
    items = parse_irf(SAMPLE)
    # IRF-SYS-001 is under "Governance & Standards" subsection of "System-Wide"
    sys001 = next(i for i in items if i.id == "IRF-SYS-001")
    assert "Governance" in sys001.section or "System" in sys001.section


def test_parse_open_items_count():
    items = parse_irf(SAMPLE)
    open_items = [i for i in items if i.status == "open"]
    assert len(open_items) == 8


def test_parse_priority_distribution():
    items = parse_irf(SAMPLE)
    open_items = [i for i in items if i.status == "open"]
    p0 = [i for i in open_items if i.priority == "P0"]
    p1 = [i for i in open_items if i.priority == "P1"]
    p2 = [i for i in open_items if i.priority == "P2"]
    p3 = [i for i in open_items if i.priority == "P3"]
    assert len(p0) == 2
    assert len(p1) == 2
    assert len(p2) == 3
    assert len(p3) == 1


# ---------------------------------------------------------------------------
# irf_stats
# ---------------------------------------------------------------------------

def test_stats_returns_dict():
    items = parse_irf(SAMPLE)
    stats = irf_stats(items)
    assert isinstance(stats, dict)


def test_stats_required_keys():
    items = parse_irf(SAMPLE)
    stats = irf_stats(items)
    expected_keys = {"total", "open", "completed", "blocked", "archived",
                     "completion_rate", "by_priority", "by_domain"}
    assert expected_keys.issubset(stats.keys())


def test_stats_total():
    items = parse_irf(SAMPLE)
    stats = irf_stats(items)
    assert stats["total"] == len(items) == 12


def test_stats_open():
    items = parse_irf(SAMPLE)
    stats = irf_stats(items)
    assert stats["open"] == 8


def test_stats_completed():
    items = parse_irf(SAMPLE)
    stats = irf_stats(items)
    assert stats["completed"] == 4


def test_stats_blocked():
    items = parse_irf(SAMPLE)
    stats = irf_stats(items)
    assert stats["blocked"] == 0


def test_stats_archived():
    items = parse_irf(SAMPLE)
    stats = irf_stats(items)
    assert stats["archived"] == 0


def test_stats_completion_rate():
    items = parse_irf(SAMPLE)
    stats = irf_stats(items)
    expected = round(4 / 12, 4)
    assert stats["completion_rate"] == pytest.approx(expected, abs=1e-4)


def test_stats_by_priority_keys():
    items = parse_irf(SAMPLE)
    stats = irf_stats(items)
    assert set(stats["by_priority"].keys()) == {"P0", "P1", "P2", "P3"}


def test_stats_by_priority_values():
    items = parse_irf(SAMPLE)
    stats = irf_stats(items)
    bp = stats["by_priority"]
    assert bp["P0"] == 2
    assert bp["P1"] == 2
    assert bp["P2"] == 3
    assert bp["P3"] == 1


def test_stats_by_domain_includes_known_domains():
    items = parse_irf(SAMPLE)
    stats = irf_stats(items)
    bd = stats["by_domain"]
    assert "SYS" in bd
    assert "MON" in bd
    assert "CRP" in bd
    assert "OBJ" in bd
    assert "DONE" in bd


def test_stats_empty_list():
    stats = irf_stats([])
    assert stats["total"] == 0
    assert stats["open"] == 0
    assert stats["completed"] == 0
    assert stats["completion_rate"] == 0.0
    assert stats["by_priority"] == {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    assert stats["by_domain"] == {}
