"""CLI handler for the irf (Index Rerum Faciendarum) command group."""

from __future__ import annotations

import dataclasses
import json
import sys


def cmd_irf_list(args) -> int:
    """List IRF items with optional filters.

    Default (no filters): shows only open items.
    With any filter flag: applies that filter without adding implicit status=open.
    """
    from organvm_engine.irf import parse_irf, query_irf
    from organvm_engine.paths import irf_path

    path = irf_path()
    all_items = parse_irf(path)

    priority = getattr(args, "priority", None)
    domain = getattr(args, "domain", None)
    status = getattr(args, "status", None)
    owner = getattr(args, "owner", None)

    # If no filters at all, default to showing only open items.
    any_filter = any(x is not None for x in (priority, domain, status, owner))
    if not any_filter:
        status = "open"

    items = query_irf(
        all_items,
        priority=priority,
        domain=domain,
        status=status,
        owner=owner,
    )

    if getattr(args, "json", False):
        json.dump([dataclasses.asdict(i) for i in items], sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if not items:
        print("No items found.")
        return 0

    # Pretty table
    col_id = 14
    col_pri = 8
    col_dom = 8
    col_own = 16
    col_act = 45

    header = (
        f"{'ID':<{col_id}} {'Priority':<{col_pri}} {'Domain':<{col_dom}}"
        f" {'Owner':<{col_own}} {'Action'}"
    )
    sep = (
        f"{'─' * col_id} {'─' * col_pri} {'─' * col_dom}"
        f" {'─' * col_own} {'─' * col_act}"
    )
    print(header)
    print(sep)
    for item in items:
        action = item.action
        if len(action) > col_act:
            action = action[: col_act - 1] + "…"
        print(
            f"{item.id:<{col_id}} {item.priority:<{col_pri}} {item.domain:<{col_dom}}"
            f" {item.owner:<{col_own}} {action}",
        )

    print()
    print(f"{len(items)} item(s)")
    return 0


def cmd_irf_status(args) -> int:
    """Show all fields for a single IRF item by ID."""
    from organvm_engine.irf import parse_irf, query_irf
    from organvm_engine.paths import irf_path

    path = irf_path()
    all_items = parse_irf(path)

    matches = query_irf(all_items, item_id=args.item_id)
    if not matches:
        print(f"IRF item not found: {args.item_id}", file=sys.stderr)
        return 1

    item = matches[0]
    fields = dataclasses.asdict(item)
    max_key = max(len(k) for k in fields)
    for key, value in fields.items():
        print(f"  {key:<{max_key}}  {value}")
    return 0


def cmd_irf_stats(args) -> int:
    """Show summary statistics for the IRF document.

    With --write, regenerates the document's `## Statistics` block from the
    parsed items (derive-don't-copy, IRF-OPS-091). Refuses while the parse is
    incomplete.
    """
    from datetime import date

    from organvm_engine.irf import irf_stats
    from organvm_engine.irf.parser import parse_irf_diagnostics
    from organvm_engine.irf.writer import IRFWriteError, regenerate_stats_block, write_in_place
    from organvm_engine.paths import irf_path

    path = irf_path()
    items, skipped = parse_irf_diagnostics(path)
    stats = irf_stats(items)

    if getattr(args, "write", False):
        try:
            mutation = regenerate_stats_block(path, date.today().isoformat())
        except IRFWriteError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 1
        write_in_place(path, mutation.new_text)
        print(mutation.preview)
        return 0

    if skipped:
        print(
            f"⚠ parse incomplete: {len(skipped)} ID-bearing row(s) unparsed — "
            "stats below undercount (IRF-OPS-088)",
            file=sys.stderr,
        )
        for lineno, line in skipped[:5]:
            print(f"    L{lineno}: {line[:90]}", file=sys.stderr)

    if getattr(args, "json", False):
        json.dump(stats, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    rate_pct = f"{stats['completion_rate'] * 100:.1f}%"
    print("IRF Summary")
    print("─" * 40)
    print(f"  Total:           {stats['total']}")
    print(f"  Open:            {stats['open']}")
    print(f"  Completed:       {stats['completed']}")
    print(f"  Blocked:         {stats['blocked']}")
    print(f"  Archived:        {stats['archived']}")
    print(f"  Completion rate: {rate_pct}")

    print()
    print("By Priority")
    print("─" * 40)
    for pri, count in sorted(stats["by_priority"].items()):
        print(f"  {pri}:  {count}")

    print()
    print("By Domain")
    print("─" * 40)
    for domain, count in sorted(stats["by_domain"].items(), key=lambda x: -x[1]):
        print(f"  {domain:<12} {count}")

    return 0


def cmd_irf_add(args) -> int:
    """Add a new open item row (dry-run by default; --write to mutate)."""
    from organvm_engine.irf.writer import IRFWriteError, add_item, write_in_place
    from organvm_engine.paths import irf_path

    path = irf_path()
    try:
        mutation = add_item(
            path,
            domain=args.domain,
            action=args.action,
            priority=args.priority,
            owner=args.owner,
            source=args.source,
            blocker=args.blocker,
            item_id=args.id,
        )
    except IRFWriteError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1

    print(mutation.preview)
    if not args.write:
        print("(dry-run — pass --write to apply)")
        return 0
    write_in_place(path, mutation.new_text)
    print(f"written: {path}")
    return 0


def cmd_irf_complete(args) -> int:
    """Complete an open item (dry-run by default; --write to mutate).

    Strikes through the active row in place and appends a DONE ledger row —
    the additive idiom; nothing is deleted.
    """
    from datetime import date

    from organvm_engine.irf.writer import IRFWriteError, complete_item, write_in_place
    from organvm_engine.paths import irf_path

    path = irf_path()
    try:
        mutation = complete_item(
            path,
            item_id=args.item_id,
            note=args.note,
            session=args.session,
            date=date.today().isoformat(),
            done_id=args.done,
        )
    except IRFWriteError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1

    print(mutation.preview)
    if not args.write:
        print("(dry-run — pass --write to apply)")
        return 0
    write_in_place(path, mutation.new_text)
    print(f"written: {path}")
    return 0
