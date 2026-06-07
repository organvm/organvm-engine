"""Tests for organvm_engine.irf.query — query_irf()."""

from __future__ import annotations

from pathlib import Path

from organvm_engine.irf.parser import parse_irf
from organvm_engine.irf.query import query_irf

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "irf-sample.md"


def _items():
    return parse_irf(SAMPLE)


# ---------------------------------------------------------------------------
# No filter — returns all
# ---------------------------------------------------------------------------

def test_query_no_filter_returns_all():
    items = _items()
    result = query_irf(items)
    assert result == items


def test_query_returns_list():
    assert isinstance(query_irf(_items()), list)


# ---------------------------------------------------------------------------
# Filter by priority
# ---------------------------------------------------------------------------

def test_query_by_p0():
    result = query_irf(_items(), priority="P0")
    assert len(result) == 2
    assert all(i.priority == "P0" for i in result)


def test_query_by_p1():
    result = query_irf(_items(), priority="P1")
    assert len(result) == 2
    assert all(i.priority == "P1" for i in result)


def test_query_by_p2():
    result = query_irf(_items(), priority="P2")
    assert len(result) == 3
    assert all(i.priority == "P2" for i in result)


def test_query_by_p3():
    result = query_irf(_items(), priority="P3")
    assert len(result) == 1
    assert result[0].priority == "P3"


def test_query_priority_case_insensitive():
    # "p0" should match "P0"
    result_lower = query_irf(_items(), priority="p0")
    result_upper = query_irf(_items(), priority="P0")
    assert result_lower == result_upper


# ---------------------------------------------------------------------------
# Filter by domain
# ---------------------------------------------------------------------------

def test_query_by_domain_sys():
    result = query_irf(_items(), domain="SYS")
    assert len(result) == 2
    assert all(i.domain == "SYS" for i in result)


def test_query_by_domain_mon():
    result = query_irf(_items(), domain="MON")
    assert len(result) == 2
    assert all(i.domain == "MON" for i in result)


def test_query_by_domain_crp():
    result = query_irf(_items(), domain="CRP")
    assert len(result) == 3
    assert all(i.domain == "CRP" for i in result)


def test_query_by_domain_done():
    result = query_irf(_items(), domain="DONE")
    assert len(result) == 4
    assert all(i.domain == "DONE" for i in result)


def test_query_domain_case_insensitive():
    result_lower = query_irf(_items(), domain="sys")
    result_upper = query_irf(_items(), domain="SYS")
    assert result_lower == result_upper


def test_query_domain_no_match_returns_empty():
    result = query_irf(_items(), domain="NONEXISTENT")
    assert result == []


# ---------------------------------------------------------------------------
# Filter by status
# ---------------------------------------------------------------------------

def test_query_by_status_open():
    result = query_irf(_items(), status="open")
    assert len(result) == 8
    assert all(i.status == "open" for i in result)


def test_query_by_status_completed():
    result = query_irf(_items(), status="completed")
    assert len(result) == 4
    assert all(i.status == "completed" for i in result)


def test_query_by_status_blocked():
    result = query_irf(_items(), status="blocked")
    assert result == []


def test_query_by_status_archived():
    result = query_irf(_items(), status="archived")
    assert result == []


def test_query_status_case_insensitive():
    result_lower = query_irf(_items(), status="completed")
    result_upper = query_irf(_items(), status="COMPLETED")
    assert result_lower == result_upper


# ---------------------------------------------------------------------------
# Filter by owner
# ---------------------------------------------------------------------------

def test_query_by_owner_agent():
    result = query_irf(_items(), owner="Agent")
    assert len(result) >= 1
    assert all("agent" in i.owner.lower() for i in result)


def test_query_by_owner_human():
    result = query_irf(_items(), owner="Human")
    assert len(result) >= 1
    assert all("human" in i.owner.lower() for i in result)


def test_query_owner_case_insensitive():
    result_lower = query_irf(_items(), owner="agent")
    result_upper = query_irf(_items(), owner="AGENT")
    assert result_lower == result_upper


def test_query_owner_substring_match():
    # "gen" is a substring of "Agent"
    result = query_irf(_items(), owner="gen")
    assert len(result) >= 1


def test_query_owner_no_match_returns_empty():
    result = query_irf(_items(), owner="xyzzy-nonexistent")
    assert result == []


# ---------------------------------------------------------------------------
# Filter by item_id
# ---------------------------------------------------------------------------

def test_query_by_id_exact():
    result = query_irf(_items(), item_id="IRF-SYS-001")
    assert len(result) == 1
    assert result[0].id == "IRF-SYS-001"


def test_query_by_id_done():
    result = query_irf(_items(), item_id="DONE-002")
    assert len(result) == 1
    assert result[0].id == "DONE-002"


def test_query_by_id_case_insensitive():
    result_lower = query_irf(_items(), item_id="irf-sys-001")
    result_upper = query_irf(_items(), item_id="IRF-SYS-001")
    assert result_lower == result_upper


def test_query_by_id_no_match_returns_empty():
    result = query_irf(_items(), item_id="IRF-FAKE-999")
    assert result == []


# ---------------------------------------------------------------------------
# Combined filters (AND logic)
# ---------------------------------------------------------------------------

def test_query_combined_priority_and_status():
    result = query_irf(_items(), priority="P1", status="open")
    assert len(result) == 2
    assert all(i.priority == "P1" and i.status == "open" for i in result)


def test_query_combined_domain_and_status():
    result = query_irf(_items(), domain="SYS", status="open")
    assert len(result) == 2
    assert all(i.domain == "SYS" and i.status == "open" for i in result)


def test_query_combined_priority_and_domain():
    result = query_irf(_items(), priority="P0", domain="MON")
    assert len(result) == 1
    assert result[0].id == "IRF-MON-001"


def test_query_combined_three_filters():
    result = query_irf(_items(), priority="P0", domain="CRP", status="open")
    assert len(result) == 1
    assert result[0].id == "IRF-CRP-003"


def test_query_combined_contradictory_filters_returns_empty():
    # Completed items don't have P0 priority
    result = query_irf(_items(), status="completed", priority="P0")
    assert result == []


def test_query_combined_id_and_status():
    result = query_irf(_items(), item_id="DONE-001", status="completed")
    assert len(result) == 1
    assert result[0].id == "DONE-001"
