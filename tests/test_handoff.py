from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from organvm_engine.cli import main
from organvm_engine.contextmd.sync import sync_repo
from organvm_engine.handoff import (
    clean_handoffs,
    discover_handoffs,
    parse_duration,
    render_context_handoff_warning,
)
from organvm_engine.registry.loader import load_registry

FIXTURES = Path(__file__).parent / "fixtures"


def _write_handoff(repo: Path, *, created_at: datetime, expires_at: datetime | None = None) -> Path:
    handoff = repo / ".conductor" / "active-handoff.md"
    handoff.parent.mkdir(parents=True)
    expires_line = f"expires_at: {expires_at.isoformat()}\n" if expires_at else ""
    handoff.write_text(
        "---\n"
        f"created_at: {created_at.isoformat()}\n"
        f"{expires_line}"
        "---\n\n"
        "# Active Handoff\n\n"
        "Constraints here.\n",
        encoding="utf-8",
    )
    return handoff


def test_discover_handoffs_parses_metadata_and_workspace_repo(tmp_path):
    now = datetime(2026, 6, 18, 12, tzinfo=timezone.utc)
    repo = tmp_path / "meta-organvm" / "organvm-engine"
    repo.mkdir(parents=True)
    _write_handoff(
        repo,
        created_at=now - timedelta(hours=2),
        expires_at=now + timedelta(hours=46),
    )

    entries = discover_handoffs(tmp_path, include_additional_roots=False, now=now)

    assert len(entries) == 1
    assert entries[0].repo == "organvm-engine"
    assert entries[0].organ == "meta-organvm"
    assert entries[0].status(now) == "active"
    assert entries[0].metadata_source == "frontmatter"


def test_stale_handoff_renders_context_warning(tmp_path):
    now = datetime(2026, 6, 18, 12, tzinfo=timezone.utc)
    repo = tmp_path / "meta-organvm" / "organvm-engine"
    repo.mkdir(parents=True)
    path = _write_handoff(repo, created_at=now - timedelta(hours=72))
    entry = discover_handoffs(tmp_path, include_additional_roots=False, now=now)[0]

    warning = render_context_handoff_warning(entry, now=now)

    assert path.exists()
    assert "Handoff Staleness Warning" in warning
    assert "STALE" in warning
    assert "3d" in warning


def test_clean_handoffs_removes_expired_files(tmp_path):
    now = datetime(2026, 6, 18, 12, tzinfo=timezone.utc)
    repo = tmp_path / "meta-organvm" / "organvm-engine"
    repo.mkdir(parents=True)
    path = _write_handoff(
        repo,
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(hours=1),
    )

    result = clean_handoffs(
        tmp_path,
        older_than=parse_duration("7d"),
        include_additional_roots=False,
        now=now,
    )

    assert len(result.removed) == 1
    assert result.errors == []
    assert not path.exists()


def test_handoff_list_cli_outputs_json(tmp_path, capsys):
    now = datetime.now(timezone.utc)
    repo = tmp_path / "meta-organvm" / "organvm-engine"
    repo.mkdir(parents=True)
    _write_handoff(repo, created_at=now - timedelta(hours=1))

    with patch(
        "sys.argv",
        ["organvm", "handoff", "list", "--workspace", str(tmp_path), "--json"],
    ):
        rc = main()

    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["repo"] == "organvm-engine"
    assert data[0]["status"] == "active"


def test_sync_repo_injects_stale_handoff_warning(tmp_path):
    now = datetime.now(timezone.utc)
    registry = load_registry(FIXTURES / "registry-minimal.json")
    repo = tmp_path / "organvm-i-theoria" / "recursive-engine"
    repo.mkdir(parents=True)
    _write_handoff(repo, created_at=now - timedelta(hours=72))

    result = sync_repo(repo, "recursive-engine", "organvm-i-theoria", registry)
    content = (repo / "CLAUDE.md").read_text(encoding="utf-8")

    assert result["action"] == "created"
    assert "Handoff Staleness Warning" in content
    assert "created_at" in content
    assert "expires_at" in content
