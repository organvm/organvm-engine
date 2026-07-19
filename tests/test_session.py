"""Tests for session transcript parsing and export."""

import json
from datetime import datetime, timezone
from pathlib import Path

from organvm_engine.session.parser import (
    SessionExport,
    SessionMeta,
    _extract_assistant_actions,
    _extract_human_text,
    _fence,
    _read_cwd_from_project,
    _render_tool_use_unabridged,
    find_session,
    list_projects,
    list_sessions,
    parse_session,
    render_prompts,
    render_transcript_unabridged,
)


def _make_jsonl(tmp_path: Path, messages: list[dict], name: str = "abc123.jsonl") -> Path:
    """Write a list of message dicts as a .jsonl file."""
    f = tmp_path / name
    with f.open("w", encoding="utf-8") as fh:
        for msg in messages:
            fh.write(json.dumps(msg) + "\n")
    return f


def _user_msg(text: str, ts: str = "2026-03-06T10:00:00Z", **extra) -> dict:
    return {
        "type": "user",
        "sessionId": "test-session-001",
        "slug": "test-slug",
        "cwd": "/Users/test/Workspace/project",
        "gitBranch": "main",
        "timestamp": ts,
        "message": {"role": "user", "content": text},
        **extra,
    }


def _assistant_msg(text: str = "response", ts: str = "2026-03-06T10:01:00Z",
                   tools: list[str] | None = None) -> dict:
    content: list[dict] = [{"type": "text", "text": text}]
    if tools:
        for t in tools:
            content.append({"type": "tool_use", "name": t, "input": {}})
    return {
        "type": "assistant",
        "sessionId": "test-session-001",
        "slug": "test-slug",
        "cwd": "/Users/test/Workspace/project",
        "gitBranch": "main",
        "timestamp": ts,
        "message": {"role": "assistant", "content": content},
    }


class TestParseSession:
    def test_basic_parse(self, tmp_path):
        f = _make_jsonl(tmp_path, [
            _user_msg("Hello world", ts="2026-03-06T10:00:00Z"),
            _assistant_msg("Hi there", ts="2026-03-06T10:01:00Z"),
            _user_msg("Do something", ts="2026-03-06T10:02:00Z"),
            _assistant_msg("Done", ts="2026-03-06T10:03:00Z", tools=["Read", "Edit"]),
        ])

        meta = parse_session(f)
        assert meta is not None
        assert meta.session_id == "abc123"
        assert meta.slug == "test-slug"
        assert meta.cwd == "/Users/test/Workspace/project"
        assert meta.git_branch == "main"
        assert meta.human_messages == 2
        assert meta.assistant_messages == 2
        assert meta.message_count == 4
        assert meta.tools_used == {"Read": 1, "Edit": 1}
        assert meta.first_human_message == "Hello world"

    def test_timestamps(self, tmp_path):
        f = _make_jsonl(tmp_path, [
            _user_msg("start", ts="2026-03-06T10:00:00Z"),
            _assistant_msg("end", ts="2026-03-06T11:30:00Z"),
        ])

        meta = parse_session(f)
        assert meta is not None
        assert meta.started == datetime(2026, 3, 6, 10, 0, tzinfo=timezone.utc)
        assert meta.ended == datetime(2026, 3, 6, 11, 30, tzinfo=timezone.utc)
        assert meta.duration_minutes == 90
        assert meta.date_str == "2026-03-06"

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        assert parse_session(f) is None

    def test_nonexistent_file(self, tmp_path):
        assert parse_session(tmp_path / "nope.jsonl") is None

    def test_malformed_json_lines_skipped(self, tmp_path):
        f = tmp_path / "bad.jsonl"
        f.write_text('{"type":"user","sessionId":"x","slug":"s","cwd":"/c","gitBranch":"m","timestamp":"2026-03-06T10:00:00Z","message":{"role":"user","content":"hello"}}\n{bad json\n')
        meta = parse_session(f)
        assert meta is not None
        assert meta.human_messages == 1

    def test_tool_counting(self, tmp_path):
        f = _make_jsonl(tmp_path, [
            _user_msg("go"),
            _assistant_msg("ok", tools=["Read", "Read", "Write"]),
            _assistant_msg("done", tools=["Read", "Bash"]),
        ])
        meta = parse_session(f)
        assert meta is not None
        assert meta.tools_used == {"Read": 3, "Write": 1, "Bash": 1}

    def test_content_as_list(self, tmp_path):
        """Test user message with content as list of blocks."""
        f = _make_jsonl(tmp_path, [{
            "type": "user",
            "sessionId": "test-session-001",
            "slug": "test-slug",
            "cwd": "/test",
            "gitBranch": "main",
            "timestamp": "2026-03-06T10:00:00Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "This is a long enough message to pass the filter"},
                ],
            },
        }])
        meta = parse_session(f)
        assert meta is not None
        assert "long enough" in meta.first_human_message

    def test_no_timestamp_messages(self, tmp_path):
        f = _make_jsonl(tmp_path, [{
            "type": "user",
            "sessionId": "x",
            "slug": "s",
            "cwd": "/c",
            "gitBranch": "m",
            "message": {"role": "user", "content": "a message without timestamp padding"},
        }])
        meta = parse_session(f)
        assert meta is not None
        assert meta.started is None
        assert meta.duration_minutes is None


