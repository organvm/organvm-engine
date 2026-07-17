"""Bounded Engine owner commands for Limen's distill and render stages."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from organvm_engine.corpus.governance_lineage import content_digest
from organvm_engine.events.spine import EventSpine
from organvm_engine.testament.governance_cadence_contract import (
    DISTILL_CONTRACT,
    DISTILL_OUTPUT_NAMES,
    DISTILL_PROJECTION_NAME,
    OWNER_REFERENCE,
    RENDER_CONTRACT,
    RENDER_OUTPUT_NAMES,
    RENDER_PROJECTION_NAME,
    DirectArtifactPaths,
    EngineCadenceError,
    artifact_descriptors,
    bounded_unit_count,
    build_projection,
    cadence_runtime,
    canonical_document,
    direct_input_digest,
    distill_readiness,
    load_direct_bundle,
    proof_child,
    validate_candidate_outputs,
    validate_owner_reference,
    validate_render_outputs,
    validate_snapshot_digest,
    write_metrics,
)
from organvm_engine.testament.governance_compiler import compile_candidate_testament
from organvm_engine.testament.iceberg_atlas import (
    IcebergAtlasCompiler,
    ReceiptIdentity,
)


def _write_if_changed(path: Path, content: bytes) -> bool:
    try:
        if path.read_bytes() == content:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    return True


def _copy_owner_outputs(source: Path, target: Path, names: Sequence[str]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in names:
        _write_if_changed(target / name, (source / name).read_bytes())


def _assert_exact_outputs(source: Path, target: Path, names: Sequence[str]) -> None:
    for name in names:
        try:
            if (source / name).read_bytes() != (target / name).read_bytes():
                raise EngineCadenceError(
                    f"proof output differs from governed Engine artifact {name}",
                )
        except OSError as exc:
            raise EngineCadenceError(
                f"proof cannot read governed Engine artifact {name}",
            ) from exc


def _paths(args: argparse.Namespace, *, render: bool) -> DirectArtifactPaths:
    return DirectArtifactPaths(
        source_envelopes=args.source_envelopes.resolve(),
        normalized_events=args.normalized_events.resolve(),
        lineage_graph=args.lineage_graph.resolve(),
        assertion_evidence=args.assertion_evidence.resolve(),
        coverage=args.coverage.resolve(),
        ideal_form_register=args.ideal_form_register.resolve(),
        governance_testament=args.governance_testament.resolve(),
        node_self_image_set=args.node_self_image_set.resolve() if render else None,
    )


def _child(
    *,
    child_id: str,
    input_digest: str,
    output_dir: Path,
    names: Sequence[str],
) -> dict[str, str]:
    return {
        "child_id": child_id,
        "status": "completed",
        "input_digest": input_digest,
        "output_digest": content_digest(artifact_descriptors(output_dir, names)),
    }


def run_distill(args: argparse.Namespace) -> None:
    runtime = cadence_runtime("distill")
    snapshot_digest = validate_snapshot_digest(args.snapshot_digest)
    owner_reference = validate_owner_reference(args.owner_reference)
    paths = _paths(args, render=False)
    bundle = load_direct_bundle(
        paths,
        snapshot_id=runtime.snapshot_id,
        snapshot_at=runtime.snapshot_at,
        snapshot_digest=snapshot_digest,
        require_ratified=False,
    )
    bounded_units = bounded_unit_count(bundle, render=False)
    if bounded_units > runtime.max_items:
        raise EngineCadenceError(
            f"distill denominator {bounded_units} exceeds LIMEN_GOV_MAX_ITEMS",
        )
    input_digest = direct_input_digest(
        paths,
        runtime,
        snapshot_digest=snapshot_digest,
        owner_reference=owner_reference,
    )
    output_dir = args.output_dir.resolve()
    governed_names = (*DISTILL_OUTPUT_NAMES, DISTILL_PROJECTION_NAME)
    with tempfile.TemporaryDirectory(prefix="engine-governance-distill-") as root:
        proof_dir = Path(root)
        result = compile_candidate_testament(
            bundle,
            output_dir=proof_dir,
            max_units=runtime.max_items,
        )
        readiness = distill_readiness(bundle, result.receipt)
        projection = build_projection(
            contract_name=DISTILL_CONTRACT,
            stage="distill",
            runtime=runtime,
            snapshot_digest=snapshot_digest,
            owner_reference=owner_reference,
            input_digest=input_digest,
            artifacts=artifact_descriptors(proof_dir, DISTILL_OUTPUT_NAMES),
            readiness=readiness,
            bounded_units=bounded_units,
        )
        (proof_dir / DISTILL_PROJECTION_NAME).write_bytes(canonical_document(projection))
        validate_candidate_outputs(
            bundle=bundle,
            output_dir=proof_dir,
            projection_path=proof_dir / DISTILL_PROJECTION_NAME,
            paths=paths,
            runtime=runtime,
            snapshot_digest=snapshot_digest,
            owner_reference=owner_reference,
        )
        if runtime.proof_mode:
            _assert_exact_outputs(proof_dir, output_dir, governed_names)
        else:
            _copy_owner_outputs(proof_dir, output_dir, governed_names)

    child = _child(
        child_id=f"engine:distill:{runtime.snapshot_id}",
        input_digest=input_digest,
        output_dir=output_dir,
        names=governed_names,
    )
    if runtime.proof_mode:
        child = proof_child(
            runtime=runtime,
            child_id=child["child_id"],
            input_digest=child["input_digest"],
            output_digest=child["output_digest"],
        )
    write_metrics(runtime, child, emitted_events=0)


def _line_count(path: Path) -> int:
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


def _render_in_temporary(
    *,
    bundle: Mapping[str, Any],
    output_dir: Path,
    existing_event_spine: Path,
    max_items: int,
    owner_reference: str,
) -> int:
    event_path = output_dir / RENDER_OUTPUT_NAMES[4]
    if existing_event_spine.is_file():
        event_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(existing_event_spine, event_path)
    else:
        event_path.parent.mkdir(parents=True, exist_ok=True)
        event_path.write_bytes(b"")
    before_events = _line_count(event_path)
    compiler = IcebergAtlasCompiler(
        EventSpine(path=event_path, max_chain_bytes=0),
        receipt_identity=ReceiptIdentity(
            actor="governance-cadence",
            source_organ="ORGAN-IV",
            source_repo=owner_reference,
        ),
    )
    result = compiler.compile(
        bundle,
        output_dir=output_dir,
        cursor_path=output_dir / RENDER_OUTPUT_NAMES[3],
        max_children=max_items,
        strict=False,
    )
    if not result.complete:
        raise EngineCadenceError("Atlas render did not complete within LIMEN_GOV_MAX_ITEMS")
    return _line_count(event_path) - before_events


def run_render(args: argparse.Namespace) -> None:
    runtime = cadence_runtime("render")
    snapshot_digest = validate_snapshot_digest(args.snapshot_digest)
    owner_reference = validate_owner_reference(args.owner_reference)
    paths = _paths(args, render=True)
    bundle = load_direct_bundle(
        paths,
        snapshot_id=runtime.snapshot_id,
        snapshot_at=runtime.snapshot_at,
        snapshot_digest=snapshot_digest,
        require_ratified=True,
    )
    bounded_units = bounded_unit_count(bundle, render=True)
    if bounded_units > runtime.max_items:
        raise EngineCadenceError(
            f"render denominator {bounded_units} exceeds LIMEN_GOV_MAX_ITEMS",
        )
    input_digest = direct_input_digest(
        paths,
        runtime,
        snapshot_digest=snapshot_digest,
        owner_reference=owner_reference,
    )
    output_dir = args.output_dir.resolve()
    governed_names = (*RENDER_OUTPUT_NAMES, RENDER_PROJECTION_NAME)
    with tempfile.TemporaryDirectory(prefix="engine-governance-render-") as root:
        proof_dir = Path(root)
        emitted_events = _render_in_temporary(
            bundle=bundle,
            output_dir=proof_dir,
            existing_event_spine=output_dir / RENDER_OUTPUT_NAMES[4],
            max_items=runtime.max_items,
            owner_reference=owner_reference,
        )
        receipt = json_object(proof_dir / RENDER_OUTPUT_NAMES[2])
        readiness_value = receipt.get("readiness")
        if not isinstance(readiness_value, Mapping):
            raise EngineCadenceError("Atlas receipt readiness is missing")
        projection = build_projection(
            contract_name=RENDER_CONTRACT,
            stage="render",
            runtime=runtime,
            snapshot_digest=snapshot_digest,
            owner_reference=owner_reference,
            input_digest=input_digest,
            artifacts=artifact_descriptors(proof_dir, RENDER_OUTPUT_NAMES),
            readiness=readiness_value,
            bounded_units=bounded_units,
        )
        (proof_dir / RENDER_PROJECTION_NAME).write_bytes(canonical_document(projection))
        validate_render_outputs(
            bundle=bundle,
            output_dir=proof_dir,
            projection_path=proof_dir / RENDER_PROJECTION_NAME,
            paths=paths,
            runtime=runtime,
            snapshot_digest=snapshot_digest,
            owner_reference=owner_reference,
        )
        if runtime.proof_mode:
            if emitted_events != 0:
                raise EngineCadenceError("proof render emitted a new verified Atlas event")
            _assert_exact_outputs(proof_dir, output_dir, governed_names)
        else:
            _copy_owner_outputs(proof_dir, output_dir, governed_names)

    child = _child(
        child_id=f"engine:render:{runtime.snapshot_id}",
        input_digest=input_digest,
        output_dir=output_dir,
        names=governed_names,
    )
    if runtime.proof_mode:
        child = proof_child(
            runtime=runtime,
            child_id=child["child_id"],
            input_digest=child["input_digest"],
            output_digest=child["output_digest"],
        )
    write_metrics(runtime, child, emitted_events=emitted_events)


def json_object(path: Path) -> dict[str, Any]:
    import json

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EngineCadenceError(f"{path.name} must contain a valid JSON object") from exc
    if not isinstance(value, dict):
        raise EngineCadenceError(f"{path.name} must contain a JSON object")
    return value


def _common_arguments(parser: argparse.ArgumentParser, *, render: bool) -> None:
    parser.add_argument("--source-envelopes", type=Path, required=True)
    parser.add_argument("--normalized-events", type=Path, required=True)
    parser.add_argument("--lineage-graph", type=Path, required=True)
    parser.add_argument("--assertion-evidence", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--ideal-form-register", type=Path, required=True)
    parser.add_argument("--governance-testament", type=Path, required=True)
    if render:
        parser.add_argument("--node-self-image-set", type=Path, required=True)
    parser.add_argument("--snapshot-digest", required=True)
    parser.add_argument("--owner-reference", default=OWNER_REFERENCE)
    parser.add_argument("--output-dir", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run bounded Engine governance cadence owner stages.",
    )
    subparsers = parser.add_subparsers(dest="stage", required=True)
    distill = subparsers.add_parser("distill")
    _common_arguments(distill, render=False)
    distill.set_defaults(handler=run_distill)
    render = subparsers.add_parser("render")
    _common_arguments(render, render=True)
    render.set_defaults(handler=run_render)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.handler(args)
    except (EngineCadenceError, ValueError) as exc:
        raise SystemExit(f"engine governance cadence failed: {exc}") from exc
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess tests
    raise SystemExit(main())
