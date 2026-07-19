"""Contract tests for Engine's real Limen cadence owner adapters."""

from __future__ import annotations

import json
from argparse import Namespace
from copy import deepcopy
from pathlib import Path

import pytest
from test_governance_atlas import _bundle

from organvm_engine.corpus.governance_lineage import content_digest
from organvm_engine.testament.governance_cadence import run_distill, run_render
from organvm_engine.testament.governance_cadence_contract import (
    DISTILL_OUTPUT_NAMES,
    DISTILL_PROJECTION_NAME,
    RENDER_OUTPUT_NAMES,
    RENDER_PROJECTION_NAME,
    EngineCadenceError,
)
from organvm_engine.testament.governance_cadence_predicate import (
    assert_distill_predicate,
    assert_render_predicate,
)

PREDECESSOR_DIGEST = "sha256:" + "a" * 64


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _direct_inputs(root: Path, bundle: dict, *, render: bool) -> Namespace:
    root.mkdir(parents=True, exist_ok=True)
    source_envelopes = root / "source-envelope.v1.jsonl"
    normalized_events = root / "normalized-events.v1.jsonl"
    lineage = root / "lineage-graph.v1.json"
    assertions = root / "assertion-evidence.v1.json"
    coverage = root / "coverage-receipt.v1.json"
    ideals = root / "ideal-form-register.v1.json"
    testament = root / "governance-testament.v1.json"
    self_images = root / "node-self-image-set.v1.json"
    _write_jsonl(source_envelopes, bundle["source_envelopes"])
    _write_jsonl(normalized_events, bundle["normalized_events"])
    _write_json(lineage, bundle["lineage_graph"])
    _write_json(assertions, bundle["assertion_evidence"])
    _write_json(coverage, bundle["coverage"])
    _write_json(ideals, bundle["ideal_form_register"])
    _write_json(testament, bundle["governance_testament"])
    if render:
        _write_json(self_images, bundle["node_self_image_set"])
    return Namespace(
        source_envelopes=source_envelopes,
        normalized_events=normalized_events,
        lineage_graph=lineage,
        assertion_evidence=assertions,
        coverage=coverage,
        ideal_form_register=ideals,
        governance_testament=testament,
        node_self_image_set=self_images if render else None,
        snapshot_digest=bundle["snapshot_digest"],
        owner_reference="repo:fixture/engine",
        output_dir=root / ("render" if render else "distill"),
    )


def _candidate_bundle() -> dict:
    bundle = _bundle()
    bundle["governance_testament"]["status"] = "candidate"
    bundle["governance_testament"].pop("ratification")
    assertion = bundle["assertion_evidence"][0]
    assertion["verification_state"] = "unverified"
    assertion["evidence_references"][1] = {
        "evidence_id": "evidence:reviewed-lineage",
        "independence_group": "reviewed-lineage",
        "evidence_type": "reviewed_lineage",
        "reference": "lineage:fixture",
        "body_hash": content_digest(bundle["lineage_graph"]),
    }
    return bundle


def _blocked_render_bundle() -> dict:
    bundle = _bundle()
    blocker = {
        "source_id": "source-unavailable-export",
        "status": "owner_blocked",
        "accessible": False,
        "owner_reference": "owner:source-export",
        "failed_predicate": "official-export-present",
        "next_action": "Acquire the owner-issued read-only export.",
        "evidence_references": ["owner:source-export"],
    }
    coverage = bundle["coverage"]
    coverage["sources"].append(blocker)
    coverage["denominator"]["count"] += 1
    coverage["counts"]["owner_blocked"] = 1
    coverage["ready"] = False
    coverage["unresolved_blockers"] = [blocker["source_id"]]
    coverage["quarantines"] = []
    coverage["missing_requirements"] = []
    coverage["citation_debt"] = []
    coverage["incomplete_predicates"] = []
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
    return bundle


