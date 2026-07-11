"""BIFRONS resonance scoring — lenses + the two independent scores."""

from __future__ import annotations

from organvm_engine.network.resonance import (
    InternalRepo,
    absorption_score,
    compute_resonance,
    contribution_score,
)

DOSSIER = {
    "external_repo": "astral-sh/ruff",
    "github_node_id": "R_1",
    "snapshot_ref": "abc1234",
    "identity": {
        "description": "An extremely fast Python linter and code formatter",
        "topics": ["python", "linter", "static-analysis"],
        "primary_language": "Rust",
        "languages": {"Rust": 0.9, "Python": 0.1},
    },
    "state": {"archived": False, "fork": False, "last_push_at": "2026-07-01T00:00:00Z"},
    "contracts": {"license": {"spdx": "MIT", "class": "permissive"},
                  "decision": "code-adaptation-with-attribution",
                  "contributing": "CONTRIBUTING.md", "cla_or_dco": "dco"},
}


def test_technical_lens_on_shared_language():
    internal = [InternalRepo("organvm-engine", languages={"Python", "Rust"},
                             topics={"linter"}, description="python quality control")]
    edges = compute_resonance(DOSSIER, internal)
    lenses = {e.lens for e in edges}
    assert "technical" in lenses
    tech = next(e for e in edges if e.lens == "technical")
    assert tech.score > 0
    assert any("language" in ev for ev in tech.evidence)


def test_parallel_and_kinship_lenses():
    internal = [InternalRepo("a-i--skills", topics={"linter", "static-analysis"},
                             description="a linter and code formatter with conventions")]
    edges = compute_resonance(DOSSIER, internal)
    lenses = {e.lens for e in edges}
    assert "parallel" in lenses  # shared topics
    assert "kinship" in lenses   # shared description words (linter, code, formatter)


def test_no_edges_below_threshold():
    internal = [InternalRepo("unrelated", languages={"COBOL"}, topics={"banking"},
                             description="mainframe payroll batch jobs")]
    edges = compute_resonance(DOSSIER, internal)
    assert edges == []


def test_absorption_score_higher_for_permissive_active_repo():
    internal = [InternalRepo("organvm-engine", languages={"Rust", "Python"},
                             topics={"linter"}, description="python quality control")]
    edges = compute_resonance(DOSSIER, internal)
    score = absorption_score(DOSSIER, edges)
    assert 0.0 < score <= 1.0

    archived = {**DOSSIER, "state": {**DOSSIER["state"], "archived": True}}
    assert absorption_score(archived, edges) < score


def test_contribution_score_penalizes_cla_and_rewards_dco():
    dco = contribution_score(DOSSIER, has_verified_friction=True, existing_evidence=True)
    cla_dossier = {**DOSSIER, "contracts": {**DOSSIER["contracts"], "cla_or_dco": "cla"}}
    cla = contribution_score(cla_dossier, has_verified_friction=True, existing_evidence=True)
    assert dco > cla


def test_scores_are_independent():
    # A permissive, healthy repo can be great material yet a poor contribution
    # target if there is no verified friction.
    internal = [InternalRepo("organvm-engine", languages={"Rust"}, description="linting")]
    edges = compute_resonance(DOSSIER, internal)
    absorb = absorption_score(DOSSIER, edges)
    contrib = contribution_score(DOSSIER, has_verified_friction=False)
    assert absorb != contrib
