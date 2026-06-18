"""CLI commands for active handoff discovery and cleanup."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta

from organvm_engine.handoff import (
    clean_handoffs,
    discover_handoffs,
    parse_duration,
    render_handoff_table,
)


def cmd_handoff_list(args: argparse.Namespace) -> int:
    """List active handoff files across the workspace."""
    stale_after = timedelta(hours=getattr(args, "stale_hours", 48.0))
    entries = discover_handoffs(
        workspace=getattr(args, "workspace", None),
        include_additional_roots=not getattr(args, "no_additional_roots", False),
    )

    if getattr(args, "json", False):
        print(json.dumps([entry.to_dict(stale_after=stale_after) for entry in entries], indent=2))
    else:
        print(render_handoff_table(entries, stale_after=stale_after))
    return 0


def cmd_handoff_clean(args: argparse.Namespace) -> int:
    """Remove expired or old handoff files."""
    try:
        older_than = parse_duration(getattr(args, "older_than", "7d"))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    result = clean_handoffs(
        workspace=getattr(args, "workspace", None),
        older_than=older_than,
        include_additional_roots=not getattr(args, "no_additional_roots", False),
        dry_run=getattr(args, "dry_run", False),
    )

    if getattr(args, "json", False):
        print(json.dumps(result.to_dict(), indent=2))
    else:
        action = "Would remove" if result.dry_run else "Removed"
        print(f"{action} {len(result.removed)} handoff(s). Kept {len(result.kept)}.")
        for entry in result.removed:
            print(f"  - {entry.path}")
        if result.errors:
            print(f"Errors: {len(result.errors)}", file=sys.stderr)
            for error in result.errors:
                print(f"  - {error['path']}: {error['error']}", file=sys.stderr)

    return 1 if result.errors else 0