def _runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stage: str,
    bundle: dict,
    metrics: Path,
    proof: bool = False,
    prior: Path | None = None,
    predicate: bool = False,
    max_items: int = 100,
) -> None:
    monkeypatch.setenv("LIMEN_GOV_STAGE", stage)
    monkeypatch.setenv("LIMEN_GOV_STAGE_ATTEMPT", "1")
    monkeypatch.setenv("LIMEN_GOV_TRAVERSAL", "2" if proof else "1")
    monkeypatch.setenv("LIMEN_GOV_PROOF_MODE", "1" if proof else "0")
    monkeypatch.setenv("LIMEN_GOV_STAGE_METRICS_OUT", str(metrics))
    monkeypatch.setenv("LIMEN_GOV_STAGE_RECEIPTS", str(metrics.parent / "receipts.json"))
    monkeypatch.setenv("LIMEN_GOV_PREDECESSOR_RECEIPT_DIGEST", PREDECESSOR_DIGEST)
    monkeypatch.setenv("LIMEN_GOV_PRIOR_STAGE_RECEIPT", str(prior or ""))
    monkeypatch.setenv("LIMEN_GOV_MAX_ITEMS", str(max_items))
    monkeypatch.setenv("LIMEN_GOV_SNAPSHOT_ID", bundle["snapshot_id"])
    monkeypatch.setenv("LIMEN_GOV_SNAPSHOT_AT", bundle["snapshot_at"])
    if predicate:
        monkeypatch.setenv("LIMEN_GOV_PREDICATE_MODE", "1")
    else:
        monkeypatch.delenv("LIMEN_GOV_PREDICATE_MODE", raising=False)


def _prior_receipt(path: Path, stage: str, bundle: dict, metrics: Path) -> None:
    child_receipts = json.loads(metrics.read_text(encoding="utf-8"))["child_receipts"]
    _write_json(
        path,
        {
            "stage": stage,
            "snapshot_id": bundle["snapshot_id"],
            "child_receipts": child_receipts,
        },
    )


def _output_bytes(root: Path, names: tuple[str, ...]) -> dict[str, bytes]:
    return {name: (root / name).read_bytes() for name in names}


def test_distill_compiles_candidate_then_proves_exact_skipped_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _candidate_bundle()
    args = _direct_inputs(tmp_path, bundle, render=False)
    metrics = tmp_path / "metrics" / "distill.json"
    _runtime(monkeypatch, stage="distill", bundle=bundle, metrics=metrics)

    run_distill(args)

    first_metrics = json.loads(metrics.read_text(encoding="utf-8"))
    projection = json.loads(
        (args.output_dir / DISTILL_PROJECTION_NAME).read_text(encoding="utf-8"),
    )
    candidate = json.loads(
        (args.output_dir / DISTILL_OUTPUT_NAMES[0]).read_text(encoding="utf-8"),
    )
    assert candidate["status"] == "candidate"
    assert "ratification" not in candidate
    assert projection["readiness"]["ready"] is True
    assert first_metrics["emitted_events"] == 0
    assert first_metrics["child_receipts"][0]["status"] == "completed"

    _runtime(
        monkeypatch,
        stage="distill",
        bundle=bundle,
        metrics=metrics,
        predicate=True,
    )
    assert_distill_predicate(args)

    prior = tmp_path / "distill-prior.json"
    _prior_receipt(prior, "distill", bundle, metrics)
    governed_names = (*DISTILL_OUTPUT_NAMES, DISTILL_PROJECTION_NAME)
    before = _output_bytes(args.output_dir, governed_names)
    proof_metrics = tmp_path / "metrics" / "distill-proof.json"
    _runtime(
        monkeypatch,
        stage="distill",
        bundle=bundle,
        metrics=proof_metrics,
        proof=True,
        prior=prior,
    )
    run_distill(args)

    proof = json.loads(proof_metrics.read_text(encoding="utf-8"))
    proof_child = proof["child_receipts"][0]
    assert proof["emitted_events"] == 0
    assert proof_child["status"] == "skipped_completed"
    assert proof_child["prior_receipt_digest"].startswith("sha256:")
    assert _output_bytes(args.output_dir, governed_names) == before


def test_distill_reprojects_exact_candidate_from_ratified_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle()
    args = _direct_inputs(tmp_path, bundle, render=False)
    metrics = tmp_path / "metrics" / "ratified-distill.json"
    _runtime(monkeypatch, stage="distill", bundle=bundle, metrics=metrics)

    run_distill(args)

    candidate = json.loads(
        (args.output_dir / DISTILL_OUTPUT_NAMES[0]).read_text(encoding="utf-8"),
    )
    receipt = json.loads(
        (args.output_dir / DISTILL_OUTPUT_NAMES[1]).read_text(encoding="utf-8"),
    )
    assert candidate["status"] == "candidate"
    assert "ratification" not in candidate
    assert (
        content_digest(candidate)
        == bundle["governance_testament"]["ratification"]["candidate_digest"]
        == receipt["candidate_digest"]
    )
    _runtime(
        monkeypatch,
        stage="distill",
        bundle=bundle,
        metrics=metrics,
        predicate=True,
    )
    assert_distill_predicate(args)


