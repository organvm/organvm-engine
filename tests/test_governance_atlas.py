"""Regression fixtures for the deterministic governance Iceberg Atlas."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from organvm_engine.events.spine import EventSpine, EventType
from organvm_engine.testament.iceberg_atlas import (
    IcebergAtlasCompiler,
    ReceiptIdentity,
)

SNAPSHOT_ID = "snapshot-governance-20260716"
PRIVATE_MARKER = "PRIVATE-PRIME-DIRECTIVE-BODY"
RECEIPT_IDENTITY = ReceiptIdentity(
    actor="fixture-atlas-compiler",
    source_organ="fixture-governance-organ",
    source_repo="fixture-engine-repository",
)


def _hash(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()}"


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
        "snapshot_id": SNAPSHOT_ID,
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
                "authority_event_reference": f"lineage-node:{july['node_id']}",
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
            "generated_at": "2026-07-16T17:56:00Z",
            "frozen_snapshot_id": SNAPSHOT_ID,
            "ideal_forms": [
                {
                    "ideal_form_id": ideal_form_id,
                    "title": "Bounded Perpetual Memory",
                    "controlling_formulation": "governance-testament:directive-prime",
                    "lineage_references": ["lineage:fixture"],
                    "owner_reference": "owner-governance-fixture",
                    "implementation_state": "partial",
                    "distance_to_ideal": {
                        "classification": "integration_gap",
                        "verified_predicates": 3,
                        "total_predicates": 4,
                    },
                    "predicates": [
                        {
                            "predicate_id": "IF-001",
                            "statement": "Two unchanged renders are byte-identical.",
                            "status": "pass",
                            "evidence_references": ["receipt:fixed-point-fixture"],
                        },
                    ],
                    "receipt_target": "receipt:governance-atlas",
                    "residual_gaps": [],
                },
            ],
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
                "observations": [],
                "active_ideal_forms": [
                    {
                        "form_id": ideal_form_id,
                        "implementation_state": "partial",
                        "distance_to_ideal": 0.25,
                        "predicate_references": ["IF-001"],
                        "evidence_references": ["receipt:fixed-point-fixture"],
                    },
                ],
                "reconciled_at": "2026-07-16T18:00:00Z",
                "evidence_references": ["receipt:self-image-fixture"],
            },
        ],
    }
    _refresh_coverage(bundle)
    return bundle


def _compile(tmp_path: Path, bundle: dict, max_children: int = 1_000):
    spine = EventSpine(path=tmp_path / "events.jsonl", max_chain_bytes=0)
    compiler = IcebergAtlasCompiler(spine, receipt_identity=RECEIPT_IDENTITY)
    result = compiler.compile(
        bundle,
        output_dir=tmp_path / "output",
        cursor_path=tmp_path / "cursor.json",
        max_children=max_children,
    )
    return spine, compiler, result


def test_march_april_may_july_lineage_renders_dual_timelines_and_atlas(
    tmp_path: Path,
) -> None:
    _, _, result = _compile(tmp_path, _bundle())
    assert result.complete
    public = json.loads(result.public_path.read_text())
    detail = json.loads(result.detail_path.read_text())

    assert [item["node_id"] for item in public["timelines"]["operator_intent"]][:4] == [
        "intent-march-origin",
        "intent-april-refinement",
        "intent-may-citation-correction",
        "intent-july-controlling-form",
    ]
    assert [item["node_id"] for item in public["timelines"]["artifact"]] == [
        "artifact-assistant-plan",
    ]
    assert all(public["zoom_levels"][level] for level in public["zoom_levels"])
    assert public["relationships"]["refinements"]
    assert public["relationships"]["supersessions"]
    assert public["relationships"]["contradictions"]
    assert public["relationships"]["implementations"]
    assert public["relationships"]["adoptions"]
    ideal = public["ideal_forms"][0]
    assert ideal["controlling_node_id"] == "intent-july-controlling-form"
    assert ideal["distance_fraction"] == 0.25
    assert public["coverage"]["exact_all"] is True
    assert public["coverage"]["atlas_exact_all"] is True
    assert public["self_images"][0]["node_id"] == "entity-governance-organ"
    assert detail["governance_testament"]["contract_name"] == "governance-testament.v1"
    assert detail["lineage_graph"]["contract_name"] == "lineage-graph.v1"
    assert detail["ideal_form_register"]["contract_name"] == "ideal-form-register.v1"
    assert all("_zoom_level" not in node for node in detail["lineage_graph"]["nodes"])


def test_assistant_plan_never_becomes_operator_authority(tmp_path: Path) -> None:
    bundle = _bundle()
    bundle["lineage_graph"]["edges"] = [
        edge for edge in bundle["lineage_graph"]["edges"] if edge["edge_type"] != "adopts"
    ]
    bundle["governance_testament"]["ratification"]["authority_event_reference"] = (
        "lineage-node:artifact-assistant-plan"
    )

    _, _, result = _compile(tmp_path, bundle)
    public = json.loads(result.public_path.read_text())
    detail = json.loads(result.detail_path.read_text())

    plan = next(
        item
        for item in public["timelines"]["artifact"]
        if item["node_id"] == "artifact-assistant-plan"
    )
    assert plan["lane"] == "artifact"
    assert detail["adopted_artifact_node_ids"] == []
    assert public["governance_testament"] is None
    assert public["ideal_forms"] == []
    assert result.receipt["counts"]["directives"] == 0
    assert {item["error_code"] for item in detail["quarantine"]} >= {
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
    public = json.loads(result.public_path.read_text())
    lanes = {
        item["node_id"]: item["lane"] for lane in public["timelines"].values() for item in lane
    }
    assert lanes[operator["node_id"]] == "operator_intent"
    assert lanes[continuation["node_id"]] == "artifact"
    assert lanes[echo["node_id"]] == "artifact"
    assert len(public["relationships"]["duplicates_and_echoes"]) == 2


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

    _, _, result = _compile(tmp_path, bundle)
    public_text = result.public_path.read_text()
    detail_text = result.detail_path.read_text()
    public = json.loads(public_text)

    assert result.complete
    assert result.receipt["counts"]["nodes"] == 6
    assert result.receipt["counts"]["quarantined"] == 3
    assert public["coverage"]["exact_all"] is True
    assert public["coverage"]["atlas_exact_all"] is False
    assert "MALFORMED-PRIVATE-BODY" not in public_text
    assert "MALFORMED-PRIVATE-BODY" not in detail_text
    assert all(
        item["record_hash"].startswith("sha256:") for item in json.loads(detail_text)["quarantine"]
    )


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


def test_coverage_contract_rejects_inconsistent_exact_all(tmp_path: Path) -> None:
    bundle = _bundle()
    bundle["coverage"]["denominator"]["count"] += 1
    with pytest.raises(ValueError, match="exact_all"):
        _compile(tmp_path, bundle)


def test_interruption_resumes_and_two_runs_reach_byte_fixed_point(tmp_path: Path) -> None:
    bundle = _bundle()
    spine, compiler, result = _compile(tmp_path, bundle, max_children=2)
    assert not result.complete
    assert result.processed_children == 2
    first_cursor = json.loads(result.cursor_path.read_text())
    assert first_cursor["next_child"] == 2
    assert len(first_cursor["state"]["nodes"]) == 2

    while not result.complete:
        result = compiler.compile(
            bundle,
            output_dir=tmp_path / "output",
            cursor_path=tmp_path / "cursor.json",
            max_children=2,
        )

    public_before = result.public_path.read_bytes()
    detail_before = result.detail_path.read_bytes()
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
    assert fixed.cursor_path.read_bytes() == cursor_before
    assert spine.path.read_bytes() == events_before
    assert len(spine.query(event_type=EventType.TESTAMENT_VERIFIED)) == 1