class TestListProjects:
    def test_lists_projects(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.parser.CLAUDE_PROJECTS_DIR", tmp_path)

        proj = tmp_path / "project-a"
        proj.mkdir()
        _make_jsonl(proj, [_user_msg("hi")], name="sess1.jsonl")
        _make_jsonl(proj, [_user_msg("bye")], name="sess2.jsonl")

        proj2 = tmp_path / "project-b"
        proj2.mkdir()
        _make_jsonl(proj2, [_user_msg("test")], name="sess3.jsonl")

        results = list_projects()
        assert len(results) == 2
        assert results[0]["session_count"] == 2
        assert results[1]["session_count"] == 1

    def test_empty_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.parser.CLAUDE_PROJECTS_DIR", tmp_path)
        assert list_projects() == []

    def test_nonexistent_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.parser.CLAUDE_PROJECTS_DIR", tmp_path / "nope")
        assert list_projects() == []


class TestListSessions:
    def test_lists_sessions_for_project(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.parser.CLAUDE_PROJECTS_DIR", tmp_path)

        proj = tmp_path / "myproj"
        proj.mkdir()
        _make_jsonl(proj, [
            _user_msg("first", ts="2026-03-06T10:00:00Z"),
            _assistant_msg("ok", ts="2026-03-06T10:05:00Z"),
        ], name="sess1.jsonl")
        _make_jsonl(proj, [
            _user_msg("second", ts="2026-03-07T10:00:00Z"),
        ], name="sess2.jsonl")

        sessions = list_sessions("myproj")
        assert len(sessions) == 2
        # Sorted newest first
        assert sessions[0].first_human_message == "second"
        assert sessions[1].first_human_message == "first"


class TestFindSession:
    def test_exact_match(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.parser.CLAUDE_PROJECTS_DIR", tmp_path)

        proj = tmp_path / "proj"
        proj.mkdir()
        _make_jsonl(proj, [_user_msg("hi")], name="abc-def-123.jsonl")

        result = find_session("abc-def-123")
        assert result is not None
        assert result.stem == "abc-def-123"

    def test_prefix_match(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.parser.CLAUDE_PROJECTS_DIR", tmp_path)

        proj = tmp_path / "proj"
        proj.mkdir()
        _make_jsonl(proj, [_user_msg("hi")], name="abc-def-123.jsonl")

        result = find_session("abc-def")
        assert result is not None
        assert result.stem == "abc-def-123"

    def test_ambiguous_prefix(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.parser.CLAUDE_PROJECTS_DIR", tmp_path)

        proj = tmp_path / "proj"
        proj.mkdir()
        _make_jsonl(proj, [_user_msg("hi")], name="abc-111.jsonl")
        _make_jsonl(proj, [_user_msg("hi")], name="abc-222.jsonl")

        assert find_session("abc") is None  # ambiguous

    def test_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.parser.CLAUDE_PROJECTS_DIR", tmp_path)
        assert find_session("nonexistent") is None


class TestReadCwdFromProject:
    def test_reads_cwd(self, tmp_path):
        _make_jsonl(tmp_path, [_user_msg("hi")], name="sess.jsonl")
        assert _read_cwd_from_project(tmp_path) == "/Users/test/Workspace/project"

    def test_fallback_on_empty(self, tmp_path):
        assert _read_cwd_from_project(tmp_path) == tmp_path.name


class TestSessionExport:
    def test_render(self, tmp_path):
        meta = SessionMeta(
            session_id="test-123",
            file_path=tmp_path / "test.jsonl",
            slug="test-slug",
            cwd="/Users/test/proj",
            git_branch="main",
            started=datetime(2026, 3, 6, 10, 0, tzinfo=timezone.utc),
            ended=datetime(2026, 3, 6, 11, 0, tzinfo=timezone.utc),
            message_count=50,
            human_messages=20,
            assistant_messages=30,
            tools_used={"Read": 10, "Write": 5},
            first_human_message="Build the thing",
            project_dir="test-proj",
        )

        export = SessionExport(meta=meta, slug="build-thing", output_path=tmp_path / "out.md")
        content = export.render()

        assert "2026-03-06" in content
        assert "build-thing" in content
        assert "test-123" in content
        assert "~60 min" in content
        assert "50 (20 human, 30 assistant)" in content
        assert "| Read | 10 |" in content
        assert "| Write | 5 |" in content
        assert "Build the thing" in content
        # Referential wires — render commands baked into the review
        assert "organvm session transcript test-123" in content
        assert "--unabridged" in content
        assert "organvm session prompts test-123" in content
        assert "Source JSONL" in content

    def test_export_write(self, tmp_path):
        meta = SessionMeta(
            session_id="test-456",
            file_path=tmp_path / "test.jsonl",
            slug="slug",
            cwd="/test",
            git_branch="feat",
            started=datetime(2026, 3, 6, 10, 0, tzinfo=timezone.utc),
            ended=datetime(2026, 3, 6, 10, 30, tzinfo=timezone.utc),
            message_count=10,
            human_messages=5,
            assistant_messages=5,
            tools_used={},
            first_human_message="test",
            project_dir="proj",
        )

        out = tmp_path / "sessions" / "2026-03-06--test-export.md"
        export = SessionExport(meta=meta, slug="test-export", output_path=out)
        content = export.render()

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")

        assert out.exists()
        assert "test-456" in out.read_text()


class TestExtractHumanText:
    def test_string_content(self):
        msg = {"message": {"content": "hello world"}}
        assert _extract_human_text(msg) == "hello world"

    def test_list_content(self):
        msg = {"message": {"content": [
            {"type": "text", "text": "first part"},
            {"type": "text", "text": "second part"},
        ]}}
        assert "first part" in _extract_human_text(msg)
        assert "second part" in _extract_human_text(msg)

    def test_empty(self):
        assert _extract_human_text({}) == ""
        assert _extract_human_text({"message": {}}) == ""


class TestExtractAssistantActions:
    def test_tool_use_actions(self):
        msg = {"message": {"content": [
            {"type": "text", "text": "Let me read that."},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/foo/bar.py"}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "git status"}},
        ]}}
        actions = _extract_assistant_actions(msg)
        assert len(actions) == 2
        assert "Read `/foo/bar.py`" in actions[0]
        assert "Bash: `git status`" in actions[1]

    def test_write_action(self):
        msg = {"message": {"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": "/out.md"}},
        ]}}
        actions = _extract_assistant_actions(msg)
        assert actions == ["Write `/out.md`"]

    def test_edit_action(self):
        msg = {"message": {"content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/src/app.py"}},
        ]}}
        assert _extract_assistant_actions(msg) == ["Edit `/src/app.py`"]

    def test_grep_glob(self):
        msg = {"message": {"content": [
            {"type": "tool_use", "name": "Grep", "input": {"pattern": "TODO", "path": "/src"}},
            {"type": "tool_use", "name": "Glob", "input": {"pattern": "**/*.py"}},
        ]}}
        actions = _extract_assistant_actions(msg)
        assert "Grep `TODO`" in actions[0]
        assert "Glob `**/*.py`" in actions[1]

    def test_unknown_tool(self):
        msg = {"message": {"content": [
            {"type": "tool_use", "name": "CustomTool", "input": {}},
        ]}}
        assert _extract_assistant_actions(msg) == ["CustomTool"]

    def test_no_tools(self):
        msg = {"message": {"content": [
            {"type": "text", "text": "just text"},
        ]}}
        assert _extract_assistant_actions(msg) == []

    def test_long_bash_truncated(self):
        long_cmd = "x" * 200
        msg = {"message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": long_cmd}},
        ]}}
        actions = _extract_assistant_actions(msg)
        assert len(actions[0]) < 200  # truncated