def test_distill_predicate_rejects_candidate_receipt_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _candidate_bundle()
    args = _direct_inputs(tmp_path, bundle, render=False)
    metrics = tmp_path / "metrics.json"
    _runtime(monkeypatch, stage="distill", bundle=bundle, metrics=metrics)
    run_distill(args)
    receipt_path = args.output_dir / DISTILL_OUTPUT_NAMES[1]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["candidate_digest"] = "sha256:" + "0" * 64
    _write_json(receipt_path, receipt)
    _runtime(
        monkeypatch,
        stage="distill",
        bundle=bundle,
        metrics=metrics,
        predicate=True,
    )

    with pytest.raises(EngineCadenceError, match="receipt is inconsistent"):
        assert_distill_predicate(args)


def test_render_materializes_honest_blocked_atlas_and_proves_no_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _blocked_render_bundle()
    args = _direct_inputs(tmp_path, bundle, render=True)
    metrics = tmp_path / "metrics" / "render.json"
    _runtime(monkeypatch, stage="render", bundle=bundle, metrics=metrics)

    run_render(args)

    first_metrics = json.loads(metrics.read_text(encoding="utf-8"))
    projection = json.loads(
        (args.output_dir / RENDER_PROJECTION_NAME).read_text(encoding="utf-8"),
    )
    assert projection["readiness"]["ready"] is False
    assert projection["readiness"]["status"] == "blocked"
    assert "source-unavailable-export" in projection["readiness"]["unresolved_blockers"]
    assert first_metrics["emitted_events"] == 0
    assert (args.output_dir / RENDER_OUTPUT_NAMES[4]).read_bytes() == b""
    public = json.loads((args.output_dir / RENDER_OUTPUT_NAMES[0]).read_text(encoding="utf-8"))
    detail = json.loads((args.output_dir / RENDER_OUTPUT_NAMES[1]).read_text(encoding="utf-8"))
    receipt = json.loads((args.output_dir / RENDER_OUTPUT_NAMES[2]).read_text(encoding="utf-8"))
    assert detail["governance_testament"] == bundle["governance_testament"]
    assert detail["ideal_form_register"] == bundle["ideal_form_register"]
    assert public["ideal_forms"] == [
        ideal["ideal_form_id"] for ideal in bundle["ideal_form_register"]["ideal_forms"]
    ]
    assert (
        receipt["ideal_form_register"]["digest"]
        == bundle["ideal_form_register"]["register_digest"]
    )
    assert {
        "ratified_governance_testament",
        "receipt_backed_ideal_forms",
        "zero_compiler_quarantine",
        "exact_one_self_images",
    }.isdisjoint(receipt["readiness"]["missing_requirements"])

    _runtime(
        monkeypatch,
        stage="render",
        bundle=bundle,
        metrics=metrics,
        predicate=True,
    )
    assert_render_predicate(args)

    prior = tmp_path / "render-prior.json"
    _prior_receipt(prior, "render", bundle, metrics)
    governed_names = (*RENDER_OUTPUT_NAMES, RENDER_PROJECTION_NAME)
    before = _output_bytes(args.output_dir, governed_names)
    proof_metrics = tmp_path / "metrics" / "render-proof.json"
    _runtime(
        monkeypatch,
        stage="render",
        bundle=bundle,
        metrics=proof_metrics,
        proof=True,
        prior=prior,
    )
    run_render(args)

    proof = json.loads(proof_metrics.read_text(encoding="utf-8"))
    assert proof["emitted_events"] == 0
    assert proof["child_receipts"][0]["status"] == "skipped_completed"
    assert _output_bytes(args.output_dir, governed_names) == before


