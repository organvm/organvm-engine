"""MCP tool functions for the metrics CLI (LIMEN-060).

Exposes read-only metrics computation as pure functions returning
JSON-serializable dicts. Consumed by the MCP server in
organvm-mcp-server — these functions do NOT depend on the MCP SDK.

Two tools (mirroring the read paths of ``organvm metrics``):
    metrics_calculate  — derive system metrics from the registry
    metrics_word_count — workspace word-count breakdown

These tools are non-mutating: unlike the CLI, they never write
``system-metrics.json`` or update the registry. Callers may pass an
explicit ``registry_path`` / ``workspace``; both default to production.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def metrics_calculate(
    registry_path: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Derive all computable system metrics from the registry.

    This is the read-only projection of ``organvm metrics calculate`` —
    it computes and returns the metrics without writing any files.

    Parameters
    ----------
    registry_path:
        Optional path to a registry file or split-registry directory.
    workspace:
        Optional workspace root. When provided, word counts and code/test
        file counts are computed and included in the result.
    """
    from organvm_engine.metrics.calculator import compute_metrics
    from organvm_engine.registry.loader import load_registry

    registry = load_registry(registry_path)
    ws = Path(workspace) if workspace else None
    return compute_metrics(registry, workspace=ws)


def metrics_word_count(
    workspace: str | None = None,
) -> dict[str, Any]:
    """Return the workspace word-count breakdown.

    Counts words across READMEs, essays, corpus docs, and org profiles,
    plus a humanized total.

    Parameters
    ----------
    workspace:
        Workspace root to scan. Defaults to ~/Workspace conventions.
    """
    from organvm_engine.metrics.calculator import count_words, format_word_count
    from organvm_engine.paths import workspace_root

    ws = Path(workspace) if workspace else workspace_root()
    counts = count_words(ws)
    total_words, total_numeric, total_short = format_word_count(counts["total"])

    return {
        "word_counts": counts,
        "total_words": total_words,
        "total_words_numeric": total_numeric,
        "total_words_short": total_short,
    }
