"""Canonical agent lifecycle — shared definitions for SPEC-013 and SPEC-014.

The ORGANVM agent lifecycle has five phases:

    SPAWN -> CLAIM -> OPERATE -> RELEASE -> DEBRIEF

This module defines them once. Both the claim registry (SPEC-013) and the
tool checkout line (SPEC-014) reference these definitions rather than
duplicating them.

It also provides the shared event-log infrastructure (append/read) and the
weight vocabulary used across both coordination subsystems.
"""

from __future__ import annotations

import enum
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Agent lifecycle phases
# ---------------------------------------------------------------------------

class AgentPhase(str, enum.Enum):
    """The five canonical phases of an agent work session."""

    SPAWN = "spawn"
    CLAIM = "claim"
    OPERATE = "operate"
    RELEASE = "release"
    DEBRIEF = "debrief"


# Ordered transitions — each phase may only advance to its successor.
PHASE_ORDER: list[AgentPhase] = list(AgentPhase)

# Valid forward transitions (phase -> set of reachable next phases).
PHASE_TRANSITIONS: dict[AgentPhase, set[AgentPhase]] = {
    AgentPhase.SPAWN: {AgentPhase.CLAIM},
    AgentPhase.CLAIM: {AgentPhase.OPERATE},
    AgentPhase.OPERATE: {AgentPhase.RELEASE},
    AgentPhase.RELEASE: {AgentPhase.DEBRIEF},
    AgentPhase.DEBRIEF: set(),  # terminal
}


def valid_transition(current: AgentPhase, target: AgentPhase) -> bool:
    """Return True if *target* is a valid successor of *current*."""
    return target in PHASE_TRANSITIONS.get(current, set())


# ---------------------------------------------------------------------------
# Conductor lifecycle and Score -> Rehearse -> Perform ritual
# ---------------------------------------------------------------------------

class ConductorPhase(str, enum.Enum):
    """Canonical Conductor lifecycle phases owned by ORGAN-IV."""

    FRAME = "FRAME"
    SHAPE = "SHAPE"
    BUILD = "BUILD"
    PROVE = "PROVE"
    DONE = "DONE"


class ConductorRitualStage(str, enum.Enum):
    """The ritual overlay that gates the Conductor lifecycle."""

    SCORE = "score"
    REHEARSE = "rehearse"
    PERFORM = "perform"


CONDUCTOR_PHASE_ORDER: list[ConductorPhase] = list(ConductorPhase)

CONDUCTOR_PHASE_TRANSITIONS: dict[ConductorPhase, set[ConductorPhase]] = {
    ConductorPhase.FRAME: {ConductorPhase.SHAPE},
    ConductorPhase.SHAPE: {ConductorPhase.BUILD},
    ConductorPhase.BUILD: {ConductorPhase.PROVE},
    ConductorPhase.PROVE: {ConductorPhase.DONE},
    ConductorPhase.DONE: set(),
}

CONDUCTOR_RITUAL_SEQUENCE: list[ConductorRitualStage] = [
    ConductorRitualStage.SCORE,
    ConductorRitualStage.REHEARSE,
    ConductorRitualStage.PERFORM,
]

CONDUCTOR_PHASE_RITUAL: dict[ConductorPhase, ConductorRitualStage] = {
    ConductorPhase.FRAME: ConductorRitualStage.SCORE,
    ConductorPhase.SHAPE: ConductorRitualStage.SCORE,
    ConductorPhase.BUILD: ConductorRitualStage.REHEARSE,
    ConductorPhase.PROVE: ConductorRitualStage.REHEARSE,
    ConductorPhase.DONE: ConductorRitualStage.PERFORM,
}


@dataclass(frozen=True)
class ConductorRitualGate:
    """Metadata required at a lifecycle gate."""

    phase: ConductorPhase
    stage: ConductorRitualStage
    required_metadata: tuple[str, ...]
    prompt: str
    purpose: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "ritual_stage": self.stage.value,
            "required_metadata": list(self.required_metadata),
            "prompt": self.prompt,
            "purpose": self.purpose,
        }


