"""MCP tool functions for the dispatch CLI (LIMEN-060).

Exposes dispatch payload creation, validation, and routing as pure
functions returning JSON-serializable dicts. Consumed by the MCP server
in organvm-mcp-server — these functions do NOT depend on the MCP SDK.

Three tools:
    dispatch_validate — validate a payload structure (+ optional contract)
    dispatch_create   — build a well-formed dispatch payload
    dispatch_route    — find repos subscribed to an event via seed.yaml
"""

from __future__ import annotations

from typing import Any


def dispatch_validate(
    payload: dict[str, Any],
    check_contract: bool = False,
) -> dict[str, Any]:
    """Validate a dispatch payload structure.

    Parameters
    ----------
    payload:
        The dispatch payload dict to validate.
    check_contract:
        Also verify the payload against a registered event contract
        (if one exists for the payload's event type).
    """
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["payload must be a mapping"]}

    if check_contract:
        from organvm_engine.dispatch.payload import validate_payload_with_contract

        valid, errors, contract_found = validate_payload_with_contract(payload)
        return {
            "valid": valid,
            "errors": errors,
            "contract_checked": True,
            "contract_found": contract_found,
        }

    from organvm_engine.dispatch.payload import validate_payload

    valid, errors = validate_payload(payload)
    return {
        "valid": valid,
        "errors": errors,
        "contract_checked": False,
    }


def dispatch_create(
    event: str,
    source_organ: str,
    target_organ: str,
    payload_data: dict[str, Any] | None = None,
    priority: str = "normal",
    source_org: str | None = None,
    source_repo: str | None = None,
    target_org: str | None = None,
    target_repo: str | None = None,
) -> dict[str, Any]:
    """Build a well-formed dispatch payload.

    Parameters
    ----------
    event:
        Event type (must contain a dot, e.g. ``theory.published``).
    source_organ:
        Source organ identifier.
    target_organ:
        Target organ identifier.
    payload_data:
        Event-specific data dict.
    priority:
        Event priority: ``low``, ``normal``, ``high``, or ``critical``.
    source_org, source_repo, target_org, target_repo:
        Optional GitHub org/repo coordinates for source and target.
    """
    from organvm_engine.dispatch.payload import create_payload, validate_payload

    if not event:
        return {"created": False, "error": "event is required"}
    if not source_organ or not target_organ:
        return {"created": False, "error": "source_organ and target_organ are required"}

    payload = create_payload(
        event=event,
        source_organ=source_organ,
        target_organ=target_organ,
        payload_data=payload_data or {},
        priority=priority,
        source_org=source_org,
        source_repo=source_repo,
        target_org=target_org,
        target_repo=target_repo,
    )

    valid, errors = validate_payload(payload)
    return {
        "created": True,
        "valid": valid,
        "errors": errors,
        "payload": payload,
    }


def dispatch_route(
    event_type: str,
    source_organ: str,
    payload_data: dict[str, Any] | None = None,
    workspace: str | None = None,
    orgs: list[str] | None = None,
) -> dict[str, Any]:
    """Find all repos subscribed to an event, with contract verification.

    Scans every seed.yaml in the workspace for matching subscriptions
    (event + source organ) and returns the matches. When ``payload_data``
    is supplied, the payload is also verified against the event contract.

    Parameters
    ----------
    event_type:
        Event type to route (e.g. ``governance.updated``).
    source_organ:
        Organ where the event originated.
    payload_data:
        Optional payload to verify against the event contract.
    workspace:
        Root workspace directory for seed.yaml discovery.
    orgs:
        Restrict scanning to these org directory names.
    """
    from organvm_engine.dispatch.router import route_event_verified
    from organvm_engine.seed.discover import discover_seeds
    from organvm_engine.seed.reader import read_seed, seed_identity

    if not event_type or not source_organ:
        return {"error": "event_type and source_organ are required"}

    all_seeds: dict[str, dict] = {}
    for path in discover_seeds(workspace, orgs):
        try:
            seed = read_seed(path)
        except Exception:  # skip unparseable seeds
            continue
        all_seeds[seed_identity(seed)] = seed

    receipt = route_event_verified(
        event_type,
        source_organ,
        all_seeds,
        payload_data=payload_data,
    )
    return receipt.to_dict()
