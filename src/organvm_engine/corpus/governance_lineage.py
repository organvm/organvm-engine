"""Normalize governance contracts into an authority-safe lineage graph.

The compiler consumes owner-published contracts without redefining them.  Its
internal state only adds derived authority bindings needed by the Iceberg
Atlas; the canonical testament, lineage, coverage, self-image, and ideal-form
documents remain available as exact projections.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA_TESTAMENT = "governance-testament.v1"
SCHEMA_LINEAGE = "lineage-graph.v1"
SCHEMA_COVERAGE = "coverage-receipt.v1"
SCHEMA_SELF_IMAGE = "node-self-image.v1"
SCHEMA_IDEAL_FORM_REGISTER = "ideal-form-register.v1"

AUTHORITY_LANES = {"operator_intent", "artifact"}
AUTHORITY_CLASSES = {
    "operator_intent",
    "artifact",
    "transport_echo",
    "system_metadata",
    "unknown",
}
NODE_TYPES = {
    "ask",
    "correction",
    "constraint",
    "acceptance_criterion",
    "human_gate",
    "plan",
    "brainstorm",
    "specification",
    "document",
    "commit",
    "issue",
    "pull_request",
    "implementation",
    "receipt",
    "source_event",
    "ideal_form",
}
ARTIFACT_NODE_TYPES = {
    "plan",
    "brainstorm",
    "specification",
    "document",
    "commit",
    "issue",
    "pull_request",
    "implementation",
    "receipt",
}
ZOOM_LEVELS = ("system", "organ", "repository", "document", "session", "atom")
REVIEW_STATES = {"unreviewed", "reviewed", "rejected"}
REVIEWED_EDGE_TYPES = {
    "exact_duplicate",
    "transport_echo",
    "quotes",
    "references",
    "refines",
    "corrects",
    "supersedes",
    "splits",
    "merges",
    "contradicts",
    "implements",
    "adopts",
}
COVERAGE_STATUSES = (
    "acquired",
    "parsed",
    "quarantined",
    "inaccessible",
    "missing_expected",
    "owner_blocked",
)


def canonical_json(value: Any) -> str:
    """Return the stable representation used for hashes and deterministic sorting."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_digest(value: Any) -> str:
    """Hash a JSON-compatible value with an explicit algorithm prefix."""
    return f"sha256:{hashlib.sha256(canonical_json(value).encode()).hexdigest()}"


def schema_id(document: Mapping[str, Any]) -> str:
    """Read a contract identifier, preferring the public contract field."""
    return str(
        document.get("contract_name") or document.get("schema_id") or document.get("$id") or "",
    )


def _require_contract(document: Any, name: str, field_name: str) -> Mapping[str, Any]:
    if not isinstance(document, Mapping):
        raise ValueError(f"bundle field {field_name} must be an object")
    if document.get("contract_name") != name or document.get("contract_version") != 1:
        raise ValueError(f"bundle field {field_name} must use {name} contract version 1")
    return document


def _validate_coverage_semantics(coverage: Mapping[str, Any]) -> None:
    """Check exactly-once classification and the ready/exact-all invariants."""
    sources = coverage.get("sources")
    denominator = coverage.get("denominator")
    counts = coverage.get("counts")
    residual_owners = coverage.get("residual_owners")
    if not isinstance(sources, list):
        raise ValueError("coverage sources must be a list")
    if not isinstance(denominator, Mapping) or not isinstance(counts, Mapping):
        raise ValueError("coverage denominator and counts must be objects")
    if not isinstance(residual_owners, list):
        raise ValueError("coverage residual_owners must be a list")

    source_ids: list[str] = []
    observed = {status: 0 for status in COVERAGE_STATUSES}
    residual_source_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, Mapping):
            raise ValueError("coverage source must be an object")
        source_id = _required_text(source, "source_id")
        status = _required_text(source, "status")
        if status not in observed:
            raise ValueError("coverage source has invalid status")
        source_ids.append(source_id)
        observed[status] += 1
        if status != "parsed":
            residual_source_ids.add(source_id)
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("coverage source_ids must be unique")

    for status, count in observed.items():
        if counts.get(status) != count:
            raise ValueError(f"coverage count mismatch for {status}")
    denominator_count = denominator.get("count")
    if not isinstance(denominator_count, int) or isinstance(denominator_count, bool):
        raise ValueError("coverage denominator count must be an integer")
    computed_exact_all = denominator_count == len(source_ids)
    if coverage.get("exact_all") is not computed_exact_all:
        raise ValueError("coverage exact_all disagrees with frozen denominator")

    owner_source_ids: set[str] = set()
    for residual in residual_owners:
        if not isinstance(residual, Mapping):
            raise ValueError("coverage residual owner must be an object")
        owner_source_ids.add(_required_text(residual, "source_id"))
    if owner_source_ids != residual_source_ids:
        raise ValueError("coverage residual owners do not mirror non-parsed sources")
    computed_ready = computed_exact_all and not residual_source_ids
    if coverage.get("ready") is not computed_ready:
        raise ValueError("coverage ready disagrees with source classifications")


