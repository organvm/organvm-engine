"""MCP tool functions for the five core organvm CLIs (LIMEN-060).

Exposes the ``registry``, ``governance``, ``seed``, ``metrics``, and
``dispatch`` command groups as pure functions returning JSON-serializable
dicts. These functions are consumed by the MCP server in
organvm-mcp-server — they do NOT depend on the MCP SDK and they never
print to stdout (CLI handlers do that; these return structured data).

Read-only by default: none of these tools mutate the registry or write
files. They mirror the ``--json`` projections the CLI already offers and,
where the CLI only renders text, build an equivalent structured payload.

Tools
-----
registry_show       — full record for a single repo
registry_list       — filtered repo list
registry_search     — text search across repos
registry_stats      — registry-wide statistics
registry_deps       — dependency / dependent edges for a repo
registry_validate   — schema / integrity validation report
governance_audit    — full governance audit (critical/warnings/info)
governance_check_deps — dependency-graph validation report
governance_impact   — blast-radius / downstream impact for a repo
seed_discover       — list discovered seed.yaml files
seed_validate       — validate required fields across seeds
seed_graph          — produces/consumes graph summary
metrics_calculate   — compute system metrics (no write side effects)
dispatch_validate   — validate a dispatch event payload
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


def registry_show(repo: str, registry_path: str | None = None) -> dict[str, Any]:
    """Return the full registry record for a single repo.

    Parameters
    ----------
    repo:
        Repository name or resolvable entity alias.
    registry_path:
        Optional path to a registry-v2.json file. Defaults to the
        canonical production registry.
    """
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.registry.query import find_repo, resolve_entity

    registry = load_registry(registry_path)
    resolved = resolve_entity(repo, registry=registry)
    if resolved and resolved.get("registry_entry"):
        organ_key, entry = resolved["organ_key"], resolved["registry_entry"]
    else:
        result = find_repo(registry, repo)
        if not result:
            return {"error": f"Repo {repo!r} not found in registry"}
        organ_key, entry = result

    return {"organ": organ_key, "repo": entry}


def registry_list(
    organ: str | None = None,
    status: str | None = None,
    tier: str | None = None,
    promotion_status: str | None = None,
    name_contains: str | None = None,
    public_only: bool = False,
    platinum_only: bool = False,
    archived: bool | None = None,
    sort_by: str = "name",
    descending: bool = False,
    registry_path: str | None = None,
) -> dict[str, Any]:
    """List repos with optional filters.

    Parameters mirror ``organvm registry list``. Returns a compact
    projection (name, organ, status, tier, promotion, org) per repo.
    """
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.registry.query import list_repos, sort_repo_results

    registry = load_registry(registry_path)
    results = list_repos(
        registry,
        organ=organ,
        status=status,
        tier=tier,
        public_only=public_only,
        promotion_status=promotion_status,
        name_contains=name_contains,
        platinum_only=platinum_only,
        archived=archived,
    )
    results = sort_repo_results(results, field=sort_by, descending=descending)

    repos = [
        {
            "name": entry.get("name", ""),
            "organ": organ_key,
            "status": entry.get("implementation_status", ""),
            "tier": entry.get("tier", ""),
            "promotion": entry.get("promotion_status", ""),
            "org": entry.get("org", ""),
        }
        for organ_key, entry in results
    ]
    return {"total": len(repos), "repos": repos}


def registry_search(
    query: str,
    fields: list[str] | None = None,
    case_sensitive: bool = False,
    exact: bool = False,
    limit: int | None = None,
    organ: str | None = None,
    status: str | None = None,
    tier: str | None = None,
    public_only: bool = False,
    promotion_status: str | None = None,
    registry_path: str | None = None,
) -> dict[str, Any]:
    """Search repositories by text query across selected fields.

    Parameters mirror ``organvm registry search``. Returns matching
    ``{organ, repo}`` records.
    """
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.registry.query import search_repos

    if not query or not query.strip():
        return {"error": "query is required"}

    registry = load_registry(registry_path)
    results = search_repos(
        registry,
        query=query,
        fields=fields,
        case_sensitive=case_sensitive,
        exact=exact,
        limit=limit,
        organ=organ,
        status=status,
        tier=tier,
        public_only=public_only,
        promotion_status=promotion_status,
    )
    matches = [{"organ": organ_key, "repo": entry} for organ_key, entry in results]
    return {"total": len(matches), "matches": matches}


def registry_stats(registry_path: str | None = None) -> dict[str, Any]:
    """Return registry-wide statistics (counts by organ/status/tier/promotion)."""
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.registry.query import summarize_registry

    registry = load_registry(registry_path)
    return summarize_registry(registry).to_dict()


def registry_deps(
    repo: str,
    reverse: bool = False,
    both: bool = False,
    transitive: bool = False,
    max_depth: int | None = None,
    registry_path: str | None = None,
) -> dict[str, Any]:
    """Return dependency and/or dependent edges for a repo.

    Parameters
    ----------
    repo:
        Repository name.
    reverse:
        Return dependents (who depends on this) instead of dependencies.
    both:
        Return both dependencies and dependents.
    transitive:
        Follow edges transitively rather than direct-only.
    max_depth:
        Cap transitive traversal depth.
    registry_path:
        Optional registry path.
    """
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.registry.query import (
        find_repo,
        get_repo_dependencies,
        get_repo_dependents,
    )

    registry = load_registry(registry_path)
    if not find_repo(registry, repo):
        return {"error": f"Repo {repo!r} not found in registry"}

    payload: dict[str, Any] = {"repo": repo}
    if both or not reverse:
        payload["dependencies"] = get_repo_dependencies(
            registry, repo, transitive=transitive, max_depth=max_depth,
        )
    if both or reverse:
        payload["dependents"] = get_repo_dependents(
            registry, repo, transitive=transitive, max_depth=max_depth,
        )
    return payload


def registry_validate(registry_path: str | None = None) -> dict[str, Any]:
    """Validate registry schema/integrity. Returns errors, warnings, pass flag."""
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.registry.validator import validate_registry

    registry = load_registry(registry_path)
    result = validate_registry(registry)
    return {
        "passed": result.passed,
        "total_repos": result.total_repos,
        "errors": result.errors,
        "warnings": result.warnings,
    }


# ---------------------------------------------------------------------------
# governance
# ---------------------------------------------------------------------------


def governance_audit(
    registry_path: str | None = None,
    rules_path: str | None = None,
) -> dict[str, Any]:
    """Run the full governance audit.

    Returns critical/warnings/info issue lists and an overall pass flag.
    """
    from organvm_engine.governance.audit import run_audit
    from organvm_engine.governance.rules import load_governance_rules
    from organvm_engine.registry.loader import load_registry

    registry = load_registry(registry_path)
    rules = load_governance_rules(rules_path) if rules_path else None
    result = run_audit(registry, rules)
    return {
        "passed": result.passed,
        "critical": result.critical,
        "warnings": result.warnings,
        "info": result.info,
    }


def governance_check_deps(registry_path: str | None = None) -> dict[str, Any]:
    """Validate the dependency graph (missing targets, cycles, back-edges)."""
    from organvm_engine.governance.dependency_graph import validate_dependencies
    from organvm_engine.registry.loader import load_registry

    registry = load_registry(registry_path)
    result = validate_dependencies(registry)
    return {
        "passed": result.passed,
        "total_edges": result.total_edges,
        "missing_targets": [list(t) for t in result.missing_targets],
        "self_deps": result.self_deps,
        "back_edges": [list(e) for e in result.back_edges],
        "cycles": result.cycles,
        "cross_organ": result.cross_organ,
        "violations": result.violations,
    }


def governance_impact(
    repo: str,
    registry_path: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Return the downstream blast radius for a change to ``repo``."""
    from organvm_engine.governance.impact import calculate_impact
    from organvm_engine.registry.loader import load_registry

    registry = load_registry(registry_path)
    report = calculate_impact(repo, registry, workspace)
    return {
        "source_repo": report.source_repo,
        "affected_repos": sorted(report.affected_repos),
        "affected_count": len(report.affected_repos),
        "impact_graph": report.impact_graph,
    }