CONDUCTOR_RITUAL_GATES: tuple[ConductorRitualGate, ...] = (
    ConductorRitualGate(
        phase=ConductorPhase.SHAPE,
        stage=ConductorRitualStage.SCORE,
        required_metadata=(
            "appetite_minutes",
            "micro_spec.outcome",
            "micro_spec.non_goals",
            "micro_spec.acceptance_checks",
        ),
        prompt="Score the work before BUILD: appetite, outcome, non-goals, checks.",
        purpose="Prevents open-ended implementation before the problem is shaped.",
    ),
    ConductorRitualGate(
        phase=ConductorPhase.PROVE,
        stage=ConductorRitualStage.REHEARSE,
        required_metadata=(
            "rehearsal_commands",
            "test_obligations",
        ),
        prompt="Rehearse the change before DONE: enumerate and run verification.",
        purpose="Turns deferred test obligations into an explicit proof pass.",
    ),
    ConductorRitualGate(
        phase=ConductorPhase.DONE,
        stage=ConductorRitualStage.PERFORM,
        required_metadata=(
            "regression_detected",
            "postmortem_required",
            "session_export.conductor_ritual",
        ),
        prompt="Perform the close-out: regression result, postmortem if needed, export.",
        purpose="Makes the final session artifact carry the ritual metadata.",
    ),
)


def normalise_conductor_phase(phase: ConductorPhase | str) -> ConductorPhase:
    """Return a canonical Conductor phase or raise for unknown values."""
    if isinstance(phase, ConductorPhase):
        return phase
    try:
        return ConductorPhase(str(phase).strip().upper())
    except ValueError as exc:
        valid = ", ".join(p.value for p in CONDUCTOR_PHASE_ORDER)
        raise ValueError(f"Unknown Conductor phase {phase!r}; expected one of: {valid}") from exc


def valid_conductor_transition(
    current: ConductorPhase | str,
    target: ConductorPhase | str,
) -> bool:
    """Return True if *target* is a valid successor of *current*."""
    current_phase = normalise_conductor_phase(current)
    target_phase = normalise_conductor_phase(target)
    return target_phase in CONDUCTOR_PHASE_TRANSITIONS.get(current_phase, set())


def conductor_ritual_stage(phase: ConductorPhase | str) -> ConductorRitualStage:
    """Return the Score/Rehearse/Perform stage for a Conductor phase."""
    return CONDUCTOR_PHASE_RITUAL[normalise_conductor_phase(phase)]


def conductor_ritual_contract() -> dict[str, Any]:
    """Return the engine-side contract the ORGAN-IV Conductor can consume."""
    return {
        "schema_version": "conductor-ritual/v1",
        "source_issue": "a-organvm/organvm-engine#10",
        "lifecycle": [phase.value for phase in CONDUCTOR_PHASE_ORDER],
        "transitions": {
            phase.value: [target.value for target in sorted(targets, key=CONDUCTOR_PHASE_ORDER.index)]
            for phase, targets in CONDUCTOR_PHASE_TRANSITIONS.items()
        },
        "ritual_sequence": [stage.value for stage in CONDUCTOR_RITUAL_SEQUENCE],
        "phase_to_ritual": {
            phase.value: stage.value for phase, stage in CONDUCTOR_PHASE_RITUAL.items()
        },
        "gates": {gate.phase.value: gate.to_dict() for gate in CONDUCTOR_RITUAL_GATES},
        "session_export_metadata": [
            "conductor_lifecycle",
            "conductor_ritual",
            "conductor_phase",
            "conductor_ritual_stage",
            "appetite_minutes",
            "micro_spec",
            "rehearsal_commands",
            "test_obligations",
            "regression_detected",
            "postmortem_required",
        ],
    }


def _string_list(value: Any) -> list[str]:
    """Normalize scalar or iterable metadata into a string list."""
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    try:
        return [str(item).strip() for item in value if str(item).strip()]
    except TypeError:
        text = str(value).strip()
        return [text] if text else []


