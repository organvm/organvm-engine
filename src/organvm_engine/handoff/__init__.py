"""Agent handoff discovery and staleness detection.

A handoff is an ``.conductor/active-handoff.md`` file written by an
originating agent for the next agent to read before doing any work. It
records constraints, locked files, conventions, and completed work.

This module discovers handoffs across every repo in the workspace, parses
their metadata, and flags ones that have gone stale — older than a
configurable age threshold. A stale handoff usually means an agent session
was abandoned without releasing its claim, leaving locked files and
constraints in force for nobody.
"""

from organvm_engine.handoff.parser import (
    DEFAULT_STALE_HOURS,
    HANDOFF_RELPATH,
    Handoff,
    discover_handoffs,
    filter_stale,
    format_handoffs,
    parse_handoff,
)

__all__ = [
    "DEFAULT_STALE_HOURS",
    "HANDOFF_RELPATH",
    "Handoff",
    "discover_handoffs",
    "filter_stale",
    "format_handoffs",
    "parse_handoff",
]