def validate_bundle_headers(bundle: Mapping[str, Any]) -> None:
    """Validate owner-contract identity and frozen-snapshot cohesion."""
    snapshot_id = bundle.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id or not bundle.get("snapshot_at"):
        raise ValueError("bundle requires snapshot_id and snapshot-native snapshot_at")
    testament = _require_contract(
        bundle.get("governance_testament"),
        SCHEMA_TESTAMENT,
        "governance_testament",
    )
    lineage = _require_contract(bundle.get("lineage_graph"), SCHEMA_LINEAGE, "lineage_graph")
    coverage = _require_contract(bundle.get("coverage"), SCHEMA_COVERAGE, "coverage")
    ideal_register = _require_contract(
        bundle.get("ideal_form_register"),
        SCHEMA_IDEAL_FORM_REGISTER,
        "ideal_form_register",
    )
    for document, fields in (
        (testament, ("testament_id", "version", "title", "status")),
        (lineage, ("graph_id", "generated_at", "frozen_snapshot_id")),
        (coverage, ("receipt_id", "generated_at", "snapshot_id", "receipt_hash")),
        (ideal_register, ("register_id", "generated_at", "frozen_snapshot_id")),
    ):
        for field_name in fields:
            _required_text(document, field_name)
    if not isinstance(lineage.get("nodes"), list) or not isinstance(
        lineage.get("edges"),
        list,
    ):
        raise ValueError("lineage graph nodes and edges must be lists")
    if not isinstance(ideal_register.get("ideal_forms"), list):
        raise ValueError("ideal-form register ideal_forms must be a list")
    if lineage.get("frozen_snapshot_id") != snapshot_id:
        raise ValueError("lineage graph frozen_snapshot_id does not match bundle")
    if coverage.get("snapshot_id") != snapshot_id:
        raise ValueError("coverage snapshot_id does not match bundle")
    if ideal_register.get("frozen_snapshot_id") != snapshot_id:
        raise ValueError("ideal-form register frozen_snapshot_id does not match bundle")
    _validate_coverage_semantics(coverage)
    self_images = bundle.get("self_images", [])
    if not isinstance(self_images, (list, dict)):
        raise ValueError("bundle field self_images must be a list or object")


def _units(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value[key] for key in sorted(value)]
    return [value]


def bundle_children(bundle: Mapping[str, Any]) -> list[tuple[str, int, Any]]:
    """Return the deterministic bounded-work sequence for one snapshot."""
    lineage = bundle["lineage_graph"]
    ideal_register = bundle["ideal_form_register"]
    collections = (
        ("node", _units(lineage.get("nodes", []))),
        ("edge", _units(lineage.get("edges", []))),
        ("directive", [bundle["governance_testament"]]),
        ("ideal_form", _units(ideal_register.get("ideal_forms", []))),
        ("self_image", _units(bundle.get("self_images", []))),
    )
    children: list[tuple[str, int, Any]] = []
    for kind, units in collections:
        children.extend((kind, index, unit) for index, unit in enumerate(units))
    return children


@dataclass(frozen=True)
class QuarantineDiagnostic:
    """Hashed parser diagnostic that never stores a malformed source body."""

    diagnostic_id: str
    collection: str
    source_index: int
    record_hash: str
    error_code: str

    @classmethod
    def create(
        cls,
        collection: str,
        source_index: int,
        unit: Any,
        error_code: str,
    ) -> QuarantineDiagnostic:
        try:
            record_hash = content_digest(unit)
        except (TypeError, ValueError):
            record_hash = f"sha256:{hashlib.sha256(repr(unit).encode()).hexdigest()}"
        identity = {
            "collection": collection,
            "source_index": source_index,
            "record_hash": record_hash,
            "error_code": error_code,
        }
        return cls(
            diagnostic_id=content_digest(identity),
            collection=collection,
            source_index=source_index,
            record_hash=record_hash,
            error_code=error_code,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagnostic_id": self.diagnostic_id,
            "collection": self.collection,
            "source_index": self.source_index,
            "record_hash": self.record_hash,
            "error_code": self.error_code,
        }


