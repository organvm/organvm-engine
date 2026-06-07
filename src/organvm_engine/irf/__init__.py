"""IRF — Index Rerum Faciendarum parser and query interface.

Parses INST-INDEX-RERUM-FACIENDARUM.md — the canonical universal work registry
for the ORGANVM system — into typed Python objects for use by the CLI,
dashboard, MCP server, and auditor components.

Public API::

    from organvm_engine.irf import IRFItem, parse_irf, parse_irf_diagnostics, irf_stats, query_irf
    from organvm_engine.irf.writer import add_item, complete_item, regenerate_stats_block

    items = parse_irf(Path("INST-INDEX-RERUM-FACIENDARUM.md"))
    stats = irf_stats(items)
    p0_items = query_irf(items, priority="P0")
    sys_items = query_irf(items, domain="SYS")
"""

from organvm_engine.irf.parser import IRFItem, irf_stats, parse_irf, parse_irf_diagnostics
from organvm_engine.irf.query import query_irf

__all__ = [
    "IRFItem",
    "irf_stats",
    "parse_irf",
    "parse_irf_diagnostics",
    "query_irf",
]
