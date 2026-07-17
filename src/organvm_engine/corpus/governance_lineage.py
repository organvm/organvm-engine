"""Normalize governance contracts into an authority-safe lineage graph.

The compiler consumes owner-published contracts without redefining them.  Its
internal state only adds derived authority bindings needed by the Iceberg
Atlas; the canonical testament, lineage, coverage, self-image, and ideal-form
documents remain available as exact projections.
"""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

import rfc8785

SCHEMA_TESTAMENT = "governance-testament.v1"
SCHEMA_LINEAGE = "lineage-graph.v1"
SCHEMA_COVERAGE = "coverage-receipt.v1"
SCHEMA_SOURCE_ENVELOPE = "source-envelope.v1"
SCHEMA_NORMALIZED_EVENT = "normalized-event.v1"
SCHEMA_ASSERTION_EVIDENCE = "assertion-evidence.v1"
SCHEMA_SELF_IMAGE = "node-self-image.v1"
SCHEMA_SELF_IMAGE_SET = "node-self-image-set.v1"
SCHEMA_IDEAL_FORM_REGISTER = "ideal-form-register.v1"
SCHEMA_SNAPSHOT_BUNDLE = "governance-snapshot-bundle.v1"

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
READINESS_DEBT_FIELDS = (
    "unresolved_blockers",
    "quarantines",
    "missing_requirements",
    "citation_debt",
    "incomplete_predicates",
)
_DIGEST_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")


def canonical_json(value: Any) -> str:
    """Return RFC 8785 canonical JSON for governed identity and digests."""
    return rfc8785.dumps(value).decode("utf-8")


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


def _validate_self_digest(
    document: Mapping[str, Any],
    *,
    digest_field: str,
    field_name: str,
) -> None:
    if document.get("digest_algorithm") != "sha256-rfc8785-excluding-self-digest-v1":
        raise ValueError(f"{field_name} digest algorithm is invalid")
    claimed = document.get(digest_field)
    if not isinstance(claimed, str) or not _DIGEST_PATTERN.fullmatch(claimed):
        raise ValueError(f"{field_name} self digest is invalid")
    body = deepcopy(dict(document))
    body.pop(digest_field, None)
    if content_digest(body) != claimed:
        raise ValueError(f"{field_name} self digest mismatch")


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
    readiness_debt = [item for field in READINESS_DEBT_FIELDS for item in coverage.get(field, [])]
    computed_ready = computed_exact_all and not residual_source_ids and not readiness_debt
    if coverage.get("ready") is not computed_ready:
        raise ValueError("coverage ready disagrees with source classifications")


