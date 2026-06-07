import pytest
from pathlib import Path
from organvm_engine.irf.writer import add_irf_item, complete_irf_item


@pytest.fixture
def sample_irf(tmp_path: Path) -> Path:
    p = tmp_path / "IRF.md"
    p.write_text(
        "# INST — Index Rerum Faciendarum\n\n"
        "## Backlog\n\n"
        "| ID | Priority | What | Owner | Session | Blocker |\n"
        "|----|----------|------|-------|---------|---------|\n"
        "| IRF-SYS-001 | P2 | Do something | Human | None | None |\n\n"
        "## Completed\n\n"
        "| ID | What | Session | Date |\n"
        "|----|------|---------|------|\n"
        "| IRF-SYS-002 | Old thing | S-001 | 2026-06-01 |\n",
        encoding="utf-8",
    )
    return p


def test_add_irf_item(sample_irf: Path):
    success = add_irf_item(
        sample_irf,
        item_id="IRF-SYS-003",
        priority="P1",
        action="Test add",
        owner="Agent",
        source="S-TEST",
    )
    assert success
    content = sample_irf.read_text(encoding="utf-8")
    assert "| IRF-SYS-003 | P1 | Test add | Agent | S-TEST | None |" in content
    # Should still contain the old item
    assert "| IRF-SYS-001 | P2 | Do something | Human | None | None |" in content


def test_complete_irf_item(sample_irf: Path):
    success = complete_irf_item(
        sample_irf,
        item_id="IRF-SYS-001",
        session="S-TEST",
        date="2026-06-07",
    )
    assert success
    content = sample_irf.read_text(encoding="utf-8")
    assert "| IRF-SYS-001 | P2 | Do something | Human | None | None |" not in content
    assert "| IRF-SYS-001 | Do something | S-TEST | 2026-06-07 |" in content

def test_add_to_missing_section(sample_irf: Path):
    success = add_irf_item(
        sample_irf,
        item_id="IRF-SYS-004",
        priority="P1",
        action="Test missing",
        owner="Agent",
        source="S-TEST",
        section="MissingSection",
    )
    assert not success
