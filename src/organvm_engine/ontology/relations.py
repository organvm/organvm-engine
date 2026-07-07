"""Unified relation layer — one query interface over three relation stores.

Implements: SPEC-002, PRIM-003 (Relation)
Resolves: engine #28

Abstracts over the three existing relation stores in the ORGANVM system:
  1. Ontologia lineage (LineageRecord — predecessor/successor genealogy)
  2. Seed graph (produces/consumes edges — data-flow contracts)
  3. Dependency graph (dependency edges — build/import ordering)

Each store uses different types, different key formats, and different query
APIs. This module normalizes everything into a single Relation dataclass
and a UnifiedRelationStore that can aggregate queries across all three.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Relation types — superset of all edge semantics across the three stores
# ---------------------------------------------------------------------------

class RelationType(str, Enum):
    """Canonical relation types across all ORGANVM stores."""

    CONTAINMENT = "CONTAINMENT"              # hierarchy edge (organ→repo, repo→module)
    LINEAGE = "LINEAGE"                      # predecessor/successor genealogy
    DEPENDENCY = "DEPENDENCY"                # build/import dependency
    DATA_FLOW = "DATA_FLOW"                  # produces/consumes artifact edge
    SUBSCRIPTION = "SUBSCRIPTION"            # event subscription
    NAMING = "NAMING"                        # name record association
    INHERENCE = "INHERENCE"                  # dependent entity inhering in bearer
    PROMOTION_CONSTRAINT = "PROMOTION_CONSTRAINT"  # governance constraint on promotion


# ---------------------------------------------------------------------------
# Normalized relation record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Relation:
    """A single normalized relation between two entities.

    Fields:
        source_uid:    Identifier of the source entity. May be an ontologia UID
                       (e.g. "ent_repo_abc") or a registry key (e.g. "meta-organvm/organvm-engine").
        target_uid:    Identifier of the target entity, same format as source_uid.
        relation_type: One of the canonical RelationType values.
        metadata:      Store-specific metadata (e.g. lineage_type, artifact_type).
        created_at:    UTC timestamp when the relation was created or discovered.
        store_origin:  Which store this relation was loaded from ("lineage", "seed", "dependency").
    """

    source_uid: str
    target_uid: str
    relation_type: RelationType
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    store_origin: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "source_uid": self.source_uid,
            "target_uid": self.target_uid,
            "relation_type": self.relation_type.value,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "store_origin": self.store_origin,
        }


# ---------------------------------------------------------------------------
# Store adapters — extract Relation objects from each existing store
# ---------------------------------------------------------------------------

# Mapping from ontologia LineageType values to our RelationType
_LINEAGE_TYPE_MAP: dict[str, RelationType] = {
    "derived_from": RelationType.LINEAGE,
    "supersedes": RelationType.LINEAGE,
    "merged_into": RelationType.LINEAGE,
    "split_from": RelationType.LINEAGE,
}


def relations_from_lineage(lineage_records: list[dict[str, Any]]) -> list[Relation]:
    """Convert ontologia LineageRecord dicts into normalized Relations.

    Args:
        lineage_records: List of LineageRecord.to_dict() outputs, each with
            entity_id, related_id, lineage_type, recorded_at, metadata.

    Returns:
        List of Relation objects with relation_type=LINEAGE.
    """
    results: list[Relation] = []
    for rec in lineage_records:
        entity_id = rec.get("entity_id", "")
        related_id = rec.get("related_id", "")
        lineage_type = rec.get("lineage_type", "")
        rel_type = _LINEAGE_TYPE_MAP.get(lineage_type, RelationType.LINEAGE)

        meta: dict[str, Any] = {"lineage_type": lineage_type}
        if rec.get("metadata"):
            meta["original_metadata"] = rec["metadata"]

        results.append(Relation(
            source_uid=entity_id,
            target_uid=related_id,
            relation_type=rel_type,
            metadata=meta,
            created_at=rec.get("recorded_at", ""),
            store_origin="lineage",
        ))
    return results


def relations_from_seed_graph(
    edges: list[tuple[str, str, str]],
) -> list[Relation]:
    """Convert seed graph edges into normalized Relations.

    Args:
        edges: List of (producer, consumer, artifact_type) tuples from SeedGraph.edges.

    Returns:
        List of Relation objects with relation_type=DATA_FLOW.
    """
    results: list[Relation] = []
    for producer, consumer, artifact_type in edges:
        results.append(Relation(
            source_uid=producer,
            target_uid=consumer,
            relation_type=RelationType.DATA_FLOW,
            metadata={"artifact_type": artifact_type},
            store_origin="seed",
        ))
    return results


def relations_from_dependencies(registry: dict[str, Any]) -> list[Relation]:
    """Extract dependency edges from a registry dict into normalized Relations.

    Args:
        registry: Loaded registry-v2.json dict.

    Returns:
        List of Relation objects with relation_type=DEPENDENCY.
    """
    results: list[Relation] = []

    for organ_data in registry.get("organs", {}).values():
        for repo in organ_data.get("repositories", []):
            org = repo.get("org", "")
            name = repo.get("name", "")
            if not org or not name:
                continue
            source_key = f"{org}/{name}"

            for dep in repo.get("dependencies", []):
                results.append(Relation(
                    source_uid=source_key,
                    target_uid=dep,
                    relation_type=RelationType.DEPENDENCY,
                    metadata={},
                    store_origin="dependency",
                ))

    return results


def relations_from_hierarchy(
    hierarchy_edges: list[dict[str, Any]],
) -> list[Relation]:
    """Convert ontologia HierarchyEdge dicts into normalized Relations.

    Args:
        hierarchy_edges: List of HierarchyEdge.to_dict() outputs, each with
            parent_id, child_id, valid_from, valid_to, metadata.

    Returns:
        List of Relation objects with relation_type=CONTAINMENT.
    """
    results: list[Relation] = []
    for edge in hierarchy_edges:
        parent_id = edge.get("parent_id", "")
        child_id = edge.get("child_id", "")
        valid_from = edge.get("valid_from", "")

        meta: dict[str, Any] = {}
        if edge.get("valid_to"):
            meta["valid_to"] = edge["valid_to"]
        if edge.get("metadata"):
            meta["original_metadata"] = edge["metadata"]

        results.append(Relation(
            source_uid=parent_id,
            target_uid=child_id,
            relation_type=RelationType.CONTAINMENT,
            metadata=meta,
            created_at=valid_from,
            store_origin="lineage",
        ))
    return results


# ---------------------------------------------------------------------------
# Unified relation store
# ---------------------------------------------------------------------------

class UnifiedRelationStore:
    """Aggregates relations from multiple stores into a single query interface.

    Lazily loads relations on first query. Callers populate via load_*() methods
    or pass pre-built Relation lists to the constructor.
    """

    def __init__(self, relations: list[Relation] | None = None) -> None:
        self._relations: list[Relation] = list(relations) if relations else []

    # -- Loaders -----------------------------------------------------------

    def load_lineage(self, lineage_records: list[dict[str, Any]]) -> int:
        """Load lineage records into the store.

        Args:
            lineage_records: List of LineageRecord.to_dict() outputs.

        Returns:
            Number of relations added.
        """
        new = relations_from_lineage(lineage_records)
        self._relations.extend(new)
        return len(new)

    def load_seed_graph(self, edges: list[tuple[str, str, str]]) -> int:
        """Load seed graph edges into the store.

        Args:
            edges: SeedGraph.edges list of (producer, consumer, artifact_type).

        Returns:
            Number of relations added.
        """
        new = relations_from_seed_graph(edges)
        self._relations.extend(new)
        return len(new)

    def load_dependencies(self, registry: dict[str, Any]) -> int:
        """Load dependency edges from a registry into the store.

        Args:
            registry: Loaded registry-v2.json dict.

        Returns:
            Number of relations added.
        """
        new = relations_from_dependencies(registry)
        self._relations.extend(new)
        return len(new)

    def load_hierarchy(self, hierarchy_edges: list[dict[str, Any]]) -> int:
        """Load hierarchy edges from ontologia into the store.

        Args:
            hierarchy_edges: List of HierarchyEdge.to_dict() outputs.

        Returns:
            Number of relations added.
        """
        new = relations_from_hierarchy(hierarchy_edges)
        self._relations.extend(new)
        return len(new)

    def add(self, relation: Relation) -> None:
        """Add a single relation to the store."""
        self._relations.append(relation)

    # -- Queries -----------------------------------------------------------

    def query(
        self,
        source: str | None = None,
        target: str | None = None,
        rel_type: RelationType | None = None,
        store_origin: str | None = None,
    ) -> list[Relation]:
        """Query relations with optional filters (AND-combined).

        Args:
            source:       Filter by source_uid (exact match).
            target:       Filter by target_uid (exact match).
            rel_type:     Filter by RelationType.
            store_origin: Filter by originating store ("lineage", "seed", "dependency").

        Returns:
            List of matching Relation objects.
        """
        results: list[Relation] = []
        for rel in self._relations:
            if source is not None and rel.source_uid != source:
                continue
            if target is not None and rel.target_uid != target:
                continue
            if rel_type is not None and rel.relation_type != rel_type:
                continue
            if store_origin is not None and rel.store_origin != store_origin:
                continue
            results.append(rel)
        return results

    def neighbors(
        self,
        uid: str,
        direction: str = "both",
        rel_type: RelationType | None = None,
    ) -> list[Relation]:
        """Find all relations involving a given entity.

        Args:
            uid:       The entity identifier to search for.
            direction: "outgoing" (uid is source), "incoming" (uid is target),
                       or "both" (either).
            rel_type:  Optional filter by relation type.

        Returns:
            List of matching Relation objects.
        """
        results: list[Relation] = []
        for rel in self._relations:
            if rel_type is not None and rel.relation_type != rel_type:
                continue
            match = (
                (direction == "outgoing" and rel.source_uid == uid)
                or (direction == "incoming" and rel.target_uid == uid)
                or (direction == "both" and uid in {rel.source_uid, rel.target_uid})
            )
            if match:
                results.append(rel)
        return results

    def sources_of(self, target: str) -> list[str]:
        """Return all source UIDs that point to the given target."""
        return list({
            rel.source_uid for rel in self._relations
            if rel.target_uid == target
        })

    def targets_of(self, source: str) -> list[str]:
        """Return all target UIDs that the given source points to."""
        return list({
            rel.target_uid for rel in self._relations
            if rel.source_uid == source
        })

    def by_type(self, rel_type: RelationType) -> list[Relation]:
        """Return all relations of a given type."""
        return [rel for rel in self._relations if rel.relation_type == rel_type]

    def store_summary(self) -> dict[str, int]:
        """Count relations by store_origin."""
        counts: dict[str, int] = {}
        for rel in self._relations:
            origin = rel.store_origin or "unknown"
            counts[origin] = counts.get(origin, 0) + 1
        return counts

    def type_summary(self) -> dict[str, int]:
        """Count relations by RelationType."""
        counts: dict[str, int] = {}
        for rel in self._relations:
            key = rel.relation_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    @property
    def count(self) -> int:
        """Total number of relations in the store."""
        return len(self._relations)

    @property
    def all_relations(self) -> list[Relation]:
        """Return all relations (copy of internal list)."""
        return list(self._relations)

    def snapshot(self) -> list[dict[str, Any]]:
        """Serialize all relations to a list of dicts."""
        return [rel.to_dict() for rel in self._relations]
