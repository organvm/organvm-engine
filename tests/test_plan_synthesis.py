"""Tests for plans/synthesis.py — organ-level plan aggregation."""

from __future__ import annotations

from datetime import date, timedelta

from organvm_engine.plans.index import PlanEntry
from organvm_engine.plans.synthesis import OrganPlanSummary, synthesize_all, synthesize_organ

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(
    organ="III", repo="repo-a", agent="claude", slug="plan-a",
    task_count=5, completed_count=2, tags=None, file_refs=None,
    status="active", date="2026-03-01",
) -> PlanEntry:
    return PlanEntry(
        qualified_id=f"{agent}:{organ}:{repo}:{slug}",
        path=f"/fake/{slug}.md",
        agent=agent,
        organ=organ,
        repo=repo,
        slug=slug,
        date=date,
        version=1,
        status=status,
        title=f"Plan {slug}",
        size_bytes=1000,
        has_verification=False,
        archetype="checkbox",
        task_count=task_count,
        completed_count=completed_count,
        tags=tags or [],
        file_refs=file_refs or [],
        domain_fingerprint="abc",
    )


# ---------------------------------------------------------------------------
# synthesize_organ
# ---------------------------------------------------------------------------

class TestSynthesizeOrgan:
    def test_basic_counts(self):
        entries = [
            _entry(task_count=10, completed_count=5),
            _entry(slug="b", task_count=6, completed_count=6),
        ]
        s = synthesize_organ("III", entries)
        assert s.organ_key == "III"
        assert s.total_plans == 2
        assert s.active_plans == 2
        assert s.total_tasks == 16
        assert s.completed_tasks == 11
        assert abs(s.completion_pct - 68.8) < 0.1

    def test_agents_active(self):
        entries = [
            _entry(agent="claude"),
            _entry(slug="b", agent="gemini"),
            _entry(slug="c", agent="claude"),
        ]
        s = synthesize_organ("III", entries)
        assert s.agents_active == ["claude", "gemini"]

    def test_top_tags(self):
        entries = [
            _entry(tags=["python", "pytest", "fastapi"]),
            _entry(slug="b", tags=["python", "docker"]),
        ]
        s = synthesize_organ("III", entries)
        assert "python" in s.top_tags
        assert len(s.top_tags) <= 10

    def test_cross_organ_refs(self):
        entries = [
            _entry(file_refs=["organvm-i-theoria/lib/src/x.py"]),
        ]
        s = synthesize_organ("III", entries)
        assert "I" in s.cross_organ_refs

    def test_no_cross_organ_for_own_organ(self):
        entries = [
            _entry(organ="III", file_refs=["organvm-iii-ergon/foo/src/x.py"]),
        ]
        s = synthesize_organ("III", entries)
        assert "III" not in s.cross_organ_refs

    def test_stale_count(self):
        entries = [
            _entry(date="2025-01-01", task_count=3, completed_count=0),
            _entry(
                slug="b",
                date=(date.today() - timedelta(days=2)).isoformat(),  # recent (relative)
                task_count=3,
                completed_count=0,
            ),
        ]
        s = synthesize_organ("III", entries, stale_days=30)
        assert s.stale_count == 1  # Only the far-past entry is stale

    def test_empty_entries(self):
        s = synthesize_organ("III", [])
        assert s.total_plans == 0
        assert s.completion_pct == 0.0
        assert s.agents_active == []

    def test_no_tasks_zero_completion(self):
        entries = [_entry(task_count=0, completed_count=0)]
        s = synthesize_organ("III", entries)
        assert s.completion_pct == 0.0

    def test_archived_not_counted_active(self):
        entries = [
            _entry(status="active"),
            _entry(slug="b", status="archived"),
        ]
        s = synthesize_organ("III", entries)
        assert s.total_plans == 2
        assert s.active_plans == 1


# ---------------------------------------------------------------------------
# synthesize_all
# ---------------------------------------------------------------------------

class TestSynthesizeAll:
    def test_groups_by_organ(self):
        entries = [
            _entry(organ="I", slug="a"),
            _entry(organ="III", slug="b"),
            _entry(organ="III", slug="c"),
        ]
        result = synthesize_all(entries)
        assert "I" in result
        assert "III" in result
        assert result["I"].total_plans == 1
        assert result["III"].total_plans == 2

    def test_empty_entries(self):
        result = synthesize_all([])
        assert result == {}

    def test_unknown_organ(self):
        entries = [_entry(organ=None)]
        result = synthesize_all(entries)
        assert "unknown" in result

    def test_all_organs_have_summaries(self):
        entries = [
            _entry(organ="I"),
            _entry(organ="II", slug="b"),
            _entry(organ="META", slug="c"),
        ]
        result = synthesize_all(entries)
        assert len(result) == 3
        for key, summary in result.items():
            assert isinstance(summary, OrganPlanSummary)
            assert summary.organ_key == key
