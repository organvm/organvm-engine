"""Regression tests for flat workspace context sync."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from organvm_engine.contextmd import AUTO_START
from organvm_engine.contextmd.sync import sync_all

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_sync_all_updates_repo_in_additional_flat_workspace_root(tmp_path, monkeypatch):
    import organvm_engine.contextmd.sync as sync_mod
    import organvm_engine.ledger.emit as ledger_emit
    import organvm_engine.pulse.emitter as pulse_emitter

    workspace = tmp_path / "workspace"
    flat_root = tmp_path / "flat"
    repo = flat_root / "recursive-engine"
    workspace.mkdir()
    repo.mkdir(parents=True)

    claude_md = repo / "CLAUDE.md"
    claude_md.write_text("# Recursive Engine\n")
    (repo / "seed.yaml").write_text(
        "repo: recursive-engine\n"
        "org: organvm-i-theoria\n"
        "produces:\n"
        "  - type: context-files\n"
        "    consumers: [META-ORGANVM]\n",
    )

    monkeypatch.setattr(sync_mod, "precompute_ammoi", lambda: None)
    monkeypatch.setattr(pulse_emitter, "emit_engine_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(ledger_emit, "testament_emit", lambda *args, **kwargs: None)

    result = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[flat_root],
    )

    content = claude_md.read_text()
    synced_line = next(line for line in content.splitlines() if "Last synced:" in line)
    synced_at = synced_line.split("Last synced: ", 1)[1].rstrip("*")

    assert result["errors"] == []
    assert str(claude_md) in result["updated"]
    assert AUTO_START in content
    assert "recursive-engine" in content
    assert "**Produces**" in content
    assert "`META-ORGANVM`" in content
    synced_dt = datetime.strptime(synced_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert datetime.now(timezone.utc) - synced_dt < timedelta(minutes=1)
