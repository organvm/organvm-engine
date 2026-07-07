"""Cross-agent work coordination — punch-in/punch-out claim registry.

Lifecycle phases (SPAWN -> CLAIM -> OPERATE -> RELEASE -> DEBRIEF) are
defined once in ``lifecycle.py`` and shared by the claim registry (SPEC-013)
and tool checkout line (SPEC-014).
"""

from organvm_engine.coordination.lifecycle import (  # noqa: F401
    PHASE_ORDER,
    PHASE_TRANSITIONS,
    WEIGHT_COSTS,
    AgentPhase,
    ResourceWeight,
    valid_transition,
)
