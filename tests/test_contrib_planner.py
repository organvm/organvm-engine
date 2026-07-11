"""BIFRONS outbound pipeline — planner, policy gate, executor, backflow."""

from __future__ import annotations

import pytest

from organvm_engine.contrib.backflow import metabolize_exchange
from organvm_engine.contrib.executor import build_packet, prepare, submit
from organvm_engine.contrib.planner import InvalidCandidate, plan_candidate
from organvm_engine.contrib.policy import AutonomyLevel, ContributionPolicy, authorize_submit
from organvm_engine.contrib.validator import plan_validation
from organvm_engine.contrib.worktree import plan_workspace
from organvm_engine.portal import store

DOSSIER = {
    "external_repo": "astral-sh/ruff",
    "github_node_id": "R_1",
    "snapshot_ref": "abc1234def",
    "identity": {"description": "fast python linter", "topics": ["python", "linter"],
                 "primary_language": "Rust", "languages": {"Rust": 1.0}},
    "state": {"archived": False, "fork": False, "last_push_at": "2026-07-01T00:00:00Z"},
    "contracts": {"license": {"spdx": "MIT", "class": "permissive"},
                  "decision": "code-adaptation-with-attribution",
                  "contributing": "CONTRIBUTING.md", "cla_or_dco": "dco"},
}


@pytest.fixture
def db(tmp_path):
    conn = store.connect(tmp_path / "p.db")
    store.init_exchange_schema(conn)
    conn.execute(
        "INSERT INTO exchange(exchange_id, external_repo_node_id, external_repo, "
        "state, created_at, updated_at, data_json) VALUES(?,?,?,?,?,?, '{}')",
        ("ex_R_1", "R_1", "astral-sh/ruff", "MAPPED", "t", "t"),
    )
    conn.commit()
    DOSSIER["_exchange_id"] = "ex_R_1"
    yield conn
    conn.close()


def test_plan_candidate_requires_evidence_kind(db):
    with pytest.raises(InvalidCandidate):
        plan_candidate(db, DOSSIER, kind="random-idea", rationale="x")


def test_plan_candidate_persists_and_advances(db):
    cand = plan_candidate(db, DOSSIER, kind="missing-test-or-fixture",
                          rationale="upstream lacks a fixture we needed while integrating")
    assert cand.contribution_score > 0
    assert store.counts(db)["contribution_candidate"] == 1
    row = store.get_exchange(db, "ex_R_1")
    assert row["state"] == "CONTRIBUTION_CANDIDATE"


def test_a2_default_prepares_never_submits():
    policy = ContributionPolicy()  # A2 default
    decision = authorize_submit(policy, external_repo="astral-sh/ruff",
                                kind="documentation-ambiguity", checks_passing=True)
    assert decision.allowed is False
    assert decision.requires_human is True


def test_a3_allows_only_with_human_approval():
    policy = ContributionPolicy(autonomy=AutonomyLevel.SUBMIT_WITH_APPROVAL)
    assert not authorize_submit(policy, external_repo="a/b", kind="documentation-ambiguity",
                                checks_passing=True).allowed
    assert authorize_submit(policy, external_repo="a/b", kind="documentation-ambiguity",
                            human_approved=True, checks_passing=True).allowed


def test_a4_allowlist_low_risk_only():
    policy = ContributionPolicy(autonomy=AutonomyLevel.ALLOWLISTED,
                                allowlist={"astral-sh/ruff"})
    # allowlisted + low-risk + checks -> allowed
    assert authorize_submit(policy, external_repo="astral-sh/ruff",
                            kind="documentation-ambiguity", checks_passing=True).allowed
    # allowlisted but NOT low-risk -> blocked
    assert not authorize_submit(policy, external_repo="astral-sh/ruff",
                                kind="scoped-feature", checks_passing=True).allowed
    # low-risk but NOT allowlisted -> blocked
    assert not authorize_submit(policy, external_repo="other/repo",
                                kind="documentation-ambiguity", checks_passing=True).allowed


def test_duplicate_and_cap_block_submission():
    policy = ContributionPolicy(autonomy=AutonomyLevel.SUBMIT_WITH_APPROVAL)
    assert not authorize_submit(policy, external_repo="a/b", kind="documentation-ambiguity",
                                human_approved=True, checks_passing=True,
                                duplicate_exists=True).allowed
    assert not authorize_submit(policy, external_repo="a/b", kind="documentation-ambiguity",
                                human_approved=True, checks_passing=True, open_prs=3).allowed


def test_full_outbound_slice_prepares_then_gated_submit_then_backflow(db):
    cand = plan_candidate(db, DOSSIER, kind="missing-test-or-fixture",
                          rationale="missing fixture found during integration")
    ws = plan_workspace("astral-sh/ruff", "abc1234def")
    assert ws.executed is False  # dry-run: nothing forked/cloned
    val = plan_validation(ws, manifests=["pyproject.toml"], reproduction="repro steps")
    assert val.executed is False
    packet = build_packet(cand, DOSSIER, ws, val)
    assert packet["default_posture"] == "prepared-not-submitted"
    prepare(db, cand, packet)
    assert store.get_exchange(db, "ex_R_1")["state"] == "PATCH_PREPARED"

    # A2 default -> not submitted (prepared only).
    a2 = submit(db, ContributionPolicy(), cand, packet)
    assert a2["submitted"] is False
    assert a2["requires_human"] is True

    # A3 approved, execute=False -> authorized but not executed.
    a3 = submit(db, ContributionPolicy(autonomy=AutonomyLevel.SUBMIT_WITH_APPROVAL),
                cand, packet, human_approved=True, checks_passing=True, execute=False)
    assert a3["allowed"] is True
    assert a3["submitted"] is False
    assert store.get_exchange(db, "ex_R_1")["state"] == "HUMAN_APPROVED"

    # Metabolize the (declined) outcome through the seven organs -> BACKFLOW_COMPLETE.
    signals = metabolize_exchange(db, exchange_id="ex_R_1", external_repo="astral-sh/ruff",
                                  outcome="declined", title="add missing fixture")
    organs = {s.organ_key for s in signals}
    assert "VI" in organs  # community capital is always produced
    assert store.counts(db)["backflow_signal"] == len(signals)
    assert store.get_exchange(db, "ex_R_1")["state"] == "BACKFLOW_COMPLETE"
