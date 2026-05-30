"""Tests for session archive module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from organvm_engine.session.archive import (
    _build_meta_json,
    _resolve_since,
    _session_slug,
    load_archive_state,
)
from organvm_engine.session.parser import SessionMeta


@pytest.fixture()
def sample_meta(tmp_path: Path) -> SessionMeta:
    """A minimal SessionMeta for testing."""
    from datetime import datetime, timezone

    return SessionMeta(
        session_id="abc123-def456",
        file_path=tmp_path / "abc123-def456.jsonl",
        slug="sparkling-dancing-fox",
        cwd=str(tmp_path),
        git_branch="main",
        started=datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 15, 11, 30, 0, tzinfo=timezone.utc),
        message_count=42,
        human_messages=15,
        assistant_messages=27,
        tools_used={"Read": 10, "Edit": 5, "Bash": 3},
        first_human_message="Fix the gcloud Python version pinning",
        project_dir="test-project",
    )


class TestResolveSince:
    def test_none(self) -> None:
        assert _resolve_since(None) is None

    def test_absolute_date(self) -> None:
        assert _resolve_since("2026-04-10") == "2026-04-10"

    def test_days_relative(self) -> None:
        result = _resolve_since("7d")
        assert result is not None
        # Should be a YYYY-MM-DD string
        assert len(result) == 10
        assert result[4] == "-"
        assert result[7] == "-"

    def test_hours_relative(self) -> None:
        result = _resolve_since("24h")
        assert result is not None
        assert len(result) == 10

    def test_passthrough_unknown(self) -> None:
        assert _resolve_since("yesterday") == "yesterday"


class TestSessionSlug:
    def test_uses_meta_slug(self, sample_meta: SessionMeta) -> None:
        slug = _session_slug(sample_meta)
        assert slug == "sparkling-dancing-fox"

    def test_falls_back_to_message(self, sample_meta: SessionMeta) -> None:
        sample_meta.slug = ""
        slug = _session_slug(sample_meta)
        assert "fix" in slug.lower()
        assert "gcloud" in slug.lower()

    def test_falls_back_to_session_id(self, sample_meta: SessionMeta) -> None:
        sample_meta.slug = ""
        sample_meta.first_human_message = ""
        slug = _session_slug(sample_meta)
        assert slug == sample_meta.session_id[:12]

    def test_sanitizes_special_chars(self, sample_meta: SessionMeta) -> None:
        sample_meta.slug = "my/session\\with spaces"
        slug = _session_slug(sample_meta)
        assert "/" not in slug
        assert "\\" not in slug
        assert " " not in slug


class TestBuildMetaJson:
    def test_valid_json(self, sample_meta: SessionMeta) -> None:
        result = _build_meta_json(sample_meta)
        data = json.loads(result)
        assert data["session_id"] == "abc123-def456"
        assert data["message_count"] == 42
        assert data["duration_minutes"] == 90

    def test_includes_archived_at(self, sample_meta: SessionMeta) -> None:
        data = json.loads(_build_meta_json(sample_meta))
        assert "archived_at" in data


class TestArchiveState:
    def test_empty_state(self, tmp_path: Path) -> None:
        state = load_archive_state(tmp_path)
        assert state == {}

    def test_roundtrip(self, tmp_path: Path) -> None:
        from organvm_engine.session.archive import _save_archive_state

        state = {"session-123": {"slug": "test", "archived_at": "2026-04-15"}}
        _save_archive_state(tmp_path, state)
        loaded = load_archive_state(tmp_path)
        assert loaded["session-123"]["slug"] == "test"


class TestForceReArchive:
    """IRF-SYS-243: ``--force`` must bypass the skip-if-exists guard so a
    resumed-then-continued session's stale archive can be refreshed. The
    library always supported ``force``; the CLI never threaded it through."""

    @staticmethod
    def _make_claude_session(tmp_path: Path, session_id: str) -> Path:
        """Write a minimal parseable Claude session JSONL rooted at tmp_path."""
        jsonl = tmp_path / f"{session_id}.jsonl"
        line = {
            "type": "user",
            "timestamp": "2026-05-30T10:00:00.000Z",
            "cwd": str(tmp_path),
            "gitBranch": "main",
            "slug": "resumed-dancing-fox",
            "message": {
                "role": "user",
                "content": "A sufficiently long human prompt so the session parses cleanly.",
            },
        }
        jsonl.write_text(json.dumps(line) + "\n", encoding="utf-8")
        return jsonl

    def _seed_already_archived(self, tmp_path: Path, session_id: str) -> None:
        from organvm_engine.session.archive import _save_archive_state

        _save_archive_state(
            tmp_path,
            {session_id: {"slug": "stale", "archived_at": "2026-05-30T18:13:00+00:00"}},
        )

    def test_skips_already_archived_without_force(self, tmp_path: Path) -> None:
        from organvm_engine.session.archive import archive_session

        sid = "resumed-session-noforce"
        jsonl = self._make_claude_session(tmp_path, sid)
        self._seed_already_archived(tmp_path, sid)

        result = archive_session(jsonl, dry_run=True)

        assert result.skipped is True
        assert "Already archived" in result.skip_reason

    def test_force_re_archives_already_archived(self, tmp_path: Path) -> None:
        from organvm_engine.session.archive import archive_session

        sid = "resumed-session-force"
        jsonl = self._make_claude_session(tmp_path, sid)
        self._seed_already_archived(tmp_path, sid)

        result = archive_session(jsonl, dry_run=True, force=True)

        # force bypasses the skip guard — the session is re-processed.
        assert result.skipped is False
        assert result.error == ""
        assert "transcript.md" in result.files_written
