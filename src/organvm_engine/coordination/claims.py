"""Punch-in/punch-out claim registry for multi-agent coordination.

Implements: SPEC-013, SWARM-014 (agent session lifecycle)

When an AI stream starts working on a set of files, modules, or organs,
it "punches in" by writing a claim to the shared registry. Other streams
can query the registry to see what areas are currently claimed, and avoid
collisions. When work is done, the stream "punches out" to release its claims.

Claims auto-expire after a configurable TTL (default: 4 hours) to prevent
stale claims from blocking work indefinitely.

Resource capacity tracking: each claim declares its resource weight (light,
medium, heavy). The system tracks total load and warns when the machine
(16GB M3) is approaching saturation. This prevents the "too many parallel
AI dashes" problem where concurrent Claude/Gemini/Codex sessions compete
for RAM, CPU, and disk I/O.

The claim registry lives at ~/.organvm/claims.jsonl — a shared, append-only
log. Active claims are computed by reading all entries and filtering by
punch-in/punch-out pairs and TTL expiry.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from organvm_engine.coordination.lifecycle import (
    WEIGHT_COSTS,  # noqa: F401 — re-exported for backward compat
    AgentPhase,  # noqa: F401 — re-exported for backward compat
    ResourceWeight,  # noqa: F401 — re-exported for backward compat
    normalise_weight,
    weight_cost,
)
from organvm_engine.coordination.lifecycle import (
    append_event as _append_event,
)
from organvm_engine.coordination.lifecycle import (
    claims_file_path as _claims_file,  # noqa: F401 — re-exported for backward compat
)
from organvm_engine.coordination.lifecycle import (
    read_events as _read_events,
)

# Default TTL for claims: 4 hours
DEFAULT_CLAIM_TTL_SECONDS = 4 * 60 * 60

# On a 16GB M3, we budget ~6 capacity units (leaving room for OS + background).
# light=1 (read-only, search, planning), medium=2 (code gen, tests),
# heavy=3 (full build, parallel subagents, large file generation).
DEFAULT_CAPACITY = 6  # max concurrent weight units

# Handle word pools — each agent type gets a thematic set.
# Handles are "{agent}-{word}" (e.g. "claude-forge", "gemini-scout").
_HANDLE_POOLS = {
    "claude": [
        "forge", "anvil", "helm", "loom", "quill",
        "vault", "prism", "blade", "torch", "crown",
        "reed", "stone", "tide", "crest", "glyph",
    ],
    "gemini": [
        "scout", "lens", "spark", "drift", "echo",
        "flare", "orbit", "pulse", "shard", "weave",
        "comet", "frost", "haze", "nova", "rift",
    ],
    "codex": [
        "bolt", "grid", "node", "wire", "rune",
        "byte", "core", "link", "port", "stem",
        "arc", "chip", "flux", "mesh", "vane",
    ],
    "human": [
        "hand", "eye", "mind", "voice", "heart",
        "pen", "key", "seal", "mark", "sign",
    ],
}
_DEFAULT_POOL = [
    "alpha", "bravo", "delta", "echo", "foxtrot",
    "gamma", "kappa", "omega", "sigma", "theta",
]


# _claims_file, _append_event, and _read_events are now imported from
# organvm_engine.coordination.lifecycle and aliased above.  The old names
# are preserved as module-level aliases so that tool_lock.py (and any other
# in-tree caller) can keep using ``from .claims import _read_events``.


def _generate_handle(agent: str, existing_handles: set[str]) -> str:
    """Generate a unique, human-readable handle for an agent stream.

    Format: "{agent}-{word}" (e.g. "claude-forge", "gemini-scout").
    Avoids collisions with currently active handles.
    """
    pool = _HANDLE_POOLS.get(agent, _DEFAULT_POOL)
    for word in pool:
        handle = f"{agent}-{word}"
        if handle not in existing_handles:
            return handle
    # Pool exhausted — fall back to numbered handle
    for i in range(1, 100):
        handle = f"{agent}-{i:02d}"
        if handle not in existing_handles:
            return handle
    return f"{agent}-{int(time.time()) % 10000}"


@dataclass
class WorkClaim:
    """A claim on an area of influence by an AI stream."""

    claim_id: str
    agent: str  # claude, gemini, codex, human
    session_id: str
    timestamp: float
    handle: str = ""  # unique name tag (e.g. "claude-forge")
    organs: list[str] = field(default_factory=list)
    repos: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    scope: str = ""  # free-text description
    resource_weight: str = "medium"  # light, medium, heavy
    test_obligations: list[str] = field(default_factory=list)  # deferred test cmds
    ttl_seconds: int = DEFAULT_CLAIM_TTL_SECONDS
    released: bool = False
    release_timestamp: float = 0.0

    @property
    def cost(self) -> int:
        """Resource cost units for this claim."""
        return weight_cost(self.resource_weight)

    @property
    def is_expired(self) -> bool:
        return time.time() > (self.timestamp + self.ttl_seconds)

    @property
    def is_active(self) -> bool:
        return not self.released and not self.is_expired

    @property
    def areas(self) -> list[str]:
        """All claimed areas as a flat list for display."""
        parts = []
        for o in self.organs:
            parts.append(f"organ:{o}")
        for r in self.repos:
            parts.append(f"repo:{r}")
        for f in self.files:
            parts.append(f"file:{f}")
        for m in self.modules:
            parts.append(f"module:{m}")
        return parts

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "handle": self.handle,
            "agent": self.agent,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "organs": self.organs,
            "repos": self.repos,
            "files": self.files,
            "modules": self.modules,
            "scope": self.scope,
            "resource_weight": self.resource_weight,
            "cost": self.cost,
            "test_obligations": self.test_obligations,
            "ttl_seconds": self.ttl_seconds,
            "released": self.released,
            "release_timestamp": self.release_timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorkClaim:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


@dataclass
class ClaimConflict:
    """A detected conflict between a proposed claim and an existing one."""

    existing_claim: WorkClaim
    overlap_type: str  # organ, repo, file, module
    overlap_values: list[str]



def _build_active_claims(events: list[dict]) -> list[WorkClaim]:
    """Build list of active claims from event log."""
    claims: dict[str, WorkClaim] = {}

    for event in events:
        etype = event.get("event_type")
        if etype == "claim.punch_in":
            claim = WorkClaim.from_dict(event)
            claims[claim.claim_id] = claim
        elif etype == "claim.punch_out":
            cid = event.get("claim_id", "")
            if cid in claims:
                claims[cid].released = True
                claims[cid].release_timestamp = event.get("timestamp", time.time())

    return [c for c in claims.values() if c.is_active]


def active_claims() -> list[WorkClaim]:
    """Return all currently active (non-expired, non-released) claims."""
    events = _read_events()
    return _build_active_claims(events)


def check_conflicts(
    organs: list[str] | None = None,
    repos: list[str] | None = None,
    files: list[str] | None = None,
    modules: list[str] | None = None,
) -> list[ClaimConflict]:
    """Check if proposed areas of influence conflict with active claims."""
    conflicts = []
    current = active_claims()

    organs_set = set(organs or [])
    repos_set = set(repos or [])
    files_set = set(files or [])
    modules_set = set(modules or [])

    for claim in current:
        # Check organ overlap
        organ_overlap = organs_set & set(claim.organs)
        if organ_overlap:
            conflicts.append(ClaimConflict(
                existing_claim=claim,
                overlap_type="organ",
                overlap_values=sorted(organ_overlap),
            ))
            continue  # One conflict per claim is enough

        # Check repo overlap
        repo_overlap = repos_set & set(claim.repos)
        if repo_overlap:
            conflicts.append(ClaimConflict(
                existing_claim=claim,
                overlap_type="repo",
                overlap_values=sorted(repo_overlap),
            ))
            continue

        # Check file overlap
        file_overlap = files_set & set(claim.files)
        if file_overlap:
            conflicts.append(ClaimConflict(
                existing_claim=claim,
                overlap_type="file",
                overlap_values=sorted(file_overlap),
            ))
            continue

        # Check module overlap
        module_overlap = modules_set & set(claim.modules)
        if module_overlap:
            conflicts.append(ClaimConflict(
                existing_claim=claim,
                overlap_type="module",
                overlap_values=sorted(module_overlap),
            ))

    return conflicts


def capacity_status(max_capacity: int = DEFAULT_CAPACITY) -> dict[str, Any]:
    """Check current resource capacity utilization.

    Returns load metrics so agents can decide whether to proceed or wait.
    """
    claims = active_claims()
    current_load = sum(c.cost for c in claims)
    return {
        "current_load": current_load,
        "max_capacity": max_capacity,
        "available": max(0, max_capacity - current_load),
        "utilization_pct": round(current_load / max_capacity * 100, 1) if max_capacity else 0,
        "at_capacity": current_load >= max_capacity,
        "active_streams": len(claims),
        "by_weight": {
            "light": sum(1 for c in claims if c.resource_weight == "light"),
            "medium": sum(1 for c in claims if c.resource_weight == "medium"),
            "heavy": sum(1 for c in claims if c.resource_weight == "heavy"),
        },
    }


def punch_in(
    agent: str,
    session_id: str,
    organs: list[str] | None = None,
    repos: list[str] | None = None,
    files: list[str] | None = None,
    modules: list[str] | None = None,
    scope: str = "",
    resource_weight: str = "medium",
    test_obligations: list[str] | None = None,
    ttl_seconds: int = DEFAULT_CLAIM_TTL_SECONDS,
) -> dict[str, Any]:
    """Punch in: declare areas of influence for this work session.

    Args:
        agent: Agent type (claude, gemini, codex, human).
        session_id: Session identifier.
        organs/repos/files/modules: Areas being claimed.
        scope: Free-text description of the work.
        resource_weight: light (1), medium (2), or heavy (3) cost units.
        test_obligations: Test commands to defer to the prover session
            (e.g. ["pytest organvm-engine/tests/ -v"]).
        ttl_seconds: Claim expiry (default 4h).

    Returns a dict with:
    - handle: unique name tag for this stream (e.g. "claude-forge")
    - claim_id: unique ID for this claim (use to punch out)
    - conflicts: any detected conflicts with existing claims
    - capacity: current resource utilization after this claim
    """
    import hashlib

    now = time.time()
    raw = f"{agent}:{session_id}:{now}"
    claim_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

    organs = organs or []
    repos = repos or []
    files = files or []
    modules = modules or []
    test_obligations = test_obligations or []

    resource_weight = normalise_weight(resource_weight)

    # Generate a unique handle (name tag)
    existing_handles = {c.handle for c in active_claims() if c.handle}
    handle = _generate_handle(agent, existing_handles)

    # Check for conflicts
    conflicts = check_conflicts(organs, repos, files, modules)

    # Check capacity before claiming
    cap = capacity_status()
    proposed_cost = weight_cost(resource_weight)
    capacity_warning = None
    if cap["at_capacity"]:
        capacity_warning = (
            f"Machine at capacity ({cap['current_load']}/{cap['max_capacity']} units). "
            "This session may degrade performance. Consider waiting."
        )
    elif cap["current_load"] + proposed_cost > cap["max_capacity"]:
        capacity_warning = (
            f"This {resource_weight} session ({proposed_cost} units) would exceed capacity "
            f"({cap['current_load']}+{proposed_cost} > {cap['max_capacity']}). "
            "Consider using a lighter weight or waiting."
        )

    event = {
        "event_type": "claim.punch_in",
        "claim_id": claim_id,
        "handle": handle,
        "agent": agent,
        "session_id": session_id,
        "timestamp": now,
        "iso_time": datetime.now(timezone.utc).isoformat(),
        "organs": organs,
        "repos": repos,
        "files": files,
        "modules": modules,
        "scope": scope,
        "resource_weight": resource_weight,
        "test_obligations": test_obligations,
        "ttl_seconds": ttl_seconds,
    }
    _append_event(event)

    result: dict[str, Any] = {
        "handle": handle,
        "claim_id": claim_id,
        "conflicts": [
            {
                "with_handle": c.existing_claim.handle,
                "with_agent": c.existing_claim.agent,
                "with_session": c.existing_claim.session_id,
                "overlap_type": c.overlap_type,
                "overlap_values": c.overlap_values,
                "claimed_scope": c.existing_claim.scope,
            }
            for c in conflicts
        ],
        "conflict_count": len(conflicts),
        "active_claims": len(active_claims()),
        "resource_weight": resource_weight,
        "cost": proposed_cost,
        "capacity": capacity_status(),
        "areas": [
            *[f"organ:{o}" for o in organs],
            *[f"repo:{r}" for r in repos],
            *[f"file:{f}" for f in files],
            *[f"module:{m}" for m in modules],
        ],
    }
    if capacity_warning:
        result["capacity_warning"] = capacity_warning

    # Emit coordination event
    try:
        from organvm_engine.pulse.emitter import emit_engine_event
        from organvm_engine.pulse.types import AGENT_PUNCHED_IN

        emit_engine_event(
            event_type=AGENT_PUNCHED_IN,
            source="coordination",
            payload={
                "handle": handle,
                "agent": agent,
                "resource_weight": resource_weight,
                "areas": result["areas"],
            },
        )
    except Exception:
        pass

    # Emit to Testament Chain
    from organvm_engine.ledger.emit import testament_emit
    testament_emit(
        event_type="agent.punch_in",
        source_organ="META-ORGANVM",
        source_repo="organvm-engine",
        actor=handle,
        payload={"agent": agent, "handle": handle, "areas": result["areas"]},
    )

    return result


def punch_out(claim_id: str) -> dict[str, Any]:
    """Punch out: release a claim on areas of influence.

    Args:
        claim_id: The claim_id returned from punch_in.

    Returns:
        Dict with release confirmation.
    """
    # Verify claim exists and is active
    events = _read_events()
    claims = _build_active_claims(events)
    found = None
    for c in claims:
        if c.claim_id == claim_id:
            found = c
            break

    if found is None:
        # Check if it was already released or expired
        all_claims: dict[str, WorkClaim] = {}
        for event in events:
            if event.get("event_type") == "claim.punch_in":
                all_claims[event.get("claim_id", "")] = WorkClaim.from_dict(event)

        if claim_id in all_claims:
            claim = all_claims[claim_id]
            if claim.is_expired:
                return {"released": True, "note": "Claim had already expired"}
            return {"released": True, "note": "Claim was already released"}
        return {"error": f"No claim found with id '{claim_id}'"}

    event = {
        "event_type": "claim.punch_out",
        "claim_id": claim_id,
        "timestamp": time.time(),
        "iso_time": datetime.now(timezone.utc).isoformat(),
        "handle": found.handle,
        "agent": found.agent,
        "session_id": found.session_id,
    }
    _append_event(event)

    result: dict[str, Any] = {
        "released": True,
        "claim_id": claim_id,
        "handle": found.handle,
        "agent": found.agent,
        "areas_released": found.areas,
        "remaining_active": len(active_claims()) - 1,
    }
    if found.test_obligations:
        result["test_obligations"] = found.test_obligations
        result["note"] = (
            f"{len(found.test_obligations)} test obligation(s) deferred. "
            "Run organvm_prove_sweep to execute all pending tests."
        )

    # Emit punch-out event
    try:
        from organvm_engine.pulse.emitter import emit_engine_event
        from organvm_engine.pulse.types import AGENT_PUNCHED_OUT

        emit_engine_event(
            event_type=AGENT_PUNCHED_OUT,
            source="coordination",
            payload={
                "handle": found.handle,
                "agent": found.agent,
                "claim_id": claim_id,
            },
        )
    except Exception:
        pass

    # Emit to Testament Chain
    from organvm_engine.ledger.emit import testament_emit
    testament_emit(
        event_type="agent.punch_out",
        source_organ="META-ORGANVM",
        source_repo="organvm-engine",
        actor=found.handle,
        payload={"agent": found.agent, "handle": found.handle, "claim_id": claim_id},
    )

    return result


def work_board() -> dict[str, Any]:
    """Get the current work board — all active claims across all agents.

    This is the "who's working on what" view that any AI stream can query
    before starting work.
    """
    claims = active_claims()

    by_agent: dict[str, list[dict]] = {}
    all_test_obligations: list[str] = []
    for c in claims:
        entry = {
            "handle": c.handle,
            "claim_id": c.claim_id,
            "session_id": c.session_id,
            "scope": c.scope,
            "areas": c.areas,
            "resource_weight": c.resource_weight,
            "since": datetime.fromtimestamp(c.timestamp, tz=timezone.utc).isoformat(),
            "minutes_active": int((time.time() - c.timestamp) / 60),
            "ttl_remaining_minutes": max(
                0,
                int((c.timestamp + c.ttl_seconds - time.time()) / 60),
            ),
        }
        if c.test_obligations:
            entry["test_obligations"] = c.test_obligations
        by_agent.setdefault(c.agent, []).append(entry)
        all_test_obligations.extend(c.test_obligations)

    # Also collect test obligations from recently released claims (last hour)
    # so the prover sees what needs running even after agents punch out
    events = _read_events()
    now = time.time()
    for evt in events:
        if evt.get("event_type") == "claim.punch_in":
            ts = evt.get("timestamp", 0)
            if now - ts < 3600:  # last hour
                for ob in evt.get("test_obligations", []):
                    if ob not in all_test_obligations:
                        all_test_obligations.append(ob)

    return {
        "active_claims": len(claims),
        "agents_working": len(by_agent),
        "capacity": capacity_status(),
        "pending_test_obligations": all_test_obligations,
        "test_obligation_count": len(all_test_obligations),
        "by_agent": by_agent,
        "claims": [c.to_dict() for c in claims],
    }


def prove_sweep() -> dict[str, Any]:
    """Collect all pending test obligations for a single prover session.

    Scans all claims (active + recently released) and returns a deduplicated
    list of test commands to run. This is the "one session runs all tests"
    pattern — agents BUILD and declare obligations, the prover PROVES.
    """
    events = _read_events()
    now = time.time()

    obligations: list[str] = []
    sources: list[dict] = []
    seen: set[str] = set()

    for evt in events:
        if evt.get("event_type") != "claim.punch_in":
            continue
        ts = evt.get("timestamp", 0)
        # Only consider claims from the last 8 hours
        if now - ts > 8 * 3600:
            continue
        for ob in evt.get("test_obligations", []):
            if ob not in seen:
                seen.add(ob)
                obligations.append(ob)
                sources.append({
                    "command": ob,
                    "from_handle": evt.get("handle", ""),
                    "from_agent": evt.get("agent", ""),
                    "from_scope": evt.get("scope", ""),
                })

    return {
        "obligations": obligations,
        "total": len(obligations),
        "sources": sources,
        "active_claims": len(active_claims()),
        "note": (
            "Run these commands sequentially in one session to verify "
            "all concurrent work integrates correctly."
            if obligations
            else "No pending test obligations."
        ),
    }
