"""AMMOI — Adaptive Macro-Micro Ontological Index.

A compressed multi-scale density index that every node can carry.
Computes density at three scales:
  - Macro: system-wide (the whole ORGANVM)
  - Meso: per-organ (each of the eight organs)
  - Micro: per-entity (individual repos)

The AMMOI snapshot is the system's compressed self-image — small enough
to inject into every context file, rich enough to convey the system's
state at a glance.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class EntityDensity:
    """Micro-scale: density for a single entity."""

    entity_id: str
    entity_name: str
    organ: str
    local_edges: int = 0
    gate_pct: int = 0
    event_frequency_24h: int = 0
    blast_radius: int = 0
    active_claims: int = 0
    density: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OrganDensity:
    """Meso-scale: density for an organ."""

    organ_id: str
    organ_name: str
    repo_count: int = 0
    module_count: int = 0
    component_count: int = 0  # from deep structural indexer
    internal_edges: int = 0
    cross_edges: int = 0
    avg_gate_pct: int = 0
    event_frequency_24h: int = 0
    active_agents: int = 0
    tension_count: int = 0
    density: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AMMOI:
    """Adaptive Macro-Micro Ontological Index.

    A compressed image of the whole that can be projected at any scale.
    """

    timestamp: str = ""

    # Macro: system-wide
    system_density: float = 0.0
    total_entities: int = 0
    total_modules: int = 0
    total_components: int = 0  # from deep structural indexer
    hierarchy_depth: int = 3  # organ→repo→module (2 before modules existed)
    active_edges: int = 0
    active_loops: int = 0
    tension_count: int = 0
    event_frequency_24h: int = 0

    # Inference
    cluster_count: int = 0
    orphan_count: int = 0
    overcoupled_count: int = 0
    inference_score: float = 0.0

    # Temporal vectors (None = no historical data; 0.0 = genuinely unchanged)
    density_delta_24h: float | None = None
    density_delta_7d: float | None = None
    density_delta_30d: float | None = None

    # Meso: per-organ
    organs: dict[str, OrganDensity] = field(default_factory=dict)

    # Rhythm
    pulse_count: int = 0
    pulse_interval: int = 900  # default 15min

    # Temporal profile (from temporal.py)
    temporal: dict[str, Any] | None = None

    # Flow analysis (from flow.py)
    flow_score: float = 0.0
    flow_active: int = 0
    flow_dormant: int = 0

    # Compressed text (for context injection)
    compressed_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "system_density": self.system_density,
            "total_entities": self.total_entities,
            "total_modules": self.total_modules,
            "total_components": self.total_components,
            "hierarchy_depth": self.hierarchy_depth,
            "active_edges": self.active_edges,
            "active_loops": self.active_loops,
            "tension_count": self.tension_count,
            "event_frequency_24h": self.event_frequency_24h,
            "cluster_count": self.cluster_count,
            "orphan_count": self.orphan_count,
            "overcoupled_count": self.overcoupled_count,
            "inference_score": self.inference_score,
            "density_delta_24h": self.density_delta_24h,
            "density_delta_7d": self.density_delta_7d,
            "density_delta_30d": self.density_delta_30d,
            "organs": {k: v.to_dict() for k, v in self.organs.items()},
            "pulse_count": self.pulse_count,
            "pulse_interval": self.pulse_interval,
            "temporal": self.temporal,
            "flow_score": self.flow_score,
            "flow_active": self.flow_active,
            "flow_dormant": self.flow_dormant,
            "compressed_text": self.compressed_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AMMOI:
        organs = {}
        for k, v in data.get("organs", {}).items():
            organs[k] = OrganDensity(**v)
        return cls(
            timestamp=data.get("timestamp", ""),
            system_density=data.get("system_density", 0.0),
            total_entities=data.get("total_entities", 0),
            total_modules=data.get("total_modules", 0),
            total_components=data.get("total_components", 0),
            hierarchy_depth=data.get("hierarchy_depth", 3),
            active_edges=data.get("active_edges", 0),
            active_loops=data.get("active_loops", 0),
            tension_count=data.get("tension_count", 0),
            event_frequency_24h=data.get("event_frequency_24h", 0),
            cluster_count=data.get("cluster_count", 0),
            orphan_count=data.get("orphan_count", 0),
            overcoupled_count=data.get("overcoupled_count", 0),
            inference_score=data.get("inference_score", 0.0),
            density_delta_24h=data.get("density_delta_24h"),
            density_delta_7d=data.get("density_delta_7d"),
            density_delta_30d=data.get("density_delta_30d"),
            organs=organs,
            pulse_count=data.get("pulse_count", 0),
            pulse_interval=data.get("pulse_interval", 900),
            temporal=data.get("temporal"),
            flow_score=data.get("flow_score", 0.0),
            flow_active=data.get("flow_active", 0),
            flow_dormant=data.get("flow_dormant", 0),
            compressed_text=data.get("compressed_text", ""),
        )


# ---------------------------------------------------------------------------
# AMMOI history storage
# ---------------------------------------------------------------------------

def _history_path() -> Path:
    return Path.home() / ".organvm" / "pulse" / "ammoi-history.jsonl"


def _read_history(limit: int = 500) -> list[AMMOI]:
    """Read AMMOI snapshots from history."""
    path = _history_path()
    if not path.is_file():
        return []
    snapshots: list[AMMOI] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            snapshots.append(AMMOI.from_dict(json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue
    return snapshots[-limit:]


def _append_history(ammoi: AMMOI) -> None:
    """Append an AMMOI snapshot to history."""
    path = _history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = json.dumps(ammoi.to_dict(), separators=(",", ":"), default=str)
    with path.open("a") as f:
        f.write(entry + "\n")


def _count_history() -> int:
    """Count total AMMOI snapshots in history (without parsing all)."""
    path = _history_path()
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text().splitlines() if line.strip())


# ---------------------------------------------------------------------------
# Timeseries extraction (bridge to temporal.py)
# ---------------------------------------------------------------------------

_TIMESERIES_KEYS = (
    "system_density", "active_edges", "tension_count",
    "event_frequency_24h", "cluster_count", "orphan_count",
    "overcoupled_count", "inference_score", "flow_score",
)


def extract_timeseries(history: list[AMMOI]) -> dict[str, list[float]]:
    """Extract metric time series from AMMOI history.

    Converts a list of AMMOI snapshots into a dict of named float series,
    suitable for feeding into ``compute_temporal_profile()``.
    """
    if not history:
        return {}
    result: dict[str, list[float]] = {k: [] for k in _TIMESERIES_KEYS}
    for snap in history:
        for key in _TIMESERIES_KEYS:
            result[key].append(float(getattr(snap, key, 0.0)))
    return result


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def _count_recent_events(hours: int = 24) -> int:
    """Count events in the last N hours from the engine event log."""
    try:
        from organvm_engine.pulse.events import event_counts

        counts = event_counts()
        return sum(counts.values())
    except Exception:
        return 0


def _compute_temporal_deltas(
    current_density: float,
    history: list[AMMOI],
) -> tuple[float | None, float | None, float | None]:
    """Compute density deltas against 24h, 7d, and 30d ago.

    Returns None for each window where no suitable historical snapshot
    exists (distinguishing "no data" from "genuinely unchanged" which
    returns 0.0).
    """
    if not history:
        return None, None, None

    now = datetime.now(timezone.utc)

    def _find_closest(target_hours: int) -> float | None:
        best: AMMOI | None = None
        best_diff = float("inf")
        for snap in history:
            try:
                ts = datetime.fromisoformat(snap.timestamp)
                diff = abs((now - ts).total_seconds() - target_hours * 3600)
                if diff < best_diff:
                    best_diff = diff
                    best = snap
            except (ValueError, TypeError):
                continue
        if best and best_diff < target_hours * 3600 * 0.5:
            return best.system_density
        return None

    d24 = _find_closest(24)
    d7 = _find_closest(168)
    d30 = _find_closest(720)

    delta_24h = current_density - d24 if d24 is not None else None
    delta_7d = current_density - d7 if d7 is not None else None
    delta_30d = current_density - d30 if d30 is not None else None

    return delta_24h, delta_7d, delta_30d


def _build_compressed_text(ammoi: AMMOI) -> str:
    """Build a ~200 char human-readable summary for context injection."""
    organ_densities = sorted(
        ammoi.organs.items(),
        key=lambda x: x[1].density,
        reverse=True,
    )
    top_organs = ", ".join(
        f"{k}:{v.density:.0%}" for k, v in organ_densities[:3]
    )

    delta_str = ""
    if ammoi.density_delta_24h is not None:
        sign = "+" if ammoi.density_delta_24h > 0 else ""
        delta_str = f" | d24h:{sign}{ammoi.density_delta_24h:.1%}"

    score_str = f" IS:{ammoi.inference_score:.0%}" if ammoi.inference_score else ""

    trend_str = ""
    if ammoi.temporal:
        dominant = ammoi.temporal.get("dominant_trend", "stable")
        if dominant != "stable":
            trend_str = f" trend:{dominant}"

    if ammoi.total_components:
        depth_str = f" 8o/{ammoi.total_entities}r/{ammoi.total_components}c"
    elif ammoi.total_modules:
        depth_str = f" 8o/{ammoi.total_entities}r/{ammoi.total_modules}m"
    else:
        depth_str = ""

    return (
        f"AMMOI:{ammoi.system_density:.0%} "
        f"E:{ammoi.active_edges} "
        f"T:{ammoi.tension_count} "
        f"C:{ammoi.cluster_count} "
        f"Ev24h:{ammoi.event_frequency_24h}"
        f"{score_str}"
        f"{depth_str} "
        f"[{top_organs}]"
        f"{delta_str}"
        f"{trend_str}"
    )


def compute_ammoi(
    registry: dict | None = None,
    workspace: Path | None = None,
    include_events: bool = True,
) -> AMMOI:
    """Compute the full AMMOI snapshot.

    Draws data from:
    - Registry + organism (gate pass rates, repo counts)
    - Seed graph (edges, cross-organ wiring)
    - Density module (interconnection score)
    - Event log (activity frequency)
    - AMMOI history (temporal deltas)
    """
    from organvm_engine.metrics.organism import get_organism
    from organvm_engine.pulse.density import compute_density
    from organvm_engine.seed.graph import build_seed_graph, validate_edge_resolution

    organism = get_organism(registry=registry, include_omega=False)
    ws = workspace or Path.home() / "Workspace"
    graph = build_seed_graph(ws)
    unresolved = validate_edge_resolution(graph)
    dp = compute_density(graph, organism, len(unresolved))

    # Per-organ computation — translate org-dir names to organ keys
    from organvm_engine.organ_config import dir_to_registry_key

    d2r = dir_to_registry_key()

    # Query ontologia for module entities (the 4th scale)
    modules_by_organ: dict[str, int] = {}
    total_modules = 0
    try:
        from ontologia.entity.identity import EntityType as OntEntityType
        from ontologia.registry.store import open_store

        ont_store = open_store()
        for entity in ont_store.list_entities(entity_type=OntEntityType.MODULE):
            total_modules += 1
            organ_key = entity.metadata.get("organ_key", "")
            if organ_key:
                modules_by_organ[organ_key] = modules_by_organ.get(organ_key, 0) + 1
    except Exception:
        pass

    # Load deep structural index (ground-truth component census)
    components_by_organ: dict[str, int] = {}
    total_components = 0
    index_hierarchy_depth = 3
    try:
        from organvm_engine.paths import corpus_dir

        index_path = corpus_dir() / "data" / "index" / "deep-index.json"
        if index_path.is_file():
            idx_data = json.loads(index_path.read_text())
            total_components = idx_data.get("total_components", 0)
            components_by_organ = idx_data.get("by_organ", {})
            # Max depth across all repos
            for repo_data in idx_data.get("repos", []):
                md = repo_data.get("max_depth", 0)
                index_hierarchy_depth = max(index_hierarchy_depth, md)
    except Exception:
        pass

    organ_densities: dict[str, OrganDensity] = {}
    for organ_org in organism.organs:
        oid = organ_org.organ_id
        oname = organ_org.organ_name

        # Count edges involving this organ
        internal = 0
        cross = 0
        for src, tgt, _ in graph.edges:
            src_dir = src.split("/")[0] if "/" in src else src
            tgt_dir = tgt.split("/")[0] if "/" in tgt else tgt
            src_key = d2r.get(src_dir, src_dir)
            tgt_key = d2r.get(tgt_dir, tgt_dir)
            if oid in (src_key, tgt_key):
                if src_key == tgt_key:
                    internal += 1
                else:
                    cross += 1

        organ_densities[oid] = OrganDensity(
            organ_id=oid,
            organ_name=oname,
            repo_count=organ_org.count,
            module_count=modules_by_organ.get(oid, 0),
            component_count=components_by_organ.get(oid, 0),
            internal_edges=internal,
            cross_edges=cross,
            avg_gate_pct=organ_org.avg_pct,
            density=organ_org.avg_pct / 100.0 if organ_org.count > 0 else 0.0,
        )

    # System density from the DensityProfile composite score
    system_density = dp.interconnection_score / 100.0

    # Event frequency
    event_freq = _count_recent_events() if include_events else 0

    # Temporal deltas from history
    history = _read_history(limit=3000)
    d24h, d7d, d30d = _compute_temporal_deltas(system_density, history)

    # Pulse count from history
    pulse_count = len(history)

    # Run inference (best-effort)
    inference_data: dict = {}
    try:
        from organvm_engine.pulse.inference_bridge import run_inference

        summary = run_inference(ws)
        inference_data = {
            "tension_count": summary.tension_count,
            "cluster_count": summary.cluster_count,
            "orphan_count": len(summary.orphaned_entities),
            "overcoupled_count": len(summary.overcoupled_entities),
            "inference_score": summary.inference_score,
            "active_loops": summary.cluster_count,
        }
    except Exception:
        pass

    # Flow analysis (best-effort)
    flow_data: dict = {}
    try:
        from organvm_engine.pulse.flow import compute_flow as _compute_flow

        flow_profile = _compute_flow(graph)
        flow_data = {
            "flow_score": flow_profile.flow_score,
            "flow_active": flow_profile.active_count,
            "flow_dormant": flow_profile.dormant_count,
        }
    except Exception:
        pass

    ammoi = AMMOI(
        timestamp=datetime.now(timezone.utc).isoformat(),
        system_density=round(system_density, 4),
        total_entities=organism.total_repos,
        total_modules=total_modules,
        total_components=total_components,
        hierarchy_depth=max(index_hierarchy_depth, 3 if total_modules > 0 else 2),
        active_edges=dp.declared_edges,
        active_loops=inference_data.get("active_loops", 0),
        tension_count=inference_data.get("tension_count", 0),
        event_frequency_24h=event_freq,
        cluster_count=inference_data.get("cluster_count", 0),
        orphan_count=inference_data.get("orphan_count", 0),
        overcoupled_count=inference_data.get("overcoupled_count", 0),
        inference_score=inference_data.get("inference_score", 0.0),
        density_delta_24h=round(d24h, 4) if d24h is not None else None,
        density_delta_7d=round(d7d, 4) if d7d is not None else None,
        density_delta_30d=round(d30d, 4) if d30d is not None else None,
        organs=organ_densities,
        pulse_count=pulse_count,
        flow_score=flow_data.get("flow_score", 0.0),
        flow_active=flow_data.get("flow_active", 0),
        flow_dormant=flow_data.get("flow_dormant", 0),
    )

    # Temporal profile (needs >= 3 history snapshots)
    if len(history) >= 3:
        try:
            from organvm_engine.pulse.temporal import compute_temporal_profile

            timeseries = extract_timeseries(history)
            profile = compute_temporal_profile(timeseries)
            ammoi.temporal = profile.to_dict()
        except Exception:
            pass

    ammoi.compressed_text = _build_compressed_text(ammoi)

    return ammoi