def empty_state() -> dict[str, Any]:
    """Create the serializable state persisted in a resume cursor."""
    return {
        "nodes": [],
        "edges": [],
        "directives": [],
        "ideal_forms": [],
        "self_images": [],
        "quarantine": [],
    }


def _diagnose(
    state: dict[str, Any],
    collection: str,
    source_index: int,
    unit: Any,
    error_code: str,
) -> None:
    diagnostic = QuarantineDiagnostic.create(collection, source_index, unit, error_code)
    existing = {item["diagnostic_id"] for item in state["quarantine"]}
    if diagnostic.diagnostic_id not in existing:
        state["quarantine"].append(diagnostic.to_dict())
        state["quarantine"].sort(key=lambda item: item["diagnostic_id"])


def _required_text(unit: Mapping[str, Any], field_name: str) -> str:
    value = unit.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing_{field_name}")
    return value


def _required_list(unit: Mapping[str, Any], field_name: str) -> list[Any]:
    value = unit.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"invalid_{field_name}")
    return value


def _normalize_node(unit: Mapping[str, Any]) -> dict[str, Any]:
    node = deepcopy(dict(unit))
    lane = _required_text(node, "lane")
    node_type = _required_text(node, "node_type")
    authority_class = _required_text(node, "authority_class")
    for field_name in (
        "node_id",
        "source_envelope_id",
        "occurred_at",
        "summary",
        "content_hash",
        "review_state",
    ):
        _required_text(node, field_name)
    if lane not in AUTHORITY_LANES:
        raise ValueError("invalid_lane")
    if node_type not in NODE_TYPES:
        raise ValueError("invalid_node_type")
    if authority_class not in AUTHORITY_CLASSES:
        raise ValueError("invalid_authority_class")
    if lane == "operator_intent" and authority_class != "operator_intent":
        raise ValueError("authority_lane_mismatch")
    if node_type in ARTIFACT_NODE_TYPES and lane != "artifact":
        raise ValueError("authority_lane_mismatch")
    if node["review_state"] not in REVIEW_STATES:
        raise ValueError("invalid_review_state")
    metadata = node.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise ValueError("invalid_metadata")
    zoom_level = str(metadata.get("zoom_level", "atom"))
    if zoom_level not in ZOOM_LEVELS:
        raise ValueError("invalid_zoom_level")
    node["metadata"] = deepcopy(dict(metadata))
    node["_zoom_level"] = zoom_level
    return node


def _normalize_edge(unit: Mapping[str, Any]) -> dict[str, Any]:
    edge = deepcopy(dict(unit))
    for field_name in ("edge_id", "from_node", "to_node", "edge_type", "review_state"):
        _required_text(edge, field_name)
    edge_type = str(edge["edge_type"]).lower()
    if edge_type not in REVIEWED_EDGE_TYPES:
        raise ValueError("invalid_edge_type")
    if edge["review_state"] not in REVIEW_STATES:
        raise ValueError("invalid_review_state")
    confidence = edge.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ValueError("invalid_confidence")
    if not 0 <= float(confidence) <= 1:
        raise ValueError("invalid_confidence")
    evidence_spans = _required_list(edge, "evidence_spans")
    if not evidence_spans:
        raise ValueError("edge_missing_evidence_spans")
    for span in evidence_spans:
        if not isinstance(span, Mapping):
            raise ValueError("invalid_evidence_span")
        for field_name in ("source_envelope_id", "reference", "body_hash"):
            _required_text(span, field_name)
    edge["edge_type"] = edge_type
    edge["confidence"] = float(confidence)
    return edge


def _normalize_directive(unit: Mapping[str, Any]) -> dict[str, Any]:
    testament = deepcopy(dict(unit))
    if schema_id(testament) != SCHEMA_TESTAMENT or testament.get("contract_version") != 1:
        raise ValueError("invalid_testament_contract")
    for field_name in (
        "testament_id",
        "version",
        "title",
        "status",
        "directive",
        "directive_hash",
    ):
        _required_text(testament, field_name)
    layers = _required_list(testament, "layers")
    if set(layers) != {"ontology", "cybernetics", "phenomenology"}:
        raise ValueError("invalid_testament_layers")
    for field_name in ("instruments", "axioms", "ideal_form_references", "predicates", "citations"):
        _required_list(testament, field_name)
    if testament["status"] == "ratified" and not isinstance(
        testament.get("ratification"),
        Mapping,
    ):
        raise ValueError("missing_ratification")
    return {"directive_id": testament["testament_id"], "testament": testament}


