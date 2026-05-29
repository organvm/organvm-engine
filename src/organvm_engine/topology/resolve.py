"""Resolve queries against the topology cache.

Query types:
    - Repo name: "organvm-engine" → path
    - Alias: "conductor" → resolves alias → path
    - @capability: "@governance-policy" → find the producer → path
    - Organ key: "ORGAN-I", "META" → organ directory
"""

from __future__ import annotations

import contextlib

from organvm_engine.topology.cache import TopologyCache, build_topology, load_cache, save_cache


def resolve(query: str, cache: TopologyCache | None = None) -> str | None:
    """Resolve a query to a filesystem path.

    Tries in order:
    1. Capability lookup (@prefix)
    2. Alias expansion
    3. Direct repo name match

    Returns the canonical path or None if not found.
    """
    if cache is None:
        cache = _ensure_cache()

    # @capability: find the repo that produces this
    if query.startswith("@"):
        cap_type = query[1:]
        repo_name = cache.producers.get(cap_type)
        if repo_name and repo_name in cache.repos:
            return cache.repos[repo_name]["path"]
        return None

    # Alias expansion
    resolved_name = cache.aliases.get(query, query)

    # Direct repo name match
    if resolved_name in cache.repos:
        return cache.repos[resolved_name]["path"]

    # Fuzzy: try matching against identity (org/name)
    for _name, entry in cache.repos.items():
        if entry.get("identity", "") == resolved_name:
            return entry["path"]

    return None


def resolve_all(cache: TopologyCache | None = None) -> dict[str, str]:
    """Return a dict of all repo names → paths."""
    if cache is None:
        cache = _ensure_cache()
    return {name: entry["path"] for name, entry in cache.repos.items()}


def _ensure_cache() -> TopologyCache:
    """Load cache from disk, or build it live if missing/stale."""
    cache = load_cache()
    if cache is not None:
        return cache

    # Build fresh and save for next time
    cache = build_topology()
    # Cache write failure is not fatal.
    with contextlib.suppress(OSError):
        save_cache(cache)
    return cache