class TestRenderPrompts:
    def test_basic_prompt_extraction(self, tmp_path):
        f = _make_jsonl(tmp_path, [
            _user_msg("Implement the feature please", ts="2026-03-06T10:00:00Z"),
            _assistant_msg("ok", ts="2026-03-06T10:01:00Z", tools=["Read", "Write"]),
            _user_msg("Now check if it works correctly", ts="2026-03-06T10:05:00Z"),
            _assistant_msg("verified", ts="2026-03-06T10:06:00Z"),
        ])

        content = render_prompts(f)
        assert "### P1" in content
        assert "### P2" in content
        assert "Implement the feature please" in content
        assert "Now check if it works correctly" in content
        assert "(+5m)" in content  # elapsed time

    def test_actions_between_prompts(self, tmp_path):
        f = _make_jsonl(tmp_path, [
            _user_msg("Build it", ts="2026-03-06T10:00:00Z"),
            _assistant_msg("on it", ts="2026-03-06T10:01:00Z", tools=["Read", "Write"]),
            _user_msg("Check it", ts="2026-03-06T10:05:00Z"),
        ])

        content = render_prompts(f)
        assert "**Actions taken:**" in content
        assert "Read" in content

    def test_prompt_summary(self, tmp_path):
        f = _make_jsonl(tmp_path, [
            _user_msg("Implement the feature", ts="2026-03-06T10:00:00Z"),
            _assistant_msg("done"),
            _user_msg("Is there a bug here?", ts="2026-03-06T10:10:00Z"),
            _assistant_msg("no"),
            _user_msg("Fix the error in line 5", ts="2026-03-06T10:20:00Z"),
            _assistant_msg("fixed"),
        ])

        content = render_prompts(f)
        assert "## Prompt Summary" in content
        assert "**Total prompts:** 3" in content
        assert "Prompt Categories" in content
        assert "**Directives**" in content
        assert "**Questions**" in content
        assert "**Fixes**" in content

    def test_filters_tool_results(self, tmp_path):
        """Tool result messages (user turns carrying tool output) should be filtered."""
        messages = [
            _user_msg("Start the task with enough text to pass filter", ts="2026-03-06T10:00:00Z"),
            _assistant_msg("ok"),
            # Simulate a tool_result-only user message
            {
                "type": "user",
                "sessionId": "test-session-001",
                "slug": "test-slug",
                "cwd": "/test",
                "gitBranch": "main",
                "timestamp": "2026-03-06T10:01:00Z",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "abc", "content": "file contents here"},
                    ],
                },
            },
            _user_msg("Second real prompt with enough words", ts="2026-03-06T10:02:00Z"),
        ]
        f = _make_jsonl(tmp_path, messages)

        content = render_prompts(f)
        # Should have P1 and P2 but not a prompt for the tool_result
        assert "### P1" in content
        assert "### P2" in content
        assert "### P3" not in content

    def test_empty_session(self, tmp_path):
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        assert render_prompts(f) == ""