def _normalize_ideal_form(unit: Mapping[str, Any]) -> dict[str, Any]:
    ideal = deepcopy(dict(unit))
    for field_name in (
        "ideal_form_id",
        "title",
        "controlling_formulation",
        "owner_reference",
        "implementation_state",
        "receipt_target",
    ):
        _required_text(ideal, field_name)
    if not _required_list(ideal, "lineage_references"):
        raise ValueError("missing_lineage_references")
    predicates = _required_list(ideal, "predicates")
    if not predicates:
        raise ValueError("missing_predicates")
    distance = ideal.get("distance_to_ideal")
    if not isinstance(distance, Mapping):
        raise ValueError("invalid_distance_to_ideal")
    _required_text(distance, "classification")
    verified = distance.get("verified_predicates")
    total = distance.get("total_predicates")
    if (
        not isinstance(verified, int)
        or isinstance(verified, bool)
        or not isinstance(total, int)
        or isinstance(total, bool)
        or verified < 0
        or total <= 0
        or verified > total
    ):
        raise ValueError("invalid_distance_to_ideal")
    for predicate in predicates:
        if not isinstance(predicate, Mapping):
            raise ValueError("invalid_predicate")
        for field_name in ("predicate_id", "statement", "status"):
            _required_text(predicate, field_name)
        _required_list(predicate, "evidence_references")
    _required_list(ideal, "residual_gaps")
    return {"ideal_form_id": ideal["ideal_form_id"], "ideal_form": ideal}


def _normalize_self_image(unit: Mapping[str, Any]) -> dict[str, Any]:
    image = deepcopy(dict(unit))
    if schema_id(image) != SCHEMA_SELF_IMAGE or image.get("contract_version") != 1:
        raise ValueError("invalid_self_image_contract")
    for field_name in ("node_id", "node_type", "owner_reference", "reconciled_at"):
        _required_text(image, field_name)
    for field_name in (
        "relations",
        "cursors",
        "digests",
        "observations",
        "active_ideal_forms",
        "evidence_references",
    ):
        if field_name not in image:
            raise ValueError(f"missing_{field_name}")
    if not isinstance(image["relations"], Mapping):
        raise ValueError("invalid_relations")
    if not isinstance(image["cursors"], Mapping):
        raise ValueError("invalid_cursors")
    if not isinstance(image["digests"], Mapping):
        raise ValueError("invalid_digests")
    for field_name in ("observations", "active_ideal_forms", "evidence_references"):
        if not isinstance(image[field_name], list):
            raise ValueError(f"invalid_{field_name}")
    return image


def process_child(state: dict[str, Any], kind: str, source_index: int, unit: Any) -> None:
    """Process one bounded child, quarantining failure without stopping siblings."""
    if not isinstance(unit, Mapping):
        _diagnose(state, kind, source_index, unit, "unit_not_object")
        return
    try:
        if kind == "node":
            normalized = _normalize_node(unit)
            key = "node_id"
            destination = "nodes"
        elif kind == "edge":
            normalized = _normalize_edge(unit)
            key = "edge_id"
            destination = "edges"
        elif kind == "directive":
            normalized = _normalize_directive(unit)
            key = "directive_id"
            destination = "directives"
        elif kind == "ideal_form":
            normalized = _normalize_ideal_form(unit)
            key = "ideal_form_id"
            destination = "ideal_forms"
        elif kind == "self_image":
            normalized = _normalize_self_image(unit)
            key = "node_id"
            destination = "self_images"
        else:
            raise ValueError("unknown_collection")
    except (KeyError, TypeError, ValueError) as error:
        _diagnose(state, kind, source_index, unit, str(error))
        return

    existing = {item[key]: item for item in state[destination]}
    identity = normalized[key]
    if identity in existing:
        if canonical_json(existing[identity]) != canonical_json(normalized):
            _diagnose(state, kind, source_index, unit, f"conflicting_{key}")
        return
    state[destination].append(normalized)
    state[destination].sort(key=lambda item: str(item[key]))


