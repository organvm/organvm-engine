"""Tests for active handoff discovery and cleanup."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from organvm_engine.handoff import (
    clean_handoffs,
    inspect_repo_handoff,
    list_handoffs,
    parse_duration,
)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _write_handoff(
    repo: Path,
    *,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> Path:
    handoff = repo / ".conductor" / "active-handoff.md"
    handoff.parent.mkdir(parents=True)
    if created_at or expires_at:
        lines = ["---"]
        if created_at:
            lines.append(f"created_at: {_iso(created_at)}")
        if expires_at:
            lines.append(f"expires_at: {_iso(expires_at)}")
        lines.extend(["---", "# Active handoff", "Continue the task."])
        handoff.write_text("\n".join(lines) + "\n")
    else:
        handoff.write_text("# Active handoff\nContinue the task.\n")
    return handoff


def test_list_handoffs_classifies_active_stale_and_expired(tmp_path):
    now = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    workspace = tmp_path / "workspace"

    active_repo = workspace / "organ" / "active-repo"
    stale_repo = workspace / "organ" / "stale-repo"
    expired_repo = workspace / "organ" / "expired-repo"

    _write_handoff(
        active_repo,
        created_at=now - timedelta(hours=2),
        expires_at=now + timedelta(hours=12),
    )
    _write_handoff(
        stale_repo,
        created_at=now - timedelta(hours=60),
        expires_at=now + timedelta(hours=12),
    )
    _write_handoff(
        expired_repo,
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(minutes=1),
    )

    infos = list_handoffs(workspace, now=now)
    statuses = {info.repo: info.status for info in infos}

    assert statuses == {
        "active-repo": "active",
        "stale-repo": "stale",
        "expired-repo": "expired",
    }


def test_handoff_scan_skips_file_removed_after_discovery(tmp_path, monkeypatch):
    now = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    workspace = tmp_path / "workspace"
    handoff = _write_handoff(workspace / "organ" / "race-repo")

    def discover_then_remove(_root):
        if handoff.exists():
            handoff.unlink()
        return [handoff]

    monkeypatch.setattr("organvm_engine.handoff._discover_handoff_paths", discover_then_remove)

    assert list_handoffs(workspace, now=now) == []
    assert clean_handoffs(workspace, dry_run=False, now=now) == {
        "removed": [],
        "kept": [],
        "errors": [],
        "dry_run": False,
        "older_than": None,
    }


def test_missing_metadata_uses_mtime_for_staleness(tmp_path):
    now = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    repo = tmp_path / "repo"
    handoff = _write_handoff(repo)
    old = (now - timedelta(hours=72)).timestamp()
    os.utime(handoff, (old, old))

    info = inspect_repo_handoff(repo, now=now)

    assert info is not None
    assert info.status == "stale"
    assert info.created_at is None
    assert "created_at missing" in "; ".join(info.reasons)


def test_clean_handoffs_dry_run_then_write(tmp_path):
    now = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    workspace = tmp_path / "workspace"
    expired = _write_handoff(
        workspace / "organ" / "expired-repo",
        created_at=now - timedelta(hours=3),
        expires_at=now - timedelta(minutes=1),
    )
    fresh = _write_handoff(
        workspace / "organ" / "fresh-repo",
        created_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=3),
    )

    dry = clean_handoffs(workspace, dry_run=True, now=now)
    assert len(dry["removed"]) == 1
    assert expired.exists()
    assert fresh.exists()

    written = clean_handoffs(workspace, dry_run=False, now=now)
    assert len(written["removed"]) == 1
    assert not expired.exists()
    assert fresh.exists()


def test_clean_handoffs_older_than_removes_unexpired_old_file(tmp_path):
    now = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    workspace = tmp_path / "workspace"
    old_handoff = _write_handoff(
        workspace / "organ" / "old-repo",
        created_at=now - timedelta(days=8),
        expires_at=now + timedelta(days=1),
    )

    result = clean_handoffs(
        workspace,
        older_than=parse_duration("7d"),
        dry_run=False,
        now=now,
    )

    assert len(result["removed"]) == 1
    assert not old_handoff.exists()
