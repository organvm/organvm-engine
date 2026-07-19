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
