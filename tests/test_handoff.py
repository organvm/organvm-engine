"""Tests for organvm_engine.handoff — handoff discovery and staleness."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from textwrap import dedent

from organvm_engine.handoff.scanner import (
    DEFAULT_STALE_DAYS,
    _parse_timestamp,
    discover_handoffs,
    discover_in_repo,
    filter_stale,
    parse_handoff,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE = dedent(
    """\
    # Agent Handoff: claude → opencode

    **Session:** 2026-03-30-dispatch-signal-closure
    **Phase:** BUILD
    **Organ:** META-ORGANVM | **Repo:** organvm-engine
    **Scope:** Build validate_signal_closure + fix essay-pipeline CI
    **Timestamp:** 2026-03-30

    ## Summary

    Two well-scoped tasks.

    **CROSS-VERIFICATION REQUIRED** — Do not trust self-assessment.
    """,
)


def _write_handoff(repo_dir: Path, text: str = SAMPLE) -> Path:
    conductor = repo_dir / ".conductor"
    conductor.mkdir(parents=True, exist_ok=True)
    path = conductor / "active-handoff.md"
    path.write_text(text)
    return path


# ---------------------------------------------------------------------------
# _parse_timestamp
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    def test_iso_date(self):
        assert _parse_timestamp("2026-03-30") == date(2026, 3, 30)

    def test_iso_datetime_with_z(self):
        assert _parse_timestamp("2026-03-30T16:26:25Z") == date(2026, 3, 30)

    def test_iso_datetime_no_z(self):
        assert _parse_timestamp("2026-06-08T16:26:25") == date(2026, 6, 8)

    def test_date_with_trailing_text(self):
        assert _parse_timestamp("2026-03-30 (approx)") == date(2026, 3, 30)

    def test_empty(self):
        assert _parse_timestamp("") is None
        assert _parse_timestamp("   ") is None

    def test_unparseable(self):
        assert _parse_timestamp("last Tuesday") is None


# ---------------------------------------------------------------------------
# parse_handoff
# ---------------------------------------------------------------------------


class TestParseHandoff:
    def test_full_header(self, tmp_path):
        path = _write_handoff(tmp_path / "organvm-engine")
        h = parse_handoff(path)
        assert h is not None
        assert h.from_agent == "claude"
        assert h.to_agent == "opencode"
        assert h.session == "2026-03-30-dispatch-signal-closure"
        assert h.phase == "BUILD"
        assert h.organ == "META-ORGANVM"
        assert h.repo == "organvm-engine"
        assert "validate_signal_closure" in h.scope
        assert h.timestamp == "2026-03-30"
        assert h.handoff_date == date(2026, 3, 30)
        assert h.cross_verification is True
        assert h.archived is False

    def test_repo_falls_back_to_path(self, tmp_path):
        # No **Repo:** line -> derive from directory name (parent of .conductor).
        text = "# Agent Handoff: a → b\n\n**Timestamp:** 2026-01-01\n"
        path = _write_handoff(tmp_path / "my-repo", text)
        h = parse_handoff(path)
        assert h is not None
        assert h.repo == "my-repo"

    def test_no_title_still_parses(self, tmp_path):
        text = "**Timestamp:** 2026-01-01\n**Scope:** orphaned baton\n"
        path = _write_handoff(tmp_path / "repo", text)
        h = parse_handoff(path)
        assert h is not None
        assert h.from_agent == ""
        assert h.to_agent == ""
        assert h.scope == "orphaned baton"

    def test_arrow_variants(self, tmp_path):
        for arrow in ("->", "—", "=>"):
            text = f"# Agent Handoff: alpha {arrow} beta\n\n**Timestamp:** 2026-01-01\n"
            path = _write_handoff(tmp_path / "repo", text)
            h = parse_handoff(path)
            assert h is not None
            assert h.from_agent == "alpha"
            assert h.to_agent == "beta"

    def test_no_cross_verification(self, tmp_path):
        text = "# Agent Handoff: a → b\n\n**Timestamp:** 2026-01-01\n"
        path = _write_handoff(tmp_path / "repo", text)
        h = parse_handoff(path)
        assert h is not None
        assert h.cross_verification is False

    def test_missing_file_returns_none(self, tmp_path):
        assert parse_handoff(tmp_path / "nope.md") is None


# ---------------------------------------------------------------------------
# Handoff staleness
# ---------------------------------------------------------------------------


class TestStaleness:
    def test_age_days(self, tmp_path):
        text = "# Agent Handoff: a → b\n\n**Timestamp:** 2026-06-01\n"
        path = _write_handoff(tmp_path / "repo", text)
        h = parse_handoff(path)
        assert h.age_days(today=date(2026, 6, 18)) == 17

    def test_age_days_undated(self, tmp_path):
        text = "# Agent Handoff: a → b\n\n**Scope:** no timestamp\n"
        path = _write_handoff(tmp_path / "repo", text)
        h = parse_handoff(path)
        assert h.age_days() is None

    def test_fresh_not_stale(self, tmp_path):
        text = "# Agent Handoff: a → b\n\n**Timestamp:** 2026-06-15\n"
        path = _write_handoff(tmp_path / "repo", text)
        h = parse_handoff(path)
        assert h.is_stale(stale_days=7, today=date(2026, 6, 18)) is False
        assert h.staleness(stale_days=7, today=date(2026, 6, 18)) == "ACTIVE"

    def test_old_is_stale(self, tmp_path):
        text = "# Agent Handoff: a → b\n\n**Timestamp:** 2026-06-01\n"
        path = _write_handoff(tmp_path / "repo", text)
        h = parse_handoff(path)
        assert h.is_stale(stale_days=7, today=date(2026, 6, 18)) is True
        assert h.staleness(stale_days=7, today=date(2026, 6, 18)) == "STALE"

    def test_undated_is_stale(self, tmp_path):
        text = "# Agent Handoff: a → b\n\n**Scope:** no timestamp\n"
        path = _write_handoff(tmp_path / "repo", text)
        h = parse_handoff(path)
        assert h.is_stale() is True
        assert h.staleness() == "UNDATED"

    def test_archived_never_stale(self, tmp_path):
        text = "# Agent Handoff: a → b\n\n**Timestamp:** 2020-01-01\n"
        path = _write_handoff(tmp_path / "repo", text)
        h = parse_handoff(path, archived=True)
        assert h.is_stale(today=date(2026, 6, 18)) is False
        assert h.staleness() == "ARCHIVED"

    def test_boundary_exactly_threshold(self, tmp_path):
        # Exactly stale_days old is NOT stale (strictly greater-than).
        text = "# Agent Handoff: a → b\n\n**Timestamp:** 2026-06-11\n"
        path = _write_handoff(tmp_path / "repo", text)
        h = parse_handoff(path)
        assert h.is_stale(stale_days=7, today=date(2026, 6, 18)) is False


# ---------------------------------------------------------------------------
# discover_in_repo
# ---------------------------------------------------------------------------


class TestDiscoverInRepo:
    def test_finds_active(self, tmp_path):
        repo = tmp_path / "repo"
        _write_handoff(repo)
        found = discover_in_repo(repo)
        assert len(found) == 1
        assert found[0].archived is False

    def test_no_conductor_returns_empty(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        assert discover_in_repo(repo) == []

    def test_archive_excluded_by_default(self, tmp_path):
        repo = tmp_path / "repo"
        _write_handoff(repo)
        archive = repo / ".conductor" / "archive"
        archive.mkdir(parents=True)
        (archive / "old.md").write_text("# Agent Handoff: x → y\n\n**Timestamp:** 2020-01-01\n")
        assert len(discover_in_repo(repo)) == 1
        assert len(discover_in_repo(repo, include_archived=True)) == 2

    def test_archive_marked_archived(self, tmp_path):
        repo = tmp_path / "repo"
        archive = repo / ".conductor" / "archive"
        archive.mkdir(parents=True)
        (archive / "old.md").write_text("# Agent Handoff: x → y\n\n**Timestamp:** 2020-01-01\n")
        found = discover_in_repo(repo, include_archived=True)
        assert len(found) == 1
        assert found[0].archived is True


# ---------------------------------------------------------------------------
# discover_handoffs — workspace scan
# ---------------------------------------------------------------------------


class TestDiscoverWorkspace:
    def _make_workspace(self, tmp_path):
        """Build a fake workspace: <ws>/<org-dir>/<repo>/.conductor/."""
        from organvm_engine.organ_config import get_organ_map

        organ_map = get_organ_map()
        meta_dir = next(
            v["dir"] for v in organ_map.values() if v["registry_key"] == "META-ORGANVM"
        )
        ws = tmp_path / "ws"
        repo = ws / meta_dir / "organvm-engine"
        return ws, repo, meta_dir

    def test_scans_workspace(self, tmp_path):
        ws, repo, _ = self._make_workspace(tmp_path)
        _write_handoff(repo)
        found = discover_handoffs(workspace=ws)
        assert len(found) == 1
        assert found[0].repo == "organvm-engine"

    def test_organ_filter(self, tmp_path):
        ws, repo, _ = self._make_workspace(tmp_path)
        _write_handoff(repo)
        assert len(discover_handoffs(workspace=ws, organ="META")) == 1
        # An organ with no repos on disk yields nothing.
        assert discover_handoffs(workspace=ws, organ="I") == []

    def test_unknown_organ_returns_empty(self, tmp_path):
        ws, repo, _ = self._make_workspace(tmp_path)
        _write_handoff(repo)
        assert discover_handoffs(workspace=ws, organ="NOPE") == []

    def test_empty_workspace(self, tmp_path):
        assert discover_handoffs(workspace=tmp_path / "empty") == []

    def test_sorted_oldest_first(self, tmp_path):
        ws, repo, meta_dir = self._make_workspace(tmp_path)
        _write_handoff(repo, "# Agent Handoff: a → b\n\n**Timestamp:** 2026-06-10\n")
        repo2 = ws / meta_dir / "other-repo"
        _write_handoff(repo2, "# Agent Handoff: a → b\n\n**Timestamp:** 2026-01-01\n")
        found = discover_handoffs(workspace=ws)
        assert [h.handoff_date for h in found] == [date(2026, 1, 1), date(2026, 6, 10)]


# ---------------------------------------------------------------------------
# filter_stale
# ---------------------------------------------------------------------------


class TestFilterStale:
    def test_filters(self, tmp_path):
        repo = tmp_path / "repo"
        old = parse_handoff(
            _write_handoff(repo, "# Agent Handoff: a → b\n\n**Timestamp:** 2026-01-01\n"),
        )
        fresh = parse_handoff(
            _write_handoff(repo, "# Agent Handoff: a → b\n\n**Timestamp:** 2026-06-17\n"),
        )
        stale = filter_stale([old, fresh], stale_days=7, today=date(2026, 6, 18))
        assert stale == [old]


def test_default_stale_days_constant():
    assert DEFAULT_STALE_DAYS == 7
