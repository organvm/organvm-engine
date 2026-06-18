"""CLI handlers for the ``handoff`` command group.

    organvm handoff list   -- workspace-wide listing of agent handoffs
    organvm handoff check  -- flag stale active handoffs (non-zero exit)
"""

from __future__ import annotations

import dataclasses
import json
import sys


def _collect(args):
    """Discover handoffs honoring shared --workspace/--organ/--include-archived flags."""
    from organvm_engine.handoff import discover_handoffs
    from organvm_engine.paths import resolve_workspace

    workspace = resolve_workspace(args)
    if workspace is None:
        print(
            "Cannot resolve workspace. Set ORGANVM_WORKSPACE_DIR or pass --workspace.",
            file=sys.stderr,
        )
        return None

    return discover_handoffs(
        workspace=workspace,
        organ=getattr(args, "organ", None),
        include_archived=getattr(args, "include_archived", False),
    )


def _as_dict(h, stale_days: int) -> dict:
    d = dataclasses.asdict(h)
    d["handoff_date"] = h.handoff_date.isoformat() if h.handoff_date else None
    d["age_days"] = h.age_days()
    d["staleness"] = h.staleness(stale_days=stale_days)
    d["is_stale"] = h.is_stale(stale_days=stale_days)
    return d


def _print_table(handoffs, stale_days: int) -> None:
    col_state = 9
    col_repo = 26
    col_route = 20
    col_age = 6

    header = (
        f"{'State':<{col_state}} {'Repo':<{col_repo}} {'Route':<{col_route}}"
        f" {'Age':<{col_age}} Scope"
    )
    sep = (
        f"{'─' * col_state} {'─' * col_repo} {'─' * col_route}"
        f" {'─' * col_age} {'─' * 30}"
    )
    print(header)
    print(sep)

    for h in handoffs:
        repo = h.repo if len(h.repo) <= col_repo else "…" + h.repo[-(col_repo - 1):]
        route = f"{h.from_agent or '?'}→{h.to_agent or '?'}"
        if len(route) > col_route:
            route = route[: col_route - 1] + "…"
        age = h.age_days()
        age_str = f"{age}d" if age is not None else "—"
        scope = h.scope or h.session or ""
        if len(scope) > 40:
            scope = scope[:39] + "…"
        flag = " ⚠" if h.cross_verification else ""
        print(
            f"{h.staleness(stale_days=stale_days):<{col_state}} {repo:<{col_repo}}"
            f" {route:<{col_route}} {age_str:<{col_age}} {scope}{flag}",
        )


def cmd_handoff_list(args) -> int:
    """List agent handoffs found across the workspace."""
    handoffs = _collect(args)
    if handoffs is None:
        return 1

    stale_days = getattr(args, "stale_days", None)
    if stale_days is None:
        from organvm_engine.handoff import DEFAULT_STALE_DAYS

        stale_days = DEFAULT_STALE_DAYS

    if getattr(args, "stale_only", False):
        from organvm_engine.handoff import filter_stale

        handoffs = filter_stale(handoffs, stale_days=stale_days)

    if getattr(args, "json", False):
        json.dump([_as_dict(h, stale_days) for h in handoffs], sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if not handoffs:
        print("No agent handoffs found.")
        return 0

    _print_table(handoffs, stale_days)
    stale_count = sum(1 for h in handoffs if h.is_stale(stale_days=stale_days))
    print()
    print(
        f"{len(handoffs)} handoff(s) — {stale_count} stale "
        f"(active and older than {stale_days}d)",
    )
    return 0


def cmd_handoff_check(args) -> int:
    """Flag stale active handoffs. Exits non-zero when any are found.

    Intended for CI / health-check use: a stale ``active-handoff.md`` means an
    agent baton was dropped or never cleared.
    """
    handoffs = _collect(args)
    if handoffs is None:
        return 1

    stale_days = getattr(args, "stale_days", None)
    if stale_days is None:
        from organvm_engine.handoff import DEFAULT_STALE_DAYS

        stale_days = DEFAULT_STALE_DAYS

    from organvm_engine.handoff import filter_stale

    stale = filter_stale(handoffs, stale_days=stale_days)

    if getattr(args, "json", False):
        json.dump(
            {
                "stale_days": stale_days,
                "total": len(handoffs),
                "stale_count": len(stale),
                "stale": [_as_dict(h, stale_days) for h in stale],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 1 if stale else 0

    if not stale:
        print(f"No stale handoffs (checked {len(handoffs)}, threshold {stale_days}d).")
        return 0

    print(f"{len(stale)} stale handoff(s) (active and older than {stale_days}d):")
    print()
    for h in stale:
        age = h.age_days()
        age_str = f"{age}d old" if age is not None else "undated"
        print(f"  [{h.staleness(stale_days=stale_days)}] {h.repo} — {age_str}")
        print(f"           {h.path}")
        if h.scope:
            print(f"           scope: {h.scope}")
    return 1
