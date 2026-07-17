"""Bounded first-pass compiler for a candidate governance testament."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from organvm_engine.corpus.governance_lineage import (
    SCHEMA_ASSERTION_EVIDENCE,
    SCHEMA_LINEAGE,
    SCHEMA_NORMALIZED_EVENT,
    SCHEMA_SNAPSHOT_BUNDLE,
    SCHEMA_SOURCE_ENVELOPE,
    SCHEMA_TESTAMENT,
    content_digest,
    schema_id,
)

CANDIDATE_RECEIPT_CONTRACT = "candidate-testament-receipt.v1"


@dataclass(frozen=True)
class CandidateCompileResult:
    """Paths and receipt emitted by one complete first-pass compilation."""

    testament_path: Path
    receipt_path: Path
    receipt: dict[str, Any]


def _required_text(value: Mapping[str, Any], field_name: str) -> str:
    field = value.get(field_name)
    if not isinstance(field, str) or not field:
        raise ValueError(f"missing_{field_name}")
    return field


def _required_list(value: Mapping[str, Any], field_name: str) -> list[Any]:
    field = value.get(field_name)
    if not isinstance(field, list):
        raise ValueError(f"invalid_{field_name}")
    return field


def _write_if_changed(path: Path, value: Any) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == rendered:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _source_reference_matches(assertion: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    source_id = str(source["source_id"])
    accepted = {source_id, f"source-envelope:{source_id}"}
    return any(
        isinstance(evidence, Mapping)
        and evidence.get("evidence_type") == "immutable_source_event"
        and evidence.get("reference") in accepted
        and evidence.get("body_hash") == source.get("body_hash")
        for evidence in assertion.get("evidence_references", [])
    )


def compile_candidate_testament(
    bundle: Mapping[str, Any],
    *,
    output_dir: Path,
    max_units: int = 10_000,
) -> CandidateCompileResult:
    """Compile reviewed native operator events into a non-ratified candidate.

    This pass cannot create constitutional authority.  It proves only that a
    candidate has immutable native-event ancestry and independently verified
    operator-directive assertion evidence.  Ratification remains CORPVS-owned.
    """
    if max_units <= 0:
        raise ValueError("max_units must be positive")
    if schema_id(bundle) != SCHEMA_SNAPSHOT_BUNDLE or bundle.get("contract_version") != 1:
        raise ValueError("invalid governance snapshot bundle")
    snapshot_id = _required_text(bundle, "snapshot_id")
    snapshot_at = _required_text(bundle, "snapshot_at")
    lineage = bundle.get("lineage_graph")
    testament_value = bundle.get("governance_testament")
    if not isinstance(lineage, Mapping) or schema_id(lineage) != SCHEMA_LINEAGE:
        raise ValueError("invalid lineage graph")
    if not isinstance(testament_value, Mapping) or schema_id(testament_value) != SCHEMA_TESTAMENT:
        raise ValueError("invalid governance testament")
    if testament_value.get("status") not in {"draft", "candidate"}:
        raise ValueError("candidate pass refuses a ratified or superseded testament")
    nodes = _required_list(lineage, "nodes")
    edges = _required_list(lineage, "edges")
    sources = _required_list(bundle, "source_envelopes")
    events = _required_list(bundle, "normalized_events")
    assertions = _required_list(bundle, "assertion_evidence")
    unit_count = len(nodes) + len(edges) + len(sources) + len(events) + len(assertions)
    if unit_count > max_units:
        raise ValueError("candidate compilation exceeds max_units")

    source_by_id: dict[str, Mapping[str, Any]] = {}
    for source in sources:
        if not isinstance(source, Mapping):
            raise ValueError("source envelope must be an object")
        if schema_id(source) != SCHEMA_SOURCE_ENVELOPE or source.get("contract_version") != 1:
            raise ValueError("invalid source envelope")
        source_id = _required_text(source, "source_id")
        _required_text(source, "body_hash")
        custody = source.get("custody_snapshot")
        if not isinstance(custody, Mapping) or custody.get("immutable") is not True:
            raise ValueError("candidate source envelope is not immutable")
        if source_id in source_by_id:
            raise ValueError("duplicate source envelope")
        source_by_id[source_id] = source

    event_by_source: dict[str, Mapping[str, Any]] = {}
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("normalized event must be an object")
        if schema_id(event) != SCHEMA_NORMALIZED_EVENT or event.get("contract_version") != 1:
            raise ValueError("invalid normalized event")
        source_id = _required_text(event, "source_envelope_reference")
        identity_basis = event.get("identity_basis")
        if not isinstance(identity_basis, Mapping):
            raise ValueError("normalized event identity basis is missing")
        if event.get("identity_algorithm") != (
            "sha256-canonical-json-native-identity-role-content-v1"
        ):
            raise ValueError("normalized event identity algorithm is invalid")
        expected_event_id = "evt_" + content_digest(identity_basis).removeprefix("sha256:")
        if event.get("event_id") != expected_event_id:
            raise ValueError("normalized event identity is invalid")
        if event.get("snapshot_id") != snapshot_id:
            raise ValueError("normalized event snapshot is incompatible")
        if event.get("snapshot_digest") != bundle.get("snapshot_digest"):
            raise ValueError("normalized event snapshot digest is incompatible")
        if source_id in event_by_source:
            raise ValueError("duplicate normalized event source binding")
        event_by_source[source_id] = event

    assertion_by_id: dict[str, Mapping[str, Any]] = {}
    for assertion in assertions:
        if not isinstance(assertion, Mapping):
            raise ValueError("assertion evidence must be an object")
        if schema_id(assertion) != SCHEMA_ASSERTION_EVIDENCE or assertion.get("contract_version") != 1:
            raise ValueError("invalid assertion evidence")
        assertion_id = _required_text(assertion, "assertion_id")
        if assertion.get("verification_state") != "verified":
            raise ValueError("candidate assertion evidence is not verified")
        evidence = _required_list(assertion, "evidence_references")
        groups = {
            str(reference.get("independence_group"))
            for reference in evidence
            if isinstance(reference, Mapping) and reference.get("independence_group")
        }
        if len(evidence) < 2 or len(groups) < 2:
            raise ValueError("candidate assertion evidence is not independently corroborated")
        assertion_by_id[assertion_id] = assertion

    authority_node_ids: list[str] = []
    authority_source_ids: list[str] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            raise ValueError("lineage node must be an object")
        if node.get("lane") != "operator_intent" or node.get("review_state") != "reviewed":
            continue
        source_id = _required_text(node, "source_envelope_id")
        source = source_by_id.get(source_id)
        if source is None:
            raise ValueError("candidate operator node source envelope is unresolved")
        if source.get("authority_class") != "operator_intent":
            raise ValueError("candidate operator node source authority is incompatible")
        if source.get("role") != "operator":
            raise ValueError("candidate operator node source role is incompatible")
        if source.get("body_hash") != node.get("content_hash"):
            raise ValueError("candidate operator node source hash mismatch")
        if source.get("event_timestamp") != node.get("occurred_at"):
            raise ValueError("candidate operator node source timestamp mismatch")
        event = event_by_source.get(source_id)
        identity_basis = event.get("identity_basis") if isinstance(event, Mapping) else None
        if (
            event is None
            or event.get("normalized_role") != "operator"
            or event.get("authority_class") != "operator_intent"
            or event.get("occurred_at") != node.get("occurred_at")
            or not isinstance(identity_basis, Mapping)
            or identity_basis.get("content_hash") != node.get("content_hash")
        ):
            raise ValueError("candidate operator node normalized event is unresolved")
        authority_node_ids.append(_required_text(node, "node_id"))
        authority_source_ids.append(source_id)
    if not authority_node_ids:
        raise ValueError("candidate requires a reviewed native operator event")

    citation_ids = _required_list(testament_value, "citations")
    cited_assertions = [
        assertion_by_id[citation_id]
        for citation_id in citation_ids
        if citation_id in assertion_by_id
    ]
    operator_assertions = [
        assertion
        for assertion in cited_assertions
        if assertion.get("assertion_class") == "operator_directive"
        and any(
            _source_reference_matches(assertion, source_by_id[source_id])
            for source_id in authority_source_ids
        )
    ]
    if len(cited_assertions) != len(citation_ids) or not operator_assertions:
        raise ValueError("candidate operator-directive assertion is unresolved")

    candidate = deepcopy(dict(testament_value))
    candidate["status"] = "candidate"
    candidate.pop("ratification", None)
    receipt = {
        "contract_name": CANDIDATE_RECEIPT_CONTRACT,
        "contract_version": 1,
        "receipt_id": f"candidate-testament:{snapshot_id}",
        "snapshot_id": snapshot_id,
        "snapshot_at": snapshot_at,
        "compilation_pass": "candidate",
        "input_digest": str(
            bundle.get("_snapshot_bundle_digest") or content_digest(bundle),
        ),
        "candidate_digest": content_digest(candidate),
        "authority_node_ids": sorted(set(authority_node_ids)),
        "source_envelope_ids": sorted(set(authority_source_ids)),
        "assertion_ids": sorted(
            str(assertion["assertion_id"]) for assertion in operator_assertions
        ),
        "counts": {
            "bounded_units": unit_count,
            "operator_events": len(set(authority_node_ids)),
            "normalized_events": len(event_by_source),
            "source_envelopes": len(source_by_id),
            "verified_assertions": len(assertion_by_id),
        },
        "ready_for_owner_ratification": True,
    }
    testament_path = output_dir / "governance-testament.candidate.json"
    receipt_path = output_dir / "candidate-testament-receipt.json"
    _write_if_changed(testament_path, candidate)
    _write_if_changed(receipt_path, receipt)
    return CandidateCompileResult(
        testament_path=testament_path,
        receipt_path=receipt_path,
        receipt=receipt,
    )


__all__ = [
    "CANDIDATE_RECEIPT_CONTRACT",
    "CandidateCompileResult",
    "compile_candidate_testament",
]
