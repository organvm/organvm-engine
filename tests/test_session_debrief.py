"""Tests for session debrief (tiered to-do extraction)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from organvm_engine.session.debrief import (
    SessionDebrief,
    _derive_repos,
    _is_commit_command,
    _is_test_command,
    _short_path,
    build_debrief,
    classify_todos,
    render_debrief,
)


@pytest.fixture()
def sample_session(tmp_path: Path) -> Path:
    """Create a minimal Claude JSONL session for testing."""
    jsonl = tmp_path / "session.jsonl"
    messages = [
        {
            "type": "user",
            "cwd": "/Users/test/Workspace/meta-organvm",
            "sessionId": "test-session-123",
            "message": {
                "role": "user",
                "content": "Add coordination tools to the MCP server",
            },
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "id": "t1",
                        "input": {
                            "file_path": "/Users/test/Workspace/meta-organvm"
                            "/organvm-engine/src/main.py",
                        },
                    },
                ],
            },
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Write",
                        "id": "t2",
                        "input": {
                            "file_path": "/Users/test/Workspace/meta-organvm"
                            "/organvm-mcp-server/src/tools/coord.py",
                            "content": "# new",
                        },
                    },
                ],
            },
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "id": "t3",
                        "input": {
                            "file_path": "/Users/test/Workspace/meta-organvm"
                            "/organvm-engine/src/server.py",
                            "old_string": "a",
                            "new_string": "b",
                        },
                    },
                ],
            },
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "id": "t4",
                        "input": {"command": "pytest organvm-engine/tests/ -v"},
                    },
                ],
            },
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "id": "t5",
                        "input": {"command": "git commit -m 'feat: add tools'"},
                    },
                ],
            },
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": "We still need to wire the dashboard later",
            },
        },
    ]
    lines = [json.dumps(m) for m in messages]
    jsonl.write_text("\n".join(lines))
    return jsonl


class TestBuildDebrief:
    def test_builds_from_jsonl(self, sample_session: Path):
        debrief = build_debrief(sample_session)
        assert debrief is not None
        assert debrief.agent == "claude"
        assert debrief.session_id == "session"  # derived from filename

    def test_extracts_files_written(self, sample_session: Path):
        debrief = build_debrief(sample_session)
        assert len(debrief.files_written) == 1
        assert "coord.py" in debrief.files_written[0]

    def test_extracts_files_edited(self, sample_session: Path):
        debrief = build_debrief(sample_session)
        assert len(debrief.files_edited) == 1
        assert "server.py" in debrief.files_edited[0]

    def test_extracts_files_read(self, sample_session: Path):
        debrief = build_debrief(sample_session)
        assert len(debrief.files_read) == 1
        assert "main.py" in debrief.files_read[0]

    def test_counts_test_runs(self, sample_session: Path):
        debrief = build_debrief(sample_session)
        assert debrief.test_runs == 1

    def test_counts_commits(self, sample_session: Path):
        debrief = build_debrief(sample_session)
        assert debrief.commits_made == 1

    def test_extracts_prompts(self, sample_session: Path):
        debrief = build_debrief(sample_session)
        assert len(debrief.human_prompts) == 2

    def test_derives_repos(self, sample_session: Path):
        debrief = build_debrief(sample_session)
        assert "organvm-engine" in debrief.repos_touched
        assert "organvm-mcp-server" in debrief.repos_touched

    def test_returns_none_for_missing(self, tmp_path: Path):
        result = build_debrief(tmp_path / "nonexistent.jsonl")
        assert result is None


class TestClassifyTodos:
    def test_extracts_future_work_from_prompts(self, sample_session: Path):
        debrief = build_debrief(sample_session)
        classify_todos(debrief)
        # "we still need to wire the dashboard later" should be extracted
        found = any("wire the dashboard" in t for t in debrief.medium_todos)
        assert found, f"Expected dashboard todo, got: {debrief.medium_todos}"

    def test_infers_memory_update(self):
        debrief = SessionDebrief(
            session_id="abc",
            agent="claude",
            project="test",
            duration_minutes=30,
            date="2026-03-08",
            files_written=["a.py", "b.py", "c.py"],
            files_edited=["d.py", "e.py"],
        )
        classify_todos(debrief)
        found = any("MEMORY" in t for t in debrief.small_todos)
        assert found

    def test_infers_commit_needed(self):
        debrief = SessionDebrief(
            session_id="abc",
            agent="claude",
            project="test",
            duration_minutes=30,
            date="2026-03-08",
            files_edited=["some_file.py"],
            commits_made=0,
        )
        classify_todos(debrief)
        found = any("commit" in t.lower() for t in debrief.small_todos)
        assert found

    def test_infers_tool_wiring_check(self):
        debrief = SessionDebrief(
            session_id="abc",
            agent="claude",
            project="test",
            duration_minutes=10,
            date="2026-03-08",
            files_written=["/path/to/tools/new_tool.py"],
        )
        classify_todos(debrief)
        found = any("server.py" in t for t in debrief.small_todos)
        assert found

    def test_deduplicates(self):
        debrief = SessionDebrief(
            session_id="abc",
            agent="claude",
            project="test",
            duration_minutes=10,
            date="2026-03-08",
            human_prompts=[
                "we still need to add tests for this",
                "we still need to add tests for this",
            ],
        )
        classify_todos(debrief)
        # Should not have duplicate entries
        lowered = [t.lower() for t in debrief.medium_todos]
        assert len(lowered) == len(set(lowered))


class TestRenderDebrief:
    def test_renders_markdown(self, sample_session: Path):
        debrief = build_debrief(sample_session)
        classify_todos(debrief)
        md = render_debrief(debrief)
        assert "# Session Debrief" in md
        assert "## Analysis" in md
        assert "## To-Dos" in md

    def test_renders_file_lists(self, sample_session: Path):
        debrief = build_debrief(sample_session)
        md = render_debrief(debrief)
        assert "Files Created" in md
        assert "Files Modified" in md

    def test_renders_empty_todos(self):
        debrief = SessionDebrief(
            session_id="abc",
            agent="claude",
            project="test",
            duration_minutes=5,
            date="2026-03-08",
        )
        md = render_debrief(debrief)
        assert "No to-dos extracted" in md


class TestToDict:
    def test_serializes(self, sample_session: Path):
        debrief = build_debrief(sample_session)
        classify_todos(debrief)
        d = debrief.to_dict()
        assert d["session_id"] == "session"  # derived from filename
        assert isinstance(d["big_todos"], list)
        assert isinstance(d["medium_todos"], list)
        assert isinstance(d["small_todos"], list)
        assert d["test_runs"] == 1
        assert d["commits_made"] == 1


class TestHelpers:
    def test_is_test_command_pytest(self):
        assert _is_test_command("pytest tests/ -v")

    def test_is_test_command_npm(self):
        assert _is_test_command("npm test")

    def test_is_test_command_false(self):
        assert not _is_test_command("ruff check src/")

    def test_is_commit_command(self):
        assert _is_commit_command("git commit -m 'feat: add tools'")

    def test_is_commit_command_false(self):
        assert not _is_commit_command("git status")

    def test_derive_repos(self):
        paths = [
            "/Users/test/Workspace/meta-organvm/organvm-engine/src/main.py",
            "/Users/test/Workspace/meta-organvm/organvm-mcp-server/src/server.py",
        ]
        repos = _derive_repos(paths)
        assert "organvm-engine" in repos
        assert "organvm-mcp-server" in repos

    def test_derive_repos_empty(self):
        assert _derive_repos([]) == []

    def test_short_path_meta(self):
        result = _short_path("/Users/test/Workspace/meta-organvm/organvm-engine/src/main.py")
        assert result == "organvm-engine/src/main.py"

    def test_short_path_fallback(self):
        result = _short_path("/some/random/path/file.py")
        assert "file.py" in result