class TestFence:
    def test_basic(self):
        result = _fence("hello")
        assert result == "```\nhello\n```"

    def test_with_language(self):
        result = _fence("echo hi", "bash")
        assert result == "```bash\necho hi\n```"

    def test_escapes_inner_backticks(self):
        result = _fence("code with ``` inside")
        assert "~~~" in result
        assert "```" not in result.split("\n", 1)[1].rsplit("\n", 1)[0]


class TestRenderToolUseUnabridged:
    def test_read_tool(self):
        block = {"type": "tool_use", "name": "Read", "id": "abc123def456", "input": {"file_path": "/foo/bar.py"}}
        result = _render_tool_use_unabridged(block)
        assert "### Tool: Read" in result
        assert "`/foo/bar.py`" in result

    def test_write_tool_includes_content(self):
        block = {"type": "tool_use", "name": "Write", "id": "abc123def456",
                 "input": {"file_path": "/out.md", "content": "# Hello\nWorld"}}
        result = _render_tool_use_unabridged(block)
        assert "### Tool: Write" in result
        assert "# Hello" in result
        assert "World" in result
        assert "13 chars" in result

    def test_edit_tool_includes_diffs(self):
        block = {"type": "tool_use", "name": "Edit", "id": "abc123def456",
                 "input": {"file_path": "/src/app.py", "old_string": "foo", "new_string": "bar"}}
        result = _render_tool_use_unabridged(block)
        assert "old_string" in result
        assert "foo" in result
        assert "new_string" in result
        assert "bar" in result

    def test_bash_tool(self):
        block = {"type": "tool_use", "name": "Bash", "id": "abc123def456",
                 "input": {"command": "git status", "description": "Check git"}}
        result = _render_tool_use_unabridged(block)
        assert "git status" in result
        assert "Check git" in result

    def test_unknown_tool_dumps_json(self):
        block = {"type": "tool_use", "name": "CustomTool", "id": "abc123def456",
                 "input": {"key": "value"}}
        result = _render_tool_use_unabridged(block)
        assert "### Tool: CustomTool" in result
        assert '"key": "value"' in result


