"""BIFRONS portal — the compile/decide half of the star<->contribution portal.

BIFRONS (Janus, two-faced) absorbs starred repositories (via alchemia) and
returns value both inward (transmutation proposals that evolve ORGANVM repos)
and outward (upstream contributions), metabolizing the response back through the
seven organs. This package owns, inside organvm-engine:

* store       — the engine's half of the shared portal.db (exchange tables)
* models      — TransmutationProposal, ContributionCandidate
* proposals   — generate inbound transmutation proposals from dossiers+resonance
* state_machine — the exchange lifecycle FSM

Naming: distinct from IANVA (the MCP doorway/aggregator).
"""

from organvm_engine.portal.models import (
    ContributionCandidate,
    TransmutationProposal,
)
from organvm_engine.portal.state_machine import ExchangeState, PortalStateMachine

__all__ = [
    "ContributionCandidate",
    "ExchangeState",
    "PortalStateMachine",
    "TransmutationProposal",
]
