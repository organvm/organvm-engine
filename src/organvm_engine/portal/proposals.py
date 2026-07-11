"""Generate inbound transmutation proposals from dossiers.

The inbound side never silently transplants source code. It produces a
*transmutation proposal*: what can be learned from an absorbed repo and how it
could alter a specific ORGANVM repo — gated by the license firewall, and
realized (later, on approval) as a draft internal PR, never a default-branch write.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from organvm_engine.portal import store
from organvm_engine.portal.models import TransmutationProposal
from organvm_engine.portal.state_machine import ExchangeState, PortalStateMachine

# The inbound branch, in order — the shared prefix plus the internal-evolution
# states. ``prepare_internal_pr`` walks an exchange forward along this path.
_INBOUND_ORDER = [
    ExchangeState.STARRED,
    ExchangeState.INDEXED,
    ExchangeState.DOSSIERED,
    ExchangeState.MAPPED,
    ExchangeState.ABSORPTION_CANDIDATE,
    ExchangeState.INTERNAL_PROPOSAL,
    ExchangeState.INTERNAL_PREPARED,
    ExchangeState.INTERNAL_PR_OPEN,
]

# License decision -> permitted abstraction level + whether code may be copied.
_ABSTRACTION_BY_DECISION = {
    "code-adaptation-with-attribution": ("code", True),
    "idea-or-interface-only-unless-obligations-accepted": ("interface", False),
    "no-code-or-asset-copying": ("idea", False),
}


def _infer_class(dossier: dict) -> str:
    arch = dossier.get("architecture", {})
    manifests = arch.get("manifests", [])
    test_strategy = arch.get("test_strategy", [])
    if "Dockerfile" in manifests:
        return "dev-tool-integration"
    if test_strategy:
        return "testing-technique"
    if ".github/workflows" in manifests:
        return "dev-tool-integration"
    return "architecture-pattern"


def propose_transmutation(
    dossier: dict,
    target_repo: str,
    *,
    klass: str | None = None,
    exchange_id: str | None = None,
) -> TransmutationProposal:
    """Build a license-gated transmutation proposal for ``target_repo``."""
    contracts = dossier.get("contracts", {})
    decision = contracts.get("decision", "no-code-or-asset-copying")
    abstraction, may_copy = _ABSTRACTION_BY_DECISION.get(decision, ("idea", False))
    resolved_class = klass or _infer_class(dossier)
    ext_repo = dossier.get("external_repo", "")
    source_ref = dossier.get("snapshot_ref", "")

    finding = (
        f"{ext_repo} demonstrates a {resolved_class.replace('-', ' ')} relevant to "
        f"{target_repo}."
    )
    proposed = (
        f"Adopt the {resolved_class.replace('-', ' ')} at the '{abstraction}' level "
        f"in {target_repo}, with attribution and provenance to {ext_repo}@{source_ref[:10]}."
    )

    return TransmutationProposal(
        exchange_id=exchange_id or dossier.get("_exchange_id", ""),
        external_repo=ext_repo,
        source_ref=source_ref,
        target_repo=target_repo,
        klass=resolved_class,
        finding=finding,
        proposed_change=proposed,
        license_decision=decision,
        abstraction_level=abstraction,
        files_changed=[],
        tests_required=[f"tests covering the adopted {resolved_class}"],
        copied_code=may_copy and abstraction == "code",
        status="proposed",
    )


def _pfield(proposal: Any, key: str, default: str = "") -> str:
    """Read a field from a proposal that may be a sqlite3.Row or a dataclass."""
    if isinstance(proposal, sqlite3.Row):
        try:
            return proposal[key] if proposal[key] is not None else default
        except (IndexError, KeyError):
            return default
    return getattr(proposal, key, default)


def render_draft_pr(proposal: Any) -> str:
    """Render a draft *internal* PR body from a transmutation proposal.

    Pure: produces the review document a maintainer reads before the change is
    realized. It is never a git push — the inbound side never writes a default
    branch. The document carries the license decision and provenance so the graft
    is auditable.
    """
    klass = _pfield(proposal, "klass")
    return "\n".join([
        f"# Transmutation proposal: adopt {klass.replace('-', ' ')}",
        "",
        f"- **Source (absorbed):** {_pfield(proposal, 'external_repo')}"
        f"@{_pfield(proposal, 'source_ref')[:10]}",
        f"- **Target (ORGANVM):** {_pfield(proposal, 'target_repo')}",
        f"- **Class:** {klass}",
        f"- **License decision:** {_pfield(proposal, 'license_decision')}",
        f"- **Abstraction level:** {_pfield(proposal, 'abstraction_level', 'idea')}",
        "",
        "## Finding",
        _pfield(proposal, "finding"),
        "",
        "## Proposed change",
        _pfield(proposal, "proposed_change"),
        "",
        "## Provenance & posture",
        "- Realized as a **draft internal PR only** — no default-branch write.",
        "- Attribution + provenance to the source repo are mandatory.",
        f"- exchange_id: `{_pfield(proposal, 'exchange_id')}`",
    ])


def default_proposals_dir() -> Path:
    return Path("~/.organvm/bifrons/proposals").expanduser()


def prepare_internal_pr(
    conn: sqlite3.Connection,
    proposal: Any,
    *,
    out_dir: Path | str | None = None,
) -> tuple[str, str]:
    """Walk the exchange's inbound branch to INTERNAL_PR_OPEN and write the draft PR.

    The inbound analog of ``contrib.executor.prepare``. Advances the lifecycle
    through the legal inbound edges (idempotently, validated by the state
    machine), writes the draft internal-PR review document to ``out_dir``, and
    marks the proposal's own status ``pr_open``. Returns ``(artifact_path,
    final_state)``. Performs no git write of any kind.
    """
    store.init_exchange_schema(conn)
    exchange_id = _pfield(proposal, "exchange_id")

    final_state = ""
    row = store.get_exchange(conn, exchange_id) if exchange_id else None
    if row is not None:
        current = row["state"]
        names = [s.value for s in _INBOUND_ORDER]
        if current in names:
            idx = names.index(current)
            state = _INBOUND_ORDER[idx]
            for nxt in _INBOUND_ORDER[idx + 1:]:
                if PortalStateMachine.can_advance(state, nxt):
                    store.advance_exchange(conn, exchange_id, nxt.value)
                    state = nxt
            final_state = state.value
        else:
            # The exchange already forked onto the outbound branch — this is a
            # two-faced (BIFRONS) exchange. Record the inbound artifact without
            # rewinding the tracked lifecycle state.
            final_state = current

    directory = Path(out_dir).expanduser() if out_dir else default_proposals_dir()
    directory.mkdir(parents=True, exist_ok=True)
    safe = (exchange_id or _pfield(proposal, "external_repo").replace("/", "_")) or "proposal"
    artifact = directory / f"{safe}.md"
    artifact.write_text(render_draft_pr(proposal))

    pid = _pfield(proposal, "id")
    if pid:
        store.set_proposal_status(conn, int(pid), "pr_open")

    return str(artifact), final_state
