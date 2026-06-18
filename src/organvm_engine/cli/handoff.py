"""Handoff CLI commands — workspace-wide listing and staleness checks."""

from __future__ import annotations

import argparse
import json


def _to_dict(handoff, threshold_hours: float) -> dict:
    return {
        "org": handoff.org,
        "repo": handoff.repo,
        "path": str(handoff.path),
        "title": handoff.title,
        "agent": handoff.agent,
        "timestamp": handoff.timestamp.isoformat(),
        "timestamp_source": handoff.timestamp_source,
        "age_hours": round(handoff.age_hours(), 2),
        "stale": handoff.is_stale(threshold_hours),
        "cross_verification": handoff.cross_verification,
    }


def cmd_handoff_list(args: argparse.Namespace) -> int:
    """List active handoffs across the workspace."""
    from organvm_engine.handoff import (
        discover_handoffs,
        filter_stale,
        format_handoffs,
    )

    workspace = getattr(args, "workspace", None)
    threshold = args.stale_hours

    handoffs = discover_handoffs(workspace=workspace)
    if args.stale:
        handoffs = filter_stale(handoffs, threshold_hours=threshold)

    if args.json:
        print(json.dumps([_to_dict(h, threshold) for h in handoffs], indent=2))
        return 0

    stale_count = len(filter_stale(handoffs, threshold_hours=threshold))
    print(f"\n  Active Handoffs (stale threshold: {threshold:g}h)")
    print(f"  {'═' * 70}")
    print(format_handoffs(handoffs, threshold_hours=threshold))
    print(f"\n  {len(handoffs)} handoff(s) shown, {stale_count} stale\n")
    return 0


def cmd_handoff_check(args: argparse.Namespace) -> int:
    """Exit non-zero if any handoff is stale (for CI / session review)."""
    from organvm_engine.handoff import discover_handoffs, filter_stale

    workspace = getattr(args, "workspace", None)
    threshold = args.stale_hours

    handoffs = discover_handoffs(workspace=workspace)
    stale = filter_stale(handoffs, threshold_hours=threshold)

    if not stale:
        print(f"  No stale handoffs (threshold: {threshold:g}h).")
        return 0

    print(f"\n  {len(stale)} stale handoff(s) found (older than {threshold:g}h):\n")
    for h in stale:
        age = h.age_hours()
        age_str = f"{age:.0f}h" if age < 48 else f"{age / 24:.1f}d"  # noqa: PLR2004
        xv = " [CROSS-VERIFICATION REQUIRED]" if h.cross_verification else ""
        print(f"    {h.slug} — {age_str} old — {h.title}{xv}")
        print(f"      {h.path}")
    print()
    return 1