def validate_bundle_headers(bundle: Mapping[str, Any]) -> None:
    """Validate owner-contract identity and frozen-snapshot cohesion."""
    _require_contract(bundle, SCHEMA_SNAPSHOT_BUNDLE, "snapshot_bundle")
    snapshot_id = bundle.get("snapshot_id")
    snapshot_digest = bundle.get("snapshot_digest")
    if (
        not isinstance(snapshot_id, str)
        or not snapshot_id
        or not bundle.get("snapshot_at")
        or not isinstance(snapshot_digest, str)
        or not snapshot_digest
    ):
        raise ValueError("bundle requires snapshot identity, digest, and snapshot-native time")
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
        (
            ideal_register,
            (
                "register_id",
                "snapshot_id",
                "snapshot_digest",
                "generated_at",
                "digest_algorithm",
                "register_digest",
            ),
        ),
    ):
        for field_name in fields:
            _required_text(document, field_name)
    if not isinstance(lineage.get("nodes"), list) or not isinstance(
        lineage.get("edges"),
        list,
    ):
        raise ValueError("lineage graph nodes and edges must be lists")
    if not lineage["nodes"]:
        raise ValueError("lineage graph nodes must be non-empty")
    if not isinstance(ideal_register.get("ideal_forms"), list) or not ideal_register["ideal_forms"]:
        raise ValueError("ideal-form register ideal_forms must be non-empty")
    if lineage.get("frozen_snapshot_id") != snapshot_id:
        raise ValueError("lineage graph frozen_snapshot_id does not match bundle")
    if coverage.get("snapshot_id") != snapshot_id:
        raise ValueError("coverage snapshot_id does not match bundle")
    if ideal_register.get("snapshot_id") != snapshot_id:
        raise ValueError("ideal-form register snapshot_id does not match bundle")
    if ideal_register.get("snapshot_digest") != snapshot_digest:
        raise ValueError("ideal-form register snapshot_digest does not match bundle")
    _validate_self_digest(
        ideal_register,
        digest_field="register_digest",
        field_name="ideal-form register",
    )
    _validate_coverage_semantics(coverage)

    source_envelopes = bundle.get("source_envelopes")
    assertions = bundle.get("assertion_evidence")
    if not isinstance(source_envelopes, list) or not source_envelopes:
        raise ValueError("bundle source_envelopes must be non-empty")
    if not isinstance(assertions, list) or not assertions:
        raise ValueError("bundle assertion_evidence must be non-empty")
    normalized_events = bundle.get("normalized_events")
    if not isinstance(normalized_events, list) or not normalized_events:
        raise ValueError("bundle normalized_events must be non-empty")
    for event in normalized_events:
        if (
            not isinstance(event, Mapping)
            or event.get("contract_name") != SCHEMA_NORMALIZED_EVENT
            or event.get("snapshot_id") != snapshot_id
            or event.get("snapshot_digest") != snapshot_digest
        ):
            raise ValueError("normalized event snapshot binding is invalid")
    for source in source_envelopes:
        custody = source.get("custody_snapshot") if isinstance(source, Mapping) else None
        if not isinstance(custody, Mapping) or custody.get("snapshot_id") != snapshot_id:
            raise ValueError("source envelope snapshot binding is invalid")

    self_image_set = _require_contract(
        bundle.get("node_self_image_set"),
        SCHEMA_SELF_IMAGE_SET,
        "node_self_image_set",
    )
    for field_name in (
        "set_id",
        "snapshot_id",
        "snapshot_digest",
        "registry_reference",
        "registry_digest",
        "digest_algorithm",
        "set_digest",
    ):
        _required_text(self_image_set, field_name)
    registered_node_ids = _required_list(self_image_set, "registered_node_ids")
    self_images = _required_list(self_image_set, "self_images")
    if not registered_node_ids or not self_images:
        raise ValueError("node self-image set must be non-empty")
    if self_image_set.get("snapshot_id") != snapshot_id:
        raise ValueError("node self-image set snapshot_id does not match bundle")
    if self_image_set.get("snapshot_digest") != snapshot_digest:
        raise ValueError("node self-image set snapshot_digest does not match bundle")
    _validate_self_digest(
        self_image_set,
        digest_field="set_digest",
        field_name="node self-image set",
    )
    image_ids = [
        _required_text(image, "node_id") for image in self_images if isinstance(image, Mapping)
    ]
    if len(image_ids) != len(self_images):
        raise ValueError("node self-image set images must be objects")
    exact_one = len(image_ids) == len(set(image_ids)) and sorted(image_ids) == sorted(
        str(value) for value in registered_node_ids
    )
    counts = self_image_set.get("counts")
    if (
        not isinstance(counts, Mapping)
        or counts.get("registered")
        != len(
            registered_node_ids,
        )
        or counts.get("exported") != len(self_images)
    ):
        raise ValueError("node self-image set counts are inconsistent")
    readiness = self_image_set.get("readiness")
    if not isinstance(readiness, Mapping):
        raise ValueError("node self-image set readiness is missing")
    if not exact_one or readiness.get("exact_all") is not True:
        raise ValueError("node self-image set exact_one is inconsistent")
    readiness_debt = [item for field in READINESS_DEBT_FIELDS for item in readiness.get(field, [])]
    computed_ready = exact_one and not readiness_debt
    status = readiness.get("status")
    if (
        readiness.get("ready") is not computed_ready
        or (computed_ready and status != "ready")
        or (
            not computed_ready
            and status
            not in {"blocked", "incomplete", "closed_with_owner_routed_debt"}
        )
    ):
        raise ValueError("node self-image set readiness is inconsistent")


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
        ("source_envelope", _units(bundle.get("source_envelopes", []))),
        ("normalized_event", _units(bundle.get("normalized_events", []))),
        ("node", _units(lineage.get("nodes", []))),
        ("edge", _units(lineage.get("edges", []))),
        ("directive", [bundle["governance_testament"]]),
        ("assertion", _units(bundle.get("assertion_evidence", []))),
        ("ideal_form", _units(ideal_register.get("ideal_forms", []))),
        ("self_image", _units(bundle["node_self_image_set"].get("self_images", []))),
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
        "source_envelopes": [],
        "normalized_events": [],
        "nodes": [],
        "edges": [],
        "directives": [],
        "assertions": [],
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


