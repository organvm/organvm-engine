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
RECEIPT_FILENAME = "governance-atlas-receipt.json"

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
    receipt_path: Path | None = None
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
        assertion_id = ratification.get("assertion_evidence_reference")
        assertion = next(
            (item for item in state["assertions"] if item.get("assertion_id") == assertion_id),
            None,
        )
        groups = {
            str(reference.get("independence_group"))
            for reference in (
                assertion.get("evidence_references", []) if isinstance(assertion, Mapping) else []
            )
            if isinstance(reference, Mapping) and reference.get("independence_group")
        }
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
    ideal_forms = [deepcopy(wrapper["ideal_form"]) for wrapper in state["ideal_forms"]]
    verified = sum(ideal["implementation_state"] == "verified" for ideal in ideal_forms)
    blocked = sum(ideal["implementation_state"] == "blocked" for ideal in ideal_forms)
    incomplete_predicates = sorted(
        str(predicate["predicate_id"])
        for ideal in ideal_forms
        for predicate in ideal["predicates"]
        if predicate["result"] != "pass"
    )
    ready = bool(ideal_forms) and verified == len(ideal_forms) and not incomplete_predicates
    body = {
        **{
            key: deepcopy(value)
            for key, value in source.items()
            if key not in {"ideal_forms", "coverage", "readiness", "register_digest"}
        },
        "ideal_forms": [deepcopy(wrapper["ideal_form"]) for wrapper in state["ideal_forms"]],
        "coverage": {
            "registered": len(ideal_forms),
            "verified": verified,
            "blocked": blocked,
            "incomplete": len(ideal_forms) - verified - blocked,
        },
        "readiness": {
            "exact_all": True,
            "unresolved_blockers": [],
            "quarantines": [],
            "missing_requirements": [],
            "citation_debt": [],
            "incomplete_predicates": incomplete_predicates,
            "ready": ready,
            "status": "ready" if ready else "incomplete",
        },
    }
    return {**body, "register_digest": content_digest(body)}


def _atlas_timeline(nodes: list[dict[str, Any]], lane: str) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "entry_id": node["node_id"],
                "event_reference": node["node_id"],
                "occurred_at": node["occurred_at"],
                "title": node["summary"],
                "source_envelope_references": [node["source_envelope_id"]],
                "evidence_references": [node["source_envelope_id"]],
            }
            for node in nodes
            if node["lane"] == lane
        ],
        key=lambda item: (item["occurred_at"], item["entry_id"]),
    )


def _atlas_zooms(
    nodes: list[dict[str, Any]],
    *,
    self_image_ids: set[str],
    ideal_form_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    zooms: dict[str, list[dict[str, Any]]] = {}
    for level in ZOOM_LEVELS:
        values: list[dict[str, Any]] = []
        for node in nodes:
            if node["_zoom_level"] != level:
                continue
            entity_id = node.get("metadata", {}).get("entity_id")
            if not isinstance(entity_id, str) or entity_id not in self_image_ids:
                raise ValueError(f"lineage node {node['node_id']} has no resolved self-image")
            values.append(
                {
                    "node_id": node["node_id"],
                    "title": node["summary"],
                    "summary": node["summary"],
                    "self_image_reference": entity_id,
                    "ideal_form_references": ideal_form_ids,
                    "evidence_references": [node["source_envelope_id"]],
                },
            )
        zooms[level] = sorted(values, key=lambda item: item["node_id"])
    return zooms


def _atlas_relationships(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "relationship_id": edge["edge_id"],
                "from_node_id": edge["from_node"],
                "to_node_id": edge["to_node"],
                "relationship_type": edge["edge_type"],
                "evidence_references": sorted(evidence_groups(edge)),
            }
            for edge in state["edges"]
            if edge["review_state"] == "reviewed"
        ],
        key=lambda item: item["relationship_id"],
    )