class TestRenderTranscriptUnabridged:
    def _assistant_with_thinking(self, thinking: str, text: str, ts: str = "2026-03-06T10:01:00Z",
                                  tools: list[dict] | None = None) -> dict:
        content: list[dict] = []
        if thinking:
            content.append({"type": "thinking", "thinking": thinking})
        content.append({"type": "text", "text": text})
        if tools:
            content.extend(tools)
        return {
            "type": "assistant",
            "sessionId": "test-session-001",
            "slug": "test-slug",
            "cwd": "/Users/test/Workspace/project",
            "gitBranch": "main",
            "timestamp": ts,
            "message": {"role": "assistant", "content": content},
        }

    def test_includes_thinking_blocks(self, tmp_path):
        f = _make_jsonl(tmp_path, [
            _user_msg("Build it"),
            self._assistant_with_thinking("I should read the file first", "Let me check."),
        ])
        content = render_transcript_unabridged(f)
        assert "### Thinking" in content
        assert "I should read the file first" in content

    def test_includes_full_write_content(self, tmp_path):
        write_tool = {"type": "tool_use", "name": "Write", "id": "tool-abc-123",
                      "input": {"file_path": "/out.py", "content": "def hello():\n    return 42"}}
        f = _make_jsonl(tmp_path, [
            _user_msg("Create the file"),
            self._assistant_with_thinking("", "Creating.", tools=[write_tool]),
        ])
        content = render_transcript_unabridged(f)
        assert "def hello():" in content
        assert "return 42" in content
        assert "### Tool: Write" in content

    def test_includes_edit_diffs(self, tmp_path):
        edit_tool = {"type": "tool_use", "name": "Edit", "id": "tool-edit-1",
                     "input": {"file_path": "/src/app.py", "old_string": "old code", "new_string": "new code"}}
        f = _make_jsonl(tmp_path, [
            _user_msg("Fix the bug"),
            self._assistant_with_thinking("The bug is on line 5", "Fixed.", tools=[edit_tool]),
        ])
        content = render_transcript_unabridged(f)
        assert "old code" in content
        assert "new code" in content
        assert "old_string" in content

    def test_includes_tool_results(self, tmp_path):
        """Tool results in user messages should be included."""
        messages = [
            _user_msg("Start"),
            {"type": "assistant", "sessionId": "test-session-001", "slug": "test-slug",
             "cwd": "/test", "gitBranch": "main", "timestamp": "2026-03-06T10:01:00Z",
             "message": {"role": "assistant", "content": [
                 {"type": "tool_use", "name": "Read", "id": "read-1", "input": {"file_path": "/foo.py"}},
             ]}},
            {"type": "user", "sessionId": "test-session-001", "slug": "test-slug",
             "cwd": "/test", "gitBranch": "main", "timestamp": "2026-03-06T10:01:01Z",
             "message": {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": "read-1",
                  "content": [{"type": "text", "text": "file contents here"}]},
             ]}},
        ]
        f = _make_jsonl(tmp_path, messages)
        content = render_transcript_unabridged(f)
        assert "Tool Result" in content
        assert "file contents here" in content

    def test_strips_system_reminders(self, tmp_path):
        messages = [
            {"type": "user", "sessionId": "test-session-001", "slug": "test-slug",
             "cwd": "/test", "gitBranch": "main", "timestamp": "2026-03-06T10:00:00Z",
             "message": {"role": "user",
                         "content": "real prompt <system-reminder>noise</system-reminder> more text"}},
            _assistant_msg("ok"),
        ]
        f = _make_jsonl(tmp_path, messages)
        content = render_transcript_unabridged(f)
        assert "real prompt" in content
        assert "noise" not in content
        assert "system-reminder" not in content

    def test_header_includes_metadata(self, tmp_path):
        f = _make_jsonl(tmp_path, [
            _user_msg("Hello", ts="2026-03-06T10:00:00Z"),
            _assistant_msg("Hi", ts="2026-03-06T10:30:00Z"),
        ])
        content = render_transcript_unabridged(f)
        assert "Full Transcript (Unabridged)" in content
        assert "test-slug" in content
        assert "organvm session transcript" in content
        assert "--unabridged" in content

    def test_empty_session(self, tmp_path):
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        assert render_transcript_unabridged(f) == ""

    def test_system_messages_included(self, tmp_path):
        messages = [
            {"type": "system", "sessionId": "test-session-001", "slug": "test-slug",
             "cwd": "/test", "gitBranch": "main", "timestamp": "2026-03-06T10:00:00Z",
             "message": {"role": "system", "content": "System context loaded"}},
            _user_msg("Start"),
            _assistant_msg("ok"),
        ]
        f = _make_jsonl(tmp_path, messages)
        content = render_transcript_unabridged(f)
        assert "System" in content
        assert "System context loaded" in content
