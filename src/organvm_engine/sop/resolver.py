"""Resolve SOP-skill cascade: T4 (repo) > T3 (organ) > T2 (system)."""

from __future__ import annotations

from organvm_engine.sop.discover import SOPEntry

_SCOPE_PRIORITY = {"repo": 0, "organ": 1, "system": 2, "unknown": 3}

_PROMOTION_TO_PHASE = {
    "LOCAL": "foundation",
    "CANDIDATE": "hardening",
    "PUBLIC_PROCESS": "graduation",
    "GRADUATED": "sustaining",
    "ARCHIVED": "sustaining",
}


def promotion_to_phase(status: str) -> str:
    """Map a promotion status to a lifecycle phase.

    Returns the corresponding phase, or 'any' for unrecognized statuses.
    """
    return _PROMOTION_TO_PHASE.get(status, "any")


def resolve_sop(name: str, discovered: list[SOPEntry]) -> list[SOPEntry]:
    """Return SOPs matching name, ordered most-specific first (T4→T3→T2).

    If any entry declares ``overrides: <name>``, the overridden entry is removed.
    """
    matches = [e for e in discovered if e.sop_name == name]
    return _apply_overrides(matches)


def resolve_all(
    discovered: list[SOPEntry],
    repo: str | None = None,
    organ: str | None = None,
    phase: str | None = None,
) -> list[SOPEntry]:
    """Return all active SOPs for a given repo/organ context, with overrides applied.

    Scope filtering:
    - system SOPs always included
    - organ SOPs included if ``organ`` matches ``entry.org``
    - repo SOPs included if ``repo`` matches ``entry.repo``

    Phase filtering (when ``phase`` is set):
    - Only entries with ``entry.phase == phase`` or ``entry.phase == "any"`` are included
    """
    filtered: list[SOPEntry] = []
    for e in discovered:
        if (
            e.scope == "system"
            or (e.scope == "organ" and organ and e.org == organ)
            or (e.scope == "repo" and repo and e.repo == repo)
            or (e.scope == "unknown" and (
                (repo and e.repo == repo) or (organ and e.org == organ)
            ))
        ):
            filtered.append(e)

    if phase:
        filtered = [e for e in filtered if e.phase in (phase, "any")]

    return _apply_overrides(filtered)


def _apply_overrides(entries: list[SOPEntry]) -> list[SOPEntry]:
    """Remove entries that are overridden by more-specific entries.

    An entry with ``overrides=X`` removes entries named X that do NOT
    themselves declare an override — i.e., the overrider survives.
    """
    entries = _drop_duplicate_entries(entries)
    entries = _drop_unknown_shadow_entries(entries)

    overriders: set[int] = set()
    overridden_names: set[str] = set()
    for e in entries:
        if e.overrides:
            overriders.add(id(e))
            overridden_names.add(e.overrides)

    result = [
        e for e in entries
        if id(e) in overriders or e.sop_name not in overridden_names
    ]
    return sorted(result, key=lambda e: _SCOPE_PRIORITY.get(e.scope, 99))


def _drop_duplicate_entries(entries: list[SOPEntry]) -> list[SOPEntry]:
    """Collapse exact duplicate discovery entries while preserving order."""
    result: list[SOPEntry] = []
    seen: set[tuple[str, str | None, str, str, str, str]] = set()
    for entry in entries:
        key = (
            str(entry.path),
            entry.sop_name,
            entry.scope,
            entry.phase,
            entry.org,
            entry.repo,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def _drop_unknown_shadow_entries(entries: list[SOPEntry]) -> list[SOPEntry]:
    """Remove legacy unknown-scope copies when a governed entry of that SOP exists."""
    governed_names = {
        entry.sop_name
        for entry in entries
        if entry.sop_name and entry.scope in {"system", "organ", "repo"}
    }
    if not governed_names:
        return entries
    return [
        entry for entry in entries
        if not (entry.scope == "unknown" and entry.sop_name in governed_names)
    ]
