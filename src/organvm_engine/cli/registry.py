"""Registry CLI commands."""

import argparse
import contextlib
import json

from organvm_engine.registry.loader import load_registry, save_registry
from organvm_engine.registry.query import (
    find_repo,
    get_repo_dependencies,
    get_repo_dependents,
    list_repos,
    resolve_entity,
    search_repos,
    sort_repo_results,
    summarize_registry,
)
from organvm_engine.registry.updater import update_repo
from organvm_engine.registry.validator import validate_registry


def cmd_registry_show(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    resolved = resolve_entity(args.repo, registry=registry)
    if resolved and resolved.get("registry_entry"):
        organ_key, repo = resolved["organ_key"], resolved["registry_entry"]
    else:
        result = find_repo(registry, args.repo)
        if not result:
            print(f"ERROR: Repo '{args.repo}' not found in registry")
            return 1
        organ_key, repo = result
    print(f"\n  {repo['name']}")
    print(f"  {'─' * max(len(repo['name']), 40)}")
    print(f"  Organ:       {organ_key}")
    for key, value in repo.items():
        if key == "name":
            continue
        if isinstance(value, list):
            print(f"  {key + ':':<20}{', '.join(str(v) for v in value)}")
        elif isinstance(value, dict):
            print(f"  {key + ':':<20}{json.dumps(value, indent=None)}")
        else:
            print(f"  {key + ':':<20}{value}")
    print()
    return 0


def _archived_filter(args: argparse.Namespace) -> bool | None:
    if getattr(args, "archived", False):
        return True
    if getattr(args, "unarchived", False):
        return False
    return None


def _print_repo_table(results: list[tuple[str, dict]]) -> None:
    print(f"\n  {'Name':<45} {'Organ':<15} {'Status':<12} {'Tier':<12} {'Promotion':<14}")
    print(f"  {'─' * 99}")
    for organ_key, repo in results:
        print(
            f"  {repo['name']:<45} {organ_key:<15} "
            f"{repo.get('implementation_status', '?'):<12} "
            f"{repo.get('tier', '?'):<12} "
            f"{repo.get('promotion_status', '?'):<14}",
        )
    print(f"\n  {len(results)} repo(s)")


def cmd_registry_list(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    results = list_repos(
        registry,
        organ=args.organ,
        status=args.status,
        tier=args.tier,
        public_only=args.public,
        promotion_status=args.promotion_status,
        name_contains=args.name_contains,
        depends_on=args.depends_on,
        dependency_of=args.dependency_of,
        platinum_only=args.platinum,
        archived=_archived_filter(args),
    )
    results = sort_repo_results(results, field=args.sort_by, descending=args.desc)

    if args.json:
        payload = [
            {
                "name": repo["name"],
                "organ": organ_key,
                "status": repo.get("implementation_status", ""),
                "tier": repo.get("tier", ""),
                "promotion": repo.get("promotion_status", ""),
                "org": repo.get("org", ""),
            }
            for organ_key, repo in results
        ]
        print(json.dumps(payload, indent=2))
        return 0

    if not results:
        print("No repos match the given filters.")
        return 0

    _print_repo_table(results)
    return 0


def cmd_registry_search(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    results = search_repos(
        registry,
        query=args.query,
        fields=args.field,
        case_sensitive=args.case_sensitive,
        exact=args.exact,
        limit=args.limit,
        organ=args.organ,
        status=args.status,
        tier=args.tier,
        public_only=args.public,
        promotion_status=args.promotion_status,
    )
    results = sort_repo_results(results, field=args.sort_by, descending=args.desc)

    if args.json:
        payload = [{"organ": organ_key, "repo": repo} for organ_key, repo in results]
        print(json.dumps(payload, indent=2))
        return 0

    if not results:
        print("No repos match the search query.")
        return 0

    _print_repo_table(results)
    return 0


def cmd_registry_stats(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    stats = summarize_registry(registry)
    if args.json:
        print(json.dumps(stats.to_dict(), indent=2))
        return 0

    print("\n  Registry Stats")
    print(f"  {'─' * 40}")
    print(f"  Total repos:             {stats.total_repos}")
    print(f"  Organ groups:            {stats.organ_count}")
    print(f"  Public repos:            {stats.public_repos}")
    print(f"  Private repos:           {stats.private_repos}")
    print(f"  Platinum repos:          {stats.platinum_repos}")
    print(f"  Archived repos:          {stats.archived_repos}")
    print(f"  Repos w/ dependencies:   {stats.repos_with_dependencies}")
    print(f"  Dependency edges:        {stats.dependency_edges}")
    print("\n  By organ:")
    for key, count in stats.by_organ.items():
        print(f"    {key:<18} {count}")
    print("\n  By status:")
    for key, count in stats.by_status.items():
        print(f"    {key:<18} {count}")
    print("\n  By tier:")
    for key, count in stats.by_tier.items():
        print(f"    {key:<18} {count}")
    print("\n  By promotion:")
    for key, count in stats.by_promotion_status.items():
        print(f"    {key:<18} {count}")
    print()
    return 0


def _print_dependency_block(title: str, names: list[str]) -> None:
    print(f"\n  {title}:")
    if not names:
        print("    (none)")
        return
    for name in names:
        print(f"    - {name}")


def cmd_registry_deps(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    result = find_repo(registry, args.repo)
    if not result:
        print(f"ERROR: Repo '{args.repo}' not found in registry")
        return 1

    dependencies = get_repo_dependencies(
        registry,
        args.repo,
        transitive=args.transitive,
        max_depth=args.max_depth,
    )
    dependents = get_repo_dependents(
        registry,
        args.repo,
        transitive=args.transitive,
        max_depth=args.max_depth,
    )

    if args.json:
        if args.both:
            payload = {"repo": args.repo, "dependencies": dependencies, "dependents": dependents}
        elif args.reverse:
            payload = {"repo": args.repo, "dependents": dependents}
        else:
            payload = {"repo": args.repo, "dependencies": dependencies}
        print(json.dumps(payload, indent=2))
        return 0

    scope = "transitive" if args.transitive else "direct"
    if args.max_depth is not None:
        scope = f"{scope}, max-depth={args.max_depth}"
    print(f"\n  Dependency report for '{args.repo}' ({scope})")
    print(f"  {'─' * 56}")

    if args.both:
        _print_dependency_block("Dependencies", dependencies)
        _print_dependency_block("Dependents", dependents)
        print()
        return 0

    if args.reverse:
        _print_dependency_block("Dependents", dependents)
    else:
        _print_dependency_block("Dependencies", dependencies)
    print()
    return 0


def cmd_registry_validate(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    result = validate_registry(registry)
    print(result.summary())
    return 0 if result.passed else 1


def cmd_registry_update(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)

    # Type coercion — only for known boolean/integer fields
    BOOL_FIELDS = {"public", "platinum_status", "archived"}
    INT_FIELDS: set[str] = set()

    raw_value: str = args.value
    value: str | bool | int = raw_value
    if args.field in BOOL_FIELDS:
        if raw_value.lower() == "true":
            value = True
        elif raw_value.lower() == "false":
            value = False
    elif args.field in INT_FIELDS:
        with contextlib.suppress(ValueError):
            value = int(value)

    reason = getattr(args, "reason", "") or ""
    ok, msg = update_repo(registry, args.repo, args.field, value, reason=reason)
    print(f"  {msg}")
    if ok:
        save_registry(registry, args.registry)
        print("  Registry saved.")
    return 0 if ok else 1


def cmd_registry_split(args: argparse.Namespace) -> int:
    """Split monolithic registry into per-organ files."""
    from pathlib import Path

    from organvm_engine.registry.split import split_registry

    registry = load_registry(args.registry)
    output_dir = Path(args.output_dir)

    written = split_registry(registry, output_dir)
    print(f"  Split registry into {len(written)} files in {output_dir}/")
    for path in written:
        print(f"    {path.name}")
    return 0


def cmd_registry_merge(args: argparse.Namespace) -> int:
    """Merge per-organ files back into monolithic registry."""
    from pathlib import Path

    registry = load_registry(Path(args.input_dir))
    output = Path(args.output) if args.output else None

    if output:
        save_registry(registry, output)
        print(f"  Merged registry written to {output}")
    else:
        total = sum(
            len(o.get("repositories", []))
            for o in registry.get("organs", {}).values()
        )
        print(f"  Merged {len(registry.get('organs', {}))} organs, {total} repos")
        print("  Use --output <path> to write the merged file")
    return 0
