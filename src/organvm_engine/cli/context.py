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

    if result.get("dry_run"):
        print("\n[DRY RUN] No files were modified.")

    return 1 if result["errors"] else 0
