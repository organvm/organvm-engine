"""Independent read-only predicates for Engine cadence artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from organvm_engine.testament.governance_cadence_contract import (
    DISTILL_PROJECTION_NAME,
    OWNER_REFERENCE,
    RENDER_PROJECTION_NAME,
    DirectArtifactPaths,
    EngineCadenceError,
    bounded_unit_count,
    cadence_runtime,
    load_direct_bundle,
    validate_candidate_outputs,
    validate_owner_reference,
    validate_render_outputs,
    validate_snapshot_digest,
)


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


def assert_distill_predicate(args: argparse.Namespace) -> None:
    runtime = cadence_runtime("distill", predicate=True)
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
    if bounded_unit_count(bundle, render=False) > runtime.max_items:
        raise EngineCadenceError("distill predicate denominator exceeds LIMEN_GOV_MAX_ITEMS")
    output_dir = args.output_dir.resolve()
    validate_candidate_outputs(
        bundle=bundle,
        output_dir=output_dir,
        projection_path=output_dir / DISTILL_PROJECTION_NAME,
        paths=paths,
        runtime=runtime,
        snapshot_digest=snapshot_digest,
        owner_reference=owner_reference,
    )


def assert_render_predicate(args: argparse.Namespace) -> None:
    runtime = cadence_runtime("render", predicate=True)
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
    if bounded_unit_count(bundle, render=True) > runtime.max_items:
        raise EngineCadenceError("render predicate denominator exceeds LIMEN_GOV_MAX_ITEMS")
    output_dir = args.output_dir.resolve()
    validate_render_outputs(
        bundle=bundle,
        output_dir=output_dir,
        projection_path=output_dir / RENDER_PROJECTION_NAME,
        paths=paths,
        runtime=runtime,
        snapshot_digest=snapshot_digest,
        owner_reference=owner_reference,
    )


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
        description="Verify Engine governance cadence outputs without mutation.",
    )
    subparsers = parser.add_subparsers(dest="stage", required=True)
    distill = subparsers.add_parser("distill")
    _common_arguments(distill, render=False)
    distill.set_defaults(handler=assert_distill_predicate)
    render = subparsers.add_parser("render")
    _common_arguments(render, render=True)
    render.set_defaults(handler=assert_render_predicate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.handler(args)
    except (EngineCadenceError, ValueError) as exc:
        raise SystemExit(f"engine governance cadence predicate failed: {exc}") from exc
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess tests
    raise SystemExit(main())