def _readiness_requirements(
    bundle: Mapping[str, Any],
    state: Mapping[str, Any],
    public: Mapping[str, Any],
) -> list[str]:
    missing: list[str] = []
    if not state["directives"]:
        missing.append("ratified_governance_testament")
    if not state["ideal_forms"]:
        missing.append("receipt_backed_ideal_forms")
    if not public["timelines"]["operator_intent"]:
        missing.append("operator_intent_timeline")
    if not public["timelines"]["artifact"]:
        missing.append("artifact_timeline")
    for level in ZOOM_LEVELS:
        if not public["zoom_levels"][level]:
            missing.append(f"zoom_level:{level}")
    if public["citation_debt"]:
        missing.append("zero_citation_debt")
    if state["quarantine"]:
        missing.append("zero_compiler_quarantine")
    if bundle["coverage"].get("ready") is not True:
        missing.append("source_coverage_ready")
    image_set = bundle["node_self_image_set"]
    image_readiness = image_set.get("readiness", {})
    if image_readiness.get("exact_all") is not True or image_readiness.get("ready") is not True:
        missing.append("exact_one_self_images")
    if len(state["self_images"]) != len(image_set["registered_node_ids"]):
        missing.append("complete_self_images")
    if not state["source_envelopes"]:
        missing.append("source_envelopes")
    if not state["assertions"]:
        missing.append("verified_assertion_evidence")
    if not public["relationships"]:
        missing.append("reviewed_relationships")
    if any(
        wrapper["ideal_form"]["implementation_state"] != "verified"
        or wrapper["ideal_form"]["residual_gaps"]
        for wrapper in state["ideal_forms"]
    ):
        missing.append("complete_ideal_predicates")
    return sorted(set(missing))


