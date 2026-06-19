"""Tests for SOP staleness detection."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from organvm_engine.cli import main
from organvm_engine.sop.discover import discover_sops
from organvm_engine.sop.staleness import (
    audit_sop_staleness,
    load_sop_code_mappings,
    stale_results,
)


def _write_repo_sop(repo: Path, name: str) -> Path:
    sops_dir = repo / ".sops"
    sops_dir.mkdir(parents=True, exist_ok=True)
    path = sops_dir / f"{name}.md"
    path.write_text(
        "---\n"
        "sop: true\n"
        f"name: {name}\n"
        "scope: repo\n"
        "phase: any\n"
        "triggers: []\n"
        "complements: []\n"
        "overrides: null\n"
        "---\n"
        f"# {name}\n",
    )
    return path


def _write_seed(repo: Path, sop: str, governed_paths: list[str]) -> Path:
    seed = repo / "seed.yaml"
    seed.write_text(
        "repo: organvm-engine\n"
        "org: meta-organvm\n"
        "produces: []\n"
        "consumes: []\n"
        "sop_governance:\n"
        f"  - sop: {sop}\n"
        "    paths:\n"
        + "".join(f"      - {path}\n" for path in governed_paths),
    )
    return seed


def _workspace_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "meta-organvm" / "organvm-engine"
    repo.mkdir(parents=True)
    return repo


def test_loads_mappings_from_seed_yaml(tmp_path):
    repo = _workspace_repo(tmp_path)
    _write_seed(repo, "cli-module-pattern", ["src/organvm_engine/cli/"])

    mappings = load_sop_code_mappings(workspace=tmp_path)

    assert len(mappings) == 1
    assert mappings[0].sop_name == "cli-module-pattern"
    assert mappings[0].paths == ("src/organvm_engine/cli/",)
    assert mappings[0].base_dir == repo
    assert mappings[0].repo == "organvm-engine"


def test_reports_stale_when_code_is_newer_than_sop(tmp_path):
    repo = _workspace_repo(tmp_path)
    sop = _write_repo_sop(repo, "cli-module-pattern")
    code = repo / "src" / "organvm_engine" / "cli" / "sop.py"
    code.parent.mkdir(parents=True)
    code.write_text("def cmd():\n    return 0\n")
    _write_seed(repo, "cli-module-pattern", ["src/organvm_engine/cli/sop.py"])
    os.utime(sop, (1000, 1000))
    os.utime(code, (2000, 2000))

    entries = discover_sops(workspace=tmp_path)
    mappings = load_sop_code_mappings(workspace=tmp_path)
    results = audit_sop_staleness(entries, mappings)

    assert len(results) == 1
    assert results[0].status == "stale"
    assert results[0].newest_code_path == code
    assert stale_results(results) == results


def test_reports_fresh_when_sop_is_newer_than_code(tmp_path):
    repo = _workspace_repo(tmp_path)
    sop = _write_repo_sop(repo, "cli-module-pattern")
    code = repo / "src" / "organvm_engine" / "cli" / "sop.py"
    code.parent.mkdir(parents=True)
    code.write_text("def cmd():\n    return 0\n")
    _write_seed(repo, "cli-module-pattern", ["src/organvm_engine/cli/sop.py"])
    os.utime(sop, (3000, 3000))
    os.utime(code, (2000, 2000))

    results = audit_sop_staleness(
        discover_sops(workspace=tmp_path),
        load_sop_code_mappings(workspace=tmp_path),
    )

    assert results[0].status == "fresh"
    assert stale_results(results) == []


def test_reports_missing_code_for_unmatched_mapping_path(tmp_path):
    repo = _workspace_repo(tmp_path)
    _write_repo_sop(repo, "cli-module-pattern")
    _write_seed(repo, "cli-module-pattern", ["src/missing.py"])

    results = audit_sop_staleness(
        discover_sops(workspace=tmp_path),
        load_sop_code_mappings(workspace=tmp_path),
    )

    assert results[0].status == "missing-code"
    assert results[0].missing_paths == [repo / "src" / "missing.py"]


def test_reports_missing_sop_for_unmatched_mapping(tmp_path):
    repo = _workspace_repo(tmp_path)
    _write_seed(repo, "cli-module-pattern", ["seed.yaml"])

    results = audit_sop_staleness(
        discover_sops(workspace=tmp_path),
        load_sop_code_mappings(workspace=tmp_path),
    )

    assert results[0].status == "missing-sop"


def test_directory_mapping_uses_newest_nested_file(tmp_path):
    repo = _workspace_repo(tmp_path)
    sop = _write_repo_sop(repo, "cli-module-pattern")
    old_code = repo / "src" / "organvm_engine" / "cli" / "old.py"
    new_code = repo / "src" / "organvm_engine" / "cli" / "nested" / "new.py"
    old_code.parent.mkdir(parents=True)
    new_code.parent.mkdir(parents=True)
    old_code.write_text("old = True\n")
    new_code.write_text("new = True\n")
    _write_seed(repo, "cli-module-pattern", ["src/organvm_engine/cli/"])
    os.utime(sop, (1500, 1500))
    os.utime(old_code, (1000, 1000))
    os.utime(new_code, (2000, 2000))

    results = audit_sop_staleness(
        discover_sops(workspace=tmp_path),
        load_sop_code_mappings(workspace=tmp_path),
    )

    assert results[0].status == "stale"
    assert results[0].newest_code_path == new_code


def test_sop_audit_stale_json_output(tmp_path, capsys):
    repo = _workspace_repo(tmp_path)
    sop = _write_repo_sop(repo, "cli-module-pattern")
    code = repo / "src" / "organvm_engine" / "cli" / "sop.py"
    code.parent.mkdir(parents=True)
    code.write_text("def cmd():\n    return 0\n")
    _write_seed(repo, "cli-module-pattern", ["src/organvm_engine/cli/sop.py"])
    os.utime(sop, (1000, 1000))
    os.utime(code, (2000, 2000))

    with patch("sys.argv", ["organvm", "sop", "--workspace", str(tmp_path), "audit", "--stale", "--json"]):
        rc = main()

    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["staleness"][0]["sop"] == "cli-module-pattern"
    assert data["staleness"][0]["status"] == "stale"
