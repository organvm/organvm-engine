"""Context CLI commands."""

import argparse
import json


def cmd_context_surfaces(args: argparse.Namespace) -> int:
    from organvm_engine.contextmd.surfaces import (
        collect_conversation_corpus_surfaces,
        render_conversation_corpus_surfaces,
    )

    report = collect_conversation_corpus_surfaces(
        workspace=args.workspace,
        repo=getattr(args, "repo", None),
    )
    if getattr(args, "json", False):
        print(json.dumps(report, indent=2))
    else:
        print(render_conversation_corpus_surfaces(report))
    return 1 if report["invalid_count"] > 0 else 0


def cmd_context_sync(args: argparse.Namespace) -> int:
    from organvm_engine.contextmd.sync import sync_all

    # --write overrides the default dry_run=True
    dry_run = not getattr(args, "write", False)

    organs = [args.organ] if args.organ else None
    result = sync_all(
        workspace=args.workspace,
        registry_path=args.registry,
        dry_run=dry_run,
        organs=organs,
    )

    print("System Context Sync Results")
    print("─" * 40)
    print(f"  Updated: {len(result['updated'])}")
    print(f"  Created: {len(result['created'])}")
    print(f"  Skipped: {len(result['skipped'])}")
    if result["errors"]:
        print(f"  Errors:  {len(result['errors'])}")
        for e in result["errors"]:
            print(f"    - {e['path']}: {e['error']}")

    changes = result.get("changelog") or result.get("changes") or []
    if changes:
        print("\nChangelog")
        print("─" * 40)
        for change in changes:
            marker = _change_marker(change.get("action", "updated"))
            print(
                f"  {marker} {change['path']} "
                f"(+{change.get('added_lines', 0)}/-{change.get('removed_lines', 0)})",
            )

    if getattr(args, "diff", False) and changes:
        print("\nDiff")
        print("─" * 40)
        for change in changes:
            diff = change.get("diff")
            if diff:
                print(diff)

    if result.get("dry_run"):
        print("\n[DRY RUN] No files were modified.")

    return 1 if result["errors"] else 0


def _change_marker(action: str) -> str:
    if action == "created":
        return "A"
    if action == "updated":
        return "M"
    return "?"

def cmd_context_diff(args: argparse.Namespace) -> int:
    import json

    from organvm_engine.paths import context_changelog_path

    changelog_file = context_changelog_path()
    if not changelog_file.is_file():
        print("No changelog found.")
        return 0

    last_n = getattr(args, "last", 1)

    # Read and group by timestamp
    syncs = {}
    with changelog_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                ts = record.get("timestamp")
                if ts:
                    if ts not in syncs:
                        syncs[ts] = []
                    syncs[ts].append(record)
            except Exception:
                pass

    if not syncs:
        print("No valid changelog records found.")
        return 0

    # Sort by timestamp descending
    sorted_ts = sorted(syncs.keys(), reverse=True)
    target_ts_list = sorted_ts[:last_n]

    import datetime

    for ts in target_ts_list:
        dt = datetime.datetime.fromtimestamp(ts)
        print(f"\nSync at {dt.isoformat()} (Timestamp: {ts})")
        print("=" * 60)

        for record in syncs[ts]:
            path = record.get("path")
            action = record.get("action")
            diff = record.get("diff")

            print(f"\n--- {path} ({action}) ---")
            if diff:
                print(diff)
            else:
                print("(No diff recorded or content created)")

    return 0

def cmd_context_rollback(args: argparse.Namespace) -> int:
    import json
    import re
    from pathlib import Path

    from organvm_engine.contextmd import AUTO_END, AUTO_START
    from organvm_engine.paths import context_changelog_path

    changelog_file = context_changelog_path()
    if not changelog_file.is_file():
        print("No changelog found.")
        return 1

    target_ts = int(args.to)

    records_to_rollback = []
    with changelog_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if record.get("timestamp") == target_ts:
                    records_to_rollback.append(record)
            except Exception:
                pass

    if not records_to_rollback:
        print(f"No records found for timestamp {target_ts}.")
        return 1

    print(f"Found {len(records_to_rollback)} records for timestamp {target_ts}. Rolling back...")

    for record in records_to_rollback:
        path = Path(record.get("path"))
        action = record.get("action")
        old_section = record.get("old_section", "")

        print(f"Rolling back {path} ({action})")

        if not path.is_file():
            print(f"  File {path} does not exist. Skipping.")
            continue

        content = path.read_text()

        if action == "created":
            if not old_section:
                # Need to be careful here to only remove the auto-generated section, or delete if empty
                if AUTO_START in content and AUTO_END in content:
                    pattern = re.escape(AUTO_START) + r".*" + re.escape(AUTO_END)
                    new_content = re.sub(pattern, "", content, flags=re.DOTALL)
                    new_content = new_content.strip()
                    if new_content:
                        path.write_text(new_content + "\n")
                    else:
                        print(f"  Deleting {path} as it only contained the generated section.")
                        path.unlink()
            else:
                print("  Unexpected: created action has old_section. Replacing block.")
                pattern = re.escape(AUTO_START) + r".*" + re.escape(AUTO_END)
                new_content = re.sub(pattern, old_section, content, flags=re.DOTALL)
                path.write_text(new_content)
        elif action == "updated":
            if AUTO_START in content and AUTO_END in content:
                pattern = re.escape(AUTO_START) + r".*" + re.escape(AUTO_END)
                new_content = re.sub(pattern, old_section, content, flags=re.DOTALL)
                path.write_text(new_content)
            else:
                print(f"  No AUTO block found in {path}. Skipping.")
        else:
            print(f"  Unknown action {action} for {path}. Skipping.")

    print("Rollback complete.")
    return 0