def build_conductor_ritual_metadata(
    *,
    phase: ConductorPhase | str = ConductorPhase.DONE,
    appetite_minutes: int | None = None,
    micro_spec: dict[str, Any] | None = None,
    outcome: str = "",
    non_goals: list[str] | tuple[str, ...] | str | None = None,
    acceptance_checks: list[str] | tuple[str, ...] | str | None = None,
    rehearsal_commands: list[str] | tuple[str, ...] | str | None = None,
    test_obligations: list[str] | tuple[str, ...] | str | None = None,
    regression_detected: bool | None = None,
    postmortem: str = "",
) -> dict[str, Any]:
    """Build serializable Score/Rehearse/Perform metadata for a session artifact."""
    conductor_phase = normalise_conductor_phase(phase)
    spec = dict(micro_spec or {})
    if outcome:
        spec["outcome"] = outcome
    if non_goals is not None:
        spec["non_goals"] = _string_list(non_goals)
    if acceptance_checks is not None:
        spec["acceptance_checks"] = _string_list(acceptance_checks)

    spec.setdefault("outcome", "")
    spec.setdefault("non_goals", [])
    spec.setdefault("acceptance_checks", [])

    return {
        "schema_version": "conductor-ritual/v1",
        "source_issue": "a-organvm/organvm-engine#10",
        "conductor_lifecycle": [phase.value for phase in CONDUCTOR_PHASE_ORDER],
        "conductor_ritual": [stage.value for stage in CONDUCTOR_RITUAL_SEQUENCE],
        "conductor_phase": conductor_phase.value,
        "conductor_ritual_stage": conductor_ritual_stage(conductor_phase).value,
        "score": {
            "appetite_minutes": appetite_minutes,
            "micro_spec": {
                "outcome": str(spec.get("outcome", "")),
                "non_goals": _string_list(spec.get("non_goals")),
                "acceptance_checks": _string_list(spec.get("acceptance_checks")),
            },
        },
        "rehearse": {
            "rehearsal_commands": _string_list(rehearsal_commands),
            "test_obligations": _string_list(test_obligations),
        },
        "perform": {
            "regression_detected": regression_detected,
            "postmortem_required": regression_detected is True,
            "postmortem": postmortem,
        },
    }


# ---------------------------------------------------------------------------
# Resource weight vocabulary (shared by claims + tool checkout)
# ---------------------------------------------------------------------------

class ResourceWeight(str, enum.Enum):
    """Resource weight categories used by both claims and tool checkouts."""

    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


# Cost units per weight (claims use these for capacity budgeting).
WEIGHT_COSTS: dict[str, int] = {
    ResourceWeight.LIGHT: 1,
    ResourceWeight.MEDIUM: 2,
    ResourceWeight.HEAVY: 3,
}


def weight_cost(weight: str) -> int:
    """Return the cost units for a weight string, defaulting to medium."""
    return WEIGHT_COSTS.get(weight, WEIGHT_COSTS[ResourceWeight.MEDIUM])


def normalise_weight(weight: str) -> str:
    """Return a valid weight string, falling back to 'medium'."""
    try:
        return ResourceWeight(weight).value
    except ValueError:
        return ResourceWeight.MEDIUM.value


# ---------------------------------------------------------------------------
# Shared event-log infrastructure (JSONL append-only log)
# ---------------------------------------------------------------------------

_CLAIMS_DIR = Path.home() / ".organvm"
_CLAIMS_FILE = _CLAIMS_DIR / "claims.jsonl"


def claims_file_path() -> Path:
    """Return the path to the shared JSONL event log.

    Respects the ORGANVM_CLAIMS_FILE environment variable for test isolation.
    """
    env = os.environ.get("ORGANVM_CLAIMS_FILE")
    if env:
        return Path(env)
    return _CLAIMS_FILE


def append_event(event: dict[str, Any]) -> None:
    """Append a JSON event to the shared event log."""
    path = claims_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(event) + "\n")


def read_events() -> list[dict[str, Any]]:
    """Read all events from the shared event log."""
    path = claims_file_path()
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for raw_line in path.read_text().splitlines():
        stripped = raw_line.strip()
        if stripped:
            try:
                events.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
    return events


# ---------------------------------------------------------------------------
# Shared active-record mixin
# ---------------------------------------------------------------------------

@dataclass
class _ActiveRecordMixin:
    """Shared expiry/release logic for any time-bounded coordination record.

    Subclasses must define ``timestamp``, ``released``, and a TTL attribute
    (either ``ttl_seconds`` on the instance or via ``_ttl()``).

    This is not intended for direct instantiation — it provides properties
    that both WorkClaim and ToolCheckout inherit.
    """

    timestamp: float
    released: bool

    def _ttl(self) -> int:
        """Return the TTL in seconds. Override or set ``ttl_seconds``."""
        return getattr(self, "ttl_seconds", 0)

    @property
    def is_expired(self) -> bool:
        return time.time() > (self.timestamp + self._ttl())

    @property
    def is_active(self) -> bool:
        return not self.released and not self.is_expired
