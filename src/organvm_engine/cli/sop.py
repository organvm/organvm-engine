"""CLI commands: organvm sop discover|audit|check|resolve|init."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _resolve_sop_workspace(args: argparse.Namespace) -> Path | None:
    """Prefer the current repo when it has local .sops and no workspace was passed."""
    from organvm_engine.paths import resolve_workspace as _resolve_workspace

    if getattr(args, "workspace", None):
        return _resolve_workspace(args)
    cwd = Path.cwd()
    if (cwd / ".sops").is_dir():
        return cwd.resolve()
    return _resolve_workspace(args)


def cmd_sop_discover(args: argparse.Namespace) -> int:
    from organvm_engine.sop.discover import discover_sops

    workspace = _resolve_sop_workspace(args)
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
                "governed_paths": e.governed_paths,
                "last_reviewed": e.last_reviewed,
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
    from organvm_engine.sop.discover import discover_sops
    from organvm_engine.sop.inventory import audit_sops
    from organvm_engine.sop.staleness import audit_sop_staleness

    workspace = _resolve_sop_workspace(args)
    organ = getattr(args, "organ", None)

    entries = discover_sops(workspace=workspace, organ=organ)
    result = audit_sops(entries)
    stale_report = audit_sop_staleness(entries, workspace=workspace)

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

    _print_staleness_summary(stale_report)

    if not result.untracked and not result.missing:
        print("\nAll SOPs accounted for.")

    total = len(result.tracked) + len(result.reference_copy) + len(result.untracked)
    print(f"\nSummary: {total} discovered, {len(result.tracked)} tracked, "
          f"{len(result.reference_copy)} ref-copies, "
          f"{len(result.untracked)} untracked, {len(result.missing)} missing")
    return 0


def cmd_sop_check(args: argparse.Namespace) -> int:
    from organvm_engine.sop.discover import discover_sops
    from organvm_engine.sop.inventory import audit_sops

    workspace = _resolve_sop_workspace(args)
    strict = getattr(args, "strict", False)
    check_staleness = getattr(args, "staleness", False)

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

    if check_staleness:
        from organvm_engine.sop.staleness import audit_sop_staleness

        stale_report = audit_sop_staleness(entries, workspace=workspace)
        for check in stale_report.stale + stale_report.missing + stale_report.unknown:
            print(
                f"WARNING: {check.sop.filename} {check.status}: {check.declared_path} "
                f"({check.reason})",
                file=sys.stderr,
            )
        if strict and not stale_report.passed:
            return 1

    if not result.untracked and not result.missing:
        total = len(result.tracked) + len(result.reference_copy)
        print(f"OK: {total} SOPs accounted for, 0 untracked, 0 missing")

    return 0


def cmd_sop_staleness(args: argparse.Namespace) -> int:
    from organvm_engine.sop.discover import discover_sops
    from organvm_engine.sop.staleness import audit_sop_staleness

    workspace = _resolve_sop_workspace(args)
    organ = getattr(args, "organ", None)
    as_json = getattr(args, "json", False)
    strict = getattr(args, "strict", False)
    include_unmapped = getattr(args, "include_unmapped", False)

    entries = discover_sops(workspace=workspace, organ=organ)
    report = audit_sop_staleness(entries, workspace=workspace)

    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.passed or not strict else 1

    print("SOP Staleness")
    print("=" * 60)
    _print_staleness_summary(report, include_unmapped=include_unmapped)

    if not report.checks:
        print("\nNo SOPs declare governed code paths.")

    return 0 if report.passed or not strict else 1


def cmd_sop_resolve(args: argparse.Namespace) -> int:
    from organvm_engine.organ_config import ORGANS
    from organvm_engine.sop.discover import discover_sops
    from organvm_engine.sop.resolver import resolve_all, resolve_sop

    workspace = _resolve_sop_workspace(args)
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


def _print_staleness_summary(report, include_unmapped: bool = False) -> None:
    if not report.checks and not include_unmapped:
        return

    print("\nStaleness:")
    if report.stale:
        print(f"  STALE ({len(report.stale)}):")
        for check in report.stale:
            print(f"    {check.sop.filename:<40} {check.declared_path} - {check.reason}")
    if report.missing:
        print(f"  MISSING ({len(report.missing)}):")
        for check in report.missing:
            print(f"    {check.sop.filename:<40} {check.declared_path} - {check.reason}")
    if report.unknown:
        print(f"  UNKNOWN ({len(report.unknown)}):")
        for check in report.unknown:
            print(f"    {check.sop.filename:<40} {check.declared_path} - {check.reason}")
    if report.fresh:
        print(f"  Fresh: {len(report.fresh)} governed path(s)")
    if include_unmapped and report.unmapped:
        print(f"  Unmapped: {len(report.unmapped)} SOP(s) without governed paths")
