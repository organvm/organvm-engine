"""MCP tool functions for the registry CLI (LIMEN-060).

Exposes registry query operations as pure functions returning
JSON-serializable dicts. These functions are consumed by the MCP
server in organvm-mcp-server — they do NOT depend on the MCP SDK.

Five tools (mirroring ``organvm registry`` subcommands):
    registry_list         — list repos with optional filters
    registry_show         — show a single repo by name
    registry_search       — full-text search across repo fields
    registry_stats        — registry-wide summary statistics
    registry_dependencies — direct/transitive deps or dependents for a repo

All tools accept an optional ``registry_path`` so callers (and tests)
can point at a specific registry file or split-registry directory; it
defaults to the production registry resolved by ``paths.registry_path``.
"""

from __future__ import annotations

from typing import Any


def _entry(organ_key: str, repo: dict[str, Any]) -> dict[str, Any]:
    """Project an (organ_key, repo) pair into a flat JSON-serializable dict."""
    return {"organ": organ_key, **repo}


def registry_list(
    organ: str | None = None,
    status: str | None = None,
    tier: str | None = None,
    promotion_status: str | None = None,
    name_contains: str | None = None,
    public_only: bool = False,
    platinum_only: bool = False,
    limit: int = 100,
    registry_path: str | None = None,
) -> dict[str, Any]:
    """List repositories with optional filters.

    Parameters
    ----------
    organ:
        Filter by organ key or alias (e.g. ``"META"`` / ``"META-ORGANVM"``).
    status:
        Filter by ``implementation_status`` (e.g. ``ACTIVE``).
    tier:
        Filter by tier (e.g. ``flagship``).
    promotion_status:
        Filter by ``promotion_status`` (e.g. ``LOCAL``, ``PUBLIC_PROCESS``).
    name_contains:
        Case-insensitive substring match on the repository name.
    public_only:
        Only include public repos.
    platinum_only:
        Only include repos flagged ``platinum_status``.
    limit:
        Maximum number of repos to return (default 100).
    registry_path:
        Optional path to a registry file or split-registry directory.
    """
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.registry.query import list_repos

    registry = load_registry(registry_path)
    matches = list_repos(
        registry,
        organ=organ,
        status=status,
        tier=tier,
        public_only=public_only,
        promotion_status=promotion_status,
        name_contains=name_contains,
        platinum_only=platinum_only,
    )
    repos = [_entry(organ_key, repo) for organ_key, repo in matches[: max(limit, 0)]]
    return {
        "total": len(repos),
        "matched": len(matches),
        "repos": repos,
    }


def registry_show(
    name: str,
    registry_path: str | None = None,
) -> dict[str, Any]:
    """Show a single repository entry by name.

    Parameters
    ----------
    name:
        Repository name (e.g. ``organvm-engine``).
    registry_path:
        Optional path to a registry file or split-registry directory.
    """
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.registry.query import find_repo

    if not name:
        return {"found": False, "error": "name is required"}

    registry = load_registry(registry_path)
    result = find_repo(registry, name)
    if result is None:
        return {"found": False, "name": name}

    organ_key, repo = result
    return {
        "found": True,
        "organ": organ_key,
        "repo": repo,
    }


def registry_search(
    query: str,
    fields: list[str] | None = None,
    case_sensitive: bool = False,
    exact: bool = False,
    limit: int = 50,
    registry_path: str | None = None,
) -> dict[str, Any]:
    """Search repositories by text query across selected fields.

    Parameters
    ----------
    query:
        Text query. Tokens are AND-matched across fields unless ``exact``.
    fields:
        Restrict the search to these registry fields. Defaults to a broad
        set (name, org, description, statuses, tier, type, dependencies).
    case_sensitive:
        Match case-sensitively (default False).
    exact:
        Require an exact field-value match instead of substring tokens.
    limit:
        Maximum number of matches to return (default 50).
    registry_path:
        Optional path to a registry file or split-registry directory.
    """
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.registry.query import search_repos

    if not query or not query.strip():
        return {"total": 0, "query": query, "repos": []}

    registry = load_registry(registry_path)
    matches = search_repos(
        registry,
        query,
        fields=fields,
        case_sensitive=case_sensitive,
        exact=exact,
        limit=limit,
    )
    repos = [_entry(organ_key, repo) for organ_key, repo in matches]
    return {
        "total": len(repos),
        "query": query,
        "repos": repos,
    }


def registry_stats(
    registry_path: str | None = None,
) -> dict[str, Any]:
    """Return registry-wide summary statistics.

    Parameters
    ----------
    registry_path:
        Optional path to a registry file or split-registry directory.
    """
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.registry.query import summarize_registry

    registry = load_registry(registry_path)
    return summarize_registry(registry).to_dict()


def registry_dependencies(
    repo_name: str,
    direction: str = "out",
    transitive: bool = False,
    max_depth: int | None = None,
    registry_path: str | None = None,
) -> dict[str, Any]:
    """Return dependencies or dependents for a repository.

    Parameters
    ----------
    repo_name:
        Repository name to inspect.
    direction:
        ``"out"`` (default) for dependencies (what this repo depends on),
        or ``"in"`` for dependents (what depends on this repo).
    transitive:
        Walk the graph transitively instead of direct edges only.
    max_depth:
        Cap the transitive walk depth. ``None`` means unbounded.
    registry_path:
        Optional path to a registry file or split-registry directory.
    """
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.registry.query import (
        find_repo,
        get_repo_dependencies,
        get_repo_dependents,
    )

    if not repo_name:
        return {"found": False, "error": "repo_name is required"}

    normalized = direction.lower()
    if normalized not in ("out", "in"):
        return {"error": f"direction must be 'out' or 'in', got {direction!r}"}

    registry = load_registry(registry_path)
    if find_repo(registry, repo_name) is None:
        return {"found": False, "repo_name": repo_name}

    if normalized == "out":
        names = get_repo_dependencies(
            registry, repo_name, transitive=transitive, max_depth=max_depth,
        )
    else:
        names = get_repo_dependents(
            registry, repo_name, transitive=transitive, max_depth=max_depth,
        )

    return {
        "found": True,
        "repo_name": repo_name,
        "direction": normalized,
        "transitive": transitive,
        "count": len(names),
        "results": names,
    }
