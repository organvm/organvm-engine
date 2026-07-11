"""Contribution packet assembly + policy-gated submission for BIFRONS.

Produces the contribution packet (everything a maintainer or a human reviewer
needs to judge the contribution) and, only past the policy gate, performs the
one external write. The default posture is prepare, never submit.
"""

from __future__ import annotations

import sqlite3

from organvm_engine.contrib.policy import ContributionPolicy, authorize_submit
from organvm_engine.contrib.validator import ValidationResult
from organvm_engine.contrib.worktree import WorkspacePlan
from organvm_engine.portal import store
from organvm_engine.portal.models import ContributionCandidate
from organvm_engine.portal.state_machine import ExchangeState


def build_packet(
    candidate: ContributionCandidate,
    dossier: dict,
    workspace: WorkspacePlan,
    validation: ValidationResult,
    *,
    draft_title: str = "",
    draft_body: str = "",
) -> dict:
    """Assemble the contribution packet — prepared, never sent by this call."""
    contracts = dossier.get("contracts", {})
    return {
        "external_repo": candidate.external_repo,
        "source_ref": workspace.ref,
        "kind": candidate.kind,
        "rationale": candidate.rationale,
        "reproduction": validation.reproduction,
        "check_commands": validation.commands,
        "contribution_policy": {
            "contributing": contracts.get("contributing", ""),
            "security": contracts.get("security", ""),
            "cla_or_dco": contracts.get("cla_or_dco", "unknown"),
        },
        "license_state": contracts.get("license", {}),
        "workspace": workspace.as_dict(),
        "draft_pr": {
            "title": draft_title or f"{candidate.kind}: contribution from ORGANVM",
            "body": draft_body or candidate.rationale,
        },
        "relationship": {"exchange_id": candidate.exchange_id},
        "default_posture": "prepared-not-submitted",
    }


def prepare(
    conn: sqlite3.Connection,
    candidate: ContributionCandidate,
    packet: dict,
) -> None:
    """Record the packet on the candidate and walk the exchange to PATCH_PREPARED."""
    store.init_exchange_schema(conn)
    conn.execute(
        "UPDATE contribution_candidate SET packet_json=?, status='prepared' "
        "WHERE exchange_id=? AND external_repo=?",
        (_dumps(packet), candidate.exchange_id, candidate.external_repo),
    )
    conn.commit()
    for state in (
        ExchangeState.UPSTREAM_POLICY_CHECKED,
        ExchangeState.REPRODUCED,
        ExchangeState.PATCH_PREPARED,
    ):
        store.advance_exchange(conn, candidate.exchange_id, state.value)


def submit(
    conn: sqlite3.Connection,
    policy: ContributionPolicy,
    candidate: ContributionCandidate,
    packet: dict,
    *,
    human_approved: bool = False,
    checks_passing: bool = False,
    duplicate_exists: bool = False,
    open_prs: int = 0,
    maintainer_opt_out: bool = False,
    execute: bool = False,
) -> dict:
    """The external-write boundary. Returns the decision; submits only if allowed+executed."""
    decision = authorize_submit(
        policy,
        external_repo=candidate.external_repo,
        kind=candidate.kind,
        human_approved=human_approved,
        checks_passing=checks_passing,
        duplicate_exists=duplicate_exists,
        open_prs=open_prs,
        maintainer_opt_out=maintainer_opt_out,
    )
    result = {
        "external_repo": candidate.external_repo,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "requires_human": decision.requires_human,
        "submitted": False,
    }
    if not decision.allowed:
        return result

    # Authorized. Walk HUMAN_APPROVED; only actually open the PR when executed.
    store.advance_exchange(conn, candidate.exchange_id, ExchangeState.HUMAN_APPROVED.value)
    if not execute:
        result["reason"] = "authorized but not executed (dry-run)"
        return result

    number = _open_pr(candidate.external_repo, packet)
    conn.execute(
        "INSERT INTO upstream_interaction(exchange_id, external_repo, kind, number, "
        "url, state, review_decision, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (candidate.exchange_id, candidate.external_repo, "pr", number,
         f"https://github.com/{candidate.external_repo}/pull/{number}", "open", "",
         store.now_iso(), store.now_iso()),
    )
    conn.commit()
    store.advance_exchange(
        conn, candidate.exchange_id, ExchangeState.UPSTREAM_SUBMITTED.value,
        data={"upstream_pr": number},
    )
    result["submitted"] = True
    result["pr_number"] = number
    return result


def _open_pr(external_repo: str, packet: dict) -> int:  # pragma: no cover - external write
    """Open the upstream PR via gh (only reached under execute=True + policy pass)."""
    import json
    import subprocess

    title = packet["draft_pr"]["title"]
    body = packet["draft_pr"]["body"]
    out = subprocess.run(
        ["gh", "pr", "create", "--repo", external_repo, "--title", title,
         "--body", body, "--json", "number"],
        capture_output=True, text=True, check=True,
    )
    return int(json.loads(out.stdout).get("number", 0))


def _dumps(obj: dict) -> str:
    import json
    return json.dumps(obj)