def test_render_resolves_ratification_assertion_artifact_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle()
    bundle["governance_testament"]["ratification"][
        "assertion_evidence_reference"
    ] = "assertion-evidence.v1.json"
    args = _direct_inputs(tmp_path, bundle, render=True)
    metrics = tmp_path / "metrics.json"
    _runtime(monkeypatch, stage="render", bundle=bundle, metrics=metrics)

    run_render(args)

    detail = json.loads(
        (args.output_dir / RENDER_OUTPUT_NAMES[1]).read_text(encoding="utf-8"),
    )
    assert detail["governance_testament"] == bundle["governance_testament"]


def test_render_predicate_rejects_atlas_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _blocked_render_bundle()
    args = _direct_inputs(tmp_path, bundle, render=True)
    metrics = tmp_path / "metrics.json"
    _runtime(monkeypatch, stage="render", bundle=bundle, metrics=metrics)
    run_render(args)
    public_path = args.output_dir / RENDER_OUTPUT_NAMES[0]
    public = json.loads(public_path.read_text(encoding="utf-8"))
    public["snapshot_id"] = "tampered-snapshot"
    _write_json(public_path, public)
    _runtime(
        monkeypatch,
        stage="render",
        bundle=bundle,
        metrics=metrics,
        predicate=True,
    )

    with pytest.raises(EngineCadenceError, match="digest-bound result"):
        assert_render_predicate(args)


def test_ready_render_reuses_exact_verified_event_during_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle()
    args = _direct_inputs(tmp_path, bundle, render=True)
    metrics = tmp_path / "metrics.json"
    _runtime(monkeypatch, stage="render", bundle=bundle, metrics=metrics)
    run_render(args)

    first = json.loads(metrics.read_text(encoding="utf-8"))
    assert first["emitted_events"] == 1
    event_path = args.output_dir / RENDER_OUTPUT_NAMES[4]
    assert len([line for line in event_path.read_text().splitlines() if line]) == 1
    prior = tmp_path / "prior.json"
    _prior_receipt(prior, "render", bundle, metrics)
    governed_names = (*RENDER_OUTPUT_NAMES, RENDER_PROJECTION_NAME)
    before = _output_bytes(args.output_dir, governed_names)
    proof_metrics = tmp_path / "proof.json"
    _runtime(
        monkeypatch,
        stage="render",
        bundle=bundle,
        metrics=proof_metrics,
        proof=True,
        prior=prior,
    )
    run_render(args)

    proof = json.loads(proof_metrics.read_text(encoding="utf-8"))
    assert proof["emitted_events"] == 0
    assert proof["child_receipts"][0]["status"] == "skipped_completed"
    assert _output_bytes(args.output_dir, governed_names) == before


def test_render_refuses_candidate_and_item_limit_is_total_denominator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate_bundle()
    render_args = _direct_inputs(tmp_path / "candidate", candidate, render=True)
    _runtime(
        monkeypatch,
        stage="render",
        bundle=candidate,
        metrics=tmp_path / "candidate-metrics.json",
    )
    with pytest.raises(EngineCadenceError, match="CORPVS-ratified"):
        run_render(render_args)

    distill_args = _direct_inputs(tmp_path / "bounded", candidate, render=False)
    _runtime(
        monkeypatch,
        stage="distill",
        bundle=candidate,
        metrics=tmp_path / "bounded-metrics.json",
        max_items=1,
    )
    with pytest.raises(EngineCadenceError, match="exceeds LIMEN_GOV_MAX_ITEMS"):
        run_distill(distill_args)
    assert not distill_args.output_dir.exists()


def test_proof_fails_closed_after_direct_input_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _candidate_bundle()
    args = _direct_inputs(tmp_path, bundle, render=False)
    metrics = tmp_path / "metrics.json"
    _runtime(monkeypatch, stage="distill", bundle=bundle, metrics=metrics)
    run_distill(args)
    prior = tmp_path / "prior.json"
    _prior_receipt(prior, "distill", bundle, metrics)
    assertions = deepcopy(bundle["assertion_evidence"])
    assertions[0]["statement"] = "A changed assertion cannot reuse the prior child receipt."
    _write_json(args.assertion_evidence, assertions)
    proof_metrics = tmp_path / "proof.json"
    _runtime(
        monkeypatch,
        stage="distill",
        bundle=bundle,
        metrics=proof_metrics,
        proof=True,
        prior=prior,
    )

    with pytest.raises(
        EngineCadenceError,
        match="proof output differs|changed a completed child",
    ):
        run_distill(args)
