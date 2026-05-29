"""CLI handlers for `organvm resolve` and `organvm topology`."""

from __future__ import annotations

import argparse
import json
import sys

from organvm_engine.topology.cache import build_topology, save_cache
from organvm_engine.topology.resolve import resolve, resolve_all


def cmd_resolve(args: argparse.Namespace) -> int:
    """Resolve a capability query to a filesystem path."""
    if getattr(args, "all", False):
        paths = resolve_all()
        if getattr(args, "json", False):
            json.dump(paths, sys.stdout, indent=2)
            print()
        else:
            for _name, path in sorted(paths.items()):
                print(path)
        return 0

    query = getattr(args, "query", None)
    if not query:
        print("Usage: organvm resolve <query> [--fallback <val>]", file=sys.stderr)
        return 2

    result = resolve(query)

    if result:
        print(result)
        return 0

    fallback = getattr(args, "fallback", None)
    if fallback is not None:
        print(fallback)
        return 0

    print(f"organvm resolve: {query} not found", file=sys.stderr)
    return 1


def cmd_topology_build(args: argparse.Namespace) -> int:
    """Build the topology cache from seed.yaml discovery."""
    workspace = getattr(args, "workspace", None)
    cache = build_topology(workspace=workspace)

    repo_count = len(cache.repos)
    cap_count = len(cache.producers)
    alias_count = len(cache.aliases)

    if getattr(args, "write", False):
        path = save_cache(cache)
        print(f"Topology cache written: {path}")
    else:
        print("Dry run (use --write to save)")

    print(f"  {repo_count} repos, {cap_count} capabilities, {alias_count} aliases")

    if getattr(args, "verbose", False):
        for name, entry in sorted(cache.repos.items()):
            produces = ", ".join(entry.get("produces", [])) or "-"
            print(f"  {name:40s} {produces}")

    return 0
