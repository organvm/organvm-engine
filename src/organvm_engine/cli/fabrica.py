"""CLI handler for the fabrica command group.

Commands:
    fabrica release   -- Create a new RelayPacket (enter RELEASE phase)
    fabrica catch     -- Generate ApproachVectors for a packet (CATCH phase)
    fabrica handoff   -- Dispatch tasks to agent backends (HANDOFF phase)
    fabrica fortify   -- Review and approve dispatched work (FORTIFY phase)
    fabrica status    -- Show active relay cycles and dispatch records
    fabrica log       -- Show the full transition log for a relay cycle
    fabrica heartbeat -- Run a heartbeat cycle or manage the LaunchAgent daemon
"""

from __future__ import annotations

import json
import sys
import time


def cmd_fabrica_release(args) -> int:
    """Create a new RelayPacket and transition to CATCH."""
    from organvm_engine.fabrica.models import RelayPacket, RelayPhase
    from organvm_engine.fabrica.state import valid_transition
    from organvm_engine.fabrica.store import log_transition, save_packet

    raw_text = getattr(args, "text", None)
    source = getattr(args, "source", "cli")
    organ_hint = getattr(args, "organ", None)
    tags_str = getattr(args, "tags", None)
    tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

    if not raw_text:
        print("Error: --text is required", file=sys.stderr)
        return 1

    packet = RelayPacket(
        raw_text=raw_text,
        source=source,
        organ_hint=organ_hint,
        tags=tags,
    )

    save_packet(packet)

    # Transition RELEASE → CATCH
    if valid_transition(RelayPhase.RELEASE, RelayPhase.CATCH):
        log_transition(packet.id, RelayPhase.RELEASE, RelayPhase.CATCH, reason="auto")

    as_json = getattr(args, "json", False)
    if as_json:
        json.dump(packet.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"Released packet {packet.id}")
        print(f"  text:  {raw_text[:80]}{'...' if len(raw_text) > 80 else ''}")
        print(f"  organ: {organ_hint or '(none)'}")
        print(f"  tags:  {', '.join(tags) or '(none)'}")
        print("  phase: RELEASE → CATCH")

    return 0


