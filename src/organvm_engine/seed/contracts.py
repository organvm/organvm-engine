"""Interface contract validation for seed.yaml declarations.

Implements: SPEC-007, INTF-001 through INTF-005

Validates that produces/consumes edges in seed.yaml are well-formed,
checks signal compatibility between producers and consumers, and
enforces promotion contract monotonicity (Liskov): a promoted repo
must satisfy all prior contracts plus any new ones.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Canonical signal types (from formation protocol)
# ---------------------------------------------------------------------------

CANONICAL_SIGNAL_TYPES: frozenset[str] = frozenset({
    "RESEARCH_QUESTION",
    "ONT_FRAGMENT",
    "RULE_PROPOSAL",
    "STATE_MODEL",
    "ARCHIVE_PACKET",
    "ANNOTATED_CORPUS",
    "PEDAGOGICAL_UNIT",
    "EXECUTION_TRACE",
    "FAILURE_REPORT",
    "MIGRATION_CANDIDATE",
    "AESTHETIC_PROFILE",
    "INTERFACE_CONTRACT",
    "SYNTHESIS_PACKET",
    "VALIDATION_RECORD",
})


# ---------------------------------------------------------------------------
# Edge validation helpers
# ---------------------------------------------------------------------------

def _validate_edge_entry(
    entry: Any,
    direction: str,
    index: int,
) -> list[str]:
    """Validate a single produces or consumes entry.

    Args:
        entry:     The edge entry (should be a dict with at least 'type').
        direction: "produces" or "consumes" (for error messages).
        index:     Position in the list (for error messages).

    Returns:
        List of error strings (empty if valid).
    """
    errors: list[str] = []
    prefix = f"{direction}[{index}]"

    if isinstance(entry, str):
        # Bare string entries are tolerated but lack structure
        errors.append(f"{prefix}: bare string entry '{entry}' — should be a dict with 'type'")
        return errors

    if not isinstance(entry, dict):
        errors.append(f"{prefix}: expected dict, got {type(entry).__name__}")
        return errors

    # 'type' is required (INTF-001)
    if "type" not in entry:
        errors.append(f"{prefix}: missing required field 'type'")
    elif not isinstance(entry["type"], str):
        errors.append(f"{prefix}: 'type' must be a string")
    elif not entry["type"].strip():
        errors.append(f"{prefix}: 'type' must not be empty")

    # 'source' on consumes must be a string if present (INTF-002)
    if direction == "consumes" and "source" in entry and not isinstance(entry["source"], str):
        errors.append(f"{prefix}: 'source' must be a string")

    # 'consumers' on produces must be a list if present (INTF-003)
    if direction == "produces" and "consumers" in entry and not isinstance(entry["consumers"], list):
        errors.append(f"{prefix}: 'consumers' must be a list")

    return errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_contract(seed_data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate that produces/consumes edges are well-formed.

    Checks (INTF-001 through INTF-003):
      - Every edge entry is a dict with a non-empty 'type' string.
      - consumes entries with 'source' must have a string value.
      - produces entries with 'consumers' must have a list value.
      - No duplicate type declarations within produces or consumes.

    Args:
        seed_data: Parsed seed.yaml dict.

    Returns:
        (valid, errors) tuple.
    """
    errors: list[str] = []

    if "produces" not in seed_data:
        errors.append("missing required field 'produces'")
    if "consumes" not in seed_data:
        errors.append("missing required field 'consumes'")

    produces = seed_data.get("produces") or []
    consumes = seed_data.get("consumes") or []

    if not isinstance(produces, list):
        errors.append("'produces' must be a list")
        produces = []
    if not isinstance(consumes, list):
        errors.append("'consumes' must be a list")
        consumes = []

    # Validate individual entries
    for i, entry in enumerate(produces):
        errors.extend(_validate_edge_entry(entry, "produces", i))
    for i, entry in enumerate(consumes):
        errors.extend(_validate_edge_entry(entry, "consumes", i))

    # Check for duplicate types within produces (INTF-004)
    produces_types: list[str] = []
    for entry in produces:
        if isinstance(entry, dict) and isinstance(entry.get("type"), str):
            produces_types.append(entry["type"])
    seen: set[str] = set()
    for t in produces_types:
        if t in seen:
            errors.append(f"produces: duplicate type '{t}'")
        seen.add(t)

    # Check for duplicate (type, source) pairs within consumes (INTF-005)
    consumes_keys: list[tuple[str, str]] = []
    for entry in consumes:
        if isinstance(entry, dict) and isinstance(entry.get("type"), str):
            source = entry.get("source", "") if isinstance(entry.get("source"), str) else ""
            consumes_keys.append((entry["type"], source))
    seen_keys: set[tuple[str, str]] = set()
    for key in consumes_keys:
        if key in seen_keys:
            label = f"({key[0]}, source={key[1]!r})" if key[1] else f"({key[0]})"
            errors.append(f"consumes: duplicate entry {label}")
        seen_keys.add(key)

    return (len(errors) == 0, errors)


def check_signal_compatibility(
    producer_signals: list[dict[str, Any]],
    consumer_signals: list[dict[str, Any]],
) -> list[str]:
    """Check whether consumer signal expectations are met by producers.

    A mismatch occurs when a consumer declares a consumes type that no
    producer provides.

    Args:
        producer_signals: List of produces entries (each a dict with 'type').
        consumer_signals: List of consumes entries (each a dict with 'type').

    Returns:
        List of mismatch descriptions (empty if fully compatible).
    """
    mismatches: list[str] = []

    # Build set of produced types
    produced_types: set[str] = set()
    for entry in producer_signals:
        if isinstance(entry, dict):
            ptype = entry.get("type", "")
            if ptype:
                produced_types.add(ptype)
        elif isinstance(entry, str):
            produced_types.add(entry)

    # Check each consumer signal
    for entry in consumer_signals:
        if isinstance(entry, dict):
            ctype = entry.get("type", "")
        elif isinstance(entry, str):
            ctype = entry
        else:
            mismatches.append(f"invalid consumer entry: {entry!r}")
            continue

        if ctype and ctype not in produced_types:
            mismatches.append(f"consumer expects '{ctype}' but no producer provides it")

    return mismatches


def check_promotion_contract_monotonicity(
    current_seed: dict[str, Any],
    previous_seed: dict[str, Any],
) -> bool:
    """Check that a promoted repo satisfies all prior contracts.

    Liskov principle for seeds: after promotion, the repo must still
    produce at least everything it produced before.  It may add new
    produces entries, but removing one breaks downstream consumers.

    Args:
        current_seed:  The seed after promotion/update.
        previous_seed: The seed before promotion/update.

    Returns:
        True if monotonicity holds (no produces entries were removed).
    """
    previous_produces = previous_seed.get("produces") or []
    current_produces = current_seed.get("produces") or []

    # Build sets of produced types
    def _types(entries: list) -> set[str]:
        result: set[str] = set()
        for entry in entries:
            if isinstance(entry, dict):
                t = entry.get("type", "")
                if t:
                    result.add(t)
            elif isinstance(entry, str) and entry:
                result.add(entry)
        return result

    prev_types = _types(previous_produces)
    curr_types = _types(current_produces)

    # All previous types must still be present
    return prev_types.issubset(curr_types)
