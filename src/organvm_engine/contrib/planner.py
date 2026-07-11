"""Contribution opportunity planning for BIFRONS.

A contribution candidate is generated only when ORGANVM holds real evidence — a
reproducible defect, a confirmed documentation ambiguity, a missing test, a
compatibility problem discovered while integrating, a measured improvement, an
interoperability adapter, or a narrowly-scoped, locally-validated feature.

Candidates are recorded and the exchange advanced; nothing is submitted here.
"""

from __future__ import annotations

import sqlite3

from organvm_engine.network.resonance import contribution_score
from organvm_engine.portal import store
from organvm_engine.portal.models import CONTRIBUTION_KINDS, ContributionCandidate
from organvm_engine.portal.state_machine import ExchangeState


class InvalidCandidate(ValueError):
    """Raised when a candidate lacks a recognized evidence-driven kind."""


def plan_candidate(
    conn: sqlite3.Connection,
    dossier: dict,
    *,
    kind: str,
    rationale: str,
    tractability: float = 0.5,
    testability: float = 0.5,
    exchange_id: str | None = None,
    persist: bool = True,
) -> ContributionCandidate:
    """Build (and optionally persist) an evidence-driven contribution candidate."""
    if kind not in CONTRIBUTION_KINDS:
        raise InvalidCandidate(
            f"kind '{kind}' is not evidence-driven; expected one of {CONTRIBUTION_KINDS}",
        )
    ex_id = exchange_id or dossier.get("_exchange_id", "")
    score = contribution_score(
        dossier,
        has_verified_friction=True,  # a candidate exists => friction is verified
        tractability=tractability,
        testability=testability,
        existing_evidence=True,
    )
    candidate = ContributionCandidate(
        exchange_id=ex_id,
        external_repo=dossier.get("external_repo", ""),
        kind=kind,
        rationale=rationale,
        contribution_score=score,
        status="candidate",
    )
    if persist:
        store.init_exchange_schema(conn)
        store.insert_contribution_candidate(conn, candidate)
        if ex_id:
            store.advance_exchange(
                conn, ex_id, ExchangeState.CONTRIBUTION_CANDIDATE.value,
                data={"contribution_kind": kind, "contribution_score": score},
            )
    return candidate
