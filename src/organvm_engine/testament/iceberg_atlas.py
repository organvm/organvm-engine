"""Deterministic dual-timeline Iceberg Atlas compiler and renderer."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from organvm_engine.corpus.governance_lineage import (
    ZOOM_LEVELS,
    QuarantineDiagnostic,
    bundle_children,
    canonical_node,
    content_digest,
    empty_state,
    evidence_groups,
    finalize_state,
    process_child,
    validate_bundle_headers,
)
from organvm_engine.events.spine import EventRecord, EventSpine, EventType

CURSOR_SCHEMA = "governance-atlas-cursor.v1"
RECEIPT_SCHEMA = "governance-atlas-receipt.v1"
PUBLIC_FILENAME = "iceberg-atlas.public.json"
DETAIL_FILENAME = "iceberg-atlas.private.json"

_PRIVATE_KEY_PARTS = ("secret", "token", "cookie", "raw_body", "private_custody")


@dataclass(frozen=True)
class AtlasCompileResult:
    """One bounded invocation result."""

    complete: bool
    processed_children: int
    remaining_children: int
    cursor_path: Path
    public_path: Path | None = None
    detail_path: Path | None = None
    receipt: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReceiptIdentity:
    """Runtime-resolved Event Spine identity; never inferred from a local path."""

    actor: str
    source_organ: str
    source_repo: str

    def __post_init__(self) -> None:
        if not self.actor or not self.source_organ or not self.source_repo:
            raise ValueError("receipt identity fields must be non-empty")


def _pretty_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _write_if_changed(path: Path, value: Any) -> None:
    rendered = _pretty_json(value)
    if path.is_file() and path.read_text(encoding="utf-8") == rendered:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _redact(value: Any) -> Any:
    """Remove private source bodies and custody locators from public output."""
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for key, item in value.items():
        lowered = key.lower()
        if any(part in lowered for part in _PRIVATE_KEY_PARTS):
            continue
        if lowered in {"body", "text", "content", "source_path", "custody_pointer"}:
            continue
        if lowered.endswith("_path") and lowered not in {"json_path"}:
            continue
        result[key] = _redact(item)
    return result


def _node_summary(node: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        "node_id": node["node_id"],
        "lane": node["lane"],
        "node_type": node["node_type"],
        "source_envelope_id": node["source_envelope_id"],
        "occurred_at": node["occurred_at"],
        "authority_class": node["authority_class"],
        "summary": node["summary"],
        "content_hash": node["content_hash"],
        "review_state": node["review_state"],
        "zoom_level": node["_zoom_level"],
    }
    metadata = node.get("metadata", {})
    for key in ("entity_id", "parent_node_id", "source_family"):
        if metadata.get(key) is not None:
            summary[key] = metadata[key]
    return summary


def _edge_summary(
    edge: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    source = nodes[edge["from_node"]]
    return {
        "edge_id": edge["edge_id"],
        "from_node": edge["from_node"],
        "to_node": edge["to_node"],
        "edge_type": edge["edge_type"],
        "occurred_at": source["occurred_at"],
        "evidence_source_ids": sorted(evidence_groups(edge)),
        "confidence": edge["confidence"],
        "review_state": edge["review_state"],
    }


def _timeline(nodes: list[dict[str, Any]], lane: str) -> list[dict[str, Any]]:
    selected = [_node_summary(node) for node in nodes if node["lane"] == lane]
    return sorted(selected, key=lambda item: (item["occurred_at"], item["node_id"]))


def _relationship_views(state: Mapping[str, Any]) -> dict[str, Any]:
    nodes = {node["node_id"]: node for node in state["nodes"]}
    reviewed = [edge for edge in state["edges"] if edge["review_state"] == "reviewed"]
    derived_nodes = {
        edge["from_node"]
        for edge in reviewed
        if edge["edge_type"]
        in {"refines", "corrects", "supersedes", "exact_duplicate", "transport_echo"}
    }
    origins = [
        _node_summary(node) for node in nodes.values() if node["node_id"] not in derived_nodes
    ]

    def edges_of(*edge_types: str) -> list[dict[str, Any]]:
        return sorted(
            [_edge_summary(edge, nodes) for edge in reviewed if edge["edge_type"] in edge_types],
            key=lambda item: (item["occurred_at"], item["edge_id"]),
        )

    return {
        "origins": sorted(origins, key=lambda item: (item["occurred_at"], item["node_id"])),
        "refinements": edges_of("refines", "corrects"),
        "supersessions": edges_of("supersedes"),
        "contradictions": edges_of("contradicts"),
        "implementations": edges_of("implements"),
        "adoptions": edges_of("adopts"),
        "duplicates_and_echoes": edges_of("exact_duplicate", "transport_echo"),
    }


def _citation_debt(state: Mapping[str, Any]) -> dict[str, Any]:
    debt: list[dict[str, Any]] = []
    for node in state["nodes"]:
        assertion_class = node.get("metadata", {}).get("assertion_class")
        required = 2 if assertion_class in {"external_fact", "current_state"} else 0
        missing = max(required - len(evidence_groups(node)), 0)
        if missing:
            debt.append(
                {
                    "unit_type": "node",
                    "unit_id": node["node_id"],
                    "missing_evidence_groups": missing,
                },
            )
    for edge in state["edges"]:
        if edge["review_state"] != "reviewed":
            continue
        missing = max(1 - len(evidence_groups(edge)), 0)
        if missing:
            debt.append(
                {
                    "unit_type": "edge",
                    "unit_id": edge["edge_id"],
                    "missing_evidence_groups": missing,
                },
            )
    for directive in state["directives"]:
        ratification = directive["testament"].get("ratification", {})
        groups = {
            str(ratification.get("authority_event_reference", "")),
            str(ratification.get("constitutional_record_reference", "")),
        }
        groups.discard("")
        missing = max(2 - len(groups), 0)
        if missing:
            debt.append(
                {
                    "unit_type": "directive",
                    "unit_id": directive["directive_id"],
                    "missing_evidence_groups": missing,
                },
            )
    for ideal in state["ideal_forms"]:
        missing = sum(
            1
            for predicate in ideal["ideal_form"]["predicates"]
            if not predicate.get("evidence_references")
        )
        if missing:
            debt.append(
                {
                    "unit_type": "ideal_form",
                    "unit_id": ideal["ideal_form_id"],
                    "missing_evidence_groups": missing,
                },
            )
    debt.sort(key=lambda item: (item["unit_type"], item["unit_id"]))
    return {"count": len(debt), "items": debt}


def _coverage_view(
    coverage: Mapping[str, Any],
    quarantine: list[dict[str, Any]],
) -> dict[str, Any]:
    public = _redact(deepcopy(dict(coverage)))
    counts = coverage["counts"]
    residual_counts = {
        key: int(counts[key])
        for key in (
            "acquired",
            "quarantined",
            "inaccessible",
            "missing_expected",
            "owner_blocked",
        )
        if int(counts[key]) > 0
    }
    compiler_quarantine_count = len(quarantine)
    public.update(
        {
            "source_exact_all": bool(coverage["exact_all"]),
            "source_ready": bool(coverage["ready"]),
            "compiler_quarantine_count": compiler_quarantine_count,
            "compiler_quarantine_ids": sorted(item["diagnostic_id"] for item in quarantine),
            "atlas_exact_all": bool(coverage["exact_all"]) and not quarantine,
            "atlas_ready": bool(coverage["ready"]) and not quarantine,
            "coverage_debt": {
                "count": sum(residual_counts.values()) + compiler_quarantine_count,
                "residual_counts": residual_counts,
            },
        },
    )
    return public


def _self_image_summary(image: Mapping[str, Any]) -> dict[str, Any]:
    return _redact(deepcopy(dict(image)))


def _ideal_forms(
    state: Mapping[str, Any],
    citation_debt: Mapping[str, Any],
) -> list[dict[str, Any]]:
    debt_by_ideal = {
        item["unit_id"]: item["missing_evidence_groups"]
        for item in citation_debt["items"]
        if item["unit_type"] == "ideal_form"
    }
    ideals: list[dict[str, Any]] = []
    for wrapper in state["ideal_forms"]:
        ideal = _redact(deepcopy(wrapper["ideal_form"]))
        distance = ideal["distance_to_ideal"]
        total = distance["total_predicates"]
        ideal.update(
            {
                "controlling_node_id": wrapper["controlling_node_id"],
                "distance_fraction": 1 - (distance["verified_predicates"] / total),
                "citation_debt": debt_by_ideal.get(wrapper["ideal_form_id"], 0),
            },
        )
        ideals.append(ideal)
    return sorted(ideals, key=lambda item: item["ideal_form_id"])


def _testament_projection(state: Mapping[str, Any]) -> dict[str, Any] | None:
    if not state["directives"]:
        return None
    directive = state["directives"][0]
    return {
        **_redact(deepcopy(directive["testament"])),
        "controlling_node_id": directive["controlling_node_id"],
    }


def _compiled_lineage_graph(
    bundle: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    source = bundle["lineage_graph"]
    return {
        "contract_name": source["contract_name"],
        "contract_version": source["contract_version"],
        "graph_id": source["graph_id"],
        "generated_at": source["generated_at"],
        "frozen_snapshot_id": source["frozen_snapshot_id"],
        "nodes": [canonical_node(node) for node in state["nodes"]],
        "edges": deepcopy(state["edges"]),
    }


def _compiled_ideal_register(
    bundle: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    source = bundle["ideal_form_register"]
    return {
        "contract_name": source["contract_name"],
        "contract_version": source["contract_version"],
        "register_id": source["register_id"],
        "generated_at": source["generated_at"],
        "frozen_snapshot_id": source["frozen_snapshot_id"],
        "ideal_forms": [deepcopy(wrapper["ideal_form"]) for wrapper in state["ideal_forms"]],
    }


def _render_core(bundle: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[dict, dict]:
    nodes = state["nodes"]
    citation_debt = _citation_debt(state)
    public = {
        "contract_name": "iceberg-atlas.v1",
        "contract_version": 1,
        "snapshot_id": bundle["snapshot_id"],
        "generated_at": bundle["snapshot_at"],
        "governance_testament": _testament_projection(state),
        "timelines": {
            "operator_intent": _timeline(nodes, "operator_intent"),
            "artifact": _timeline(nodes, "artifact"),
        },
        "zoom_levels": {
            level: sorted(
                [_node_summary(node) for node in nodes if node["_zoom_level"] == level],
                key=lambda item: (item["occurred_at"], item["node_id"]),
            )
            for level in ZOOM_LEVELS
        },
        "relationships": _relationship_views(state),
        "ideal_forms": _ideal_forms(state, citation_debt),
        "coverage": _coverage_view(bundle["coverage"], state["quarantine"]),
        "self_images": sorted(
            [_self_image_summary(image) for image in state["self_images"]],
            key=lambda item: item["node_id"],
        ),
        "citation_debt": citation_debt,
    }
    testament = deepcopy(state["directives"][0]["testament"]) if state["directives"] else None
    detail = {
        "contract_name": "iceberg-atlas-detail.v1",
        "contract_version": 1,
        "snapshot_id": bundle["snapshot_id"],
        "generated_at": bundle["snapshot_at"],
        "governance_testament": testament,
        "lineage_graph": _compiled_lineage_graph(bundle, state),
        "ideal_form_register": _compiled_ideal_register(bundle, state),
        "coverage": deepcopy(bundle["coverage"]),
        "self_images": deepcopy(state["self_images"]),
        "adopted_artifact_node_ids": deepcopy(state["adopted_artifact_node_ids"]),
        "citation_debt": citation_debt,
        "quarantine": deepcopy(state["quarantine"]),
    }
    return public, detail


class IcebergAtlasCompiler:
    """Compile one frozen governance snapshot in finite, resumable children."""

    def __init__(self, event_spine: EventSpine, *, receipt_identity: ReceiptIdentity) -> None:
        self._event_spine = event_spine
        self._receipt_identity = receipt_identity

    def compile(
        self,
        bundle: Mapping[str, Any],
        *,
        output_dir: Path,
        cursor_path: Path,
        max_children: int = 1_000,
    ) -> AtlasCompileResult:
        if max_children <= 0:
            raise ValueError("max_children must be positive")
        validate_bundle_headers(bundle)
        children = bundle_children(bundle)
        input_digest = content_digest(bundle)
        cursor = self._load_cursor(cursor_path, bundle, input_digest, len(children))
        start = int(cursor["next_child"])
        stop = min(start + max_children, len(children))
        state = cursor["state"]
        for kind, source_index, unit in children[start:stop]:
            process_child(state, kind, source_index, unit)
        cursor["next_child"] = stop
        cursor["state"] = state

        if stop < len(children):
            cursor["complete"] = False
            _write_if_changed(cursor_path, cursor)
            return AtlasCompileResult(
                complete=False,
                processed_children=stop - start,
                remaining_children=len(children) - stop,
                cursor_path=cursor_path,
            )

        finalized = finalize_state(state)
        public_core, detail_core = _render_core(bundle, finalized)
        artifact_digest = content_digest(
            {"public": public_core, "detail_digest": content_digest(detail_core)},
        )
        event = self._receipt_event(str(bundle["snapshot_id"]), input_digest, artifact_digest)
        citation_debt = detail_core["citation_debt"]
        receipt = {
            "contract_name": RECEIPT_SCHEMA,
            "contract_version": 1,
            "snapshot_id": bundle["snapshot_id"],
            "snapshot_at": bundle["snapshot_at"],
            "input_digest": input_digest,
            "artifact_digest": artifact_digest,
            "processing_complete": True,
            "exact_all": public_core["coverage"]["atlas_exact_all"],
            "ready": public_core["coverage"]["atlas_ready"],
            "counts": {
                "nodes": len(finalized["nodes"]),
                "edges": len(finalized["edges"]),
                "directives": len(finalized["directives"]),
                "ideal_forms": len(finalized["ideal_forms"]),
                "self_images": len(finalized["self_images"]),
                "quarantined": len(finalized["quarantine"]),
            },
            "citation_debt": citation_debt,
            "coverage_debt": public_core["coverage"]["coverage_debt"],
            "event_spine": {
                "event_id": event.event_id,
                "sequence": event.sequence,
                "hash": event.hash,
            },
        }
        public = {**public_core, "receipt": receipt}
        detail = {**detail_core, "receipt": receipt}
        public_path = output_dir / PUBLIC_FILENAME
        detail_path = output_dir / DETAIL_FILENAME
        _write_if_changed(public_path, public)
        _write_if_changed(detail_path, detail)

        cursor.update(
            {
                "complete": True,
                "next_child": len(children),
                "state": finalized,
                "receipt": receipt,
            },
        )
        _write_if_changed(cursor_path, cursor)
        return AtlasCompileResult(
            complete=True,
            processed_children=stop - start,
            remaining_children=0,
            cursor_path=cursor_path,
            public_path=public_path,
            detail_path=detail_path,
            receipt=receipt,
        )

    def _load_cursor(
        self,
        path: Path,
        bundle: Mapping[str, Any],
        input_digest: str,
        total_children: int,
    ) -> dict[str, Any]:
        fresh = {
            "schema_id": CURSOR_SCHEMA,
            "snapshot_id": bundle["snapshot_id"],
            "input_digest": input_digest,
            "total_children": total_children,
            "next_child": 0,
            "complete": False,
            "state": empty_state(),
        }
        if not path.is_file():
            return fresh
        raw = path.read_text(encoding="utf-8")
        try:
            cursor = json.loads(raw)
        except json.JSONDecodeError:
            diagnostic = QuarantineDiagnostic.create("cursor", 0, raw, "malformed_cursor")
            fresh["state"]["quarantine"].append(diagnostic.to_dict())
            return fresh
        if (
            cursor.get("schema_id") != CURSOR_SCHEMA
            or cursor.get("snapshot_id") != bundle["snapshot_id"]
            or cursor.get("input_digest") != input_digest
            or cursor.get("total_children") != total_children
        ):
            return fresh
        if not isinstance(cursor.get("state"), dict):
            return fresh
        next_child = cursor.get("next_child")
        if not isinstance(next_child, int) or not 0 <= next_child <= total_children:
            return fresh
        return cursor

    def _receipt_event(
        self,
        snapshot_id: str,
        input_digest: str,
        artifact_digest: str,
    ) -> EventRecord:
        entity_uid = f"governance-atlas:{snapshot_id}"
        receipt_key = content_digest(
            {
                "snapshot_id": snapshot_id,
                "input_digest": input_digest,
                "artifact_digest": artifact_digest,
            },
        )
        event_count = int(self._event_spine.snapshot()["event_count"])
        existing = self._event_spine.query(
            event_type=EventType.TESTAMENT_VERIFIED,
            entity_uid=entity_uid,
            limit=max(event_count, 1),
        )
        for event in existing:
            if event.payload.get("receipt_key") == receipt_key:
                return event
        return self._event_spine.emit(
            event_type=EventType.TESTAMENT_VERIFIED,
            entity_uid=entity_uid,
            payload={
                "receipt_key": receipt_key,
                "snapshot_id": snapshot_id,
                "input_digest": input_digest,
                "artifact_digest": artifact_digest,
            },
            source_spec="governance-testament.v1+lineage-graph.v1",
            actor=self._receipt_identity.actor,
            source_organ=self._receipt_identity.source_organ,
            source_repo=self._receipt_identity.source_repo,
        )


def compile_iceberg_atlas(
    bundle: Mapping[str, Any],
    *,
    output_dir: Path,
    cursor_path: Path,
    event_spine: EventSpine,
    receipt_identity: ReceiptIdentity,
    max_children: int = 1_000,
) -> AtlasCompileResult:
    """Functional entrypoint for the deterministic Atlas compiler."""
    return IcebergAtlasCompiler(
        event_spine,
        receipt_identity=receipt_identity,
    ).compile(
        bundle,
        output_dir=output_dir,
        cursor_path=cursor_path,
        max_children=max_children,
    )
