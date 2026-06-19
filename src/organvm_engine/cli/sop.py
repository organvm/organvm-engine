"""CLI commands: organvm sop discover|audit|check|resolve|init."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_sop_discover(args: argparse.Namespace) -> int:
    from organvm_engine.paths import resolve_workspace as _resolve_workspace
    from organvm_engine.sop.discover import discover_sops

    workspace = _resolve_workspace(args)
    organ = getattr(args, "organ", None)
    as_json = getattr(args, "json", False)

    entries = discover_sops(workspace=workspace, organ=organ)

    if as_json:
        data = [
            {
                "path": str(e.path),
                "org": e.org,
                "repo": e.repo,
                "filename": e.filename,
                "title": e.title,
                "doc_type": e.doc_type,
                "canonical": e.canonical,
                "has_canonical_header": e.has_canonical_header,
                "scope": e.scope,
                "phase": e.phase,
                "triggers": e.triggers,
                "overrides": e.overrides,
                "complements": e.complements,
                "sop_name": e.sop_name,
            }
            for e in entries
        ]
        print(json.dumps(data, indent=2))
        return 0

    if not entries:
        print("No SOP/METADOC files found.")
        return 0

    print(f"{'Org':<28} {'Repo':<40} {'Type':<10} {'Scope':<8} {'Filename'}")
    print("-" * 130)
    for e in entries:
        flags = ""
        if e.canonical:
            flags = " [canonical]"
        elif e.has_canonical_header:
            flags = " [ref-copy]"
        print(f"{e.org:<28} {e.repo:<40} {e.doc_type:<10} {e.scope:<8} {e.filename}{flags}")

    print(f"\nTotal: {len(entries)} SOP/METADOC files")
    return 0


def cmd_sop_audit(args: argparse.Namespace) -> int:
    from organvm_engine.paths import resolve_workspace as _resolve_workspace
    from organvm_engine.sop.discover import discover_sops
    from organvm_engine.sop.inventory import audit_sops

    workspace = _resolve_workspace(args)
    organ = getattr(args, "organ", None)
    as_json = getattr(args, "json", False)
    check_stale = getattr(args, "stale", False)

    entries = discover_sops(workspace=workspace, organ=organ)
    result = audit_sops(entries)

    staleness_results = []
    if check_stale:
        from organvm_engine.sop.staleness import (
            audit_sop_staleness,
            load_sop_code_mappings,
        )

        mapping_path = getattr(args, "mapping", None)
        mappings = load_sop_code_mappings(workspace=workspace, mapping_path=mapping_path)
        staleness_results = audit_sop_staleness(entries, mappings)

    if as_json:
        data = {
            "inventory": _audit_result_to_dict(result),
            "staleness": [r.to_dict() for r in staleness_results],
        }
        print(json.dumps(data, indent=2))
        return 0

    print("SOP Ecosystem Audit")
    print(f"{'=' * 60}")

    if result.tracked:
        print(f"\nTracked ({len(result.tracked)}):")
        for e in result.tracked:
            print(f"  {e.filename:<55} {e.org}/{e.repo}")

    if result.reference_copy:
        print(f"\nReference Copies ({len(result.reference_copy)}):")
        for e in result.reference_copy:
            print(f"  {e.filename:<55} {e.org}/{e.repo}")

    if result.untracked:
        print(f"\nUNTRACKED ({len(result.untracked)}):")
        for e in result.untracked:
            print(f"  {e.filename:<55} {e.org}/{e.repo}")

    if result.missing:
        print(f"\nMISSING from disk ({len(result.missing)}):")
        for name in result.missing:
            print(f"  {name}")

    if not result.untracked and not result.missing:
        print("\nAll SOPs accounted for.")

    total = len(result.tracked) + len(result.reference_copy) + len(result.untracked)
    print(f"\nSummary: {total} discovered, {len(result.tracked)} tracked, "
          f"{len(result.reference_copy)} ref-copies, "
          f"{len(result.untracked)} untracked, {len(result.missing)} missing")

    if check_stale:
        include_fresh = getattr(args, "include_fresh", False)
        _print_staleness_results(staleness_results, include_fresh=include_fresh)
    return 0


def _audit_result_to_dict(result) -> dict:
    return {
        "tracked": [_sop_entry_to_dict(e) for e in result.tracked],
        "reference_copy": [_sop_entry_to_dict(e) for e in result.reference_copy],
        "untracked": [_sop_entry_to_dict(e) for e in result.untracked],
        "missing": list(result.missing),
        "summary": {
            "discovered": len(result.tracked) + len(result.reference_copy) + len(result.untracked),
            "tracked": len(result.tracked),
            "reference_copy": len(result.reference_copy),
            "untracked": len(result.untracked),
            "missing": len(result.missing),
        },
    }


def _sop_entry_to_dict(entry) -> dict:
    return {
        "path": str(entry.path),
        "org": entry.org,
        "repo": entry.repo,
        "filename": entry.filename,
        "title": entry.title,
        "doc_type": entry.doc_type,
        "canonical": entry.canonical,
        "has_canonical_header": entry.has_canonical_header,
        "scope": entry.scope,
        "phase": entry.phase,
        "sop_name": entry.sop_name,
    }


def _print_staleness_results(results: list, *, include_fresh: bool) -> None:
    from organvm_engine.sop.staleness import stale_results

    visible = results if include_fresh else stale_results(results)
    print("\nSOP Staleness")
    print("-" * 60)
    if not results:
        print("No SOP governance mappings found.")
        return
    if not visible:
        print(f"All {len(results)} mapped SOP(s) are fresh.")
        return

    print(f"{'Status':<12} {'SOP':<34} {'Newest governed code'}")
    print("-" * 90)
    for result in visible:
        newest = str(result.newest_code_path) if result.newest_code_path else "-"
        print(f"{result.status:<12} {result.mapping.sop_name:<34} {newest}")

    stale_count = sum(1 for result in results if result.status == "stale")
    missing_sop_count = sum(1 for result in results if result.status == "missing-sop")
    missing_code_count = sum(1 for result in results if result.status == "missing-code")
    print(
        f"\nStaleness summary: {len(results)} mapped, {stale_count} stale, "
        f"{missing_sop_count} missing SOP, {missing_code_count} missing code",
    )


def cmd_sop_check(args: argparse.Namespace) -> int:
    from organvm_engine.paths import resolve_workspace as _resolve_workspace
    from organvm_engine.sop.discover import discover_sops
    from organvm_engine.sop.inventory import audit_sops

    workspace = _resolve_workspace(args)
    strict = getattr(args, "strict", False)

    entries = discover_sops(workspace=workspace)
    result = audit_sops(entries)

    if result.untracked:
        print(f"WARNING: {len(result.untracked)} untracked SOP(s):", file=sys.stderr)
        for e in result.untracked:
            print(f"  {e.org}/{e.repo}/{e.filename}", file=sys.stderr)
        if strict:
            return 1

    if result.missing:
        print(f"WARNING: {len(result.missing)} missing SOP(s):", file=sys.stderr)
        for name in result.missing:
            print(f"  {name}", file=sys.stderr)
        if strict:
            return 1

    if not result.untracked and not result.missing:
        total = len(result.tracked) + len(result.reference_copy)
        print(f"OK: {total} SOPs accounted for, 0 untracked, 0 missing")

    return 0


def cmd_sop_resolve(args: argparse.Namespace) -> int:
    from organvm_engine.organ_config import ORGANS
    from organvm_engine.paths import resolve_workspace as _resolve_workspace
    from organvm_engine.sop.discover import discover_sops
    from organvm_engine.sop.resolver import resolve_all, resolve_sop

    workspace = _resolve_workspace(args)
    organ_key = getattr(args, "organ", None)
    repo = getattr(args, "repo", None)
    name = getattr(args, "name", None)
    phase = getattr(args, "phase", None)

    # Resolve organ CLI key (e.g. "META") to directory name (e.g. "meta-organvm")
    organ_dir = None
    if organ_key:
        meta = ORGANS.get(organ_key.upper())
        organ_dir = meta["dir"] if meta else organ_key

    entries = discover_sops(workspace=workspace, organ=organ_key)

    resolved = (
        resolve_sop(name, entries) if name
        else resolve_all(entries, repo=repo, organ=organ_dir, phase=phase)
    )

    if not resolved:
        print("No matching SOPs found.")
        return 0

    print(f"{'Scope':<8} {'Phase':<12} {'Name':<40} {'Location'}")
    print("-" * 110)
    for e in resolved:
        loc = f"{e.org}/{e.repo}/{e.filename}"
        print(f"{e.scope:<8} {e.phase:<12} {(e.sop_name or e.filename):<40} {loc}")
        if e.complements:
            print(f"         {'':12} Linked skills: {', '.join(e.complements)}")

    print(f"\n{len(resolved)} active directive(s)")
    return 0


_SOP_INIT_TEMPLATE = """\
---
sop: true
name: {name}
scope: {scope}
phase: any
triggers: []
complements: []
overrides: null
---
# {title}

## Purpose

<!-- Describe what this SOP governs and why it exists -->

## Procedure

<!-- Step-by-step instructions -->

## Verification

<!-- How to confirm the procedure was followed correctly -->
"""


def cmd_sop_init(args: argparse.Namespace) -> int:
    scope = getattr(args, "scope", "repo")
    name = getattr(args, "name", None) or "new-procedure"

    sops_dir = Path(".sops")
    if not sops_dir.is_dir():
        sops_dir.mkdir()
        print(f"Created {sops_dir}/")

    target = sops_dir / f"{name}.md"
    if target.exists():
        print(f"Already exists: {target}", file=sys.stderr)
        return 1

    title = name.replace("-", " ").title()
    target.write_text(_SOP_INIT_TEMPLATE.format(name=name, scope=scope, title=title))
    print(f"Created {target}")
    print("\nNext steps:")
    print(f"  1. Edit {target} with your procedure content")
    print("  2. Run 'organvm sop discover --json' to verify it's found")
    if scope == "organ":
        print("  3. Ensure the superproject .gitignore includes '!.sops/' and '!.sops/**'")
    return 0
