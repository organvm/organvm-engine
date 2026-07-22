"""Tests for SOP governed-code staleness detection."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from organvm_engine.cli import build_parser
from organvm_engine.cli.sop import cmd_sop_stale
from organvm_engine.sop.discover import SOPEntry, discover_repo_sops
from organvm_engine.sop.staleness import audit_sop_staleness


def _write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or f"# {path.name}\n", encoding="utf-8")
    return path


def _set_mtime(path: Path, timestamp: int) -> None:
    os.utime(path, (timestamp, timestamp))


def _sop_entry(path: Path, governs: list[str] | None = None) -> SOPEntry:
    return SOPEntry(
        path=path,
        org="local",
        repo="repo",
        filename=path.name,
        title=None,
        doc_type="SOP-SKILL",
        canonical=False,
        has_canonical_header=False,
        scope="repo",
        sop_name=path.stem,
        governs=governs or [],
    )


def _sop_frontmatter(name: str, governs: list[str]) -> str:
    refs = "\n".join(f"  - {ref}" for ref in governs)
    return (
        "---\n"
        "sop: true\n"
        f"name: {name}\n"
        "scope: repo\n"
        "phase: any\n"
        "triggers: []\n"
        "complements: []\n"
        "overrides: null\n"
        "governs:\n"
        f"{refs}\n"
        "---\n"
        f"# {name}\n"
    )


def test_discover_repo_sops_parses_governs(tmp_path: Path) -> None:
    sop = _write(
        tmp_path / ".sops" / "cli-pattern.md",
        _sop_frontmatter("cli-pattern", ["src/organvm_engine/cli/*.py", "tests/test_cli.py"]),
    )

    entries = discover_repo_sops(tmp_path)

    assert len(entries) == 1
    assert entries[0].path == sop
    assert entries[0].governs == ["src/organvm_engine/cli/*.py", "tests/test_cli.py"]


def test_discover_repo_sops_parses_dict_governs(tmp_path: Path) -> None:
    _write(
        tmp_path / ".sops" / "typed.md",
        (
            "---\n"
            "sop: true\n"
            "name: typed\n"
            "scope: repo\n"
            "governs:\n"
            "  - path: src/typed.py\n"
            "---\n"
            "# typed\n"
        ),
    )

    entries = discover_repo_sops(tmp_path)

    assert entries[0].governs == ["src/typed.py"]


def test_stale_when_governed_code_newer_than_sop(tmp_path: Path) -> None:
    sop = _write(tmp_path / ".sops" / "foo.md")
    code = _write(tmp_path / "src" / "foo.py", "print('new')\n")
    _set_mtime(sop, 1_700_000_000)
    _set_mtime(code, 1_700_086_400)

    report = audit_sop_staleness([_sop_entry(sop, ["src/foo.py"])], repo_root=tmp_path)

    assert report.checked_refs == 1
    assert len(report.stale) == 1
    assert report.stale[0].code_path == code
    assert report.stale[0].days_stale == 1
    assert report.has_failures()


def test_fresh_when_sop_newer_than_governed_code(tmp_path: Path) -> None:
    sop = _write(tmp_path / ".sops" / "foo.md")
    code = _write(tmp_path / "src" / "foo.py")
    _set_mtime(code, 1_700_000_000)
    _set_mtime(sop, 1_700_086_400)

    report = audit_sop_staleness([_sop_entry(sop, ["src/foo.py"])], repo_root=tmp_path)

    assert report.fresh_refs == 1
    assert report.stale == []
    assert not report.has_failures()


def test_missing_governed_code_path_is_reported(tmp_path: Path) -> None:
    sop = _write(tmp_path / ".sops" / "foo.md")

    report = audit_sop_staleness([_sop_entry(sop, ["src/missing.py"])], repo_root=tmp_path)

    assert len(report.missing) == 1
    assert report.missing[0].pattern == "src/missing.py"
    assert report.has_failures()


def test_unlinked_sop_is_reported_but_not_strict_failure_by_default(tmp_path: Path) -> None:
    sop = _write(tmp_path / ".sops" / "foo.md")

    report = audit_sop_staleness([_sop_entry(sop)], repo_root=tmp_path)

    assert len(report.unlinked) == 1
    assert not report.has_failures()
    assert report.has_failures(require_governs=True)


def test_glob_and_directory_governed_refs_expand_code_files(tmp_path: Path) -> None:
    sop = _write(tmp_path / ".sops" / "foo.md")
    globbed = _write(tmp_path / "src" / "foo.py")
    nested = _write(tmp_path / "pkg" / "nested" / "bar.ts")
    _write(tmp_path / "pkg" / "README.md")
    _set_mtime(globbed, 1_700_000_000)
    _set_mtime(nested, 1_700_000_000)
    _set_mtime(sop, 1_700_086_400)

    report = audit_sop_staleness(
        [_sop_entry(sop, ["src/*.py", "pkg"])],
        repo_root=tmp_path,
    )

    assert report.checked_refs == 2
    assert report.fresh_refs == 2
    assert report.stale == []


def test_sop_stale_parser_reaches_new_subcommand() -> None:
    parser = build_parser()

    args = parser.parse_args(["sop", "stale", "--repo-root", ".", "--json", "--strict"])

    assert args.command == "sop"
    assert args.subcommand == "stale"
    assert args.repo_root == "."
    assert args.json is True
    assert args.strict is True


def test_cmd_sop_stale_json_strict_returns_failure_for_stale_ref(
    tmp_path: Path,
    capsys,
) -> None:
    sop = _write(
        tmp_path / ".sops" / "foo.md",
        _sop_frontmatter("foo", ["src/foo.py"]),
    )
    code = _write(tmp_path / "src" / "foo.py")
    _set_mtime(sop, 1_700_000_000)
    _set_mtime(code, 1_700_086_400)
    args = SimpleNamespace(
        repo_root=str(tmp_path),
        json=True,
        strict=True,
        require_governs=False,
        linked_only=False,
    )

    rc = cmd_sop_stale(args)

    assert rc == 1
    data = json.loads(capsys.readouterr().out)
    assert data["stale_refs"] == 1
    assert data["issues"][0]["status"] == "stale"
