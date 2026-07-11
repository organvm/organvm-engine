"""Epic-6 loop-driving CLI verbs: prepare / candidate / package / submit / backflow.

These exercise the exchange lifecycle end to end against a seeded portal store —
the same code paths ``done.sh`` drives live. The critical assertions are the
human-gate boundary (A2 refuses; approval reaches HUMAN_APPROVED but opens no PR)
and the single-``exchange_id`` thread across both faces of one exchange.
"""

from __future__ import annotations

import argparse
import json

from organvm_engine.cli.portal import (
    cmd_portal_backflow,
    cmd_portal_candidate,
    cmd_portal_metabolize,
    cmd_portal_package,
    cmd_portal_prepare,
    cmd_portal_propose,
    cmd_portal_submit,
)
from organvm_engine.portal import store
from organvm_engine.portal.state_machine import ExchangeState

EXID = "01EXCHANGE0000000000000001"
REPO = "acme/widget"
NODE = "MDEwOlJlcG9zaXRvcnkx"

_DOC = {
    "external_repo": REPO,
    "snapshot_ref": "abc1234567deadbeefcafe",
    "identity": {
        "primary_language": "Python",
        "languages": {"Python": 1.0},
        "topics": ["cli", "tools"],
        "description": "A widget library.",
    },
    "state": {"archived": False, "last_push_at": "2026-01-01T00:00:00Z"},
    "contracts": {
        "decision": "idea-or-interface-only-unless-obligations-accepted",
        "license": {"spdx": "MIT"},
        "contributing": "CONTRIBUTING.md",
        "cla_or_dco": "dco",
    },
    "architecture": {"manifests": ["pyproject.toml"], "test_strategy": ["pytest"]},
    "provenance": {"hashes": {"README.md": "deadbeef"}},
}

_DOSSIER_DDL = """
CREATE TABLE IF NOT EXISTS dossier (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     TEXT NOT NULL,
    full_name   TEXT NOT NULL,
    level       TEXT NOT NULL,
    doc_json    TEXT NOT NULL,
    exchange_id TEXT DEFAULT '',
    UNIQUE(node_id, level)
)
"""


