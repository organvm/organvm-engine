"""Agent handoff discovery and staleness detection.

Walks the workspace for ``.conductor/active-handoff.md`` relay files, parses
their header metadata, and flags handoffs that have lingered past their
freshness window.
"""

from organvm_engine.handoff.scanner import (
    DEFAULT_STALE_DAYS,
    Handoff,
    discover_handoffs,
    discover_in_repo,
    filter_stale,
    parse_handoff,
)

__all__ = [
    "DEFAULT_STALE_DAYS",
    "Handoff",
    "discover_handoffs",
    "discover_in_repo",
    "filter_stale",
    "parse_handoff",
]
