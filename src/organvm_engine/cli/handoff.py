"""CLI commands for active handoff discovery and cleanup."""

from __future__ import annotations

import argparse
import json
import sys


def cmd_handoff_list(args: argparse.Namespace) -> int:
    from organvm_engine.handoff import format_age, list_handoffs, parse_duration

    try:
        stale_after = parse_duration(getattr(args, "stale_after", "48h"))
    except ValueError as exc:
        print(f"Invalid --stale-after: {exc}", file=sys.stderr)
        return 2

    handoffs = list_handoffs(args.workspace, stale_after=stale_after)
    if getattr(args, "json", False):
        print(json.dumps([h.to_dict() for h in handoffs], indent=2))
        return 0

    print("Active Handoffs")
    print("-" * 40)
    if not handoffs:
        print("No active handoff files found.")
        return 0

    for info in handoffs:
        marker = info.status.upper()
        print(f"{marker:8} {format_age(info.age):>7}  {info.relative_path}")
        detail = _metadata_detail(info)
        if detail:
            print(f"         {detail}")
    return 0


def cmd_handoff_clean(args: argparse.Namespace) -> int:
    from organvm_engine.handoff import clean_handoffs, parse_duration

    older_than = None
    if getattr(args, "older_than", None):
        try:
            older_than = parse_duration(args.older_than)
        except ValueError as exc:
            print(f"Invalid --older-than: {exc}", file=sys.stderr)
            return 2

    dry_run = getattr(args, "dry_run", False) or not getattr(args, "write", False)
    result = clean_handoffs(args.workspace, older_than=older_than, dry_run=dry_run)

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
        return 1 if result["errors"] else 0

    verb = "Would remove" if dry_run else "Removed"
    print("Handoff Clean Results")
    print("-" * 40)
    print(f"{verb}: {len(result['removed'])}")
    print(f"Kept: {len(result['kept'])}")
    for entry in result["removed"]:
        print(f"  - {entry['relative_path']} ({entry['clean_reason']})")
    if result["errors"]:
        print(f"Errors: {len(result['errors'])}")
        for error in result["errors"]:
            print(f"  - {error['path']}: {error['error']}")
    if dry_run:
        print("\n[DRY RUN] No files were removed. Use --write to remove targets.")
    return 1 if result["errors"] else 0


def _metadata_detail(info) -> str:
    parts = []
    if info.created_at is None:
        parts.append("created_at missing")
    if info.expires_at is None:
        parts.append("expires_at missing")
    if info.status in {"stale", "expired"}:
        parts.extend(info.reasons)
    return "; ".join(dict.fromkeys(parts))
