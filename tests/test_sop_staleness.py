"""Tests for SOP staleness cross-reference checks."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from organvm_engine.sop.discover import discover_sops
from organvm_engine.sop.staleness import FRESH, MISSING, STALE, audit_sop_staleness


def _write_repo_sop(repo: Path, *, reviewed: str | None, governed_paths: list[str]) -> None:
    sops_dir = repo / ".sops"
    sops_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "sop: true",
        "name: governed-pattern",
        "scope: repo",
    ]
    if reviewed is not None:
        lines.append(f"last_reviewed: {reviewed}")
    if governed_paths:
        lines.append("governed_paths:")
        lines.extend(f"  - {path}" for path in governed_paths)
    lines.extend(["---", "# Governed Pattern", ""])
    (sops_dir / "governed-pattern.md").write_text("\n".join(lines))


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "sample-repo"\n')
    return tmp_path


def _set_mtime(path: Path, value: str) -> None:
    timestamp = datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()
    os.utime(path, (timestamp, timestamp))


def test_detects_stale_sop_when_governed_code_is_newer(tmp_path):
    repo = _repo(tmp_path)
    code = repo / "src" / "feature.py"
    code.parent.mkdir()
    code.write_text("print('new')\n")
    _set_mtime(code, "2026-02-01T12:00:00")
    _write_repo_sop(repo, reviewed="2026-01-01", governed_paths=["src/feature.py"])

    entries = discover_sops(workspace=repo)
    report = audit_sop_staleness(entries, workspace=repo)

    assert report.passed is False
    assert len(report.stale) == 1
    assert report.stale[0].status == STALE
    assert report.stale[0].newest_path == code.resolve()


def test_marks_fresh_when_sop_review_is_newer_than_code(tmp_path):
    repo = _repo(tmp_path)
    code = repo / "src" / "feature.py"
    code.parent.mkdir()
    code.write_text("print('old')\n")
    _set_mtime(code, "2026-02-01T12:00:00")
    _write_repo_sop(repo, reviewed="2026-03-01", governed_paths=["src/feature.py"])

    entries = discover_sops(workspace=repo)
    report = audit_sop_staleness(entries, workspace=repo)

    assert report.passed is True
    assert len(report.fresh) == 1
    assert report.fresh[0].status == FRESH


def test_reports_missing_governed_path(tmp_path):
    repo = _repo(tmp_path)
    _write_repo_sop(repo, reviewed="2026-03-01", governed_paths=["src/missing.py"])

    entries = discover_sops(workspace=repo)
    report = audit_sop_staleness(entries, workspace=repo)

    assert report.passed is False
    assert len(report.missing) == 1
    assert report.missing[0].status == MISSING


def test_directory_governed_path_uses_newest_code_file(tmp_path):
    repo = _repo(tmp_path)
    old_code = repo / "src" / "old.py"
    new_code = repo / "src" / "new.py"
    old_code.parent.mkdir()
    old_code.write_text("print('old')\n")
    new_code.write_text("print('new')\n")
    _set_mtime(old_code, "2026-01-01T12:00:00")
    _set_mtime(new_code, "2026-03-01T12:00:00")
    _write_repo_sop(repo, reviewed="2026-02-01", governed_paths=["src/"])

    entries = discover_sops(workspace=repo)
    report = audit_sop_staleness(entries, workspace=repo)

    assert len(report.stale) == 1
    assert report.stale[0].newest_path == new_code.resolve()


def test_unmapped_sops_are_reported_separately(tmp_path):
    repo = _repo(tmp_path)
    _write_repo_sop(repo, reviewed=None, governed_paths=[])

    entries = discover_sops(workspace=repo)
    report = audit_sop_staleness(entries, workspace=repo)

    assert report.checks == []
    assert report.unmapped == entries
