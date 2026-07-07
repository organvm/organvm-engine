"""Cross-agent work coordination — punch-in/punch-out claim registry.

Lifecycle phases (SPAWN -> CLAIM -> OPERATE -> RELEASE -> DEBRIEF) are
defined once in ``lifecycle.py`` and shared by the claim registry (SPEC-013)
and tool checkout line (SPEC-014).
"""

from organvm_engine.coordination.lifecycle import (  # noqa: F401
    CONDUCTOR_PHASE_ORDER,
    CONDUCTOR_PHASE_RITUAL,
    CONDUCTOR_PHASE_TRANSITIONS,
    CONDUCTOR_RITUAL_GATES,
    CONDUCTOR_RITUAL_SEQUENCE,
    PHASE_ORDER,
    PHASE_TRANSITIONS,
    WEIGHT_COSTS,
    AgentPhase,
    ConductorPhase,
    ConductorRitualGate,
    ConductorRitualStage,
    ResourceWeight,
    build_conductor_ritual_metadata,
    conductor_ritual_contract,
    conductor_ritual_stage,
    normalise_conductor_phase,
    valid_conductor_transition,
    valid_transition,
)
