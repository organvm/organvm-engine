"""Tests for the handoff discovery and staleness module."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from organvm_engine.handoff.parser import (
    DEFAULT_STALE_HOURS,
    Handoff,
    discover_handoffs,
    filter_stale,
    format_handoffs,
    parse_handoff,
)

NOW = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)


def _write_handoff(repo_dir, text: str):
    conductor = repo_dir / ".conductor"
    conductor.mkdir(parents=True, exist_ok=True)
    path = conductor / "active-handoff.md"
    path.write_text(text)
    return path


# ── timestamp extraction ──────────────────────────────────────────


def test_parse_frontmatter_timestamp(tmp_path):
    path = _write_handoff(
        tmp_path,
        "---\ntimestamp: 2026-06-18T06:00:00Z\nagent: jules-3\n---\n# Refactor parser\n",
    )
    h = parse_handoff(path, org="meta-organvm", repo="organvm-engine")
    assert h.timestamp == datetime(2026, 6, 18, 6, 0, 0, tzinfo=timezone.utc)
    assert h.timestamp_source == "embedded"
    assert h.agent == "jules-3"
    assert h.title == "Refactor parser"


def test_parse_bold_marker_timestamp(tmp_path):
    path = _write_handoff(
        tmp_path,
        "# Handoff\n\n**Created:** 2026-06-17T09:30:00Z\n**Agent:** codex-1\n",
    )
    h = parse_handoff(path)
    assert h.timestamp == datetime(2026, 6, 17, 9, 30, 0, tzinfo=timezone.utc)
    assert h.timestamp_source == "embedded"
    assert h.agent == "codex-1"


def test_parse_naive_timestamp_assumes_utc(tmp_path):
    path = _write_handoff(tmp_path, "**Updated:** 2026-06-18 06:00:00\nWork.\n")
    h = parse_handoff(path)
    assert h.timestamp == datetime(2026, 6, 18, 6, 0, 0, tzinfo=timezone.utc)


def test_parse_falls_back_to_mtime(tmp_path):
    path = _write_handoff(tmp_path, "# No timestamp here\nJust prose.\n")
    past = time.time() - 3600
    os.utime(path, (past, past))
    h = parse_handoff(path)
    assert h.timestamp_source == "mtime"
    # mtime-based age should be roughly an hour.
    assert 0.9 < h.age_hours() < 1.2


def test_cross_verification_flag(tmp_path):
    path = _write_handoff(tmp_path, "# Handoff\nCROSS-VERIFICATION REQUIRED for this task.\n")
    assert parse_handoff(path).cross_verification is True
    plain = _write_handoff(tmp_path / "other", "# Handoff\nNo flag.\n")
    assert parse_handoff(plain).cross_verification is False


# ── staleness ─────────────────────────────────────────────────────


def _handoff(hours_old: float, **kw) -> Handoff:
    return Handoff(
        path=kw.get("path", "/tmp/h.md"),
        org=kw.get("org", "meta-organvm"),
        repo=kw.get("repo", "organvm-engine"),
        title=kw.get("title", "t"),
        timestamp=NOW - timedelta(hours=hours_old),
        timestamp_source="embedded",
        cross_verification=kw.get("cross_verification", False),
    )


def test_age_hours():
    assert _handoff(5).age_hours(now=NOW) == pytest.approx(5.0)


def test_is_stale_threshold():
    fresh = _handoff(10)
    stale = _handoff(30)
    assert not fresh.is_stale(now=NOW)
    assert stale.is_stale(now=NOW)
    # Exactly at threshold counts as stale.
    assert _handoff(DEFAULT_STALE_HOURS).is_stale(now=NOW)


def test_custom_threshold():
    h = _handoff(10)
    assert h.is_stale(threshold_hours=8, now=NOW)
    assert not h.is_stale(threshold_hours=12, now=NOW)


def test_filter_stale():
    handoffs = [_handoff(1), _handoff(48), _handoff(0.5)]
    stale = filter_stale(handoffs, now=NOW)
    assert len(stale) == 1
    assert stale[0].age_hours(now=NOW) == pytest.approx(48.0)


def test_slug():
    assert _handoff(1).slug == "meta-organvm/organvm-engine"
    assert _handoff(1, repo="").slug == "meta-organvm"


# ── discovery ─────────────────────────────────────────────────────


def test_discover_handoffs_repos_and_superproject(tmp_path):
    org = tmp_path / "meta-organvm"
    repo_a = org / "organvm-engine"
    repo_b = org / "schema-definitions"
    repo_a.mkdir(parents=True)
    repo_b.mkdir(parents=True)

    _write_handoff(org, "---\ntimestamp: 2026-06-18T00:00:00Z\n---\n# Superproject\n")
    _write_handoff(repo_a, "---\ntimestamp: 2026-06-18T06:00:00Z\n---\n# Engine work\n")
    _write_handoff(repo_b, "---\ntimestamp: 2026-06-17T00:00:00Z\n---\n# Schema work\n")

    handoffs = discover_handoffs(workspace=tmp_path, orgs=["meta-organvm"])
    assert len(handoffs) == 3
    # Sorted oldest-first.
    titles = [h.title for h in handoffs]
    assert titles == ["Schema work", "Superproject", "Engine work"]
    # Superproject handoff has empty repo.
    superproject = next(h for h in handoffs if h.title == "Superproject")
    assert superproject.repo == ""
    assert superproject.slug == "meta-organvm"


def test_discover_skips_missing_orgs(tmp_path):
    assert discover_handoffs(workspace=tmp_path, orgs=["nonexistent-org"]) == []


def test_discover_ignores_repos_without_handoff(tmp_path):
    org = tmp_path / "meta-organvm"
    (org / "empty-repo").mkdir(parents=True)
    assert discover_handoffs(workspace=tmp_path, orgs=["meta-organvm"]) == []


# ── formatting ────────────────────────────────────────────────────


def test_format_empty():
    assert "No active handoffs" in format_handoffs([])


def test_format_marks_stale_and_xv():
    handoffs = [_handoff(2), _handoff(50, cross_verification=True)]
    out = format_handoffs(handoffs, now=NOW)
    assert "STALE" in out
    assert "fresh" in out
    assert "✓" in out
