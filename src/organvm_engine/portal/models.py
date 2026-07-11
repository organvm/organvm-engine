"""Portal domain models — transmutation proposals and contribution candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Transmutation proposal classes (what can be learned from an absorbed repo).
PROPOSAL_CLASSES = (
    "architecture-pattern",
    "interface-adoption",
    "testing-technique",
    "documentation-structure",
    "dev-tool-integration",
    "performance-strategy",
    "interoperability-adapter",
    "visual-reference",
    "research-note",
    "dependency-adoption",
    "deprecation-or-security-warning",
)

# Contribution candidate kinds (evidence-driven; a candidate needs one of these).
CONTRIBUTION_KINDS = (
    "reproducible-defect",
    "documentation-ambiguity",
    "missing-test-or-fixture",
    "compatibility-problem",
    "performance-or-reliability",
    "interoperability-adapter",
    "scoped-feature",
)


@dataclass
class TransmutationProposal:
    """An inbound proposal: what an absorbed repo could teach an ORGANVM repo.

    Never a silent code transplant — a described, license-gated change with tests
    and a rollback, realized as a *draft* internal PR only after approval.
    """

    exchange_id: str
    external_repo: str
    source_ref: str
    target_repo: str
    klass: str
    finding: str = ""
    proposed_change: str = ""
    license_decision: str = ""
    abstraction_level: str = "idea"  # idea | interface | code
    files_changed: list[str] = field(default_factory=list)
    tests_required: list[str] = field(default_factory=list)
    copied_code: bool = False
    status: str = "proposed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContributionCandidate:
    """An outbound candidate: a legitimate improvement to return upstream.

    Generated only when ORGANVM holds real evidence (a defect, a confirmed doc
    ambiguity, a missing test, ...). Default posture is prepare, never submit.
    """

    exchange_id: str
    external_repo: str
    kind: str
    rationale: str = ""
    contribution_score: float = 0.0
    status: str = "candidate"
    packet: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PortalHealthSnapshot:
    """One BIFRONS metabolize beat, made observable.

    The state surface the beat writes each cycle — what the portal absorbed,
    mapped, and prepared, plus how many contributions pool awaiting the single
    human gate. This is the effector's proof-of-life for organ-health.
    """

    generated_at: str
    stars_absorbed: int = 0
    dossiers: int = 0
    resonance_edges: int = 0
    proposals_prepared: int = 0
    prepared_awaiting_gate: int = 0
    exchanges_by_state: dict[str, int] = field(default_factory=dict)
    last_run_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