def _adopted_artifacts(state: Mapping[str, Any]) -> set[str]:
    """Find artifact endpoints of reviewed operator/artifact adoption edges."""
    nodes = {node["node_id"]: node for node in state["nodes"]}
    adopted: set[str] = set()
    for edge in state["edges"]:
        if edge["review_state"] != "reviewed" or edge["edge_type"] != "adopts":
            continue
        source = nodes.get(edge["from_node"])
        target = nodes.get(edge["to_node"])
        if source is None or target is None:
            continue
        endpoints = {source["lane"], target["lane"]}
        if endpoints != {"operator_intent", "artifact"}:
            continue
        artifact = source if source["lane"] == "artifact" else target
        adopted.add(artifact["node_id"])
    return adopted


def _resolve_authority_node(
    nodes: Mapping[str, Mapping[str, Any]],
    authority_reference: str,
) -> Mapping[str, Any] | None:
    """Resolve a ratification reference without turning paths into identity."""
    candidates: list[Mapping[str, Any]] = []
    for node in nodes.values():
        metadata = node.get("metadata", {})
        aliases = metadata.get("authority_event_references", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        known = {
            node["node_id"],
            f"lineage-node:{node['node_id']}",
            node["source_envelope_id"],
        }
        if isinstance(aliases, list):
            known.update(str(alias) for alias in aliases)
        if authority_reference in known:
            candidates.append(node)
    if len(candidates) != 1:
        return None
    return candidates[0]


def finalize_state(state: dict[str, Any]) -> dict[str, Any]:
    """Enforce endpoints, controlling operator authority, and explicit adoption."""
    finalized = deepcopy(state)
    nodes = {node["node_id"]: node for node in finalized["nodes"]}

    valid_edges: list[dict[str, Any]] = []
    for index, edge in enumerate(finalized["edges"]):
        if edge["from_node"] not in nodes or edge["to_node"] not in nodes:
            _diagnose(finalized, "edge", index, edge, "missing_edge_endpoint_node")
            continue
        valid_edges.append(edge)
    finalized["edges"] = valid_edges
    adopted = _adopted_artifacts(finalized)

    active_directives: list[dict[str, Any]] = []
    for index, directive in enumerate(finalized["directives"]):
        testament = directive["testament"]
        if testament["status"] != "ratified":
            _diagnose(finalized, "directive", index, testament, "testament_not_ratified")
            continue
        ratification = testament.get("ratification")
        reference = (
            ratification.get("authority_event_reference")
            if isinstance(ratification, Mapping)
            else None
        )
        controlling = (
            _resolve_authority_node(nodes, str(reference)) if isinstance(reference, str) else None
        )
        if controlling is None:
            _diagnose(finalized, "directive", index, testament, "authority_reference_unresolved")
            continue
        if controlling["lane"] != "operator_intent":
            _diagnose(finalized, "directive", index, testament, "non_operator_controlling_node")
            continue
        active_directives.append({**directive, "controlling_node_id": controlling["node_id"]})
    finalized["directives"] = active_directives

    controlling_by_ideal: dict[str, str] = {}
    for directive in active_directives:
        for ideal_id in directive["testament"].get("ideal_form_references", []):
            controlling_by_ideal[str(ideal_id)] = directive["controlling_node_id"]

    active_ideals: list[dict[str, Any]] = []
    for index, ideal in enumerate(finalized["ideal_forms"]):
        ideal_id = ideal["ideal_form_id"]
        controlling_node_id = controlling_by_ideal.get(ideal_id)
        if controlling_node_id is None:
            _diagnose(finalized, "ideal_form", index, ideal, "ideal_not_ratified")
            continue
        active_ideals.append({**ideal, "controlling_node_id": controlling_node_id})
    active_ideals.sort(key=lambda item: item["ideal_form_id"])
    finalized["ideal_forms"] = active_ideals
    finalized["adopted_artifact_node_ids"] = sorted(adopted)
    return finalized


def canonical_node(node: Mapping[str, Any]) -> dict[str, Any]:
    """Remove compiler-only fields from a lineage node projection."""
    return {key: deepcopy(value) for key, value in node.items() if not key.startswith("_")}


def evidence_groups(unit: Mapping[str, Any]) -> set[str]:
    """Return source-envelope groups without counting transport copies twice."""
    source_envelope_id = unit.get("source_envelope_id")
    if isinstance(source_envelope_id, str) and source_envelope_id:
        return {source_envelope_id}
    spans = unit.get("evidence_spans", [])
    if not isinstance(spans, list):
        return set()
    return {
        str(span["source_envelope_id"])
        for span in spans
        if isinstance(span, Mapping) and span.get("source_envelope_id")
    }
