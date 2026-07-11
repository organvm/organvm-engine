"""Generate inbound transmutation proposals from dossiers.

The inbound side never silently transplants source code. It produces a
*transmutation proposal*: what can be learned from an absorbed repo and how it
could alter a specific ORGANVM repo — gated by the license firewall, and
realized (later, on approval) as a draft internal PR, never a default-branch write.
"""

from __future__ import annotations

from organvm_engine.portal.models import TransmutationProposal

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
