"""Tests for the session review CLI command."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from organvm_engine.cli.session import cmd_session_review

# ── Helpers ───────────────────────────────────────────────────────


def _make_test_session(tmp_path: Path, session_id: str = "test-abc-123") -> Path:
    """Create a minimal Claude session JSONL for testing."""
    jsonl = tmp_path / f"{session_id}.jsonl"
    messages = [
        {
            "type": "user",
            "sessionId": session_id,
            "slug": "test-slug",
            "cwd": "/Users/test/Workspace/project",
            "gitBranch": "main",
            "timestamp": "2026-03-06T10:00:00Z",
            "message": {"role": "user", "content": "Implement the feature"},
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "slug": "test-slug",
            "cwd": "/Users/test/Workspace/project",
            "gitBranch": "main",
            "timestamp": "2026-03-06T10:05:00Z",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]},
        },
        {
            "type": "user",
            "sessionId": session_id,
            "slug": "test-slug",
            "cwd": "/Users/test/Workspace/project",
            "gitBranch": "main",
            "timestamp": "2026-03-06T10:10:00Z",
            "message": {"role": "user", "content": "Now add tests for the feature"},
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "slug": "test-slug",
            "cwd": "/Users/test/Workspace/project",
            "gitBranch": "main",
            "timestamp": "2026-03-06T10:15:00Z",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "Tests added."}]},
        },
    ]
    with jsonl.open("w") as f:
        for m in messages:
            f.write(json.dumps(m) + "\n")
    return jsonl


class _FakeArgs:
    """Minimal argparse namespace for testing."""

    def __init__(self, **kwargs):
        self.session_id = kwargs.get("session_id")
        self.latest = kwargs.get("latest", False)
        self.project = kwargs.get("project")


# ── Tests ─────────────────────────────────────────────────────────


def test_review_no_args(capsys):
    args = _FakeArgs()
    result = cmd_session_review(args)
    assert result == 1
    captured = capsys.readouterr()
    assert "Provide a session ID" in captured.out


def test_review_session_not_found(capsys):
    with patch("organvm_engine.cli.session.find_session", return_value=None):
        args = _FakeArgs(session_id="nonexistent")
        result = cmd_session_review(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "Session not found" in captured.out


def test_review_by_session_id(tmp_path, capsys):
    jsonl = _make_test_session(tmp_path)

    with (
        patch("organvm_engine.cli.session.find_session", return_value=jsonl),
        patch("organvm_engine.cli.session.discover_plans", return_value=[]),
    ):
        args = _FakeArgs(session_id="test-abc")
        result = cmd_session_review(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "Session Review:" in captured.out
        assert "test-abc" in captured.out
        assert "claude" in captured.out
        assert "Export:" in captured.out


def test_review_latest(tmp_path, capsys):
    jsonl = _make_test_session(tmp_path)

    from organvm_engine.session.agents import AgentSession

    mock_session = AgentSession(
        agent="claude",
        session_id="test-abc-123",
        file_path=jsonl,
        project_dir="/Users/test/Workspace/project",
        started=datetime(2026, 3, 6, 10, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 3, 6, 10, 15, tzinfo=timezone.utc),
        size_bytes=jsonl.stat().st_size,
    )

    with (
        patch(
            "organvm_engine.cli.session.discover_all_sessions",
            return_value=[mock_session],
        ),
        patch("organvm_engine.cli.session.discover_plans", return_value=[]),
    ):
        args = _FakeArgs(latest=True)
        result = cmd_session_review(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "Session Review:" in captured.out


def test_review_latest_no_sessions(capsys):
    with patch(
        "organvm_engine.cli.session.discover_all_sessions",
        return_value=[],
    ):
        args = _FakeArgs(latest=True)
        result = cmd_session_review(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "No sessions found" in captured.out


def test_review_shows_plans(tmp_path, capsys):
    jsonl = _make_test_session(tmp_path)

    from organvm_engine.session.plans import PlanFile

    mock_plan = PlanFile(
        path=Path("/tmp/2026-03-06-feature-plan.md"),
        project="project",
        slug="feature-plan",
        date="2026-03-06",
        title="Feature Plan",
        size_bytes=512,
        has_verification=True,
    )

    with (
        patch("organvm_engine.cli.session.find_session", return_value=jsonl),
        patch("organvm_engine.cli.session.discover_plans", return_value=[mock_plan]),
    ):
        args = _FakeArgs(session_id="test-abc")
        result = cmd_session_review(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "Plans in this project" in captured.out
        assert "Feature Plan" in captured.out
        assert "same day" in captured.out


def test_review_unparseable_session(tmp_path, capsys):
    bad_jsonl = tmp_path / "bad.jsonl"
    bad_jsonl.write_text("not valid json\n")

    with patch("organvm_engine.cli.session.find_session", return_value=bad_jsonl):
        args = _FakeArgs(session_id="bad")
        result = cmd_session_review(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "Could not parse" in captured.out
