"""Tests for the IRF CLI command handlers."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from organvm_engine.cli.irf import cmd_irf_stats
from organvm_engine.irf.parser import parse_irf

FIXTURES = Path(__file__).parent / "fixtures"
CASES = FIXTURES / "irf-parser-cases.md"


def test_irf_stats_counts_tail_row_without_leading_pipe(tmp_path: Path, monkeypatch, capsys):
    irf_path = tmp_path / "INST-INDEX-RERUM-FACIENDARUM.md"
    irf_path.write_text(
        CASES.read_text()
        + "\n\n### S-tail Discovered Items (2026-06-18)\n\n"
        + "ID | Priority | Action | Owner | Source | Blocker\n"
        + "---|---|---|---|---|---\n"
        + "IRF-TAIL-001 | P2 | Tail-created compact row | Agent | issue-71 | None\n",
    )
    monkeypatch.setenv("ORGANVM_CORPUS_DIR", str(tmp_path))

    rc = cmd_irf_stats(Namespace(write=False, json=True))
    captured = capsys.readouterr()
    stats = json.loads(captured.out)

    assert rc == 0
    assert captured.err == ""
    assert stats["total"] == len(parse_irf(CASES)) + 1
    assert stats["by_domain"]["TAIL"] == 1