def cmd_fabrica_catch(args) -> int:
    """Generate or list ApproachVectors for a packet."""
    from organvm_engine.fabrica.models import ApproachVector, RelayPhase
    from organvm_engine.fabrica.state import valid_transition
    from organvm_engine.fabrica.store import (
        load_packet,
        load_vectors,
        log_transition,
        save_vector,
    )

    packet_id = getattr(args, "packet_id", None)
    thesis = getattr(args, "thesis", None)
    select = getattr(args, "select", None)
    list_mode = getattr(args, "list", False)

    if not packet_id:
        print("Error: --packet-id is required", file=sys.stderr)
        return 1

    packet = load_packet(packet_id)
    if packet is None:
        print(f"Error: packet {packet_id!r} not found", file=sys.stderr)
        return 1

    # List existing vectors
    if list_mode or (not thesis and not select):
        vectors = load_vectors(packet_id=packet_id)
        if not vectors:
            print(f"No vectors for packet {packet_id}. Use --thesis to create one.")
            return 0
        as_json = getattr(args, "json", False)
        if as_json:
            json.dump([v.to_dict() for v in vectors], sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print(f"Vectors for packet {packet_id}:")
            for v in vectors:
                sel = " *" if v.selected else ""
                print(f"  {v.id}  [{v.scope}]  {v.thesis[:60]}{'...' if len(v.thesis) > 60 else ''}{sel}")
        return 0

    # Select a vector
    if select:
        vectors = load_vectors(packet_id=packet_id)
        target = None
        for v in vectors:
            if v.id.startswith(select):
                target = v
                break
        if target is None:
            print(f"Error: vector {select!r} not found for packet {packet_id}", file=sys.stderr)
            return 1
        target.selected = True
        save_vector(target)
        if valid_transition(RelayPhase.CATCH, RelayPhase.HANDOFF):
            log_transition(packet_id, RelayPhase.CATCH, RelayPhase.HANDOFF, reason="vector selected")
        print(f"Selected vector {target.id} → phase CATCH → HANDOFF")
        return 0

    # Create a new vector. Reaching here implies --thesis was provided (the
    # list/select branches above return first); guard explicitly so the type is
    # narrowed and the contract is self-documenting.
    if not thesis:
        print(f"Error: --thesis is required to create a vector for packet {packet_id}", file=sys.stderr)
        return 1
    organs_str = getattr(args, "organs", None)
    target_organs = [o.strip() for o in organs_str.split(",") if o.strip()] if organs_str else []
    scope = getattr(args, "scope", "medium")
    agents_str = getattr(args, "agents", None)
    agent_types = [a.strip() for a in agents_str.split(",") if a.strip()] if agents_str else []

    vector = ApproachVector(
        packet_id=packet_id,
        thesis=thesis,
        target_organs=target_organs,
        scope=scope,
        agent_types=agent_types,
    )
    save_vector(vector)

    as_json = getattr(args, "json", False)
    if as_json:
        json.dump(vector.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"Created vector {vector.id} for packet {packet_id}")
        print(f"  thesis: {thesis[:80]}{'...' if len(thesis) > 80 else ''}")
        print(f"  scope:  {scope}")
        print(f"  organs: {', '.join(target_organs) or '(none)'}")
        print(f"  agents: {', '.join(agent_types) or '(none)'}")

    return 0


def cmd_fabrica_handoff(args) -> int:
    """Dispatch a task to an agent backend during HANDOFF phase."""
    from organvm_engine.fabrica.backends import VALID_BACKENDS, get_backend
    from organvm_engine.fabrica.models import RelayIntent, RelayPhase
    from organvm_engine.fabrica.state import valid_transition
    from organvm_engine.fabrica.store import (
        load_active_intents,
        load_packet,
        log_transition,
        save_dispatch,
        save_intent,
    )

    packet_id = getattr(args, "packet_id", None)
    backend_name = getattr(args, "backend", None)
    repo = getattr(args, "repo", None)
    title = getattr(args, "title", None)
    body = getattr(args, "body", "")
    task_id = getattr(args, "task_id", None)
    dry_run = not getattr(args, "execute", False)

    if not packet_id:
        print("Error: --packet-id is required", file=sys.stderr)
        return 1
    if not backend_name:
        print(f"Error: --backend is required. Valid: {', '.join(sorted(VALID_BACKENDS))}", file=sys.stderr)
        return 1
    if backend_name not in VALID_BACKENDS:
        print(f"Error: unknown backend {backend_name!r}. Valid: {', '.join(sorted(VALID_BACKENDS))}", file=sys.stderr)
        return 1
    if not repo:
        print("Error: --repo is required", file=sys.stderr)
        return 1

    packet = load_packet(packet_id)
    if packet is None:
        print(f"Error: packet {packet_id!r} not found", file=sys.stderr)
        return 1

    # Use title from args or derive from packet
    if not title:
        title = packet.raw_text[:72]

    # Generate a task_id if not provided
    if not task_id:
        import hashlib
        task_id = hashlib.sha256(f"{packet_id}:{title}:{time.time()}".encode()).hexdigest()[:16]

    # Find or create an intent for this packet
    active = load_active_intents()
    intent = next((i for i in active if i.packet_id == packet_id), None)
    if intent is None:
        # Create a minimal intent
        from organvm_engine.fabrica.store import load_vectors
        vectors = load_vectors(packet_id=packet_id)
        selected = next((v for v in vectors if v.selected), None)
        vector_id = selected.id if selected else "auto"
        intent = RelayIntent(vector_id=vector_id, packet_id=packet_id)
        save_intent(intent)

    # Dispatch to the backend
    backend = get_backend(backend_name)
    labels_str = getattr(args, "labels", None)
    labels = [l.strip() for l in labels_str.split(",") if l.strip()] if labels_str else None
    branch = getattr(args, "branch", None)

    record = backend.dispatch(
        task_id=task_id,
        intent_id=intent.id,
        repo=repo,
        title=title,
        body=body or packet.raw_text,
        labels=labels,
        branch=branch,
        dry_run=dry_run,
    )

    save_dispatch(record)

    # Transition to FORTIFY
    if valid_transition(RelayPhase.HANDOFF, RelayPhase.FORTIFY):
        log_transition(packet_id, RelayPhase.HANDOFF, RelayPhase.FORTIFY, reason=f"dispatched to {backend_name}")

    as_json = getattr(args, "json", False)
    if as_json:
        json.dump(record.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        mode = "LIVE" if not dry_run else "DRY-RUN"
        print(f"[{mode}] Dispatched to {backend_name}")
        print(f"  record:  {record.id}")
        print(f"  task:    {task_id}")
        print(f"  target:  {record.target}")
        print(f"  status:  {record.status.value}")

    return 0


def cmd_fabrica_fortify(args) -> int:
    """Review dispatched work and render a verdict."""
    from organvm_engine.fabrica.backends import get_backend
    from organvm_engine.fabrica.models import DispatchStatus, RelayPhase
    from organvm_engine.fabrica.state import valid_transition
    from organvm_engine.fabrica.store import (
        load_dispatches,
        log_transition,
        save_dispatch,
    )

    intent_id = getattr(args, "intent_id", None)
    verdict = getattr(args, "verdict", None)  # approve | reject | recycle
    record_id = getattr(args, "record_id", None)
    check = getattr(args, "check", False)

    # Status check mode: poll all dispatches for updates
    if check:
        dispatches = load_dispatches(intent_id=intent_id)
        if not dispatches:
            print("No dispatches found.")
            return 0

        updated = 0
        for record in dispatches:
            if record.status in (DispatchStatus.MERGED, DispatchStatus.REJECTED, DispatchStatus.FORTIFIED):
                continue
            try:
                backend = get_backend(record.backend)
                new_record = backend.check_status(record)
                if new_record.status != record.status:
                    save_dispatch(new_record)
                    updated += 1
                    print(f"  {record.id}  {record.status.value} → {new_record.status.value}")
            except (KeyError, Exception) as exc:
                print(f"  {record.id}  check failed: {exc}", file=sys.stderr)

        if updated == 0:
            print("All dispatches unchanged.")
        else:
            print(f"\n{updated} dispatch(es) updated.")
        return 0

    # Verdict mode
    if not verdict:
        print("Error: --verdict is required (approve | reject | recycle)", file=sys.stderr)
        return 1

    dispatches = load_dispatches(intent_id=intent_id)
    if record_id:
        dispatches = [d for d in dispatches if d.id == record_id]

    if not dispatches:
        print("No matching dispatches found.", file=sys.stderr)
        return 1

    for record in dispatches:
        if verdict == "approve":
            record.verdict = "approved"
            record.status = DispatchStatus.FORTIFIED
            record.returned_at = record.returned_at or time.time()
        elif verdict == "reject":
            record.verdict = "rejected"
            record.status = DispatchStatus.REJECTED
            record.returned_at = record.returned_at or time.time()
        elif verdict == "recycle":
            record.verdict = "recycle"
            # Recycle transitions back to CATCH
        else:
            print(f"Error: unknown verdict {verdict!r}", file=sys.stderr)
            return 1

        save_dispatch(record)
        print(f"  {record.id}  verdict={verdict}  status={record.status.value}")

    # Log phase transition based on verdict
    if dispatches:
        packet_id = _packet_id_from_dispatches(dispatches)
        if packet_id:
            if verdict == "approve":
                if valid_transition(RelayPhase.FORTIFY, RelayPhase.COMPLETE):
                    log_transition(packet_id, RelayPhase.FORTIFY, RelayPhase.COMPLETE, reason="approved")
            elif verdict == "reject":
                if valid_transition(RelayPhase.FORTIFY, RelayPhase.COMPLETE):
                    log_transition(packet_id, RelayPhase.FORTIFY, RelayPhase.COMPLETE, reason="rejected")
            elif verdict == "recycle" and valid_transition(RelayPhase.FORTIFY, RelayPhase.CATCH):
                log_transition(packet_id, RelayPhase.FORTIFY, RelayPhase.CATCH, reason="recycled")

    return 0


def cmd_fabrica_status(args) -> int:
    """Show active relay cycles and dispatch records."""
    from organvm_engine.fabrica.store import (
        load_active_intents,
        load_dispatches,
        load_packets,
        load_transitions,
        load_vectors,
    )

    as_json = getattr(args, "json", False)
    packet_filter = getattr(args, "packet_id", None)

    packets = load_packets()
    if packet_filter:
        packets = [p for p in packets if p.id.startswith(packet_filter)]

    if not packets:
        print("No relay cycles found.")
        return 0

    if as_json:
        data = []
        for p in packets:
            transitions = load_transitions(packet_id=p.id)
            vectors = load_vectors(packet_id=p.id)
            dispatches = []
            for intent in load_active_intents():
                if intent.packet_id == p.id:
                    dispatches.extend(load_dispatches(intent_id=intent.id))
            current_phase = transitions[-1]["to"] if transitions else p.phase.value
            data.append({
                "packet": p.to_dict(),
                "current_phase": current_phase,
                "vector_count": len(vectors),
                "dispatch_count": len(dispatches),
                "transitions": len(transitions),
            })
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print(f"Fabrica Status — {len(packets)} relay cycle(s)\n")
    for p in packets:
        transitions = load_transitions(packet_id=p.id)
        vectors = load_vectors(packet_id=p.id)
        current_phase = transitions[-1]["to"] if transitions else p.phase.value

        preview = p.raw_text[:60].replace("\n", " ")
        print(f"  {p.id}  [{current_phase.upper():8s}]  {preview}{'...' if len(p.raw_text) > 60 else ''}")
        print(f"    source={p.source}  vectors={len(vectors)}  transitions={len(transitions)}")

        # Show dispatches
        for intent in load_active_intents():
            if intent.packet_id == p.id:
                dispatches = load_dispatches(intent_id=intent.id)
                for d in dispatches:
                    print(f"    → [{d.backend:10s}]  {d.status.value:15s}  {d.target[:50]}")
        print()

    return 0


def cmd_fabrica_log(args) -> int:
    """Show the full transition log for a relay cycle."""
    from organvm_engine.fabrica.store import load_transitions

    packet_id = getattr(args, "packet_id", None)
    as_json = getattr(args, "json", False)

    transitions = load_transitions(packet_id=packet_id)

    if not transitions:
        if packet_id:
            print(f"No transitions for packet {packet_id}.")
        else:
            print("No transitions recorded.")
        return 0

    if as_json:
        json.dump(transitions, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print(f"Transition Log — {len(transitions)} event(s)\n")
    for t in transitions:
        from datetime import datetime, timezone
        ts = datetime.fromtimestamp(t["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        reason = f"  ({t['reason']})" if t.get("reason") else ""
        pid = t["packet_id"][:8]
        print(f"  {ts}  {pid}  {t['from']:8s} → {t['to']:8s}{reason}")

    return 0


def cmd_fabrica_heartbeat(args) -> int:
    """Run a heartbeat cycle or manage the LaunchAgent daemon."""
    import logging

    install = getattr(args, "install", False)
    uninstall = getattr(args, "uninstall", False)
    interval = getattr(args, "interval", 900)
    as_json = getattr(args, "json", False)

    if install and uninstall:
        print("Error: --install and --uninstall are mutually exclusive", file=sys.stderr)
        return 1

    from organvm_engine.fabrica.heartbeat import (
        install_launchagent,
        run_heartbeat,
        uninstall_launchagent,
    )

    if install:
        try:
            install_launchagent(interval=interval)
            return 0
        except Exception as exc:
            print(f"Error installing LaunchAgent: {exc}", file=sys.stderr)
            return 1

    if uninstall:
        try:
            uninstall_launchagent()
            return 0
        except Exception as exc:
            print(f"Error uninstalling LaunchAgent: {exc}", file=sys.stderr)
            return 1

    # Run a single heartbeat cycle
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    report = run_heartbeat(quiet=False, json_output=as_json)
    return 0 if report.errors == 0 else 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _packet_id_from_dispatches(dispatches: list) -> str | None:
    """Recover the packet_id by tracing intent_id → intent → packet_id."""
    if not dispatches:
        return None
    from organvm_engine.fabrica.store import load_intents
    intent_id = dispatches[0].intent_id
    intents = load_intents()
    for intent in intents:
        if intent.id == intent_id:
            return intent.packet_id
    return None
