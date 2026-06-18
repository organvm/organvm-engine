"""MCP tool layer for organvm-engine (LIMEN-060).

A single discovery point that the MCP server in ``organvm-mcp-server``
imports to expose the five core organvm CLIs (registry, governance,
seed, metrics, dispatch) as MCP tools — without this package depending
on the MCP SDK.

Each tool is a pure function returning a JSON-serializable dict (see
``organvm_engine.mcp.tools``). ``MCP_TOOLS`` describes them as
``ToolSpec`` records so a server can register them generically:

    from organvm_engine.mcp import MCP_TOOLS, call_tool, list_tools

    for spec in MCP_TOOLS:
        server.register(spec.name, spec.handler, spec.description)

    # or dispatch by name:
    result = call_tool("registry_stats")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from organvm_engine.mcp import tools

__all__ = [
    "ToolSpec",
    "MCP_TOOLS",
    "TOOLS_BY_NAME",
    "list_tools",
    "call_tool",
]


@dataclass(frozen=True)
class ToolSpec:
    """Description of a single MCP tool.

    Attributes
    ----------
    name:
        Stable tool name (``<cli>_<verb>``) used for registration/dispatch.
    cli:
        The organvm CLI group this tool wraps.
    description:
        One-line summary, suitable for an MCP tool manifest.
    handler:
        The pure callable returning a JSON-serializable dict.
    """

    name: str
    cli: str
    description: str
    handler: Callable[..., dict[str, Any]]


MCP_TOOLS: list[ToolSpec] = [
    # registry
    ToolSpec(
        "registry_show", "registry",
        "Return the full registry record for a single repo.",
        tools.registry_show,
    ),
    ToolSpec(
        "registry_list", "registry",
        "List repos with optional organ/status/tier/promotion filters.",
        tools.registry_list,
    ),
    ToolSpec(
        "registry_search", "registry",
        "Search repositories by text query across selected fields.",
        tools.registry_search,
    ),
    ToolSpec(
        "registry_stats", "registry",
        "Return registry-wide statistics (counts by organ/status/tier).",
        tools.registry_stats,
    ),
    ToolSpec(
        "registry_deps", "registry",
        "Return dependency and/or dependent edges for a repo.",
        tools.registry_deps,
    ),
    ToolSpec(
        "registry_validate", "registry",
        "Validate registry schema/integrity; return errors and warnings.",
        tools.registry_validate,
    ),
    # governance
    ToolSpec(
        "governance_audit", "governance",
        "Run the full governance audit (critical/warnings/info).",
        tools.governance_audit,
    ),
    ToolSpec(
        "governance_check_deps", "governance",
        "Validate the dependency graph (missing targets, cycles, back-edges).",
        tools.governance_check_deps,
    ),
    ToolSpec(
        "governance_impact", "governance",
        "Return the downstream blast radius for a change to a repo.",
        tools.governance_impact,
    ),
    # seed
    ToolSpec(
        "seed_discover", "seed",
        "List discovered seed.yaml files as org/repo identities.",
        tools.seed_discover,
    ),
    ToolSpec(
        "seed_validate", "seed",
        "Validate that every seed.yaml has the required top-level fields.",
        tools.seed_validate,
    ),
    ToolSpec(
        "seed_graph", "seed",
        "Build the produces/consumes graph across all seeds.",
        tools.seed_graph,
    ),
    # metrics
    ToolSpec(
        "metrics_calculate", "metrics",
        "Compute system-wide metrics from the registry (no write).",
        tools.metrics_calculate,
    ),
    # dispatch
    ToolSpec(
        "dispatch_validate", "dispatch",
        "Validate a dispatch event payload against the schema.",
        tools.dispatch_validate,
    ),
]

TOOLS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in MCP_TOOLS}


def list_tools() -> list[dict[str, str]]:
    """Return a serializable manifest of all tools (name, cli, description)."""
    return [
        {"name": spec.name, "cli": spec.cli, "description": spec.description}
        for spec in MCP_TOOLS
    ]


def call_tool(name: str, **kwargs: Any) -> dict[str, Any]:
    """Dispatch a tool call by name.

    Parameters
    ----------
    name:
        One of the registered tool names (see ``TOOLS_BY_NAME``).
    **kwargs:
        Keyword arguments forwarded to the tool handler.

    Returns
    -------
    dict
        The handler's JSON-serializable result, or ``{"error": ...}`` if
        the tool name is unknown.
    """
    spec = TOOLS_BY_NAME.get(name)
    if spec is None:
        return {
            "error": f"Unknown tool {name!r}. "
            f"Valid: {', '.join(sorted(TOOLS_BY_NAME))}",
        }
    return spec.handler(**kwargs)