def _normalize_source_envelope(unit: Mapping[str, Any]) -> dict[str, Any]:
    envelope = deepcopy(dict(unit))
    if schema_id(envelope) != SCHEMA_SOURCE_ENVELOPE or envelope.get("contract_version") != 1:
        raise ValueError("invalid_source_envelope_contract")
    for field_name in (
        "source_id",
        "source_family",
        "source_instance",
        "format_adapter",
        "role",
        "event_timestamp",
        "ingestion_timestamp",
        "authority_class",
        "body_hash",
        "private_custody_pointer",
    ):
        _required_text(envelope, field_name)
    custody = envelope.get("custody_snapshot")
    if not isinstance(custody, Mapping):
        raise ValueError("invalid_custody_snapshot")
    for field_name in ("snapshot_id", "captured_at", "snapshot_hash", "custody_pointer"):
        _required_text(custody, field_name)
    if custody.get("immutable") is not True:
        raise ValueError("source_envelope_not_immutable")
    native_identifiers = envelope.get("native_identifiers")
    if not isinstance(native_identifiers, Mapping) or not native_identifiers:
        raise ValueError("missing_native_identifiers")
    return envelope


def _normalize_event(unit: Mapping[str, Any]) -> dict[str, Any]:
    event = deepcopy(dict(unit))
    if schema_id(event) != SCHEMA_NORMALIZED_EVENT or event.get("contract_version") != 1:
        raise ValueError("invalid_normalized_event_contract")
    for field_name in (
        "event_id",
        "identity_algorithm",
        "snapshot_id",
        "snapshot_digest",
        "raw_unit_id",
        "source_family",
        "source_instance",
        "format_adapter",
        "normalized_role",
        "occurred_at",
        "authority_class",
        "source_envelope_reference",
    ):
        _required_text(event, field_name)
    identity_basis = event.get("identity_basis")
    if not isinstance(identity_basis, Mapping):
        raise ValueError("invalid_event_identity_basis")
    for field_name in (
        "native_identity_namespace",
        "native_role",
        "content_hash",
    ):
        _required_text(identity_basis, field_name)
    native_identifiers = identity_basis.get("native_identifiers")
    if not isinstance(native_identifiers, Mapping) or not native_identifiers:
        raise ValueError("missing_event_native_identifiers")
    if event["identity_algorithm"] != ("sha256-canonical-json-native-identity-role-content-v1"):
        raise ValueError("invalid_event_identity_algorithm")
    expected_event_id = "evt_" + content_digest(identity_basis).removeprefix("sha256:")
    if event["event_id"] != expected_event_id:
        raise ValueError("event_identity_mismatch")
    if not _required_list(event, "evidence_references"):
        raise ValueError("missing_event_evidence_references")
    if event["authority_class"] == "operator_intent" and event["normalized_role"] != "operator":
        raise ValueError("event_authority_role_mismatch")
    return event