def _render_core(bundle: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[dict, dict]:
    nodes = state["nodes"]
    citation_debt = _citation_debt(state)
    ideal_form_ids = sorted(wrapper["ideal_form_id"] for wrapper in state["ideal_forms"])
    self_image_ids = {str(image["node_id"]) for image in state["self_images"]}
    public_body = {
        "contract_name": "iceberg-atlas.v1",
        "contract_version": 1,
        "atlas_id": f"iceberg-atlas:{bundle['snapshot_id']}",
        "snapshot_id": bundle["snapshot_id"],
        "snapshot_digest": bundle["snapshot_digest"],
        "generated_at": bundle["snapshot_at"],
        "source_envelope_references": sorted(
            str(source["source_id"]) for source in state["source_envelopes"]
        ),
        "assertion_evidence_references": sorted(
            str(assertion["assertion_id"]) for assertion in state["assertions"]
        ),
        "timelines": {
            "operator_intent": _atlas_timeline(nodes, "operator_intent"),
            "artifact": _atlas_timeline(nodes, "artifact"),
        },
        "zoom_levels": _atlas_zooms(
            nodes,
            self_image_ids=self_image_ids,
            ideal_form_ids=ideal_form_ids,
        ),
        "relationships": _atlas_relationships(state),
        "ideal_forms": ideal_form_ids,
        "self_images": sorted(self_image_ids),
        "coverage": {
            "exact_all": bool(bundle["coverage"]["exact_all"]) and not state["quarantine"],
            "source_count": len(state["source_envelopes"]),
            "event_count": len(bundle.get("normalized_events", nodes)),
            "node_count": len(nodes),
            "ideal_form_count": len(ideal_form_ids),
        },
        "citation_debt": sorted(
            f"{item['unit_type']}:{item['unit_id']}" for item in citation_debt["items"]
        ),
        "digest_algorithm": "sha256-rfc8785-excluding-self-digest-v1",
    }
    public = {**public_body, "atlas_digest": content_digest(public_body)}
    missing_requirements = _readiness_requirements(bundle, state, public)
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
        "source_envelopes": deepcopy(state["source_envelopes"]),
        "assertion_evidence": deepcopy(state["assertions"]),
        "node_self_image_set": {
            **deepcopy(bundle["node_self_image_set"]),
            "self_images": deepcopy(state["self_images"]),
        },
        "atlas": deepcopy(public),
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
        "governance_testament_projection": _testament_projection(state),
        "adopted_artifact_node_ids": deepcopy(state["adopted_artifact_node_ids"]),
        "citation_debt": citation_debt,
        "quarantine": deepcopy(state["quarantine"]),
        "readiness": {
            "missing_requirements": missing_requirements,
            "ready": not missing_requirements,
        },
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
        strict: bool = True,
    ) -> AtlasCompileResult:
        if max_children <= 0:
            raise ValueError("max_children must be positive")
        validate_bundle_headers(bundle)
        children = bundle_children(bundle)
        input_digest = str(
            bundle.get("_snapshot_bundle_digest") or content_digest(bundle),
        )
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

        finalized = finalize_state(
            state,
            source_ready=bundle["coverage"].get("ready") is True,
        )
        public_core, detail_core = _render_core(bundle, finalized)
        missing_requirements = detail_core["readiness"]["missing_requirements"]
        if missing_requirements and strict:
            cursor.update(
                {
                    "complete": False,
                    "next_child": len(children),
                    "state": finalized,
                    "blocked_requirements": missing_requirements,
                },
            )
            _write_if_changed(cursor_path, cursor)
            raise ValueError(
                "atlas strict readiness failed: " + ", ".join(missing_requirements),
            )

        artifact_digest = str(public_core["atlas_digest"])
        ideal_register = detail_core["ideal_form_register"]
        coverage = bundle["coverage"]
        self_image_readiness = bundle["node_self_image_set"].get("readiness", {})
        predicate_results = {
            "source_envelopes_resolved": bool(finalized["source_envelopes"])
            and "source_coverage_ready" not in missing_requirements,
            "assertions_verified": bool(finalized["assertions"])
            and "verified_assertion_evidence" not in missing_requirements,
            "ideal_forms_complete": "complete_ideal_predicates" not in missing_requirements,
            "self_images_complete": not {
                "exact_one_self_images",
                "complete_self_images",
            }
            & set(missing_requirements),
            "timelines_complete": all(
                public_core["timelines"][lane] for lane in ("operator_intent", "artifact")
            ),
            "zooms_complete": all(public_core["zoom_levels"][level] for level in ZOOM_LEVELS),
            "atlas_digest_verified": True,
        }

        def debt_values(*values: Any) -> list[str]:
            return sorted(
                {str(item) for value in values if isinstance(value, list) for item in value},
            )

        quarantine_ids = [
            f"{item.get('reason', 'quarantine')}:{item.get('unit_id', 'unknown')}"
            for item in finalized["quarantine"]
            if isinstance(item, Mapping)
        ]
        incomplete_ideal_predicates = [
            str(predicate["predicate_id"])
            for wrapper in finalized["ideal_forms"]
            for predicate in wrapper["ideal_form"].get("predicates", [])
            if isinstance(predicate, Mapping) and predicate.get("result") != "pass"
        ]
        readiness = {
            "exact_all": bool(coverage.get("exact_all"))
            and self_image_readiness.get("exact_all") is True
            and not finalized["quarantine"],
            "unresolved_blockers": debt_values(
                coverage.get("unresolved_blockers"),
                self_image_readiness.get("unresolved_blockers"),
            ),
            "quarantines": debt_values(
                coverage.get("quarantines"),
                self_image_readiness.get("quarantines"),
                quarantine_ids,
            ),
            "missing_requirements": debt_values(
                coverage.get("missing_requirements"),
                self_image_readiness.get("missing_requirements"),
                missing_requirements,
            ),
            "citation_debt": debt_values(
                coverage.get("citation_debt"),
                self_image_readiness.get("citation_debt"),
                public_core["citation_debt"],
            ),
            "incomplete_predicates": debt_values(
                coverage.get("incomplete_predicates"),
                self_image_readiness.get("incomplete_predicates"),
                incomplete_ideal_predicates,
            ),
        }
        readiness["ready"] = bool(
            readiness["exact_all"]
            and all(predicate_results.values())
            and not any(
                readiness[field]
                for field in (
                    "unresolved_blockers",
                    "quarantines",
                    "missing_requirements",
                    "citation_debt",
                    "incomplete_predicates",
                )
            )
        )
        readiness["status"] = "ready" if readiness["ready"] else "blocked"
        receipt_body = {
            "contract_name": RECEIPT_SCHEMA,
            "contract_version": 1,
            "atlas_receipt_id": f"governance-atlas:{bundle['snapshot_id']}",
            "snapshot_id": bundle["snapshot_id"],
            "snapshot_digest": bundle["snapshot_digest"],
            "owner_reference": self._receipt_identity.source_repo,
            "generated_at": bundle["snapshot_at"],
            "source_envelope_set": {
                "artifact_id": f"source-envelopes:{bundle['snapshot_id']}",
                "reference": "snapshot-bundle:#/source_envelopes",
                "snapshot_id": bundle["snapshot_id"],
                "digest": content_digest(finalized["source_envelopes"]),
                "count": len(finalized["source_envelopes"]),
            },
            "assertion_evidence_set": {
                "artifact_id": f"assertion-evidence:{bundle['snapshot_id']}",
                "reference": "snapshot-bundle:#/assertion_evidence",
                "snapshot_id": bundle["snapshot_id"],
                "digest": content_digest(finalized["assertions"]),
                "count": len(finalized["assertions"]),
            },
            "ideal_form_register": {
                "artifact_id": ideal_register["register_id"],
                "reference": f"{DETAIL_FILENAME}#/ideal_form_register",
                "snapshot_id": bundle["snapshot_id"],
                "digest": ideal_register["register_digest"],
            },
            "node_self_image_set": {
                "artifact_id": bundle["node_self_image_set"]["set_id"],
                "reference": "snapshot-bundle:#/node_self_image_set",
                "snapshot_id": bundle["snapshot_id"],
                "digest": bundle["node_self_image_set"]["set_digest"],
                "count": len(finalized["self_images"]),
            },
            "iceberg_atlas": {
                "artifact_id": public_core["atlas_id"],
                "reference": PUBLIC_FILENAME,
                "snapshot_id": bundle["snapshot_id"],
                "digest": artifact_digest,
            },
            "timeline_counts": {
                lane: len(public_core["timelines"][lane])
                for lane in ("operator_intent", "artifact")
            },
            "zoom_counts": {level: len(public_core["zoom_levels"][level]) for level in ZOOM_LEVELS},
            "predicate_results": predicate_results,
            "readiness": readiness,
            "digest_algorithm": "sha256-rfc8785-excluding-self-digest-v1",
        }
        receipt = {**receipt_body, "receipt_digest": content_digest(receipt_body)}
        event = (
            self._receipt_event(
                str(bundle["snapshot_id"]),
                input_digest,
                artifact_digest,
            )
            if readiness["ready"]
            else None
        )
        detail = {
            **detail_core,
            "receipt": receipt,
            "event_spine": (
                {
                    "event_id": event.event_id,
                    "sequence": event.sequence,
                    "hash": event.hash,
                }
                if event is not None
                else {
                    "status": "not_emitted",
                    "reason": "atlas-readiness-blocked",
                }
            ),
        }
        public_path = output_dir / PUBLIC_FILENAME
        detail_path = output_dir / DETAIL_FILENAME
        receipt_path = output_dir / RECEIPT_FILENAME
        _write_if_changed(public_path, public_core)
        _write_if_changed(detail_path, detail)
        _write_if_changed(receipt_path, receipt)

        cursor.update(
            {
                "complete": True,
                "next_child": len(children),
                "state": finalized,
                "receipt": receipt,
                "blocked_requirements": missing_requirements,
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
            receipt_path=receipt_path,
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
    strict: bool = True,
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
        strict=strict,
    )
