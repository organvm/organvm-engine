"""Exchange lifecycle state machine for the BIFRONS portal.

One star's traversal moves through a shared prefix (STARRED -> MAPPED) and then
forks into an inbound branch (internal evolution) and/or an outbound branch
(upstream contribution), both converging on BACKFLOW_COMPLETE.

Every transition is idempotent, timestamped (by the store), evidence-backed,
reversible where technically possible, and attributable.
"""

from __future__ import annotations

from enum import Enum


class ExchangeState(str, Enum):
    # shared prefix
    STARRED = "STARRED"
    INDEXED = "INDEXED"
    DOSSIERED = "DOSSIERED"
    MAPPED = "MAPPED"
    # inbound (internal evolution)
    ABSORPTION_CANDIDATE = "ABSORPTION_CANDIDATE"
    INTERNAL_PROPOSAL = "INTERNAL_PROPOSAL"
    INTERNAL_PREPARED = "INTERNAL_PREPARED"
    INTERNAL_PR_OPEN = "INTERNAL_PR_OPEN"
    INTERNAL_MERGED = "INTERNAL_MERGED"
    # outbound (upstream contribution)
    CONTRIBUTION_CANDIDATE = "CONTRIBUTION_CANDIDATE"
    UPSTREAM_POLICY_CHECKED = "UPSTREAM_POLICY_CHECKED"
    REPRODUCED = "REPRODUCED"
    PATCH_PREPARED = "PATCH_PREPARED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    UPSTREAM_SUBMITTED = "UPSTREAM_SUBMITTED"
    MERGED = "MERGED"
    DECLINED = "DECLINED"
    DORMANT = "DORMANT"
    # convergence
    BACKFLOW_COMPLETE = "BACKFLOW_COMPLETE"


# Allowed transitions (directed). A state maps to the set it may advance to.
_TRANSITIONS: dict[ExchangeState, set[ExchangeState]] = {
    ExchangeState.STARRED: {ExchangeState.INDEXED},
    ExchangeState.INDEXED: {ExchangeState.DOSSIERED},
    ExchangeState.DOSSIERED: {ExchangeState.MAPPED},
    ExchangeState.MAPPED: {
        ExchangeState.ABSORPTION_CANDIDATE,
        ExchangeState.CONTRIBUTION_CANDIDATE,
    },
    # inbound branch
    ExchangeState.ABSORPTION_CANDIDATE: {ExchangeState.INTERNAL_PROPOSAL},
    ExchangeState.INTERNAL_PROPOSAL: {ExchangeState.INTERNAL_PREPARED},
    ExchangeState.INTERNAL_PREPARED: {ExchangeState.INTERNAL_PR_OPEN},
    ExchangeState.INTERNAL_PR_OPEN: {
        ExchangeState.INTERNAL_MERGED,
        ExchangeState.BACKFLOW_COMPLETE,
    },
    ExchangeState.INTERNAL_MERGED: {ExchangeState.BACKFLOW_COMPLETE},
    # outbound branch
    ExchangeState.CONTRIBUTION_CANDIDATE: {ExchangeState.UPSTREAM_POLICY_CHECKED},
    ExchangeState.UPSTREAM_POLICY_CHECKED: {ExchangeState.REPRODUCED},
    ExchangeState.REPRODUCED: {ExchangeState.PATCH_PREPARED},
    ExchangeState.PATCH_PREPARED: {ExchangeState.HUMAN_APPROVED},
    ExchangeState.HUMAN_APPROVED: {ExchangeState.UPSTREAM_SUBMITTED},
    ExchangeState.UPSTREAM_SUBMITTED: {
        ExchangeState.MERGED,
        ExchangeState.DECLINED,
        ExchangeState.DORMANT,
    },
    ExchangeState.MERGED: {ExchangeState.BACKFLOW_COMPLETE},
    ExchangeState.DECLINED: {ExchangeState.BACKFLOW_COMPLETE},
    ExchangeState.DORMANT: {ExchangeState.BACKFLOW_COMPLETE},
    ExchangeState.BACKFLOW_COMPLETE: set(),
}

# The single external-write boundary: only past this line does anything leave
# ORGANVM. Reaching it requires an explicit HUMAN_APPROVED predecessor.
EXTERNAL_WRITE_STATE = ExchangeState.UPSTREAM_SUBMITTED


class InvalidTransition(ValueError):
    """Raised when an exchange is advanced along an illegal edge."""


class PortalStateMachine:
    """Validate and apply exchange lifecycle transitions."""

    @staticmethod
    def can_advance(current: ExchangeState, target: ExchangeState) -> bool:
        return target in _TRANSITIONS.get(current, set())

    @staticmethod
    def advance(current: ExchangeState, target: ExchangeState) -> ExchangeState:
        """Return ``target`` if the transition is legal, else raise."""
        if target not in _TRANSITIONS.get(current, set()):
            raise InvalidTransition(f"{current.value} -> {target.value} is not allowed")
        return target

    @staticmethod
    def is_terminal(state: ExchangeState) -> bool:
        return not _TRANSITIONS.get(state)

    @staticmethod
    def requires_human_approval(target: ExchangeState) -> bool:
        """True for the transition that performs the external write."""
        return target == EXTERNAL_WRITE_STATE
