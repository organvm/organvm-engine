"""Tests for content pipeline cadence checker."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from organvm_engine.content.cadence import check_cadence
from organvm_engine.content.reader import ContentPost


def _post(slug: str, d: str, status: str = "draft") -> ContentPost:
    """Helper: create a ContentPost with minimal fields."""
    return ContentPost(
        slug=slug, title=slug, date=d, hook="", status=status,
        source_session="", context="", tags=[], distribution={},
        engagement={}, redacted_items=[], directory=Path(f"/fake/{d}-{slug}"),
    )


def test_check_cadence_empty():
    report = check_cadence([])
    assert report.total_posts == 0
    assert report.streak == 0
    assert report.last_post_date is None
    assert report.posts_this_week == []


def test_check_cadence_single_post_this_week():
    ref = date(2026, 6, 2)
    posts = [_post("today", ref.isoformat())]
    report = check_cadence(posts, reference_date=ref)
    assert report.total_posts == 1
    assert len(report.posts_this_week) == 1
    assert report.streak >= 1
    assert report.last_post_date == ref.isoformat()


def test_check_cadence_counts_statuses():
    posts = [
        _post("a", "2026-03-10", status="draft"),
        _post("b", "2026-03-11", status="published"),
        _post("c", "2026-03-12", status="archived"),
        _post("d", "2026-03-13", status="draft"),
    ]
    report = check_cadence(posts, reference_date=date(2026, 6, 2))
    assert report.draft_count == 2
    assert report.published_count == 1
    assert report.archived_count == 1


def test_check_cadence_streak_consecutive_weeks():
    today = date(2026, 6, 2)
    posts = [
        _post("a", today.isoformat()),
        _post("b", (today - timedelta(weeks=1)).isoformat()),
        _post("c", (today - timedelta(weeks=2)).isoformat()),
    ]
    report = check_cadence(posts, reference_date=today)
    assert report.streak == 3


def test_check_cadence_streak_broken():
    today = date(2026, 6, 2)
    posts = [
        _post("a", today.isoformat()),
        _post("b", (today - timedelta(weeks=3)).isoformat()),
    ]
    report = check_cadence(posts, reference_date=today)
    assert report.streak == 1


def test_check_cadence_weeks_since_last_post():
    today = date(2026, 6, 2)
    two_weeks_ago = today - timedelta(weeks=2)
    posts = [_post("old", two_weeks_ago.isoformat())]
    report = check_cadence(posts, reference_date=today)
    assert report.weeks_since_last_post >= 2


def test_check_cadence_no_post_this_week():
    ref = date(2026, 6, 2)
    old_date = (ref - timedelta(weeks=5)).isoformat()
    posts = [_post("ancient", old_date)]
    report = check_cadence(posts, reference_date=ref)
    assert report.posts_this_week == []


def test_check_cadence_multiple_posts_same_week():
    ref = date(2026, 6, 3)  # Wednesday
    d1 = ref.isoformat()
    d2 = (ref - timedelta(days=1)).isoformat()  # Tuesday
    posts = [_post("a", d1), _post("b", d2)]
    report = check_cadence(posts, reference_date=ref)
    assert report.streak == 1
    assert len(report.posts_this_week) == 2