# ---------------------------------------------------------------------------
# seed
# ---------------------------------------------------------------------------


def seed_discover(workspace: str | None = None) -> dict[str, Any]:
    """List discovered seed.yaml files as ``org/repo`` identities."""
    from organvm_engine.seed.discover import discover_seeds

    seeds = discover_seeds(workspace)
    found = []
    for path in seeds:
        parts = path.parts
        found.append({"org": parts[-3], "repo": parts[-2], "path": str(path)})
    return {"total": len(found), "seeds": found}


def seed_validate(workspace: str | None = None) -> dict[str, Any]:
    """Validate that every seed.yaml has the required top-level fields."""
    from organvm_engine.seed.discover import discover_seeds
    from organvm_engine.seed.reader import read_seed

    required = ["schema_version", "organ", "repo", "org"]
    seeds = discover_seeds(workspace)
    results: list[dict[str, Any]] = []
    failed = 0
    for path in seeds:
        try:
            seed = read_seed(path)
            missing = [f for f in required if f not in seed]
            if missing:
                failed += 1
                results.append(
                    {"path": str(path), "passed": False, "missing": missing},
                )
            else:
                results.append(
                    {
                        "path": str(path),
                        "passed": True,
                        "org": seed.get("org"),
                        "repo": seed.get("repo"),
                    },
                )
        except Exception as e:  # noqa: BLE001 — surface parse errors as data
            failed += 1
            results.append({"path": str(path), "passed": False, "error": str(e)})

    return {
        "total": len(seeds),
        "passed": len(seeds) - failed,
        "failed": failed,
        "results": results,
    }


def seed_graph(workspace: str | None = None) -> dict[str, Any]:
    """Build the produces/consumes graph across all seeds."""
    from organvm_engine.seed.graph import build_seed_graph

    graph = build_seed_graph(workspace)
    return {
        "nodes": graph.nodes,
        "node_count": len(graph.nodes),
        "edges": [
            {"source": src, "target": tgt, "type": artifact_type}
            for src, tgt, artifact_type in graph.edges
        ],
        "edge_count": len(graph.edges),
        "errors": graph.errors,
    }


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


def metrics_calculate(
    registry_path: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Compute system-wide metrics from the registry.

    Read-only: computes and returns metrics without writing
    system-metrics.json or mutating the registry.
    """
    from pathlib import Path

    from organvm_engine.metrics.calculator import compute_metrics
    from organvm_engine.registry.loader import load_registry

    registry = load_registry(registry_path)
    ws = Path(workspace) if workspace else None
    return compute_metrics(registry, workspace=ws)


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


def dispatch_validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a dispatch event payload.

    Parameters
    ----------
    payload:
        The event payload object to validate against the dispatch schema.
    """
    from organvm_engine.dispatch.payload import validate_payload

    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["payload must be a JSON object"]}

    ok, errors = validate_payload(payload)
    return {"valid": ok, "errors": errors}
