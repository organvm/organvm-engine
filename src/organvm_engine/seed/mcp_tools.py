"""MCP tool functions for the seed CLI (LIMEN-060).

Exposes seed.yaml discovery and graphing as pure functions returning
JSON-serializable dicts. Consumed by the MCP server in
organvm-mcp-server — these functions do NOT depend on the MCP SDK.

Four tools (mirroring ``organvm seed`` subcommands):
    seed_discover  — list every seed.yaml across the workspace
    seed_validate  — validate required fields in each seed.yaml
    seed_graph     — produces/consumes graph (nodes + edges)
    seed_ownership — ownership declarations for one repo's seed.yaml

All tools accept an optional ``workspace`` (and ``orgs``) so callers and
tests can scope discovery; they default to the workspace resolved by
``paths.workspace_root``.
"""

from __future__ import annotations

from typing import Any

_REQUIRED_SEED_FIELDS = ("schema_version", "organ", "repo", "org")


def seed_discover(
    workspace: str | None = None,
    orgs: list[str] | None = None,
) -> dict[str, Any]:
    """List all seed.yaml files discovered across the workspace.

    Parameters
    ----------
    workspace:
        Root workspace directory. Defaults to ~/Workspace conventions.
    orgs:
        Restrict scanning to these org directory names.
    """
    from organvm_engine.seed.discover import discover_seeds

    paths = discover_seeds(workspace, orgs)
    seeds: list[dict[str, Any]] = []
    for path in paths:
        parts = path.parts
        seeds.append({
            "org": parts[-3] if len(parts) >= 3 else "",
            "repo": parts[-2] if len(parts) >= 2 else "",
            "path": str(path),
        })

    return {
        "total": len(seeds),
        "seeds": seeds,
    }


def seed_validate(
    workspace: str | None = None,
    orgs: list[str] | None = None,
) -> dict[str, Any]:
    """Validate that each seed.yaml has the required top-level fields.

    Required fields: ``schema_version``, ``organ``, ``repo``, ``org``.

    Parameters
    ----------
    workspace:
        Root workspace directory.
    orgs:
        Restrict scanning to these org directory names.
    """
    from organvm_engine.seed.discover import discover_seeds
    from organvm_engine.seed.reader import read_seed

    paths = discover_seeds(workspace, orgs)
    results: list[dict[str, Any]] = []
    failed = 0

    for path in paths:
        try:
            seed = read_seed(path)
        except Exception as exc:  # surface any parse error as a failure
            failed += 1
            results.append({
                "path": str(path),
                "passed": False,
                "error": str(exc),
            })
            continue

        missing = [f for f in _REQUIRED_SEED_FIELDS if f not in seed]
        if missing:
            failed += 1
            results.append({
                "path": str(path),
                "passed": False,
                "missing": missing,
            })
        else:
            results.append({
                "identity": f"{seed.get('org')}/{seed.get('repo')}",
                "passed": True,
            })

    return {
        "total": len(paths),
        "passed": len(paths) - failed,
        "failed": failed,
        "results": results,
    }


def seed_graph(
    workspace: str | None = None,
    orgs: list[str] | None = None,
) -> dict[str, Any]:
    """Build the produces/consumes graph from all seed.yaml declarations.

    Parameters
    ----------
    workspace:
        Root workspace directory.
    orgs:
        Restrict scanning to these org directory names.
    """
    from organvm_engine.seed.graph import build_seed_graph

    graph = build_seed_graph(workspace, orgs)
    edges = [
        {"source": src, "target": tgt, "type": artifact_type}
        for src, tgt, artifact_type in graph.edges
    ]

    return {
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "nodes": graph.nodes,
        "edges": edges,
        "errors": graph.errors,
    }


def seed_ownership(
    repo: str,
    workspace: str | None = None,
    orgs: list[str] | None = None,
) -> dict[str, Any]:
    """Return ownership declarations for a single repo's seed.yaml.

    Parameters
    ----------
    repo:
        Repository name, or ``org/repo`` identity, to look up.
    workspace:
        Root workspace directory.
    orgs:
        Restrict scanning to these org directory names.
    """
    from organvm_engine.seed.discover import discover_seeds
    from organvm_engine.seed.ownership import (
        get_ai_agents,
        get_collaborators,
        get_lead,
        get_review_gates,
        has_ownership,
    )
    from organvm_engine.seed.reader import read_seed

    if not repo:
        return {"found": False, "error": "repo is required"}

    for path in discover_seeds(workspace, orgs):
        try:
            seed = read_seed(path)
        except Exception:  # skip unparseable seeds
            continue

        repo_name = seed.get("repo", "")
        org = seed.get("org", "")
        if repo not in (repo_name, f"{org}/{repo_name}"):
            continue

        if not has_ownership(seed):
            return {
                "found": True,
                "identity": f"{org}/{repo_name}",
                "has_ownership": False,
                "note": "no ownership section (v1.0 seed — solo-operator mode)",
            }

        return {
            "found": True,
            "identity": f"{org}/{repo_name}",
            "has_ownership": True,
            "lead": get_lead(seed),
            "collaborators": get_collaborators(seed),
            "ai_agents": get_ai_agents(seed),
            "review_gates": get_review_gates(seed),
        }

    return {"found": False, "repo": repo}
