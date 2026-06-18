"""Tests for context sync diff/changelog (issue #73 / LIMEN-050)."""

from organvm_engine.contextmd import AUTO_END, AUTO_START
from organvm_engine.contextmd.changelog import (
    RunChangelog,
    append_changelog,
    compute_change,
    load_changelog,
    render_changelog,
    render_changes,
)
from organvm_engine.contextmd.sync import _inject_section


class TestComputeChange:
    def test_created_counts_all_lines_as_added(self):
        section = f"{AUTO_START}\nline one\nline two\n{AUTO_END}"
        change = compute_change("CLAUDE.md", None, section, "created")
        assert change.action == "created"
        assert change.added == 4
        assert change.removed == 0
        assert change.diff.startswith("+")

    def test_updated_diffs_only_the_auto_block(self):
        old = (
            f"# Manual title\n\n{AUTO_START}\n## Old\nalpha\n{AUTO_END}\n\n## Manual\n"
        )
        new_section = f"{AUTO_START}\n## New\nbeta\n{AUTO_END}"
        change = compute_change("CLAUDE.md", old, new_section, "updated")
        assert change.action == "updated"
        assert change.added > 0
        assert change.removed > 0
        # Manual content outside the markers must never appear in the diff
        assert "Manual" not in change.diff
        assert "alpha" in change.diff
        assert "beta" in change.diff

    def test_unchanged_has_empty_diff(self):
        change = compute_change("CLAUDE.md", "whatever", "x", "unchanged")
        assert change.diff == ""
        assert change.added == 0


class TestInjectSectionCollectsChanges:
    def test_created_change_recorded(self, tmp_path):
        target = tmp_path / "CLAUDE.md"
        changes: list = []
        _inject_section(target, f"{AUTO_START}\nhi\n{AUTO_END}", changes=changes)
        assert len(changes) == 1
        assert changes[0].action == "created"

    def test_updated_change_recorded_with_diff(self, tmp_path):
        target = tmp_path / "CLAUDE.md"
        target.write_text(f"# T\n\n{AUTO_START}\nold\n{AUTO_END}\n")
        changes: list = []
        _inject_section(target, f"{AUTO_START}\nnew\n{AUTO_END}", changes=changes)
        assert changes[0].action == "updated"
        assert "old" in changes[0].diff
        assert "new" in changes[0].diff

    def test_unchanged_recorded_without_diff(self, tmp_path):
        section = f"{AUTO_START}\nsame\n{AUTO_END}"
        target = tmp_path / "CLAUDE.md"
        target.write_text(f"# T\n\n{section}\n")
        changes: list = []
        action = _inject_section(target, section, changes=changes)
        assert action == "unchanged"
        assert changes[0].action == "unchanged"
        assert changes[0].diff == ""

    def test_no_collector_keeps_string_return(self, tmp_path):
        target = tmp_path / "CLAUDE.md"
        action = _inject_section(target, "## Plain")
        assert action == "created"


class TestRunChangelog:
    def _sample(self):
        return RunChangelog(
            timestamp="2026-06-18T00:00:00+00:00",
            dry_run=False,
            changes=[
                compute_change("a/CLAUDE.md", None, f"{AUTO_START}\nx\n{AUTO_END}", "created"),
                compute_change(
                    "b/CLAUDE.md",
                    f"{AUTO_START}\nold\n{AUTO_END}",
                    f"{AUTO_START}\nnew\n{AUTO_END}",
                    "updated",
                ),
                compute_change("c/CLAUDE.md", "z", "z", "unchanged"),
            ],
        )

    def test_with_diffs_excludes_unchanged(self):
        run = self._sample()
        assert len(run.with_diffs()) == 2

    def test_partitions(self):
        run = self._sample()
        assert len(run.created) == 1
        assert len(run.updated) == 1

    def test_render_changes_summary_and_diff(self):
        run = self._sample()
        summary = render_changes(run, show_diff=False)
        assert "b/CLAUDE.md" in summary
        assert "new" not in summary  # no line-level diff without show_diff
        detailed = render_changes(run, show_diff=True)
        assert "new" in detailed

    def test_render_changes_empty(self):
        run = RunChangelog(changes=[compute_change("c", "z", "z", "unchanged")])
        assert "No context sections changed" in render_changes(run)

    def test_to_entry_counts(self):
        entry = self._sample().to_entry()
        assert entry["counts"]["created"] == 1
        assert entry["counts"]["updated"] == 1
        # only diffable changes are persisted
        assert len(entry["changes"]) == 2


class TestChangelogPersistence:
    def test_append_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "changelog.jsonl"
        run = RunChangelog(
            timestamp="2026-06-18T00:00:00+00:00",
            changes=[compute_change("a", None, f"{AUTO_START}\nx\n{AUTO_END}", "created")],
        )
        written = append_changelog(run, path)
        assert written == path
        entries = load_changelog(path)
        assert len(entries) == 1
        assert entries[0]["counts"]["created"] == 1

    def test_append_skips_empty_run(self, tmp_path):
        path = tmp_path / "changelog.jsonl"
        run = RunChangelog(changes=[compute_change("c", "z", "z", "unchanged")])
        assert append_changelog(run, path) is None
        assert not path.exists()

    def test_append_accumulates_runs(self, tmp_path):
        path = tmp_path / "changelog.jsonl"
        for _ in range(3):
            run = RunChangelog(
                timestamp="2026-06-18T00:00:00+00:00",
                changes=[compute_change("a", None, f"{AUTO_START}\nx\n{AUTO_END}", "created")],
            )
            append_changelog(run, path)
        assert len(load_changelog(path)) == 3

    def test_load_missing_returns_empty(self, tmp_path):
        assert load_changelog(tmp_path / "nope.jsonl") == []

    def test_render_changelog_history_and_limit(self, tmp_path):
        path = tmp_path / "changelog.jsonl"
        for i in range(3):
            run = RunChangelog(
                timestamp=f"2026-06-18T00:0{i}:00+00:00",
                changes=[compute_change("a", None, f"{AUTO_START}\nx\n{AUTO_END}", "created")],
            )
            append_changelog(run, path)
        entries = load_changelog(path)
        rendered = render_changelog(entries, limit=2)
        assert "Context Sync History" in rendered
        assert "earlier run(s) not shown" in rendered

    def test_render_changelog_empty(self):
        assert "No context-sync history" in render_changelog([])