def _seed(db_path, *, state=ExchangeState.MAPPED):
    """Seed one exchange + dossier (the alchemia intake, minimally)."""
    conn = store.connect(str(db_path))
    store.init_exchange_schema(conn)
    conn.execute(_DOSSIER_DDL)
    conn.execute(
        "INSERT OR IGNORE INTO exchange(exchange_id, external_repo_node_id, "
        "external_repo, state, created_at, updated_at, data_json) "
        "VALUES(?,?,?,?,?,?,?)",
        (EXID, NODE, REPO, state.value, store.now_iso(), store.now_iso(), "{}"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO dossier(node_id, full_name, level, doc_json, exchange_id) "
        "VALUES(?,?,?,?,?)",
        (NODE, REPO, "S1", json.dumps(_DOC), EXID),
    )
    conn.commit()
    conn.close()


def _ns(db_path, **kw):
    return argparse.Namespace(external=REPO, db=str(db_path), **kw)


def _exchange_state(db_path):
    conn = store.connect(str(db_path))
    row = store.get_exchange(conn, EXID)
    conn.close()
    return row["state"]


def _count(db_path, table, where=""):
    conn = store.connect(str(db_path))
    q = f"SELECT COUNT(*) n FROM {table} {where}"  # noqa: S608 - test-local table names
    n = conn.execute(q).fetchone()["n"]
    conn.close()
    return n


def test_prepare_inbound_draft_pr(tmp_path):
    db = tmp_path / "portal.db"
    _seed(db)
    assert cmd_portal_propose(_ns(db, target="organvm-engine")) == 0
    out_dir = tmp_path / "proposals"
    assert cmd_portal_prepare(_ns(db, out_dir=str(out_dir))) == 0
    # Inbound branch walked to INTERNAL_PR_OPEN, artifact written, no default-branch write.
    assert _exchange_state(db) == ExchangeState.INTERNAL_PR_OPEN.value
    artifact = out_dir / f"{EXID}.md"
    assert artifact.exists()
    body = artifact.read_text()
    assert "draft internal pr" in body.lower()
    assert EXID in body


def test_candidate_and_package_outbound(tmp_path):
    db = tmp_path / "portal.db"
    _seed(db)
    assert cmd_portal_candidate(
        _ns(db, kind="documentation-ambiguity", rationale="Ambiguous README setup step",
            tractability=0.6, testability=0.6),
    ) == 0
    assert _count(db, "contribution_candidate") == 1
    assert _exchange_state(db) == ExchangeState.CONTRIBUTION_CANDIDATE.value
    # Packaging plans a workspace + checks and stores the packet; nothing is sent.
    assert cmd_portal_package(_ns(db, ref=None)) == 0
    assert _exchange_state(db) == ExchangeState.PATCH_PREPARED.value
    assert _count(db, "upstream_interaction") == 0  # prepared, not submitted


def test_candidate_rejects_unknown_kind(tmp_path):
    db = tmp_path / "portal.db"
    _seed(db)
    # Not an evidence-driven kind -> refused.
    assert cmd_portal_candidate(
        _ns(db, kind="i-just-like-it", rationale="vibes"),
    ) == 1
    assert _count(db, "contribution_candidate") == 0


def test_submit_refuses_without_approval(tmp_path):
    """A2 default: prepare, never submit. The gate must hold."""
    db = tmp_path / "portal.db"
    _seed(db)
    cmd_portal_candidate(_ns(db, kind="documentation-ambiguity", rationale="x"))
    cmd_portal_package(_ns(db, ref=None))
    assert cmd_portal_submit(
        _ns(db, approve=False, checks_passing=False, execute=False),
    ) == 0
    # No external-write record; lifecycle never reached UPSTREAM_SUBMITTED.
    assert _count(db, "upstream_interaction") == 0
    assert _exchange_state(db) != ExchangeState.UPSTREAM_SUBMITTED.value


def test_submit_authorizes_but_does_not_execute(tmp_path):
    """--approve --checks-passing reaches HUMAN_APPROVED; no --execute => no PR opened."""
    db = tmp_path / "portal.db"
    _seed(db)
    cmd_portal_candidate(_ns(db, kind="documentation-ambiguity", rationale="x"))
    cmd_portal_package(_ns(db, ref=None))
    assert cmd_portal_submit(
        _ns(db, approve=True, checks_passing=True, execute=False),
    ) == 0
    assert _exchange_state(db) == ExchangeState.HUMAN_APPROVED.value
    assert _count(db, "upstream_interaction") == 0  # the external write never happened


def test_backflow_completes_and_threads_one_exchange(tmp_path):
    """The two-faced proof: one exchange_id threads inbound + outbound + backflow."""
    db = tmp_path / "portal.db"
    _seed(db)
    # Inbound face
    cmd_portal_propose(_ns(db, target="organvm-engine"))
    cmd_portal_prepare(_ns(db, out_dir=str(tmp_path / "p")))
    # Outbound face
    cmd_portal_candidate(_ns(db, kind="documentation-ambiguity", rationale="x"))
    cmd_portal_package(_ns(db, ref=None))
    cmd_portal_submit(_ns(db, approve=True, checks_passing=True, execute=False))
    # Backflow
    assert cmd_portal_backflow(_ns(db, outcome="dormant", write=False)) == 0
    assert _exchange_state(db) == ExchangeState.BACKFLOW_COMPLETE.value
    assert _count(db, "backflow_signal") >= 2  # community + distribution at minimum

    # One exchange_id threads every stage.
    for table in ("transmutation_proposal", "contribution_candidate", "backflow_signal"):
        assert _count(db, table, f"WHERE exchange_id='{EXID}'") >= 1


def _metabolize_ns(db, tmp_path):
    return argparse.Namespace(
        db=str(db), budget=5, threshold=0.15, no_absorb=True,
        state_dir=str(tmp_path / "state"), out_dir=str(tmp_path / "prop"),
    )


def test_metabolize_bounded_idempotent_and_surfaces(tmp_path):
    """The autopoietic beat: absorb(skip)->map->prepare(inbound)->surface. Never submits."""
    db = tmp_path / "portal.db"
    _seed(db)
    # A resonance edge so the bounded inbound-prepare JOIN matches this exchange.
    conn = store.connect(str(db))
    store.upsert_resonance_edge(
        conn, exchange_id=EXID, external_node_id=NODE, external_repo=REPO,
        internal_repo="organvm-engine", lens="technical", score=0.5,
        evidence=["shared language: python"],
    )
    conn.commit()
    conn.close()

    ns = _metabolize_ns(db, tmp_path)
    assert cmd_portal_metabolize(ns) == 0
    # Observable state surface written (organ-health probes this).
    assert (tmp_path / "state" / "state.json").exists()
    # Inbound face prepared; exchange moved off MAPPED; nothing sent.
    assert _count(db, "transmutation_proposal") >= 1
    assert _count(db, "upstream_interaction") == 0
    assert _exchange_state(db) != ExchangeState.MAPPED.value

    # Idempotent + bounded: re-run finds nothing at MAPPED, adds no new proposals.
    before = _count(db, "transmutation_proposal")
    assert cmd_portal_metabolize(ns) == 0
    assert _count(db, "transmutation_proposal") == before
