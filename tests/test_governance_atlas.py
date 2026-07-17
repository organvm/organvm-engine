"""Regression fixtures for the deterministic governance Iceberg Atlas."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from organvm_engine.corpus.governance_bundle import load_materialized_snapshot_bundle
from organvm_engine.corpus.governance_lineage import (
    canonical_json,
    content_digest,
    validate_bundle_headers,
)
from organvm_engine.events.spine import EventSpine, EventType
from organvm_engine.testament.governance_compiler import compile_candidate_testament
from organvm_engine.testament.iceberg_atlas import (
    IcebergAtlasCompiler,
    ReceiptIdentity,
)

SNAPSHOT_ID = "snapshot-governance-20260716"
SNAPSHOT_DIGEST = "sha256:" + "d" * 64
PRIVATE_MARKER = "PRIVATE-PRIME-DIRECTIVE-BODY"
RECEIPT_IDENTITY = ReceiptIdentity(
    actor="fixture-atlas-compiler",
    source_organ="fixture-governance-organ",
    source_repo="fixture-engine-repository",
)


def _hash(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()}"


def test_governance_canonical_json_is_rfc8785() -> None:
    assert canonical_json({"\U0001f600": 1, "\ue000": 2}) == '{"😀":1,"\ue000":2}'
    assert canonical_json(1.0) == "1"
    with pytest.raises(ValueError, match="safe integer domain"):
        canonical_json(2**60)


def _source_id(node_id: str) -> str:
    return "src_" + "".join(character if character.isalnum() else "_" for character in node_id)


def _node(
    node_id: str,
    *,
    lane: str,
    node_type: str,
    occurred_at: str,
    zoom_level: str,
    authority_class: str | None = None,
    content_hash: str | None = None,
    metadata: dict | None = None,
) -> dict:
    node_metadata = {
        "zoom_level": zoom_level,
        "entity_id": "entity-governance-organ",
        **(metadata or {}),
    }
    return {
        "node_id": node_id,
        "lane": lane,
        "node_type": node_type,
        "source_envelope_id": _source_id(node_id),
        "occurred_at": occurred_at,
        "authority_class": authority_class
        or ("operator_intent" if lane == "operator_intent" else "artifact"),
        "summary": f"Reviewed fixture node {node_id}.",
        "content_hash": content_hash or _hash(node_id),
        "review_state": "reviewed",
        "metadata": node_metadata,
    }


def _edge(
    source: dict,
    target: dict,
    edge_type: str,
    minute: int,
) -> dict:
    return {
        "edge_id": f"edge-{minute:02d}-{edge_type}",
        "from_node": source["node_id"],
        "to_node": target["node_id"],
        "edge_type": edge_type,
        "evidence_spans": [
            {
                "source_envelope_id": source["source_envelope_id"],
                "reference": f"private-cas://fixture/{minute}",
                "body_hash": source["content_hash"],
            },
        ],
        "confidence": 1.0,
        "review_state": "reviewed",
        "reviewer_reference": "owner-governance-fixture",
    }


def _source_envelope(node: dict) -> dict:
    return {
        "contract_name": "source-envelope.v1",
        "contract_version": 1,
        "source_id": node["source_envelope_id"],
        "source_family": node.get("metadata", {}).get("source_family", "fixture-provider"),
        "source_instance": "fixture-instance",
        "format_adapter": "fixture-json",
        "custody_snapshot": {
            "snapshot_id": SNAPSHOT_ID,
            "captured_at": "2026-07-16T18:00:00Z",
            "snapshot_hash": _hash("fixture-custody"),
            "custody_pointer": "private-cas://fixture/snapshot",
            "immutable": True,
        },
        "native_identifiers": {"event_id": node["node_id"]},
        "role": "operator" if node["lane"] == "operator_intent" else "assistant",
        "event_timestamp": node["occurred_at"],
        "ingestion_timestamp": "2026-07-16T18:00:00Z",
        "authority_class": node["authority_class"],
        "body_hash": node["content_hash"],
        "private_custody_pointer": f"private-cas://fixture/{node['node_id']}",
    }


def _normalized_event(node: dict) -> dict:
    role = "operator" if node["lane"] == "operator_intent" else "assistant"
    identity_basis = {
        "native_identity_namespace": "fixture-governance-lineage",
        "native_identifiers": {"event_id": node["node_id"]},
        "native_role": role,
        "content_hash": node["content_hash"],
    }
    return {
        "contract_name": "normalized-event.v1",
        "contract_version": 1,
        "event_id": "evt_" + content_digest(identity_basis).removeprefix("sha256:"),
        "identity_algorithm": "sha256-canonical-json-native-identity-role-content-v1",
        "identity_basis": identity_basis,
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_digest": SNAPSHOT_DIGEST,
        "raw_unit_id": "raw_" + _source_id(node["node_id"]).removeprefix("src_"),
        "source_family": node.get("metadata", {}).get(
            "source_family",
            "fixture-provider",
        ),
        "source_instance": "fixture-instance",
        "format_adapter": "fixture-json",
        "normalized_role": role,
        "occurred_at": node["occurred_at"],
        "authority_class": node["authority_class"],
        "source_envelope_reference": node["source_envelope_id"],
        "evidence_references": [f"source-envelope:{node['source_envelope_id']}"],
    }


def _refresh_artifact_digest(
    bundle: dict,
    field_name: str,
    digest_field: str,
) -> None:
    document = bundle.get(field_name)
    if not isinstance(document, dict):
        return
    body = deepcopy(document)
    body.pop(digest_field, None)
    document[digest_field] = content_digest(body)


def _refresh_coverage(bundle: dict) -> None:
    source_ids = sorted(
        {
            node["source_envelope_id"]
            for node in bundle["lineage_graph"]["nodes"]
            if isinstance(node, dict) and node.get("source_envelope_id")
        },
    )
    sources = [
        {
            "source_id": source_id,
            "status": "parsed",
            "accessible": True,
            "evidence_references": [f"receipt:parsed:{source_id}"],
        }
        for source_id in source_ids
    ]
    coverage = bundle["coverage"]
    coverage["denominator"]["count"] = len(sources)
    coverage["denominator"]["manifest_hash"] = _hash(json.dumps(source_ids))
    coverage["sources"] = sources
    coverage["counts"] = {
        "acquired": 0,
        "parsed": len(sources),
        "quarantined": 0,
        "inaccessible": 0,
        "missing_expected": 0,
        "owner_blocked": 0,
    }
    coverage["exact_all"] = True
    coverage["ready"] = True
    coverage["residual_owners"] = []
    coverage["receipt_hash"] = _hash(json.dumps(sources, sort_keys=True))
    bundle["source_envelopes"] = [
        _source_envelope(node)
        for node in bundle["lineage_graph"]["nodes"]
        if isinstance(node, dict) and node.get("source_envelope_id")
    ]
    bundle["normalized_events"] = [
        _normalized_event(node)
        for node in bundle["lineage_graph"]["nodes"]
        if isinstance(node, dict) and node.get("content_hash")
    ]
    ratification = bundle.get("governance_testament", {}).get("ratification")
    if isinstance(ratification, dict):
        authority_nodes = [
            node
            for node in bundle["lineage_graph"]["nodes"]
            if isinstance(node, dict)
            and node.get("lane") == "operator_intent"
            and node.get("node_id") != "intent-operator-adoption"
        ]
        event_by_node = {node["node_id"]: _normalized_event(node) for node in authority_nodes}
        ratification["authority_events"] = [
            {
                "event_id": event_by_node[node["node_id"]]["event_id"],
                "source_envelope_reference": node["source_envelope_id"],
                "role": "operator",
                "authority_class": "operator_intent",
                "content_hash": node["content_hash"],
            }
            for node in authority_nodes
        ]
        candidate = deepcopy(bundle["governance_testament"])
        candidate["status"] = "candidate"
        candidate.pop("ratification", None)
        ratification["candidate_digest"] = content_digest(candidate)
    for field_name, digest_field in (
        ("ideal_form_register", "register_digest"),
        ("node_self_image_set", "set_digest"),
    ):
        _refresh_artifact_digest(bundle, field_name, digest_field)


def _bundle() -> dict:
    march = _node(
        "intent-march-origin",
        lane="operator_intent",
        node_type="ask",
        occurred_at="2026-03-20T10:00:00Z",
        zoom_level="system",
    )
    april = _node(
        "intent-april-refinement",
        lane="operator_intent",
        node_type="correction",
        occurred_at="2026-04-23T10:00:00Z",
        zoom_level="organ",
    )
    may = _node(
        "intent-may-citation-correction",
        lane="operator_intent",
        node_type="correction",
        occurred_at="2026-05-22T10:00:00Z",
        zoom_level="repository",
    )
    july = _node(
        "intent-july-controlling-form",
        lane="operator_intent",
        node_type="acceptance_criterion",
        occurred_at="2026-07-16T10:00:00Z",
        zoom_level="document",
    )
    plan = _node(
        "artifact-assistant-plan",
        lane="artifact",
        node_type="plan",
        occurred_at="2026-07-16T10:05:00Z",
        zoom_level="atom",
        metadata={
            "body": PRIVATE_MARKER,
            "private_custody_pointer": "/private/archive/plan.json",
        },
    )
    adoption = _node(
        "intent-operator-adoption",
        lane="operator_intent",
        node_type="source_event",
        occurred_at="2026-07-16T10:10:00Z",
        zoom_level="session",
    )
    ideal_form_id = "ideal-form-perpetual-memory"
    bundle = {
        "contract_name": "governance-snapshot-bundle.v1",
        "contract_version": 1,
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_digest": SNAPSHOT_DIGEST,
        "snapshot_at": "2026-07-16T18:00:00Z",
        "governance_testament": {
            "contract_name": "governance-testament.v1",
            "contract_version": 1,
            "testament_id": "directive-prime",
            "version": "1.0.0",
            "title": "Governed Memory Fixture",
            "status": "ratified",
            "directive": "Preserve source authority and reconcile memory through bounded events.",
            "directive_hash": _hash("fixture prime directive"),
            "layers": ["ontology", "cybernetics", "phenomenology"],
            "instruments": [
                {
                    "instrument_id": "EVENT-SPINE",
                    "reference": "spec://event-spine",
                    "status": "partial",
                },
            ],
            "axioms": [
                {
                    "axiom_id": "AX-AUTHORITY",
                    "statement": "Operator intent and generated artifacts remain distinct.",
                    "citation_references": ["assertion:authority-fixture"],
                },
            ],
            "ideal_form_references": [ideal_form_id],
            "ratification": {
                "ratified_at": "2026-07-16T18:00:00Z",
                "candidate_digest": _hash("fixture candidate testament"),
                "controlling_formulation": "The July operator event controls this directive.",
                "assertion_evidence_reference": "assertion:authority-fixture",
                "authority_event_reference": f"lineage-node:{july['node_id']}",
                "authority_events": [],
                "constitutional_coverage": {
                    "scope_reference": "coverage:fixture-constitution",
                    "exact_all": True,
                    "blocked_scopes": [],
                    "missing_requirements": [],
                    "ready": True,
                },
                "constitutional_record_reference": "constitution:fixture-amendment",
                "source_lineage_references": ["lineage:fixture"],
                "approver_reference": "owner-governance-fixture",
            },
            "predicates": [
                {
                    "predicate_id": "predicate-fixed-point",
                    "command": "pytest tests/test_governance_atlas.py",
                    "expected_result": "two unchanged renders are byte-identical",
                },
            ],
            "citations": ["assertion:authority-fixture"],
        },
        "lineage_graph": {
            "contract_name": "lineage-graph.v1",
            "contract_version": 1,
            "graph_id": "fixture-prime-directive-lineage",
            "generated_at": "2026-07-16T17:55:00Z",
            "frozen_snapshot_id": SNAPSHOT_ID,
            "nodes": [march, april, may, july, plan, adoption],
            "edges": [
                _edge(april, march, "refines", 1),
                _edge(may, april, "corrects", 2),
                _edge(july, may, "supersedes", 3),
                _edge(july, march, "contradicts", 4),
                _edge(plan, july, "implements", 5),
                _edge(adoption, plan, "adopts", 6),
            ],
        },
        "ideal_form_register": {
            "contract_name": "ideal-form-register.v1",
            "contract_version": 1,
            "register_id": "fixture-ideal-forms",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "generated_at": "2026-07-16T17:56:00Z",
            "ideal_forms": [
                {
                    "ideal_form_id": ideal_form_id,
                    "title": "Bounded Perpetual Memory",
                    "controlling_formulation": "governance-testament:directive-prime",
                    "source_envelope_references": [july["source_envelope_id"]],
                    "lineage_references": ["lineage:fixture"],
                    "owner_reference": "owner-governance-fixture",
                    "implementation_state": "verified",
                    "distance_to_ideal": {
                        "classification": "verified",
                        "verified_predicates": 2,
                        "total_predicates": 2,
                    },
                    "predicates": [
                        {
                            "predicate_id": "IF-001",
                            "statement": "Two unchanged renders are byte-identical.",
                            "receipt_reference": "receipt:fixed-point-fixture",
                            "result": "pass",
                            "evidence_references": ["evidence:fixed-point-fixture"],
                        },
                        {
                            "predicate_id": "IF-002",
                            "statement": "Every owner has completed the second pass.",
                            "receipt_reference": "receipt:owner-pass-fixture",
                            "result": "pass",
                            "evidence_references": ["evidence:owner-pass-fixture"],
                        },
                    ],
                    "assertion_evidence_references": ["assertion:authority-fixture"],
                    "derivation": {
                        "algorithm": "predicate-receipt-status-v1",
                        "receipt_references": [
                            "receipt:fixed-point-fixture",
                            "receipt:owner-pass-fixture",
                            "receipt:additional-derivation-context",
                        ],
                    },
                    "receipt_target": "receipt:governance-atlas",
                    "residual_gaps": [],
                },
            ],
            "coverage": {
                "registered": 1,
                "verified": 1,
                "blocked": 0,
                "incomplete": 0,
            },
            "readiness": {
                "exact_all": True,
                "unresolved_blockers": [],
                "quarantines": [],
                "missing_requirements": [],
                "citation_debt": [],
                "incomplete_predicates": [],
                "ready": True,
                "status": "ready",
            },
            "digest_algorithm": "sha256-rfc8785-excluding-self-digest-v1",
            "register_digest": _hash("fixture ideal register"),
        },
        "coverage": {
            "contract_name": "coverage-receipt.v1",
            "contract_version": 1,
            "receipt_id": "coverage-fixture",
            "snapshot_id": SNAPSHOT_ID,
            "generated_at": "2026-07-16T17:57:00Z",
            "denominator": {
                "discovery_manifest_reference": "manifest:fixture",
                "count": 0,
                "manifest_hash": _hash("empty"),
            },
            "sources": [],
            "counts": {},
            "exact_all": True,
            "ready": True,
            "residual_owners": [],
            "receipt_hash": _hash("coverage-fixture"),
        },
        "assertion_evidence": [
            {
                "contract_name": "assertion-evidence.v1",
                "contract_version": 1,
                "assertion_id": "assertion:authority-fixture",
                "assertion_class": "operator_directive",
                "statement": "The July native operator event controls the directive.",
                "verification_state": "verified",
                "evidence_references": [
                    {
                        "evidence_id": "evidence:july-event",
                        "independence_group": "native-operator-event",
                        "evidence_type": "immutable_source_event",
                        "reference": july["source_envelope_id"],
                        "body_hash": july["content_hash"],
                    },
                    {
                        "evidence_id": "evidence:constitutional-record",
                        "independence_group": "constitutional-chain",
                        "evidence_type": "ratified_constitutional_record",
                        "reference": "constitution:fixture-amendment",
                        "body_hash": _hash("fixture constitutional record"),
                    },
                ],
            },
        ],
        "node_self_image_set": {
            "contract_name": "node-self-image-set.v1",
            "contract_version": 1,
            "set_id": "self-images:fixture",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "registry_reference": "registry:fixture",
            "registry_digest": _hash("fixture registry"),
            "registered_node_ids": ["entity-governance-organ"],
            "self_images": [
                {
                    "contract_name": "node-self-image.v1",
                    "contract_version": 1,
                    "node_id": "entity-governance-organ",
                    "node_type": "organ",
                    "display_name": "${NODE_DISPLAY_NAME}",
                    "owner_reference": "owner-governance-fixture",
                    "relations": {"incoming": [], "outgoing": []},
                    "cursors": {"memory": july["node_id"], "event": "event:6"},
                    "digests": {
                        "constitutional": _hash("constitution"),
                        "topology": _hash("topology"),
                    },
                    "observations": [
                        {
                            "key": "governance.coverage",
                            "value": 1.0,
                            "observed_at": "2026-07-16T18:00:00Z",
                            "evidence_references": ["receipt:self-image-fixture"],
                        },
                    ],
                    "active_ideal_forms": [
                        {
                            "form_id": ideal_form_id,
                            "implementation_state": "verified",
                            "distance_to_ideal": 0.0,
                            "predicate_references": ["IF-001", "IF-002"],
                            "evidence_references": [
                                "receipt:fixed-point-fixture",
                                "receipt:owner-pass-fixture",
                            ],
                        },
                    ],
                    "reconciled_at": "2026-07-16T18:00:00Z",
                    "evidence_references": ["receipt:self-image-fixture"],
                },
            ],
            "counts": {"registered": 1, "exported": 1},
            "readiness": {
                "exact_all": True,
                "unresolved_blockers": [],
                "quarantines": [],
                "missing_requirements": [],
                "citation_debt": [],
                "incomplete_predicates": [],
                "ready": True,
                "status": "ready",
            },
            "digest_algorithm": "sha256-rfc8785-excluding-self-digest-v1",
            "set_digest": _hash("fixture self images"),
        },
    }
    _refresh_coverage(bundle)
    return bundle


def _compile(
    tmp_path: Path,
    bundle: dict,
    max_children: int = 1_000,
    *,
    strict: bool = True,
):
    spine = EventSpine(path=tmp_path / "events.jsonl", max_chain_bytes=0)
    compiler = IcebergAtlasCompiler(spine, receipt_identity=RECEIPT_IDENTITY)
    result = compiler.compile(
        bundle,
        output_dir=tmp_path / "output",
        cursor_path=tmp_path / "cursor.json",
        max_children=max_children,
        strict=strict,
    )
    return spine, compiler, result


def test_march_april_may_july_lineage_renders_dual_timelines_and_atlas(
    tmp_path: Path,
) -> None:
    _, _, result = _compile(tmp_path, _bundle())
    assert result.complete
    public = json.loads(result.public_path.read_text())
    detail = json.loads(result.detail_path.read_text())

    assert [item["entry_id"] for item in public["timelines"]["operator_intent"]][:4] == [
        "intent-march-origin",
        "intent-april-refinement",
        "intent-may-citation-correction",
        "intent-july-controlling-form",
    ]
    assert [item["entry_id"] for item in public["timelines"]["artifact"]] == [
        "artifact-assistant-plan",
    ]
    assert all(public["zoom_levels"][level] for level in public["zoom_levels"])
    assert detail["relationships"]["refinements"]
    assert detail["relationships"]["supersessions"]
    assert detail["relationships"]["contradictions"]
    assert detail["relationships"]["implementations"]
    assert detail["relationships"]["adoptions"]
    ideal = detail["ideal_forms"][0]
    assert ideal["controlling_node_id"] == "intent-july-controlling-form"
    assert ideal["distance_fraction"] == 0.0
    assert public["coverage"]["exact_all"] is True
    assert public["self_images"] == ["entity-governance-organ"]
    assert result.receipt["readiness"]["ready"] is True
    assert result.receipt_path.read_bytes()
    assert detail["governance_testament"]["contract_name"] == "governance-testament.v1"
    assert detail["lineage_graph"]["contract_name"] == "lineage-graph.v1"
    assert detail["ideal_form_register"]["contract_name"] == "ideal-form-register.v1"
    assert detail["assertion_evidence"][0]["contract_name"] == "assertion-evidence.v1"
    assert all("_zoom_level" not in node for node in detail["lineage_graph"]["nodes"])


def test_assistant_plan_never_becomes_operator_authority(tmp_path: Path) -> None:
    bundle = _bundle()
    bundle["lineage_graph"]["edges"] = [
        edge for edge in bundle["lineage_graph"]["edges"] if edge["edge_type"] != "adopts"
    ]
    bundle["governance_testament"]["ratification"]["authority_event_reference"] = (
        "lineage-node:artifact-assistant-plan"
    )

    with pytest.raises(ValueError, match="strict readiness"):
        _compile(tmp_path, bundle)
    cursor = json.loads((tmp_path / "cursor.json").read_text())
    assert cursor["state"]["adopted_artifact_node_ids"] == []
    assert cursor["state"]["directives"] == []
    assert cursor["state"]["ideal_forms"] == []
    assert {item["error_code"] for item in cursor["state"]["quarantine"]} >= {
        "non_operator_controlling_node",
        "ideal_not_ratified",
    }


def test_duplicate_transports_keep_role_aware_authority(tmp_path: Path) -> None:
    bundle = _bundle()
    shared_hash = _hash("transported text")
    operator = bundle["lineage_graph"]["nodes"][0]
    operator["content_hash"] = shared_hash
    continuation = _node(
        "artifact-continuation-summary",
        lane="artifact",
        node_type="source_event",
        authority_class="transport_echo",
        occurred_at="2026-07-16T10:20:00Z",
        zoom_level="atom",
        content_hash=shared_hash,
    )
    echo = _node(
        "artifact-tool-echo",
        lane="artifact",
        node_type="source_event",
        authority_class="transport_echo",
        occurred_at="2026-07-16T10:21:00Z",
        zoom_level="atom",
        content_hash=shared_hash,
    )
    bundle["lineage_graph"]["nodes"].extend([continuation, echo])
    bundle["lineage_graph"]["edges"].extend(
        [
            _edge(continuation, operator, "transport_echo", 20),
            _edge(echo, operator, "exact_duplicate", 21),
        ],
    )
    _refresh_coverage(bundle)

    _, _, result = _compile(tmp_path, bundle)
    detail = json.loads(result.detail_path.read_text())
    lanes = {
        item["node_id"]: item["lane"] for lane in detail["timelines"].values() for item in lane
    }
    assert lanes[operator["node_id"]] == "operator_intent"
    assert lanes[continuation["node_id"]] == "artifact"
    assert lanes[echo["node_id"]] == "artifact"
    assert len(detail["relationships"]["duplicates_and_echoes"]) == 2


def test_malformed_units_quarantine_without_stopping_siblings(tmp_path: Path) -> None:
    bundle = _bundle()
    bundle["lineage_graph"]["nodes"].extend(
        [
            "MALFORMED-PRIVATE-BODY",
            {
                **deepcopy(bundle["lineage_graph"]["nodes"][4]),
                "node_id": "invalid-lane-promotion",
                "lane": "operator_intent",
            },
        ],
    )
    bundle["lineage_graph"]["edges"].append(
        {
            **_edge(
                bundle["lineage_graph"]["nodes"][4],
                bundle["lineage_graph"]["nodes"][3],
                "refines",
                30,
            ),
            "edge_type": "fabricated_relation",
        },
    )

    with pytest.raises(ValueError, match="zero_compiler_quarantine"):
        _compile(tmp_path, bundle)
    cursor_text = (tmp_path / "cursor.json").read_text()
    cursor = json.loads(cursor_text)
    assert "MALFORMED-PRIVATE-BODY" not in cursor_text
    assert not (tmp_path / "output" / "iceberg-atlas.public.json").exists()
    assert len(cursor["state"]["quarantine"]) == 3
    assert all(item["record_hash"].startswith("sha256:") for item in cursor["state"]["quarantine"])


def test_public_output_is_redacted_while_private_detail_preserves_custody(
    tmp_path: Path,
) -> None:
    _, _, result = _compile(tmp_path, _bundle())
    public_text = result.public_path.read_text()
    detail_text = result.detail_path.read_text()

    assert PRIVATE_MARKER not in public_text
    assert "/private/archive/plan.json" not in public_text
    assert PRIVATE_MARKER in detail_text
    assert "/private/archive/plan.json" in detail_text


def test_allow_blocked_materializes_honest_atlas_without_verified_event(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    coverage = bundle["coverage"]
    blocker = {
        "source_id": "source-unavailable-export",
        "status": "owner_blocked",
        "accessible": False,
        "owner_reference": "owner:source-export",
        "failed_predicate": "official-export-present",
        "next_action": "Acquire the owner-issued read-only export.",
        "evidence_references": ["owner:source-export"],
    }
    coverage["sources"].append(blocker)
    coverage["denominator"]["count"] += 1
    coverage["counts"]["owner_blocked"] = 1
    coverage["ready"] = False
    coverage["unresolved_blockers"] = [blocker["source_id"]]
    coverage["residual_owners"] = [
        {
            key: blocker[key]
            for key in (
                "source_id",
                "owner_reference",
                "failed_predicate",
                "next_action",
            )
        },
    ]

    spine, compiler, result = _compile(tmp_path, bundle, strict=False)
    assert result.complete
    assert result.receipt["readiness"]["ready"] is False
    assert result.receipt["readiness"]["status"] == "blocked"
    assert "source_coverage_ready" in result.receipt["readiness"]["missing_requirements"]
    false_gaps = {
        "ratified_governance_testament",
        "receipt_backed_ideal_forms",
        "zero_compiler_quarantine",
        "exact_one_self_images",
    }
    assert false_gaps.isdisjoint(result.receipt["readiness"]["missing_requirements"])
    assert result.public_path.is_file()
    assert result.detail_path.is_file()
    assert result.receipt_path.is_file()
    assert spine.snapshot()["event_count"] == 0
    public = json.loads(result.public_path.read_text(encoding="utf-8"))
    detail = json.loads(result.detail_path.read_text(encoding="utf-8"))
    expected_ideal_ids = sorted(
        ideal["ideal_form_id"]
        for ideal in bundle["ideal_form_register"]["ideal_forms"]
    )
    assert detail["governance_testament"] == bundle["governance_testament"]
    assert detail["ideal_form_register"] == bundle["ideal_form_register"]
    assert public["ideal_forms"] == expected_ideal_ids
    assert public["coverage"]["ideal_form_count"] == len(expected_ideal_ids)
    assert (
        result.receipt["ideal_form_register"]["digest"]
        == bundle["ideal_form_register"]["register_digest"]
    )

    before = {
        path: path.read_bytes()
        for path in (
            result.public_path,
            result.detail_path,
            result.receipt_path,
            result.cursor_path,
        )
    }
    fixed = compiler.compile(
        bundle,
        output_dir=tmp_path / "output",
        cursor_path=tmp_path / "cursor.json",
        strict=False,
    )
    assert fixed.complete
    assert fixed.processed_children == 0
    assert all(path.read_bytes() == value for path, value in before.items())
    assert spine.snapshot()["event_count"] == 0


def test_coverage_contract_rejects_inconsistent_exact_all(tmp_path: Path) -> None:
    bundle = _bundle()
    bundle["coverage"]["denominator"]["count"] += 1
    with pytest.raises(ValueError, match="exact_all"):
        _compile(tmp_path, bundle)


def test_assertion_gate_rejects_single_source_and_keeps_atlas_unready(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    bundle["assertion_evidence"][0]["evidence_references"] = bundle["assertion_evidence"][0][
        "evidence_references"
    ][:1]

    with pytest.raises(ValueError, match="strict readiness"):
        _compile(tmp_path, bundle)
    cursor = json.loads((tmp_path / "cursor.json").read_text())
    assert {item["error_code"] for item in cursor["state"]["quarantine"]} >= {
        "assertion_requires_multiple_evidence_references",
        "operator_directive_assertion_unresolved",
    }


def test_normalized_event_identity_mismatch_is_quarantined(tmp_path: Path) -> None:
    bundle = _bundle()
    bundle["normalized_events"][0]["event_id"] = "evt_" + "0" * 64

    with pytest.raises(ValueError, match="zero_compiler_quarantine"):
        _compile(tmp_path, bundle)
    cursor = json.loads((tmp_path / "cursor.json").read_text())
    assert "event_identity_mismatch" in {
        item["error_code"] for item in cursor["state"]["quarantine"]
    }


def test_ratification_requires_ready_constitutional_coverage(tmp_path: Path) -> None:
    bundle = _bundle()
    constitutional_coverage = bundle["governance_testament"]["ratification"][
        "constitutional_coverage"
    ]
    constitutional_coverage["ready"] = False
    constitutional_coverage["blocked_scopes"] = ["operator-source-events"]

    with pytest.raises(ValueError, match="ratified_governance_testament"):
        _compile(tmp_path, bundle)
    cursor = json.loads((tmp_path / "cursor.json").read_text())
    assert "constitutional_coverage_not_ready" in {
        item["error_code"] for item in cursor["state"]["quarantine"]
    }


def test_ratification_fails_when_an_immutable_operator_event_is_missing(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    missing_event_id = bundle["governance_testament"]["ratification"]["authority_events"][-1][
        "event_id"
    ]
    bundle["normalized_events"] = [
        event for event in bundle["normalized_events"] if event["event_id"] != missing_event_id
    ]

    with pytest.raises(ValueError, match="ratified_governance_testament"):
        _compile(tmp_path, bundle)
    cursor = json.loads((tmp_path / "cursor.json").read_text())
    assert "authority_event_unresolved" in {
        item["error_code"] for item in cursor["state"]["quarantine"]
    }


def test_ratification_resolves_owner_native_jsonl_fragment_references(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    for authority_event in bundle["governance_testament"]["ratification"][
        "authority_events"
    ]:
        authority_event["source_envelope_reference"] = (
            "receipt:parity-fixture:source-envelope.v1.jsonl#"
            + authority_event["source_envelope_reference"]
        )
    for event in bundle["normalized_events"]:
        event["source_envelope_reference"] = (
            "source-envelope.v1.jsonl#" + event["source_envelope_reference"]
        )
    immutable_event = bundle["assertion_evidence"][0]["evidence_references"][0]
    immutable_event["reference"] = (
        "receipt:parity-fixture:source-envelope.v1.jsonl#"
        + immutable_event["reference"]
    )

    _, _, result = _compile(tmp_path, bundle)

    assert result.receipt["readiness"]["ready"] is True


def test_handwritten_ideal_status_cannot_override_predicate_receipts(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    ideal = bundle["ideal_form_register"]["ideal_forms"][0]
    ideal["implementation_state"] = "partial"
    _refresh_artifact_digest(
        bundle,
        "ideal_form_register",
        "register_digest",
    )

    with pytest.raises(ValueError, match="zero_compiler_quarantine"):
        _compile(tmp_path, bundle)
    cursor = json.loads((tmp_path / "cursor.json").read_text())
    assert "implementation_state_not_receipt_derived" in {
        item["error_code"] for item in cursor["state"]["quarantine"]
    }


def test_self_image_active_ideal_form_is_node_local_owner_state(tmp_path: Path) -> None:
    bundle = _bundle()
    active_form = bundle["node_self_image_set"]["self_images"][0]["active_ideal_forms"][0]
    active_form["form_id"] = "ideal:owner-native-node-state"
    _refresh_artifact_digest(bundle, "node_self_image_set", "set_digest")

    _, _, result = _compile(tmp_path, bundle)
    detail = json.loads(result.detail_path.read_text(encoding="utf-8"))

    assert result.receipt["readiness"]["ready"] is True
    assert (
        detail["node_self_image_set"]["self_images"][0]["active_ideal_forms"][0]["form_id"]
        == "ideal:owner-native-node-state"
    )


def test_ratified_testament_and_ideal_register_must_cover_the_same_ids(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    bundle["governance_testament"]["ideal_form_references"].append(
        "ideal-form:missing-from-register",
    )
    candidate = deepcopy(bundle["governance_testament"])
    candidate["status"] = "candidate"
    candidate.pop("ratification", None)
    bundle["governance_testament"]["ratification"]["candidate_digest"] = content_digest(candidate)

    with pytest.raises(ValueError, match="zero_compiler_quarantine"):
        _compile(tmp_path, bundle)
    cursor = json.loads((tmp_path / "cursor.json").read_text())
    assert "ratified_ideal_register_mismatch" in {
        item["error_code"] for item in cursor["state"]["quarantine"]
    }


def test_ready_artifact_self_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    bundle = _bundle()
    bundle["ideal_form_register"]["register_digest"] = _hash("fabricated register")
    with pytest.raises(ValueError, match="self digest mismatch"):
        _compile(tmp_path, bundle)


def test_all_six_zooms_are_strict_readiness_requirements(tmp_path: Path) -> None:
    bundle = _bundle()
    for node in bundle["lineage_graph"]["nodes"]:
        if node["metadata"]["zoom_level"] == "session":
            node["metadata"]["zoom_level"] = "atom"
    _refresh_coverage(bundle)

    with pytest.raises(ValueError, match="zoom_level:session"):
        _compile(tmp_path, bundle)


def test_source_envelope_hash_mismatch_fails_directive_activation(tmp_path: Path) -> None:
    bundle = _bundle()
    controlling_id = bundle["governance_testament"]["ratification"][
        "authority_event_reference"
    ].removeprefix("lineage-node:")
    controlling = next(
        node for node in bundle["lineage_graph"]["nodes"] if node["node_id"] == controlling_id
    )
    source = next(
        envelope
        for envelope in bundle["source_envelopes"]
        if envelope["source_id"] == controlling["source_envelope_id"]
    )
    source["body_hash"] = _hash("fabricated replacement")

    with pytest.raises(ValueError, match="strict readiness"):
        _compile(tmp_path, bundle)
    cursor = json.loads((tmp_path / "cursor.json").read_text())
    assert cursor["state"]["directives"] == []
    assert {item["error_code"] for item in cursor["state"]["quarantine"]} >= {
        "source_envelope_hash_mismatch",
        "authority_event_unresolved",
    }


def test_self_image_set_must_cover_each_registered_node_exactly_once(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    bundle["node_self_image_set"]["registered_node_ids"].append("entity-missing-image")
    bundle["node_self_image_set"]["counts"]["registered"] = 2
    bundle["node_self_image_set"]["readiness"]["exact_all"] = True
    _refresh_artifact_digest(bundle, "node_self_image_set", "set_digest")
    with pytest.raises(ValueError, match="exact_one"):
        _compile(tmp_path, bundle)


def test_self_image_set_preserves_owner_routed_debt_without_aliasing_ready() -> None:
    bundle = _bundle()
    readiness = bundle["node_self_image_set"]["readiness"]
    readiness["unresolved_blockers"] = ["owner:unavailable-export"]
    readiness["ready"] = False
    readiness["status"] = "closed_with_owner_routed_debt"
    _refresh_artifact_digest(bundle, "node_self_image_set", "set_digest")

    validate_bundle_headers(bundle)


def test_candidate_pass_is_non_ratifying_bounded_and_idempotent(tmp_path: Path) -> None:
    bundle = _bundle()
    bundle["governance_testament"]["status"] = "candidate"
    bundle["governance_testament"].pop("ratification")
    candidate_assertion = bundle["assertion_evidence"][0]
    candidate_assertion["verification_state"] = "unverified"
    candidate_assertion["evidence_references"] = [
        evidence
        for evidence in candidate_assertion["evidence_references"]
        if evidence["evidence_type"] == "immutable_source_event"
    ]
    candidate_assertion["evidence_references"].append(
        {
            "evidence_id": "evidence:second-native-event",
            "independence_group": "second-native-custody",
            "evidence_type": "immutable_source_event",
            "reference": bundle["source_envelopes"][1]["source_id"],
            "body_hash": bundle["source_envelopes"][1]["body_hash"],
        },
    )
    bundle["governance_testament"]["citations"].append("specs/SPEC-000.md")
    output = tmp_path / "candidate"

    first = compile_candidate_testament(bundle, output_dir=output, max_units=100)
    testament_before = first.testament_path.read_bytes()
    receipt_before = first.receipt_path.read_bytes()
    second = compile_candidate_testament(bundle, output_dir=output, max_units=100)

    candidate = json.loads(second.testament_path.read_text())
    assert candidate["status"] == "candidate"
    assert "ratification" not in candidate
    assert second.receipt["compilation_pass"] == "candidate"
    assert second.receipt["ready_for_owner_ratification"] is True
    assert second.receipt["counts"]["candidate_assertions"] == 1
    assert second.testament_path.read_bytes() == testament_before
    assert second.receipt_path.read_bytes() == receipt_before

    bundle["governance_testament"]["status"] = "ratified"
    with pytest.raises(ValueError, match="missing its ratification record"):
        compile_candidate_testament(bundle, output_dir=output, max_units=100)

    preverified = _bundle()
    preverified["governance_testament"]["status"] = "candidate"
    preverified["governance_testament"].pop("ratification")
    with pytest.raises(ValueError, match="must remain unverified"):
        compile_candidate_testament(preverified, output_dir=output, max_units=100)

    missing_event = _bundle()
    missing_event["governance_testament"]["status"] = "candidate"
    missing_event["governance_testament"].pop("ratification")
    missing_event["assertion_evidence"] = [deepcopy(candidate_assertion)]
    missing_event["normalized_events"] = missing_event["normalized_events"][1:]
    with pytest.raises(ValueError, match="normalized event is unresolved"):
        compile_candidate_testament(missing_event, output_dir=output, max_units=100)


def test_candidate_resolves_owner_native_jsonl_fragment_references(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    bundle["governance_testament"]["status"] = "candidate"
    bundle["governance_testament"].pop("ratification")
    assertion = bundle["assertion_evidence"][0]
    assertion["verification_state"] = "unverified"
    assertion["evidence_references"] = [
        evidence
        for evidence in assertion["evidence_references"]
        if evidence["evidence_type"] == "immutable_source_event"
    ]
    controlling_source = assertion["evidence_references"][0]["reference"]
    assertion["evidence_references"][0]["reference"] = (
        "receipt:parity-fixture:source-envelope.v1.jsonl#" + controlling_source
    )
    assertion["evidence_references"].append(
        {
            "evidence_id": "evidence:second-native-event",
            "independence_group": "second-native-custody",
            "evidence_type": "immutable_source_event",
            "reference": bundle["source_envelopes"][1]["source_id"],
            "body_hash": bundle["source_envelopes"][1]["body_hash"],
        },
    )
    for event in bundle["normalized_events"]:
        event["source_envelope_reference"] = (
            "source-envelope.v1.jsonl#" + event["source_envelope_reference"]
        )

    result = compile_candidate_testament(
        bundle,
        output_dir=tmp_path / "candidate-owner-native",
        max_units=100,
    )
    assert result.receipt["ready_for_owner_ratification"] is True


def test_snapshot_artifact_references_materialize_only_at_exact_digest(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    reference_bundle = deepcopy(bundle)
    for field_name in (
        "lineage_graph",
        "governance_testament",
        "coverage",
        "ideal_form_register",
        "node_self_image_set",
    ):
        artifact = bundle[field_name]
        artifact_path = tmp_path / f"{field_name}.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        reference_bundle[field_name] = {
            "contract_name": artifact["contract_name"],
            "artifact_id": str(
                artifact.get("graph_id")
                or artifact.get("testament_id")
                or artifact.get("receipt_id")
                or artifact.get("register_id")
                or artifact.get("set_id"),
            ),
            "reference": artifact_path.name,
            "snapshot_id": SNAPSHOT_ID,
            "digest": content_digest(artifact),
        }
    bundle_path = tmp_path / "snapshot-bundle.json"
    bundle_path.write_text(json.dumps(reference_bundle), encoding="utf-8")

    materialized = load_materialized_snapshot_bundle(bundle_path)
    assert materialized["lineage_graph"] == bundle["lineage_graph"]
    assert materialized["node_self_image_set"] == bundle["node_self_image_set"]

    reference_bundle["lineage_graph"]["digest"] = _hash("wrong")
    bundle_path.write_text(json.dumps(reference_bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        load_materialized_snapshot_bundle(bundle_path)


def test_interruption_resumes_and_two_runs_reach_byte_fixed_point(tmp_path: Path) -> None:
    bundle = _bundle()
    spine, compiler, result = _compile(tmp_path, bundle, max_children=2)
    assert not result.complete
    assert result.processed_children == 2
    first_cursor = json.loads(result.cursor_path.read_text())
    assert first_cursor["next_child"] == 2
    assert len(first_cursor["state"]["source_envelopes"]) == 2

    while not result.complete:
        result = compiler.compile(
            bundle,
            output_dir=tmp_path / "output",
            cursor_path=tmp_path / "cursor.json",
            max_children=2,
        )

    public_before = result.public_path.read_bytes()
    detail_before = result.detail_path.read_bytes()
    receipt_before = result.receipt_path.read_bytes()
    cursor_before = result.cursor_path.read_bytes()
    events_before = spine.path.read_bytes()
    assert len(spine.query(event_type=EventType.TESTAMENT_VERIFIED)) == 1

    fixed = compiler.compile(
        bundle,
        output_dir=tmp_path / "output",
        cursor_path=tmp_path / "cursor.json",
        max_children=2,
    )
    assert fixed.complete
    assert fixed.processed_children == 0
    assert fixed.public_path.read_bytes() == public_before
    assert fixed.detail_path.read_bytes() == detail_before
    assert fixed.receipt_path.read_bytes() == receipt_before
    assert fixed.cursor_path.read_bytes() == cursor_before
    assert spine.path.read_bytes() == events_before
    assert len(spine.query(event_type=EventType.TESTAMENT_VERIFIED)) == 1