def _normalize_assertion(unit: Mapping[str, Any]) -> dict[str, Any]:
    assertion = deepcopy(dict(unit))
    if schema_id(assertion) != SCHEMA_ASSERTION_EVIDENCE or assertion.get("contract_version") != 1:
        raise ValueError("invalid_assertion_evidence_contract")
    for field_name in (
        "assertion_id",
        "assertion_class",
        "statement",
        "verification_state",
    ):
        _required_text(assertion, field_name)
    if assertion["verification_state"] != "verified":
        raise ValueError("assertion_not_verified")
    references = _required_list(assertion, "evidence_references")
    if len(references) < 2:
        raise ValueError("assertion_requires_multiple_evidence_references")
    independence_groups: set[str] = set()
    for reference in references:
        if not isinstance(reference, Mapping):
            raise ValueError("invalid_assertion_evidence_reference")
        for field_name in (
            "evidence_id",
            "independence_group",
            "evidence_type",
            "reference",
            "body_hash",
        ):
            _required_text(reference, field_name)
        independence_groups.add(str(reference["independence_group"]))
    if len(independence_groups) < 2:
        raise ValueError("assertion_evidence_not_independent")
    freshness = assertion.get("freshness")
    if assertion["assertion_class"] == "current_state" and (
        not isinstance(freshness, Mapping) or freshness.get("status") != "fresh"
    ):
        raise ValueError("current_state_assertion_not_fresh")
    return assertion


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
    if testament["status"] == "ratified":
        ratification = testament.get("ratification")
        if not isinstance(ratification, Mapping):
            raise ValueError("missing_ratification")
        for field_name in (
            "ratified_at",
            "candidate_digest",
            "controlling_formulation",
            "assertion_evidence_reference",
            "constitutional_record_reference",
            "approver_reference",
        ):
            _required_text(ratification, field_name)
        if not _DIGEST_PATTERN.fullmatch(str(ratification["candidate_digest"])):
            raise ValueError("invalid_candidate_digest")
        if not _required_list(ratification, "authority_events"):
            raise ValueError("authority_events_missing")
        if not _required_list(ratification, "source_lineage_references"):
            raise ValueError("source_lineage_references_missing")
        if not isinstance(ratification.get("constitutional_coverage"), Mapping):
            raise ValueError("constitutional_coverage_missing")
        candidate = deepcopy(testament)
        candidate["status"] = "candidate"
        candidate.pop("ratification", None)
        if ratification["candidate_digest"] != content_digest(candidate):
            raise ValueError("candidate_digest_mismatch")
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
    if not _required_list(ideal, "source_envelope_references"):
        raise ValueError("missing_source_envelope_references")
    if not _required_list(ideal, "lineage_references"):
        raise ValueError("missing_lineage_references")
    if not _required_list(ideal, "assertion_evidence_references"):
        raise ValueError("missing_assertion_evidence_references")
    predicates = _required_list(ideal, "predicates")
    if not predicates:
        raise ValueError("missing_predicates")
    verified = 0
    blocked = False
    for predicate in predicates:
        if not isinstance(predicate, Mapping):
            raise ValueError("invalid_predicate")
        for field_name in (
            "predicate_id",
            "statement",
            "receipt_reference",
            "result",
        ):
            _required_text(predicate, field_name)
        if predicate["result"] not in {"pass", "fail", "blocked"}:
            raise ValueError("invalid_predicate_result")
        evidence_references = _required_list(predicate, "evidence_references")
        if predicate["receipt_reference"] not in evidence_references:
            raise ValueError("predicate_receipt_not_evidence_backed")
        verified += predicate["result"] == "pass"
        blocked = blocked or predicate["result"] == "blocked"
    total = len(predicates)
    computed_state = "blocked" if blocked else "verified" if verified == total else "partial"
    computed_distance = {
        "classification": computed_state,
        "verified_predicates": verified,
        "total_predicates": total,
    }
    declared_distance = ideal.get("distance_to_ideal")
    if declared_distance is not None and canonical_json(declared_distance) != canonical_json(
        computed_distance,
    ):
        raise ValueError("distance_to_ideal_not_receipt_derived")
    declared_state = ideal.get("implementation_state")
    if declared_state is not None and declared_state != computed_state:
        raise ValueError("implementation_state_not_receipt_derived")
    ideal["implementation_state"] = computed_state
    ideal["distance_to_ideal"] = computed_distance
    derivation = ideal.get("derivation")
    if not isinstance(derivation, Mapping):
        raise ValueError("missing_predicate_derivation")
    if derivation.get("algorithm") != "predicate-receipt-status-v1":
        raise ValueError("invalid_predicate_derivation")
    receipt_references = _required_list(derivation, "receipt_references")
    expected_receipts = sorted(str(predicate["receipt_reference"]) for predicate in predicates)
    if sorted(str(reference) for reference in receipt_references) != expected_receipts:
        raise ValueError("predicate_derivation_receipts_incomplete")
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
        if not isinstance(image[field_name], list) or not image[field_name]:
            raise ValueError(f"invalid_{field_name}")
    return image


def process_child(state: dict[str, Any], kind: str, source_index: int, unit: Any) -> None:
    """Process one bounded child, quarantining failure without stopping siblings."""
    if not isinstance(unit, Mapping):
        _diagnose(state, kind, source_index, unit, "unit_not_object")
        return
    try:
        if kind == "source_envelope":
            normalized = _normalize_source_envelope(unit)
            key = "source_id"
            destination = "source_envelopes"
        elif kind == "normalized_event":
            normalized = _normalize_event(unit)
            key = "event_id"
            destination = "normalized_events"
        elif kind == "node":
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
        elif kind == "assertion":
            normalized = _normalize_assertion(unit)
            key = "assertion_id"
            destination = "assertions"
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


def _assertion_resolves_source(
    assertion: Mapping[str, Any],
    source: Mapping[str, Any],
) -> bool:
    source_id = str(source["source_id"])
    accepted_references = {source_id, f"source-envelope:{source_id}"}
    for evidence in assertion.get("evidence_references", []):
        if not isinstance(evidence, Mapping):
            continue
        if (
            evidence.get("evidence_type") == "immutable_source_event"
            and evidence.get("reference") in accepted_references
            and evidence.get("body_hash") == source.get("body_hash")
        ):
            return True
    return False


