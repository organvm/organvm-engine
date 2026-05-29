"""Tests for plans/hygiene.py — sweep rules engine and archive operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from organvm_engine.plans.hygiene import (
    SweepCandidate,
    archive_plans,
    compute_archive_path,
    compute_sprawl,
    sweep_candidates,
)

# ---------------------------------------------------------------------------
# Lightweight PlanEntry stub
# ---------------------------------------------------------------------------


@dataclass
class FakePlanEntry:
    """Minimal stub matching the PlanEntry fields used by hygiene.py."""

    qualified_id: str = ""
    path: str = ""
    agent: str = "claude"
    organ: str | None = None
    repo: str | None = None
    slug: str = ""
    date: str = "2026-01-01"
    version: int = 1
    status: str = "active"
    title: str = ""
    size_bytes: int = 100
    has_verification: bool = False
    archetype: str | None = None
    task_count: int = 5
    completed_count: int = 0
    tags: list[str] = field(default_factory=list)
    file_refs: list[str] = field(default_factory=list)
    domain_fingerprint: str = ""


# ---------------------------------------------------------------------------
# compute_archive_path
# ---------------------------------------------------------------------------


class TestComputeArchivePath:
    def test_date_prefix_in_filename(self, tmp_path: Path):
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        plan = plans_dir / "2026-03-15-deploy-pipeline.md"
        plan.write_text("# Plan")
        result = compute_archive_path(plan)
        assert result == plans_dir / "archive" / "2026-03" / "2026-03-15-deploy-pipeline.md"

    def test_mtime_fallback(self, tmp_path: Path):
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        plan = plans_dir / "no-date-plan.md"
        plan.write_text("# Plan")
        result = compute_archive_path(plan)
        # Should use mtime-derived YYYY-MM
        assert "archive" in str(result)
        assert result.name == "no-date-plan.md"

    def test_collision_handling(self, tmp_path: Path):
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        archive_dir = plans_dir / "archive" / "2026-03"
        archive_dir.mkdir(parents=True)

        plan = plans_dir / "2026-03-01-dup.md"
        plan.write_text("# Plan")
        # Create the existing target to force collision
        existing = archive_dir / "2026-03-01-dup.md"
        existing.write_text("# Already here")

        result = compute_archive_path(plan)
        assert result.name == "2026-03-01-dup-2.md"
        assert result.parent == archive_dir

    def test_double_collision(self, tmp_path: Path):
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        archive_dir = plans_dir / "archive" / "2026-03"
        archive_dir.mkdir(parents=True)

        plan = plans_dir / "2026-03-01-dup.md"
        plan.write_text("# Plan")
        (archive_dir / "2026-03-01-dup.md").write_text("v1")
        (archive_dir / "2026-03-01-dup-2.md").write_text("v2")

        result = compute_archive_path(plan)
        assert result.name == "2026-03-01-dup-3.md"

    def test_nested_plans_ancestor(self, tmp_path: Path):
        plans_dir = tmp_path / "project" / "plans"
        sub = plans_dir / "sprint-1"
        sub.mkdir(parents=True)
        plan = sub / "2026-02-10-tasks.md"
        plan.write_text("# Sprint")
        result = compute_archive_path(plan)
        # Should find the plans/ ancestor
        assert "plans" in str(result)
        assert "archive" in str(result)

    def test_no_plans_ancestor_uses_parent(self, tmp_path: Path):
        # File not under any plans/ directory
        plan = tmp_path / "2026-01-01-orphan.md"
        plan.write_text("# Orphan")
        result = compute_archive_path(plan)
        # Fallback: tmp_path / archive / YYYY-MM / filename
        assert result.parent.parent.parent == tmp_path
        assert "archive" in str(result)
        assert result.name == "2026-01-01-orphan.md"


# ---------------------------------------------------------------------------
# sweep_candidates
# ---------------------------------------------------------------------------


class TestSweepCandidates:
    def test_superseded_entries(self):
        e = FakePlanEntry(
            qualified_id="p1",
            path="/plans/old.md",
            status="superseded",
            slug="deploy",
        )
        candidates = sweep_candidates([e])
        assert len(candidates) == 1
        assert candidates[0].reason == "superseded"
        assert candidates[0].confidence == "auto"

    def test_completed_entries(self):
        e = FakePlanEntry(
            qualified_id="p1",
            path="/plans/done.md",
            status="active",
            task_count=5,
            completed_count=5,
            slug="finished",
        )
        candidates = sweep_candidates([e])
        assert len(candidates) == 1
        assert candidates[0].reason == "completed"

    def test_orphan_subplan(self):
        parent = FakePlanEntry(
            qualified_id="parent",
            path="/plans/deploy.md",
            status="archived",
            slug="deploy",
            agent="claude",
        )
        child = FakePlanEntry(
            qualified_id="child",
            path="/plans/deploy-agent-a1b2c3d4.md",
            status="active",
            slug="deploy-agent-a1b2c3d4",
            agent="claude",
        )
        candidates = sweep_candidates([parent, child])
        orphan = [c for c in candidates if c.reason == "orphan_subplan"]
        assert len(orphan) == 1
        assert orphan[0].entry.qualified_id == "child"

    def test_orphan_no_parent_found(self):
        # Subplan with no matching parent at all -> orphan
        child = FakePlanEntry(
            qualified_id="orphan",
            path="/plans/ghost-agent-a1b2c3d4.md",
            status="active",
            slug="ghost-agent-a1b2c3d4",
            agent="claude",
        )
        candidates = sweep_candidates([child])
        assert len(candidates) == 1
        assert candidates[0].reason == "orphan_subplan"

    def test_stale_no_progress(self):
        e = FakePlanEntry(
            qualified_id="stale",
            path="/plans/old.md",
            status="active",
            date="2025-01-01",  # very old
            task_count=10,
            completed_count=0,
            slug="old-plan",
        )
        candidates = sweep_candidates([e], stale_days=14)
        stale = [c for c in candidates if c.reason == "stale"]
        assert len(stale) == 1
        assert stale[0].confidence == "review"

    def test_stale_zero_tasks(self):
        e = FakePlanEntry(
            qualified_id="empty-stale",
            path="/plans/empty.md",
            status="active",
            date="2025-01-01",
            task_count=0,
            completed_count=0,
            slug="empty",
        )
        candidates = sweep_candidates([e], stale_days=14)
        stale = [c for c in candidates if c.reason == "stale"]
        assert len(stale) == 1

    def test_not_stale_if_recent(self):
        e = FakePlanEntry(
            qualified_id="fresh",
            path="/plans/new.md",
            status="active",
            date=(date.today() - timedelta(days=2)).isoformat(),  # recent (relative, never rots)
            task_count=5,
            completed_count=0,
            slug="fresh",
        )
        candidates = sweep_candidates([e], stale_days=14)
        assert len(candidates) == 0

    def test_not_stale_if_progress(self):
        e = FakePlanEntry(
            qualified_id="progressing",
            path="/plans/wip.md",
            status="active",
            date="2025-01-01",
            task_count=10,
            completed_count=3,
            slug="wip",
        )
        candidates = sweep_candidates([e], stale_days=14)
        stale = [c for c in candidates if c.reason == "stale"]
        assert len(stale) == 0

    def test_skips_already_archived(self):
        e = FakePlanEntry(
            qualified_id="archived",
            path="/plans/archive/done.md",
            status="archived",
            slug="done",
        )
        candidates = sweep_candidates([e])
        assert len(candidates) == 0

    def test_no_duplicate_candidates(self):
        e = FakePlanEntry(
            qualified_id="dup",
            path="/plans/superseded.md",
            status="superseded",
            slug="superseded",
        )
        # Pass the same entry twice
        candidates = sweep_candidates([e, e])
        assert len(candidates) == 1


# ---------------------------------------------------------------------------
# archive_plans
# ---------------------------------------------------------------------------


class TestArchivePlans:
    def _make_candidate(
        self, src_path: Path, dst_path: Path, reason: str = "superseded",
    ) -> SweepCandidate:
        entry = FakePlanEntry(
            qualified_id="test",
            path=str(src_path),
            slug="test-plan",
        )
        return SweepCandidate(
            entry=entry,
            reason=reason,
            confidence="auto",
            archive_target=str(dst_path),
        )

    def test_dry_run_does_not_move(self, tmp_path: Path):
        src = tmp_path / "plans" / "old.md"
        src.parent.mkdir(parents=True)
        src.write_text("# Old plan")
        dst = tmp_path / "plans" / "archive" / "2026-03" / "old.md"

        c = self._make_candidate(src, dst)
        result = archive_plans([c], dry_run=True)

        assert result.moved == 1
        assert src.exists(), "File should not be moved in dry run"
        assert not dst.exists()
        assert any("WOULD MOVE" in d for d in result.details)

    def test_real_move(self, tmp_path: Path):
        src = tmp_path / "plans" / "old.md"
        src.parent.mkdir(parents=True)
        src.write_text("# Old plan")
        dst = tmp_path / "plans" / "archive" / "2026-03" / "old.md"

        c = self._make_candidate(src, dst)
        result = archive_plans([c], dry_run=False)

        assert result.moved == 1
        assert not src.exists(), "Source should be moved"
        assert dst.exists(), "Destination should exist"
        assert dst.read_text() == "# Old plan"

    def test_missing_source_skipped(self, tmp_path: Path):
        src = tmp_path / "plans" / "nonexistent.md"
        dst = tmp_path / "plans" / "archive" / "2026-03" / "nonexistent.md"

        c = self._make_candidate(src, dst)
        result = archive_plans([c], dry_run=False)

        assert result.skipped >= 1
        assert any("SKIP" in d for d in result.details)

    def test_multiple_candidates(self, tmp_path: Path):
        plans = tmp_path / "plans"
        plans.mkdir()
        candidates = []
        for i in range(3):
            src = plans / f"plan-{i}.md"
            src.write_text(f"# Plan {i}")
            dst = plans / "archive" / "2026-03" / f"plan-{i}.md"
            candidates.append(self._make_candidate(src, dst))

        result = archive_plans(candidates, dry_run=False)
        assert result.moved == 3
        assert all(not (plans / f"plan-{i}.md").exists() for i in range(3))

    def test_empty_candidates(self):
        result = archive_plans([], dry_run=False)
        assert result.moved == 0
        assert result.errors == []


# ---------------------------------------------------------------------------
# compute_sprawl
# ---------------------------------------------------------------------------


class TestComputeSprawl:
    def test_clean_level(self):
        entries = [
            FakePlanEntry(
                qualified_id=f"p{i}",
                path=f"/plans/plan-{i}.md",
                status="active",
                date="2026-03-15",
                slug=f"plan-{i}",
            )
            for i in range(5)
        ]
        sprawl = compute_sprawl(entries)
        assert sprawl.total_active == 5
        assert sprawl.sprawl_level == "clean"

    def test_growing_level(self):
        entries = [
            FakePlanEntry(
                qualified_id=f"p{i}",
                path=f"/plans/plan-{i}.md",
                status="active",
                date="2026-03-15",
                slug=f"plan-{i}",
            )
            for i in range(30)
        ]
        sprawl = compute_sprawl(entries)
        assert sprawl.total_active == 30
        assert sprawl.sprawl_level == "growing"

    def test_sprawling_level(self):
        entries = [
            FakePlanEntry(
                qualified_id=f"p{i}",
                path=f"/plans/plan-{i}.md",
                status="active",
                date="2026-03-15",
                slug=f"plan-{i}",
            )
            for i in range(60)
        ]
        sprawl = compute_sprawl(entries)
        assert sprawl.sprawl_level == "sprawling"

    def test_critical_level(self):
        entries = [
            FakePlanEntry(
                qualified_id=f"p{i}",
                path=f"/plans/plan-{i}.md",
                status="active",
                date="2026-03-15",
                slug=f"plan-{i}",
            )
            for i in range(120)
        ]
        sprawl = compute_sprawl(entries)
        assert sprawl.sprawl_level == "critical"

    def test_non_active_entries_excluded(self):
        entries = [
            FakePlanEntry(
                qualified_id="active",
                path="/plans/a.md",
                status="active",
                date="2026-03-15",
                slug="active",
            ),
            FakePlanEntry(
                qualified_id="archived",
                path="/plans/b.md",
                status="archived",
                date="2026-03-15",
                slug="archived",
            ),
            FakePlanEntry(
                qualified_id="superseded",
                path="/plans/c.md",
                status="superseded",
                date="2026-03-15",
                slug="superseded",
            ),
        ]
        sprawl = compute_sprawl(entries)
        assert sprawl.total_active == 1

    def test_oldest_untouched(self):
        entries = [
            FakePlanEntry(
                qualified_id="old",
                path="/plans/old.md",
                status="active",
                date="2025-01-01",
                slug="old",
            ),
            FakePlanEntry(
                qualified_id="new",
                path="/plans/new.md",
                status="active",
                date="2026-03-15",
                slug="new",
            ),
        ]
        sprawl = compute_sprawl(entries)
        assert sprawl.oldest_untouched_days > 300  # >1 year old

    def test_empty_entries(self):
        sprawl = compute_sprawl([])
        assert sprawl.total_active == 0
        assert sprawl.sweep_candidates == 0
        assert sprawl.sprawl_level == "clean"
        assert sprawl.oldest_untouched_days == 0

    def test_sweep_candidates_counted(self):
        entries = [
            FakePlanEntry(
                qualified_id="done",
                path="/plans/done.md",
                status="active",
                task_count=3,
                completed_count=3,
                date="2026-03-15",
                slug="done",
            ),
        ]
        sprawl = compute_sprawl(entries)
        assert sprawl.sweep_candidates == 1  # completed -> sweep candidate
