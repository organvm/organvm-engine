"""Testament CLI commands — the system's generative self-portrait."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory


def cmd_testament_status(args: argparse.Namespace) -> int:
    """Show testament system status — what the system can and has produced."""
    from organvm_engine.testament.catalog import catalog_summary, load_catalog
    from organvm_engine.testament.manifest import (
        MODULE_SOURCES,
        ORGAN_OUTPUT_MATRIX,
        all_artifact_types,
    )

    as_json = getattr(args, "json", False)
    base_dir = _resolve_base_dir(args)

    types = all_artifact_types()
    catalog = load_catalog(base_dir)
    summary = catalog_summary(catalog)

    if as_json:
        print(json.dumps({
            "registered_types": len(types),
            "organ_profiles": len(ORGAN_OUTPUT_MATRIX),
            "source_modules": len(MODULE_SOURCES),
            "catalog": {
                "total": summary.total,
                "by_modality": summary.by_modality,
                "by_organ": summary.by_organ,
                "latest": summary.latest_timestamp,
            },
        }, indent=2))
        return 0

    print("\n  ORGANVM Testament — Generative Self-Portrait")
    print(f"  {'═' * 48}")
    print(f"\n  Registered artifact types:  {len(types)}")
    print(f"  Organ output profiles:     {len(ORGAN_OUTPUT_MATRIX)}")
    print(f"  Source modules:            {len(MODULE_SOURCES)}")
    print(f"\n  Catalog: {summary.total} artifacts produced")
    if summary.latest_timestamp:
        print(f"  Latest:  {summary.latest_timestamp[:19]}")
    if summary.by_modality:
        print("\n  By modality:")
        for mod, count in sorted(summary.by_modality.items()):
            print(f"    {mod:<16} {count}")
    print()
    return 0


def cmd_testament_render(args: argparse.Namespace) -> int:
    """Render testament artifacts from live system data."""
    from organvm_engine.testament.aesthetic import load_taste
    from organvm_engine.testament.pipeline import render_all, render_organ

    organ = getattr(args, "organ", None)
    all_repos = getattr(args, "all_repos", False)
    dry_run = getattr(args, "dry_run", True)
    write = getattr(args, "write", False)
    if write:
        dry_run = False

    output_dir = _resolve_output_dir(args)
    registry_path = getattr(args, "registry", None)
    if registry_path:
        registry_path = Path(registry_path)

    load_taste()  # validates taste.yaml is parseable before rendering

    if all_repos:
        return _render_all_repos(output_dir, dry_run, registry_path)

    if organ:
        results = render_organ(
            organ, output_dir, dry_run=dry_run, registry_path=registry_path,
        )
    else:
        results = render_all(
            output_dir, dry_run=dry_run, registry_path=registry_path,
        )

    succeeded = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    if dry_run:
        print(f"\n  [dry-run] Would produce {len(results)} artifacts:")
        for r in results:
            organ_label = r.artifact.organ or "system"
            print(f"    {r.artifact.modality.value:<14} {organ_label:<8} {r.artifact.title}")
        print("\n  Run with --write to produce artifacts.\n")
    else:
        print(f"\n  Produced {len(succeeded)} artifacts" +
              (f" ({len(failed)} failed)" if failed else ""))
        for r in succeeded:
            print(f"    ✓ {r.artifact.path}")
        for r in failed:
            print(f"    ✗ {r.artifact.title}: {r.error}")
        print()

    return 1 if failed and not dry_run else 0


def cmd_testament_cascade(args: argparse.Namespace) -> int:
    """Execute the full feedback network — renderers feed each other."""
    from organvm_engine.testament.network import cascade, network_summary

    execute = getattr(args, "write", False)
    as_json = getattr(args, "json", False)
    registry_path = getattr(args, "registry", None)
    if registry_path:
        registry_path = Path(registry_path)

    summary = network_summary()
    results = cascade({}, execute=execute, registry_path=registry_path)

    if as_json:
        import json as json_mod
        print(json_mod.dumps({"summary": summary, "results": results}, indent=2, default=str))
        return 0

    print(f"\n  Testament Cascade — {summary['nodes']} nodes, "
          f"{summary['feedback_edges']} feedback edges")
    print(f"  Execution order: {' → '.join(summary['execution_order'])}")
    print(f"  {'═' * 60}")

    for name, data in results.items():
        if execute:
            success = "✓" if data.get("success") else "✗"
            content_len = data.get("content_length", 0)
            shapes = data.get("shapes_produced", [])
            inputs = data.get("inputs_received", {})
            received = sum(1 for v in inputs.values() if v)
            total_in = len(inputs)
            err = data.get("error", "")
            print(f"  {success} {name:<12} {content_len:>6} bytes  "
                  f"in:{received}/{total_in}  out:{len(shapes)}"
                  f"{'  ERROR: ' + err if err else ''}")
        else:
            avail = data.get("inputs_available", {})
            received = sum(1 for v in avail.values() if v)
            total_in = len(avail)
            produces = data.get("produces", [])
            print(f"  ○ {name:<12} would produce {len(produces)} shapes  "
                  f"needs:{total_in} inputs")

    if not execute:
        print("\n  Run with --write to execute the cascade.\n")
    else:
        ok = sum(1 for d in results.values() if d.get("success"))
        fail = sum(1 for d in results.values() if not d.get("success"))
        print(f"\n  {ok} succeeded, {fail} failed.\n")

    return 0


def cmd_testament_catalog(args: argparse.Namespace) -> int:
    """List all produced testament artifacts."""
    from organvm_engine.testament.catalog import load_catalog

    as_json = getattr(args, "json", False)
    organ = getattr(args, "organ", None)
    base_dir = _resolve_base_dir(args)
    catalog = load_catalog(base_dir)

    if organ:
        catalog = [a for a in catalog if a.organ == organ]

    if as_json:
        import dataclasses
        print(json.dumps([dataclasses.asdict(a) for a in catalog], indent=2, default=str))
        return 0

    if not catalog:
        print("\n  No testament artifacts found. Run `organvm testament render --write`.\n")
        return 0

    print(f"\n  Testament Catalog — {len(catalog)} artifacts")
    print(f"\n  {'Date':<12} {'Modality':<14} {'Organ':<8} {'Format':<8} Title")
    print(f"  {'─' * 75}")
    for a in catalog:
        date = a.timestamp[:10] if a.timestamp else "unknown"
        organ_label = a.organ or "system"
        mod = a.modality.value if hasattr(a.modality, 'value') else str(a.modality)
        fmt = a.format.value if hasattr(a.format, 'value') else str(a.format)
        print(f"  {date:<12} {mod:<14} {organ_label:<8} {fmt:<8} {a.title}")
    print()
    return 0


def cmd_testament_gallery(args: argparse.Namespace) -> int:
    """Generate a static HTML gallery of all testament artifacts."""
    from organvm_engine.testament.aesthetic import load_taste
    from organvm_engine.testament.catalog import load_catalog
    from organvm_engine.testament.renderers.html import render_gallery_page

    dry_run = not getattr(args, "write", False)
    output_dir = _resolve_output_dir(args)
    base_dir = _resolve_base_dir(args)

    catalog = load_catalog(base_dir)
    aesthetic = load_taste()

    palette = {
        "primary": aesthetic.palette.primary,
        "secondary": aesthetic.palette.secondary,
        "accent": aesthetic.palette.accent,
        "background": aesthetic.palette.background,
        "text": aesthetic.palette.text,
        "muted": aesthetic.palette.muted,
    }

    artifact_dicts = []
    for a in catalog:
        mod = a.modality.value if hasattr(a.modality, 'value') else str(a.modality)
        fmt = a.format.value if hasattr(a.format, 'value') else str(a.format)
        artifact_dicts.append({
            "title": a.title,
            "modality": mod,
            "format": fmt,
            "path": a.path,
            "timestamp": a.timestamp,
            "organ": a.organ or "system",
        })

    html = render_gallery_page(artifact_dicts, palette=palette)
    gallery_path = output_dir / "index.html"

    if dry_run:
        print(f"\n  [dry-run] Would write gallery to {gallery_path}")
        print(f"  {len(catalog)} artifacts, {len(html)} bytes")
        print("\n  Run with --write to generate.\n")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    gallery_path.write_text(html)
    print(f"\n  Gallery written to {gallery_path}")
    print(f"  {len(catalog)} artifacts indexed.\n")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_all_repos(
    output_dir: Path, dry_run: bool, registry_path: Path | None,
) -> int:
    """Render SVG identity cards for all repos in the registry."""
    from organvm_engine.organ_config import ORGANS
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.testament.aesthetic import load_taste
    from organvm_engine.testament.renderers.svg import Palette as SvgPalette
    from organvm_engine.testament.renderers.svg import render_organ_card

    taste = load_taste()
    palette = SvgPalette(
        primary=taste.palette.primary, secondary=taste.palette.secondary,
        accent=taste.palette.accent, background=taste.palette.background,
        text=taste.palette.text, muted=taste.palette.muted,
    )

    registry = load_registry(registry_path)
    organs_data = registry.get("organs", {})
    reg_to_cli: dict[str, str] = {}
    for cli_key, meta in ORGANS.items():
        rk = meta.get("registry_key", "")
        if rk:
            reg_to_cli[rk] = cli_key

    repos_dir = output_dir / "repos"
    total = 0

    for reg_key, organ_data in organs_data.items():
        cli_key = reg_to_cli.get(str(reg_key), str(reg_key))
        for _repo in organ_data.get("repositories", []):
            total += 1

    if dry_run:
        print(f"\n  [dry-run] Would render {total} per-repo identity cards")
        print(f"  Output: {repos_dir}")
        print("\n  Run with --write to produce.\n")
        return 0

    repos_dir.mkdir(parents=True, exist_ok=True)
    rendered = 0
    for reg_key, organ_data in organs_data.items():
        cli_key: str = reg_to_cli.get(str(reg_key), str(reg_key))
        for repo in organ_data.get("repositories", []):
            name = repo.get("name", "unknown")
            status = repo.get("promotion_status", repo.get("status", "unknown"))
            tier = repo.get("tier", "standard")

            svg = render_organ_card(
                cli_key, repo_count=1,
                flagship_count=1 if tier == "flagship" else 0,
                status_counts={status: 1}, palette=palette,
                width=350, height=200,
            )
            svg = svg.replace(f"ORGAN {cli_key}", name[:25])

            safe_name = name.replace("/", "-").replace(" ", "-").lower()
            (repos_dir / f"{safe_name}.svg").write_text(svg)
            rendered += 1

    print(f"\n  Rendered {rendered} per-repo identity cards")
    print(f"  Output: {repos_dir}\n")
    return 0


def cmd_testament_play(args: argparse.Namespace) -> int:
    """Render system metrics as sonic parameters and emit OSC messages.

    Produces YAML for BrahmaModBus.sc and a list of OSC message strings
    suitable for piping to SuperCollider's TestamentReceiver.sc.
    """
    from organvm_engine.testament.renderers.sonic import (
        render_osc_messages,
        render_sonic_params,
        render_sonic_yaml,
    )
    from organvm_engine.testament.sources import density_data, omega_data, topology_data

    as_json = getattr(args, "json", False)
    osc_only = getattr(args, "osc", False)
    yaml_only = getattr(args, "yaml", False)
    registry_path = getattr(args, "registry", None)
    if registry_path:
        registry_path = Path(registry_path)

    # Gather live system data
    topo = topology_data(registry_path)
    omega = omega_data(registry_path)
    dens = density_data(registry_path)
    met_ratio = omega["met_count"] / omega["total"] if omega["total"] else 0

    testament = render_sonic_params(
        organ_densities=dens["organ_densities"],
        organ_repo_counts=topo["organ_repo_counts"],
        status_distribution={},
        met_ratio=met_ratio,
        total_repos=topo["total_repos"],
    )

    osc_msgs = render_osc_messages(testament)

    if as_json:
        import dataclasses
        data = dataclasses.asdict(testament)
        data["osc_messages"] = osc_msgs
        print(json.dumps(data, indent=2))
        return 0

    if osc_only:
        for msg in osc_msgs:
            print(msg)
        return 0

    if yaml_only:
        print(render_sonic_yaml(testament))
        return 0

    # Default: show both
    yaml_out = render_sonic_yaml(testament)
    print(yaml_out)
    print("# OSC Messages")
    for msg in osc_msgs:
        print(f"#   {msg}")
    print(f"\n# {len(testament.voices)} voices, "
          f"{testament.rhythm.bpm if testament.rhythm else 120} BPM, "
          f"master {testament.master_amplitude}")
    return 0


def cmd_testament_record_session(args: argparse.Namespace) -> int:
    """Detect self-referential changes between commits and emit testament events.

    Scans ``git diff --name-status`` for:
      - New ``__init__.py`` files  -> MODULE_ADDED events
      - Changes to scorecard files -> SCORECARD_EXPANDED events
      - Changes to ``events/spine.py`` -> VOCABULARY_EXPANDED events
      - Any structural change      -> ARCHITECTURE_CHANGED event (summary)
      - Always emits               -> SESSION_RECORDED event
    """
    import subprocess

    from organvm_engine.events.spine import EventSpine, EventType

    from_commit = getattr(args, "from_commit", "HEAD~1")
    to_commit = getattr(args, "to_commit", "HEAD")
    spine_path = getattr(args, "spine_path", None)
    dry_run = not getattr(args, "write", False)

    # Run git diff --name-status between the two commits
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", from_commit, to_commit],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent.parent.parent.parent,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"  Error running git diff: {exc}")
        return 1

    diff_output = result.stdout.strip()
    if not diff_output:
        print("  No changes detected between commits.")
        return 0

    # Parse the diff output into (status, path) pairs
    changes: list[tuple[str, str]] = []
    for line in diff_output.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            changes.append((parts[0].strip(), parts[1].strip()))

    # Classify changes
    new_modules: list[str] = []
    scorecard_changes: list[str] = []
    vocabulary_changes: list[str] = []
    all_paths: list[str] = []

    for status, path in changes:
        all_paths.append(path)
        if path.endswith("__init__.py") and status.startswith("A"):
            new_modules.append(path)
        if "scorecard" in path.lower():
            scorecard_changes.append(path)
        if "events/spine.py" in path:
            vocabulary_changes.append(path)

    events_to_emit: list[tuple[EventType, str, dict]] = []

    for mod_path in new_modules:
        # Extract module name from the path (parent directory of __init__.py)
        module_name = str(Path(mod_path).parent)
        events_to_emit.append((
            EventType.MODULE_ADDED,
            f"module:{module_name}",
            {"path": mod_path, "commit_range": f"{from_commit}..{to_commit}"},
        ))

    for sc_path in scorecard_changes:
        events_to_emit.append((
            EventType.SCORECARD_EXPANDED,
            f"scorecard:{sc_path}",
            {"path": sc_path, "commit_range": f"{from_commit}..{to_commit}"},
        ))

    for vc_path in vocabulary_changes:
        events_to_emit.append((
            EventType.VOCABULARY_EXPANDED,
            f"vocabulary:{vc_path}",
            {"path": vc_path, "commit_range": f"{from_commit}..{to_commit}"},
        ))

    if changes:
        events_to_emit.append((
            EventType.ARCHITECTURE_CHANGED,
            "organvm-engine",
            {
                "files_changed": len(changes),
                "new_modules": len(new_modules),
                "commit_range": f"{from_commit}..{to_commit}",
            },
        ))

    # Always record the session itself
    events_to_emit.append((
        EventType.SESSION_RECORDED,
        "organvm-engine",
        {
            "from_commit": from_commit,
            "to_commit": to_commit,
            "files_changed": len(changes),
            "events_detected": len(events_to_emit),  # count before this one
        },
    ))

    # Print summary
    print(f"\n  Testament Record-Session: {from_commit}..{to_commit}")
    print(f"  {'=' * 50}")
    print(f"  Files changed:      {len(changes)}")
    print(f"  New modules:        {len(new_modules)}")
    print(f"  Scorecard changes:  {len(scorecard_changes)}")
    print(f"  Vocabulary changes: {len(vocabulary_changes)}")
    print(f"  Events to emit:     {len(events_to_emit)}")

    if dry_run:
        print("\n  [dry-run] Events that would be emitted:")
        for etype, entity, _payload in events_to_emit:
            print(f"    {etype.value:<28} {entity}")
        print("\n  Run with --write to emit events.\n")
        return 0

    # Emit events to the spine
    spine = EventSpine(path=spine_path) if spine_path else EventSpine()
    emitted = 0
    for etype, entity, payload in events_to_emit:
        spine.emit(
            event_type=etype,
            entity_uid=entity,
            payload=payload,
            source_spec="IRF-TST-002",
            actor="cli:testament:record-session",
            source_organ="META-ORGANVM",
            source_repo="organvm-engine",
        )
        emitted += 1

    print(f"\n  Emitted {emitted} events to {spine.path}")
    for etype, entity, _payload in events_to_emit:
        print(f"    {etype.value:<28} {entity}")
    print()
    return 0


def _resolve_output_dir(args: argparse.Namespace) -> Path:
    """Resolve the output directory for testament artifacts."""
    output = getattr(args, "output_dir", None)
    if output:
        return Path(output)
    return Path.home() / ".organvm" / "testament" / "artifacts"


def _resolve_base_dir(args: argparse.Namespace) -> Path | None:
    """Resolve the base directory for the testament catalog."""
    base = getattr(args, "base_dir", None)
    return Path(base) if base else None


def _load_bounded_json(
    path: str,
    max_input_bytes: int,
    max_artifact_bytes: int,
) -> dict:
    from organvm_engine.corpus.governance_bundle import load_materialized_snapshot_bundle

    return load_materialized_snapshot_bundle(
        Path(path),
        max_input_bytes=max_input_bytes,
        max_artifact_bytes=max_artifact_bytes,
    )


def cmd_testament_candidate(args: argparse.Namespace) -> int:
    """Compile the bounded, non-ratified first-pass governance testament."""
    from organvm_engine.testament.governance_compiler import compile_candidate_testament

    bundle = _load_bounded_json(
        args.snapshot_bundle,
        args.max_input_bytes,
        args.max_artifact_bytes,
    )
    if args.write:
        result = compile_candidate_testament(
            bundle,
            output_dir=Path(args.output_dir),
            max_units=args.max_units,
        )
        print(json.dumps(result.receipt, indent=2, sort_keys=True))
        return 0
    with TemporaryDirectory(prefix="organvm-candidate-testament-") as temporary:
        result = compile_candidate_testament(
            bundle,
            output_dir=Path(temporary),
            max_units=args.max_units,
        )
        print(json.dumps({**result.receipt, "dry_run": True}, indent=2, sort_keys=True))
    return 0


def cmd_testament_iceberg_atlas(args: argparse.Namespace) -> int:
    """Compile one bounded/resumable final Iceberg Atlas pass."""
    from organvm_engine.events.spine import EventSpine
    from organvm_engine.testament.iceberg_atlas import (
        ReceiptIdentity,
        compile_iceberg_atlas,
    )

    bundle = _load_bounded_json(
        args.snapshot_bundle,
        args.max_input_bytes,
        args.max_artifact_bytes,
    )
    identity = ReceiptIdentity(
        actor=args.actor,
        source_organ=args.source_organ,
        source_repo=args.source_repo,
    )

    def run(output_dir: Path, cursor_path: Path, spine_path: Path):
        return compile_iceberg_atlas(
            bundle,
            output_dir=output_dir,
            cursor_path=cursor_path,
            event_spine=EventSpine(path=spine_path, max_chain_bytes=0),
            receipt_identity=identity,
            max_children=args.max_children,
        )

    if args.write:
        output_dir = Path(args.output_dir)
        result = run(
            output_dir,
            Path(args.cursor) if args.cursor else output_dir / ".governance-atlas-cursor.json",
            Path(args.event_spine),
        )
    else:
        with TemporaryDirectory(prefix="organvm-iceberg-atlas-") as temporary:
            root = Path(temporary)
            result = run(root / "output", root / "cursor.json", root / "events.jsonl")
            print(
                json.dumps(
                    {
                        "complete": result.complete,
                        "processed_children": result.processed_children,
                        "remaining_children": result.remaining_children,
                        "receipt": result.receipt,
                        "dry_run": True,
                    },
                    indent=2,
                    sort_keys=True,
                ),
            )
            return 0
    print(
        json.dumps(
            {
                "complete": result.complete,
                "processed_children": result.processed_children,
                "remaining_children": result.remaining_children,
                "receipt": result.receipt,
            },
            indent=2,
            sort_keys=True,
        ),
    )
    return 0
