"""MCP tool functions for the governance CLI (LIMEN-060).

Exposes governance checks as pure functions returning JSON-serializable
dicts. Consumed by the MCP server in organvm-mcp-server — these functions
do NOT depend on the MCP SDK.

Four tools (mirroring ``organvm governance`` subcommands):
    governance_audit      — full system audit against governance rules
    governance_check_deps — dependency graph validation
    governance_impact     — blast-radius / downstream impact for a repo
    governance_dictums    — list governance dictums (axiom/organ/repo)

Tools accept optional ``registry_path`` / ``rules_path`` / ``workspace``
so callers (and tests) can point at specific data; they default to the
production locations resolved by ``paths``.
"""

from __future__ import annotations

from typing import Any


def governance_audit(
    registry_path: str | None = None,
    rules_path: str | None = None,
    verify_ci: bool = False,
    check_dictums: bool = True,
) -> dict[str, Any]:
    """Run a full governance audit and return findings by severity.

    Parameters
    ----------
    registry_path:
        Optional path to a registry file or split-registry directory.
    rules_path:
        Optional path to a governance-rules JSON file. Defaults to the
        production rules when omitted.
    verify_ci:
        Also verify CI workflows on the filesystem (slower).
    check_dictums:
        Run dictum compliance validators as part of the audit.
    """
    from organvm_engine.governance.audit import run_audit
    from organvm_engine.registry.loader import load_registry

    registry = load_registry(registry_path)

    rules = None
    if rules_path:
        from organvm_engine.governance.rules import load_governance_rules

        rules = load_governance_rules(rules_path)

    result = run_audit(
        registry,
        rules,
        verify_ci=verify_ci,
        check_dictums=check_dictums,
    )

    return {
        "passed": result.passed,
        "critical_count": len(result.critical),
        "warning_count": len(result.warnings),
        "info_count": len(result.info),
        "critical": result.critical,
        "warnings": result.warnings,
        "info": result.info,
    }


def governance_check_deps(
    registry_path: str | None = None,
) -> dict[str, Any]:
    """Validate the registry dependency graph.

    Reports missing targets, self-dependencies, back-edges (lower-organ
    depending on higher-organ), cycles, and cross-organ flow counts.

    Parameters
    ----------
    registry_path:
        Optional path to a registry file or split-registry directory.
    """
    from organvm_engine.governance.dependency_graph import validate_dependencies
    from organvm_engine.registry.loader import load_registry

    registry = load_registry(registry_path)
    result = validate_dependencies(registry)

    return {
        "passed": result.passed,
        "total_edges": result.total_edges,
        "missing_targets": [list(pair) for pair in result.missing_targets],
        "self_deps": result.self_deps,
        "back_edges": [list(edge) for edge in result.back_edges],
        "cycles": result.cycles,
        "cross_organ": result.cross_organ,
        "violations": result.violations,
    }


def governance_impact(
    repo: str,
    registry_path: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Calculate the downstream impact (blast radius) of changing a repo.

    Combines explicit registry dependencies with implicit seed.yaml data
    flow edges to find every repository that could be affected.

    Parameters
    ----------
    repo:
        The repository name to analyze.
    registry_path:
        Optional path to a registry file or split-registry directory.
    workspace:
        Optional workspace root used to resolve seed.yaml data-flow edges.
    """
    from organvm_engine.governance.impact import calculate_impact
    from organvm_engine.registry.loader import load_registry

    if not repo:
        return {"error": "repo is required"}

    registry = load_registry(registry_path)
    report = calculate_impact(repo, registry, workspace)

    return {
        "source_repo": report.source_repo,
        "affected_count": len(report.affected_repos),
        "affected_repos": sorted(report.affected_repos),
        "impact_graph": report.impact_graph,
    }


def governance_dictums(
    level: str | None = None,
    dictum_id: str | None = None,
    rules_path: str | None = None,
) -> dict[str, Any]:
    """List governance dictums, optionally filtered by level or id.

    Parameters
    ----------
    level:
        Filter to a single level: ``axiom``, ``organ``, or ``repo``.
    dictum_id:
        Return only the dictum with this id (e.g. ``AX-6``).
    rules_path:
        Optional path to a governance-rules JSON file.
    """
    from organvm_engine.governance.dictums import get_dictums, list_all_dictums
    from organvm_engine.governance.rules import load_governance_rules

    rules = load_governance_rules(rules_path) if rules_path else load_governance_rules()

    if not get_dictums(rules):
        return {"total": 0, "dictums": [], "note": "no dictums section in rules"}

    dictums = list_all_dictums(rules)

    if dictum_id:
        dictums = [d for d in dictums if d.get("id") == dictum_id]
    if level:
        dictums = [d for d in dictums if d.get("level") == level]

    return {
        "total": len(dictums),
        "dictums": dictums,
    }
