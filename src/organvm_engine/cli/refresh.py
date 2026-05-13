"""CLI command: organvm refresh — unified metrics + variable binding refresh."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from organvm_engine.registry.loader import load_registry


def cmd_refresh(args: argparse.Namespace) -> int:
    from organvm_engine.metrics.calculator import compute_metrics, write_metrics
    from organvm_engine.metrics.vars import build_vars, resolve_targets_from_manifest, write_vars
    from organvm_engine.paths import resolve_workspace as _resolve_workspace
    from organvm_engine.paths import workspace_root_candidates

    dry_run = args.dry_run
    prefix = "[DRY RUN] " if dry_run else ""
    skip_context = getattr(args, "skip_context", False)
    skip_organism = getattr(args, "skip_organism", False)
    skip_legacy = getattr(args, "skip_legacy", False)
    skip_plans = getattr(args, "skip_plans", False)
    skip_sop = getattr(args, "skip_sop", False)

    registry = load_registry(args.registry)
    workspace = _resolve_workspace(args)
    candidates = workspace_root_candidates(primary=workspace)
    corpus_root = Path(args.registry).parent

    # Step 1: Compute metrics
    computed = compute_metrics(registry, workspace=workspace, candidates=candidates)
    metrics_path = corpus_root / "system-metrics.json"

    if not dry_run:
        write_metrics(computed, metrics_path)

    print(f"{prefix}[1/10] Metrics calculated -> {metrics_path}")
    print(f"  Repos: {computed['total_repos']} ({computed['active_repos']} ACTIVE)")

    # Step 2: Build + write system-vars.json
    # Load metrics back (includes manual section)
    if metrics_path.exists():
        with metrics_path.open() as f:
            metrics = json.load(f)
    else:
        metrics = {"computed": computed, "manual": {}}

    variables = build_vars(metrics, registry)
    vars_path = corpus_root / "system-vars.json"

    if not dry_run:
        write_vars(variables, vars_path)

    print(f"{prefix}[2/10] Variables manifest -> {vars_path} ({len(variables)} vars)")

    # Step 2.5: Sync variables + metrics into ontologia (best-effort)
    try:
        from ontologia.entity.identity import EntityType
        from ontologia.registry.store import open_store

        from organvm_engine.pulse.variable_bridge import sync_all as _var_sync

        _store = open_store()
        _name_to_rkey: dict[str, str] = {}
        for _rk, _od in registry.get("organs", {}).items():
            _on = _od.get("name", "")
            if _on:
                _name_to_rkey[_on.lower()] = _rk

        _omap: dict[str, str] = {}
        for _ent in _store.list_entities(entity_type=EntityType.ORGAN):
            _nr = _store.current_name(_ent.uid)
            if _nr:
                _rk2 = _name_to_rkey.get(_nr.display_name.lower())
                if _rk2:
                    _omap[_rk2] = _ent.uid

        _vr = _var_sync(_store, variables, organ_entity_map=_omap or None)
        if not dry_run:
            _store.save()
        print(
            f"{prefix}[2½/10] Ontologia sync: "
            f"{_vr.variables_set} vars, {_vr.metrics_registered} metrics, "
            f"{_vr.observations_recorded} observations",
        )
    except ImportError:
        print(f"{prefix}[2½/10] Ontologia sync skipped (not installed)")
    except Exception as e:
        print(f"{prefix}[2½/10] Ontologia sync error: {e}", file=sys.stderr)

    # Step 2.75: Build system snapshot for portal consumption
    try:
        from organvm_engine.metrics.snapshot import build_system_snapshot, write_system_snapshot
        snapshot = build_system_snapshot(
            registry, computed, workspace=workspace, metrics_full=metrics,
        )
        snapshot_path = corpus_root / "system-snapshot.json"
        if not dry_run:
            write_system_snapshot(snapshot, snapshot_path)
        print(
            f"{prefix}[2¾/10] System snapshot -> {snapshot_path} "
            f"({len(snapshot.get('organs', []))} organs, "
            f"{snapshot.get('system', {}).get('total_repos', 0)} repos)",
        )
    except Exception as e:
        print(f"{prefix}[2¾/10] Snapshot error: {e}", file=sys.stderr)

    # Step 3: Resolve variable bindings
    vars_targets_path = corpus_root / "vars-targets.yaml"
    if vars_targets_path.exists():
        result = resolve_targets_from_manifest(variables, vars_targets_path, dry_run=dry_run)
        print(
            f"{prefix}[3/10] Variables resolved: "
            f"{result.total_replacements} replacement(s) in "
            f"{result.files_changed}/{result.files_scanned} file(s)",
        )
        if result.unknown_keys:
            print(f"  WARNING: unknown keys: {', '.join(result.unknown_keys)}")
        for d in result.details[:10]:
            print(f"    {d}")
        if len(result.details) > 10:
            print(f"    ... and {len(result.details) - 10} more")
    else:
        print(f"{prefix}[3/10] No vars-targets.yaml found, skipping variable resolution")
        result = None

    # Step 4: Legacy regex propagation
    if not skip_legacy:
        from organvm_engine.metrics.propagator import (
            propagate_cross_repo,
            propagate_metrics,
        )

        manifest_path = corpus_root / "metrics-targets.yaml"
        if manifest_path.exists():
            legacy_result = propagate_cross_repo(
                metrics, manifest_path, corpus_root, dry_run=dry_run, registry=registry,
            )
            print(
                f"{prefix}[4/10] Legacy propagation: "
                f"{legacy_result.replacements} replacement(s) in "
                f"{legacy_result.files_changed} file(s), "
                f"{legacy_result.json_copies} JSON copies",
            )
        else:
            # Corpus-only fallback
            whitelist_globs = [
                "README.md", "CLAUDE.md",
                "applications/*.md", "applications/shared/*.md",
                "docs/applications/*.md",
                "docs/essays/09-ai-conductor-methodology.md",
                "docs/operations/*.md",
            ]
            files: list[Path] = []
            for pattern in whitelist_globs:
                files.extend(sorted(corpus_root.glob(pattern)))
            seen: set[Path] = set()
            unique = [f for f in files if f not in seen and not seen.add(f)]  # type: ignore[func-returns-value]
            legacy_result = propagate_metrics(metrics, unique, dry_run=dry_run)
            print(
                f"{prefix}[4/10] Legacy propagation (corpus-only): "
                f"{legacy_result.replacements} replacement(s)",
            )
    else:
        print(f"{prefix}[4/10] Legacy propagation skipped")

    # Step 5: JSON copies (portfolio)
    if not skip_legacy:
        # Already handled in step 4 if cross-repo
        print(f"{prefix}[5/10] JSON copies (included in step 4)")
    else:
        print(f"{prefix}[5/10] JSON copies skipped")

    # Step 6: Context sync
    if not skip_context:
        try:
            from organvm_engine.contextmd.sync import sync_all

            if workspace:
                sync_all(workspace=workspace, dry_run=dry_run)
                print(f"{prefix}[6/10] Context sync complete")
            else:
                print(f"{prefix}[6/10] Context sync skipped (no workspace)")
        except Exception as e:
            print(f"{prefix}[6/10] Context sync error: {e}", file=sys.stderr)
    else:
        print(f"{prefix}[6/10] Context sync skipped")

    # Step 7: Organism snapshot
    if not skip_organism:
        try:
            from organvm_engine.metrics.organism import compute_organism

            compute_organism(registry, workspace=workspace)
            print(
                f"{prefix}[7/10] Organism computed "
                f"(use 'organvm organism snapshot --write' to persist)",
            )
        except Exception as e:
            print(f"{prefix}[7/10] Organism error: {e}", file=sys.stderr)
    else:
        print(f"{prefix}[7/10] Organism skipped")

    # Step 8: Plan hygiene check
    if not skip_plans:
        try:
            from organvm_engine.plans.hygiene import compute_sprawl, sweep_candidates
            from organvm_engine.plans.index import build_plan_index

            index = build_plan_index(workspace=workspace)
            candidates = sweep_candidates(index.entries)
            sprawl = compute_sprawl(index.entries)
            if candidates:
                print(
                    f"{prefix}[8/10] Plan hygiene: {len(candidates)} archival "
                    f"candidates ({sprawl.sprawl_level})",
                )
            else:
                print(
                    f"{prefix}[8/10] Plan hygiene: clean ({sprawl.total_active} active)",
                )
        except Exception as e:
            print(f"{prefix}[8/10] Plan hygiene error: {e}", file=sys.stderr)
    else:
        print(f"{prefix}[8/10] Plan hygiene skipped")

    # Step 9: SOP inventory check
    if not skip_sop:
        try:
            from organvm_engine.sop.discover import discover_sops
            from organvm_engine.sop.inventory import audit_sops

            if workspace:
                sop_entries = discover_sops(workspace=workspace)
                sop_result = audit_sops(sop_entries)
                tracked_total = len(sop_result.tracked) + len(sop_result.reference_copy)
                if sop_result.untracked:
                    print(
                        f"{prefix}[9/10] SOP check: {len(sop_result.untracked)} untracked",
                    )
                    for e in sop_result.untracked:
                        print(f"    {e.org}/{e.repo}/{e.filename}")
                else:
                    print(f"{prefix}[9/10] SOP check: {tracked_total} tracked, 0 untracked")
            else:
                print(f"{prefix}[9/10] SOP check skipped (no workspace)")
        except Exception as e:
            print(f"{prefix}[9/10] SOP check error: {e}", file=sys.stderr)
    else:
        print(f"{prefix}[9/10] SOP check skipped")

    # Step 10: Atoms pipeline + fanout
    skip_atoms = getattr(args, "skip_atoms", False)
    if not skip_atoms:
        try:
            from organvm_engine.atoms.pipeline import run_pipeline
            from organvm_engine.atoms.rollup import build_rollups, write_rollups
            from organvm_engine.paths import atoms_dir

            pipe_result = run_pipeline(dry_run=dry_run)
            print(
                f"{prefix}[10/10] Atoms: {pipe_result.atomize_count} tasks, "
                f"{pipe_result.narrate_count} prompts, {pipe_result.link_count} links",
            )

            if not dry_run:
                rollups = build_rollups(atoms_dir())
                if workspace is not None:
                    write_rollups(rollups, workspace, dry_run=False)
                    print(f"  Fanout: {len(rollups)} organ rollups written")
                else:
                    print("  Fanout skipped (no workspace)")
        except Exception as e:
            print(f"{prefix}[10/10] Atoms error: {e}", file=sys.stderr)
    else:
        print(f"{prefix}[10/10] Atoms skipped")

    # Summary
    var_count = result.total_replacements if result else 0
    var_files = result.files_changed if result else 0
    print(f"\n{prefix}Done. {var_count} variables resolved in {var_files} files.")

    return 0