def finalize_state(
    state: dict[str, Any],
    *,
    source_ready: bool,
) -> dict[str, Any]:
    """Enforce endpoints, controlling operator authority, and explicit adoption."""
    finalized = deepcopy(state)
    source_envelopes = {source["source_id"]: source for source in finalized["source_envelopes"]}
    valid_nodes: list[dict[str, Any]] = []
    for index, node in enumerate(finalized["nodes"]):
        source = source_envelopes.get(node["source_envelope_id"])
        if source is None:
            _diagnose(finalized, "node", index, node, "source_envelope_unresolved")
            continue
        if source["body_hash"] != node["content_hash"]:
            _diagnose(finalized, "node", index, node, "source_envelope_hash_mismatch")
            continue
        if source["event_timestamp"] != node["occurred_at"]:
            _diagnose(finalized, "node", index, node, "source_envelope_timestamp_mismatch")
            continue
        if node["lane"] == "operator_intent" and source["authority_class"] != "operator_intent":
            _diagnose(finalized, "node", index, node, "source_envelope_authority_mismatch")
            continue
        if node["lane"] == "artifact" and source["authority_class"] == "operator_intent":
            _diagnose(finalized, "node", index, node, "source_envelope_authority_mismatch")
            continue
        valid_nodes.append(node)
    finalized["nodes"] = valid_nodes
    nodes = {node["node_id"]: node for node in valid_nodes}

    valid_edges: list[dict[str, Any]] = []
    for index, edge in enumerate(finalized["edges"]):
        if edge["from_node"] not in nodes or edge["to_node"] not in nodes:
            _diagnose(finalized, "edge", index, edge, "missing_edge_endpoint_node")
            continue
        valid_edges.append(edge)
    finalized["edges"] = valid_edges
    adopted = _adopted_artifacts(finalized)
    assertions = {assertion["assertion_id"]: assertion for assertion in finalized["assertions"]}
    normalized_events = {event["event_id"]: event for event in finalized["normalized_events"]}

    active_directives: list[dict[str, Any]] = []
    for index, directive in enumerate(finalized["directives"]):
        testament = directive["testament"]
        if testament["status"] != "ratified":
            _diagnose(finalized, "directive", index, testament, "testament_not_ratified")
            continue
        if not source_ready:
            _diagnose(finalized, "directive", index, testament, "source_coverage_not_ready")
            continue
        ratification = testament.get("ratification")
        if not isinstance(ratification, Mapping):
            _diagnose(finalized, "directive", index, testament, "missing_ratification")
            continue
        constitutional_coverage = ratification.get("constitutional_coverage")
        if (
            not isinstance(constitutional_coverage, Mapping)
            or constitutional_coverage.get("exact_all") is not True
            or constitutional_coverage.get("ready") is not True
            or constitutional_coverage.get("blocked_scopes")
            or constitutional_coverage.get("missing_requirements")
        ):
            _diagnose(
                finalized,
                "directive",
                index,
                testament,
                "constitutional_coverage_not_ready",
            )
            continue
        authority_events = ratification.get("authority_events")
        if not isinstance(authority_events, list) or not authority_events:
            _diagnose(finalized, "directive", index, testament, "authority_events_missing")
            continue
        authority_nodes: list[dict[str, Any]] = []
        authority_valid = True
        for authority_event in authority_events:
            if not isinstance(authority_event, Mapping):
                authority_valid = False
                break
            normalized = normalized_events.get(str(authority_event.get("event_id", "")))
            source_id = authority_event.get("source_envelope_reference")
            source = source_envelopes.get(str(source_id))
            matching_nodes = [
                node
                for node in nodes.values()
                if node["source_envelope_id"] == source_id and node["lane"] == "operator_intent"
            ]
            if (
                normalized is None
                or source is None
                or len(matching_nodes) != 1
                or authority_event.get("role") != "operator"
                or authority_event.get("authority_class") != "operator_intent"
                or authority_event.get("content_hash") != source.get("body_hash")
                or normalized.get("source_envelope_reference") != source_id
                or normalized.get("authority_class") != "operator_intent"
                or normalized.get("normalized_role") != "operator"
                or normalized.get("identity_basis", {}).get("content_hash")
                != source.get("body_hash")
            ):
                authority_valid = False
                break
            authority_nodes.append(matching_nodes[0])
        if not authority_valid:
            _diagnose(finalized, "directive", index, testament, "authority_event_unresolved")
            continue
        reference = ratification.get("authority_event_reference")
        controlling = (
            _resolve_authority_node(nodes, str(reference))
            if isinstance(reference, str)
            else max(authority_nodes, key=lambda node: (node["occurred_at"], node["node_id"]))
        )
        if controlling is None:
            _diagnose(finalized, "directive", index, testament, "authority_reference_unresolved")
            continue
        if controlling["lane"] != "operator_intent":
            _diagnose(finalized, "directive", index, testament, "non_operator_controlling_node")
            continue
        source = source_envelopes.get(controlling["source_envelope_id"])
        if source is None:
            _diagnose(finalized, "directive", index, testament, "authority_source_unresolved")
            continue
        citation_ids = testament.get("citations", [])
        resolved_assertions = [
            assertions[citation_id] for citation_id in citation_ids if citation_id in assertions
        ]
        assertion_reference = ratification.get("assertion_evidence_reference")
        operator_assertions = [
            assertion
            for assertion in resolved_assertions
            if assertion["assertion_id"] == assertion_reference
            and assertion["assertion_class"] == "operator_directive"
            and _assertion_resolves_source(assertion, source)
        ]
        constitutional_record = ratification.get("constitutional_record_reference")
        constitutional_assertion_backed = any(
            evidence.get("evidence_type") == "ratified_constitutional_record"
            and evidence.get("reference") == constitutional_record
            for assertion in operator_assertions
            for evidence in assertion.get("evidence_references", [])
            if isinstance(evidence, Mapping)
        )
        if len(resolved_assertions) != len(citation_ids) or not operator_assertions:
            _diagnose(
                finalized,
                "directive",
                index,
                testament,
                "operator_directive_assertion_unresolved",
            )
            continue
        if not constitutional_assertion_backed:
            _diagnose(
                finalized,
                "directive",
                index,
                testament,
                "constitutional_assertion_unresolved",
            )
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
        ideal_document = ideal["ideal_form"]
        controlling_node_id = controlling_by_ideal.get(ideal_id)
        if controlling_node_id is None:
            _diagnose(finalized, "ideal_form", index, ideal, "ideal_not_ratified")
            continue
        if any(
            source_id not in source_envelopes
            for source_id in ideal_document["source_envelope_references"]
        ):
            _diagnose(finalized, "ideal_form", index, ideal, "ideal_source_unresolved")
            continue
        if any(
            assertion_id not in assertions
            for assertion_id in ideal_document["assertion_evidence_references"]
        ):
            _diagnose(finalized, "ideal_form", index, ideal, "ideal_assertion_unresolved")
            continue
        active_ideals.append({**ideal, "controlling_node_id": controlling_node_id})
    active_ideals.sort(key=lambda item: item["ideal_form_id"])
    finalized["ideal_forms"] = active_ideals
    ideals_by_id = {wrapper["ideal_form_id"]: wrapper["ideal_form"] for wrapper in active_ideals}
    valid_self_images: list[dict[str, Any]] = []
    for index, image in enumerate(finalized["self_images"]):
        image_valid = True
        for active_form in image["active_ideal_forms"]:
            if not isinstance(active_form, Mapping):
                image_valid = False
                break
            ideal = ideals_by_id.get(str(active_form.get("form_id", "")))
            if ideal is None:
                image_valid = False
                break
            predicates = ideal["predicates"]
            expected_predicates = sorted(str(item["predicate_id"]) for item in predicates)
            expected_receipts = {str(item["receipt_reference"]) for item in predicates}
            expected_distance = (
                len(predicates) - sum(item["result"] == "pass" for item in predicates)
            ) / len(predicates)
            evidence_references = active_form.get("evidence_references")
            if (
                active_form.get("implementation_state") != ideal["implementation_state"]
                or active_form.get("distance_to_ideal") != expected_distance
                or sorted(str(value) for value in active_form.get("predicate_references", []))
                != expected_predicates
                or not isinstance(evidence_references, list)
                or not expected_receipts.issubset(
                    {str(value) for value in evidence_references},
                )
            ):
                image_valid = False
                break
        if not image_valid:
            _diagnose(
                finalized,
                "self_image",
                index,
                image,
                "self_image_ideal_state_not_receipt_derived",
            )
        valid_self_images.append(image)
    finalized["self_images"] = valid_self_images
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
