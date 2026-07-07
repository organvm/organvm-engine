"""CLI handler for the pulse command group."""

from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from dataclasses import asdict
from datetime import datetime, timedelta, timezone


def _resolve_workspace_path(args: Namespace):
    """Resolve workspace from args/env/default."""
    from pathlib import Path

    raw = getattr(args, "workspace", None)
    if raw:
        return Path(raw).expanduser().resolve()
    import os

    env = os.environ.get("ORGANVM_WORKSPACE_DIR")
    if env:
        return Path(env).expanduser().resolve()
    default = Path.home() / "Workspace"
    return default if default.is_dir() else None


def _compute_pulse_data(args: Namespace):
    """Shared computation: organism + seed graph + density + mood + events.

    Returns (organism, graph, unresolved, density_point, mood_result, recent_events)
    or raises on failure.
    """
    from organvm_engine.metrics.organism import get_organism
    from organvm_engine.pulse.affective import MoodFactors, compute_mood
    from organvm_engine.pulse.density import compute_density
    from organvm_engine.pulse.events import recent
    from organvm_engine.seed.graph import build_seed_graph, validate_edge_resolution

    organism = get_organism(include_omega=False)

    workspace = _resolve_workspace_path(args)
    graph = build_seed_graph(workspace)
    unresolved = validate_edge_resolution(graph)

    dp = compute_density(graph, organism, len(unresolved))

    # Mood factors from organism + density
    total = organism.total_repos or 1
    total_stale = organism.total_stale
    gate_stats = organism.gate_stats()
    avg_gate_rate = (
        sum(g.rate for g in gate_stats) / len(gate_stats) if gate_stats else 0.0
    )

    factors = MoodFactors(
        health_pct=organism.sys_pct,
        health_velocity=0.0,
        stale_ratio=total_stale / total,
        stale_velocity=0.0,
        density_score=dp.interconnection_score,
        gate_pass_rate=avg_gate_rate,
        promo_ready_ratio=organism.total_promo_ready / total,
        session_frequency=0.0,
    )

    mood_result = compute_mood(factors)
    recent_events = recent(10)

    return organism, graph, unresolved, dp, mood_result, recent_events, factors


# ---------------------------------------------------------------------------
# Bar chart helper
# ---------------------------------------------------------------------------

_BAR_FILLED = "\u2588"
_BAR_EMPTY = "\u2591"


def _bar(pct: float, width: int = 20) -> str:
    """Render a percentage as a filled bar."""
    clamped = max(0.0, min(100.0, pct))
    filled = int(width * clamped / 100)
    return _BAR_FILLED * filled + _BAR_EMPTY * (width - filled)


# ---------------------------------------------------------------------------
# cmd_pulse_show
# ---------------------------------------------------------------------------

def cmd_pulse_show(args: Namespace) -> int:
    """Default pulse view — mood, density, recent events."""
    try:
        organism, graph, unresolved, dp, mood_result, recent_events, factors = (
            _compute_pulse_data(args)
        )
    except Exception as exc:
        print(f"Error computing pulse: {exc}", file=sys.stderr)
        return 1

    use_json = getattr(args, "json", False)

    if use_json:
        data = {
            "mood": mood_result.to_dict(),
            "density": dp.to_dict(),
            "organism": {
                "total_repos": organism.total_repos,
                "sys_pct": organism.sys_pct,
                "total_promo_ready": organism.total_promo_ready,
                "total_stale": organism.total_stale,
            },
            "recent_events": [asdict(e) for e in recent_events],
        }
        json.dump(data, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    # Human-readable output
    print()
    print(f"  {mood_result.mood.glyph}  System Mood: {mood_result.mood.value.upper()}")
    print(f"     {mood_result.mood.description}")
    print()
    for line in mood_result.reasoning:
        print(f"     \u2022 {line}")

    print()
    print(f"  Density: {dp.interconnection_score}/100")

    total_possible = len(graph.nodes) * (len(graph.nodes) - 1) if len(graph.nodes) > 1 else 1
    edge_pct = len(graph.edges) / total_possible * 100 if total_possible else 0.0

    print(f"     Edges: {len(graph.edges)} declared / {total_possible} possible"
          f" ({edge_pct:.1f}%)")

    # Cross-organ edge count
    cross_organ = 0
    outbound_organs: set[str] = set()
    for src, tgt, _ in graph.edges:
        src_org = src.split("/")[0] if "/" in src else src
        tgt_org = tgt.split("/")[0] if "/" in tgt else tgt
        if src_org != tgt_org:
            cross_organ += 1
            outbound_organs.add(src_org)
            outbound_organs.add(tgt_org)

    print(f"     Cross-organ: {cross_organ} edges, {len(outbound_organs)} organs")

    seed_count = len(graph.nodes)
    ci_count = sum(1 for r in organism.all_repos if any(
        g.name == "ci" and g.passed for g in r.gates
    ))
    test_count = sum(1 for r in organism.all_repos if any(
        g.name == "tests" and g.passed for g in r.gates
    ))
    total = organism.total_repos
    print(f"     Coverage: seeds {seed_count}/{total}, CI {ci_count}/{total},"
          f" tests {test_count}/{total}")

    if recent_events:
        print()
        print("  Recent Events:")
        for evt in recent_events:
            ts = evt.timestamp[:19] if len(evt.timestamp) >= 19 else evt.timestamp
            print(f"     [{ts}] {evt.event_type} \u2190 {evt.source}")

    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_density
# ---------------------------------------------------------------------------

def cmd_pulse_density(args: Namespace) -> int:
    """Show interconnection density metrics with per-organ breakdowns."""
    try:
        from organvm_engine.metrics.organism import get_organism
        from organvm_engine.pulse.density import compute_density
        from organvm_engine.seed.graph import build_seed_graph, validate_edge_resolution

        organism = get_organism(include_omega=False)
        workspace = _resolve_workspace_path(args)
        graph = build_seed_graph(workspace)
        unresolved = validate_edge_resolution(graph)
        dp = compute_density(graph, organism, len(unresolved))
    except Exception as exc:
        print(f"Error computing density: {exc}", file=sys.stderr)
        return 1

    use_json = getattr(args, "json", False)

    if use_json:
        json.dump(dp.to_dict(), sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    # Human-readable with per-organ bars
    print()
    print(f"  Interconnection Density: {dp.interconnection_score}/100")
    print(f"  {'─' * 50}")
    print(f"  Edges:      {dp.declared_edges} declared")
    print(f"  Unresolved: {dp.unresolved_edges}")
    print(f"  Seed nodes: {dp.repos_with_seeds}")
    print()

    # Per-organ bar charts
    organ_edges: dict[str, int] = {}
    organ_nodes: dict[str, int] = {}
    for node in graph.nodes:
        org = node.split("/")[0] if "/" in node else node
        organ_nodes[org] = organ_nodes.get(org, 0) + 1
    for src, _tgt, _ in graph.edges:
        org = src.split("/")[0] if "/" in src else src
        organ_edges[org] = organ_edges.get(org, 0) + 1

    max_edges = max(organ_edges.values()) if organ_edges else 1
    print(f"  {'Organ':<20} {'Edges':>6}  Bar")
    print(f"  {'─' * 20} {'─' * 6}  {'─' * 20}")
    for org in sorted(organ_nodes.keys()):
        count = organ_edges.get(org, 0)
        pct = count / max_edges * 100 if max_edges else 0.0
        print(f"  {org:<20} {count:>6}  {_bar(pct)}")

    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_mood
# ---------------------------------------------------------------------------

def cmd_pulse_mood(args: Namespace) -> int:
    """Show the system's affective state with reasoning."""
    try:
        organism, _graph, _unresolved, dp, mood_result, _events, factors = (
            _compute_pulse_data(args)
        )
    except Exception as exc:
        print(f"Error computing mood: {exc}", file=sys.stderr)
        return 1

    use_json = getattr(args, "json", False)

    if use_json:
        data = mood_result.to_dict()
        data["inputs"] = factors.to_dict()
        json.dump(data, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    print()
    print(f"  {mood_result.mood.glyph}  Mood: {mood_result.mood.value.upper()}")
    print(f"     {mood_result.mood.description}")
    print()
    print("  Reasoning:")
    for line in mood_result.reasoning:
        print(f"     \u2022 {line}")
    print()
    print("  Inputs:")
    print(f"     Health:           {factors.health_pct}%")
    print(f"     Health velocity:  {factors.health_velocity:.2f}")
    print(f"     Stale ratio:     {factors.stale_ratio:.2f}")
    print(f"     Stale velocity:  {factors.stale_velocity:.2f}")
    print(f"     Density score:   {factors.density_score}/100")
    print(f"     Gate pass rate:  {factors.gate_pass_rate:.1f}%")
    print(f"     Promo ready:     {factors.promo_ready_ratio:.2f}")
    print(f"     Session freq:    {factors.session_frequency:.2f}")
    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_events
# ---------------------------------------------------------------------------

def cmd_pulse_events(args: Namespace) -> int:
    """Show the event log, optionally filtered by type and time."""
    from organvm_engine.pulse.events import replay

    event_type = getattr(args, "type", None)
    limit = getattr(args, "limit", 20)
    since_days = getattr(args, "since_days", None)

    since: str | None = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(since_days))
        since = cutoff.isoformat()

    try:
        events = replay(since=since, event_type=event_type, limit=limit)
    except Exception as exc:
        print(f"Error reading events: {exc}", file=sys.stderr)
        return 1

    use_json = getattr(args, "json", False)

    if use_json:
        json.dump([asdict(e) for e in events], sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    if not events:
        print("  No events found.")
        return 0

    print()
    print(f"  {'Timestamp':<22} {'Type':<25} {'Source':<12} Payload")
    print(f"  {'─' * 22} {'─' * 25} {'─' * 12} {'─' * 20}")
    for evt in events:
        ts = evt.timestamp[:19] if len(evt.timestamp) >= 19 else evt.timestamp
        payload_str = json.dumps(evt.payload, separators=(",", ":")) if evt.payload else ""
        if len(payload_str) > 40:
            payload_str = payload_str[:37] + "..."
        print(f"  {ts:<22} {evt.event_type:<25} {evt.source:<12} {payload_str}")
    print()
    print(f"  {len(events)} event(s) shown")
    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_nerve
# ---------------------------------------------------------------------------

def cmd_pulse_nerve(args: Namespace) -> int:
    """Show subscription wiring from seed.yaml event declarations."""
    try:
        from organvm_engine.pulse.nerve import resolve_subscriptions
    except ImportError as exc:
        print(f"Error: nerve module not available: {exc}", file=sys.stderr)
        return 1

    try:
        workspace = _resolve_workspace_path(args)
        bundle = resolve_subscriptions(workspace)
    except Exception as exc:
        print(f"Error resolving subscriptions: {exc}", file=sys.stderr)
        return 1

    use_json = getattr(args, "json", False)

    if use_json:
        json.dump(bundle.to_dict(), sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    if not bundle.subscriptions:
        print("  No subscriptions found.")
        return 0

    total = len(bundle.subscriptions)
    by_event = bundle.by_event

    print()
    print(f"  Subscription Wiring: {total} total, {len(by_event)} event types")
    print(f"  {'─' * 50}")
    for etype in sorted(by_event.keys()):
        subs = by_event[etype]
        print(f"\n  {etype} ({len(subs)} subscriber(s)):")
        for sub in subs:
            if sub.action:
                print(f"     \u2192 {sub.subscriber}  [{sub.action}]")
            else:
                print(f"     \u2192 {sub.subscriber}")

    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_emit
# ---------------------------------------------------------------------------

def cmd_pulse_emit(args: Namespace) -> int:
    """Manually emit an event and show who would be notified."""
    from organvm_engine.pulse.events import emit

    event_type = args.event_type
    source = getattr(args, "source", "cli") or "cli"
    payload_str = getattr(args, "payload", None)

    payload: dict = {}
    if payload_str:
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError as exc:
            print(f"Error: invalid JSON payload: {exc}", file=sys.stderr)
            return 1

    try:
        event = emit(event_type, source, payload)
    except Exception as exc:
        print(f"Error emitting event: {exc}", file=sys.stderr)
        return 1

    use_json = getattr(args, "json", False)

    # Resolve subscriptions to show who gets notified
    notified: list[dict] = []
    try:
        from organvm_engine.pulse.nerve import propagate, resolve_subscriptions

        workspace = _resolve_workspace_path(args)
        bundle = resolve_subscriptions(workspace)
        notified = propagate(event, bundle)
    except ImportError:
        pass
    except Exception:
        pass

    if use_json:
        data = {
            "emitted": asdict(event),
            "notified": notified,
        }
        json.dump(data, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    ts = event.timestamp[:19] if len(event.timestamp) >= 19 else event.timestamp
    print()
    print(f"  Emitted: {event.event_type}")
    print(f"     Source:    {event.source}")
    print(f"     Time:      {ts}")
    if event.payload:
        print(f"     Payload:   {json.dumps(event.payload, separators=(',', ':'))}")

    if notified:
        print()
        print(f"  Notified ({len(notified)} subscriber(s)):")
        for n in notified:
            subscriber = n.get("subscriber", "?")
            action = n.get("action", "")
            if action:
                print(f"     \u2192 {subscriber}  [{action}]")
            else:
                print(f"     \u2192 {subscriber}")
    else:
        print()
        print("  No subscribers matched this event type.")

    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_briefing
# ---------------------------------------------------------------------------

def cmd_pulse_briefing(args: Namespace) -> int:
    """Show a session briefing — recent activity summary for onboarding."""
    from organvm_engine.pulse.continuity import briefing_to_markdown, build_briefing

    hours = getattr(args, "hours", 24)

    try:
        briefing = build_briefing(hours=hours)
    except Exception as exc:
        print(f"Error building briefing: {exc}", file=sys.stderr)
        return 1

    use_json = getattr(args, "json", False)

    if use_json:
        json.dump(briefing.to_dict(), sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    md = briefing_to_markdown(briefing)
    print(md)
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_memory
# ---------------------------------------------------------------------------

def cmd_pulse_memory(args: Namespace) -> int:
    """Query the cross-agent shared memory store."""
    from organvm_engine.pulse.shared_memory import (
        insight_summary,
        query_insights,
    )

    use_json = getattr(args, "json", False)
    show_summary = getattr(args, "summary", False)

    if show_summary:
        summary = insight_summary()
        if use_json:
            json.dump(summary, sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
        else:
            total = summary.get("total", 0)
            print()
            print(f"  Shared Memory: {total} insight(s)")
            by_cat = summary.get("by_category", {})
            if by_cat:
                print("  By category:")
                for cat, count in sorted(by_cat.items()):
                    print(f"     {cat}: {count}")
            by_agent = summary.get("by_agent", {})
            if by_agent:
                print("  By agent:")
                for agent, count in sorted(by_agent.items()):
                    print(f"     {agent}: {count}")
            print()
        return 0

    category = getattr(args, "category", None)
    agent_filter = getattr(args, "agent", None)
    limit = getattr(args, "limit", 20)

    try:
        insights = query_insights(
            category=category,
            agent=agent_filter,
            limit=limit,
        )
    except Exception as exc:
        print(f"Error querying memory: {exc}", file=sys.stderr)
        return 1

    if use_json:
        json.dump(
            [i.to_dict() for i in insights], sys.stdout, indent=2, default=str,
        )
        sys.stdout.write("\n")
        return 0

    if not insights:
        print("  No insights found.")
        return 0

    print()
    for ins in insights:
        ts = ins.timestamp[:19] if len(ins.timestamp) >= 19 else ins.timestamp
        scope = ""
        if ins.organ:
            scope = f" [{ins.organ}"
            if ins.repo:
                scope += f"/{ins.repo}"
            scope += "]"
        tags_str = ""
        if ins.tags:
            tags_str = f" ({', '.join(ins.tags)})"
        print(f"  [{ts}] {ins.category} ({ins.agent}){scope}{tags_str}")
        print(f"     {ins.content}")
        print()

    print(f"  {len(insights)} insight(s) shown")
    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_flow
# ---------------------------------------------------------------------------

def cmd_pulse_flow(args: Namespace) -> int:
    """Show dependency flow — which edges are active, warm, or dormant."""
    from organvm_engine.pulse.flow import compute_flow

    workspace = _resolve_workspace_path(args)
    hours = getattr(args, "hours", 168)

    try:
        from organvm_engine.seed.graph import build_seed_graph

        graph = build_seed_graph(workspace)
        profile = compute_flow(graph, hours=hours)
    except Exception as exc:
        print(f"Error computing flow: {exc}", file=sys.stderr)
        return 1

    use_json = getattr(args, "json", False)

    if use_json:
        json.dump(profile.to_dict(), sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    print()
    print(f"  Flow Score: {profile.flow_score}/100")
    print(f"  Active: {profile.active_count}  "
          f"Warm: {profile.warm_count}  "
          f"Dormant: {profile.dormant_count}")
    print()

    if profile.hotspots:
        print("  Hotspots (most active edges):")
        for node in profile.hotspots:
            print(f"     {node}")
        print()

    if profile.edges:
        # Show a compact table of edge activity
        print(f"  {'Source':<30} {'Target':<30} {'Type':<15} Level")
        print(f"  {'─' * 30} {'─' * 30} {'─' * 15} {'─' * 10}")
        for ea in profile.edges:
            src = ea.source[:29]
            tgt = ea.target[:29]
            print(f"  {src:<30} {tgt:<30} {ea.edge_type:<15} {ea.activity_level}")
        print()

    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_ecosystem
# ---------------------------------------------------------------------------

def cmd_pulse_ecosystem(args: Namespace) -> int:
    """Show ecosystem universality — archetype coverage across all organs."""
    from organvm_engine.pulse.ecosystem_bridge import ORGAN_ARCHETYPES

    use_json = getattr(args, "json", False)
    organ_filter = getattr(args, "organ", None)

    try:
        from organvm_engine.pulse.ecosystem_bridge import compute_ecosystem_coverage

        coverage = compute_ecosystem_coverage(_resolve_workspace_path(args))
    except Exception as exc:
        print(f"Error computing ecosystem coverage: {exc}", file=sys.stderr)
        return 1

    if use_json:
        json.dump(coverage.to_dict(), sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    d = coverage.to_dict()
    print()
    print("  Ecosystem Coverage")
    print(f"  {'─' * 50}")
    print(f"  Total repos:          {d['total_repos']}")
    print(f"  With ecosystem.yaml:  {d['repos_with_ecosystem_yaml']}")
    print(f"  With inferred context: {d['repos_with_context']}")
    print(f"  Explicit coverage:    {d['coverage_pct']}%")
    print(f"  Universal coverage:   {d['universal_coverage_pct']}%")
    print()

    by_arch = d.get("by_archetype", {})
    if by_arch:
        print(f"  {'Archetype':<20} Count")
        print(f"  {'─' * 20} {'─' * 6}")
        for arch in sorted(by_arch.keys()):
            print(f"  {arch:<20} {by_arch[arch]:>5}")
        print()

    by_organ = d.get("by_organ", {})
    if by_organ:
        print(f"  {'Organ':<20} {'Total':>6} {'Ecosystem':>10}")
        print(f"  {'─' * 20} {'─' * 6} {'─' * 10}")
        for organ_key in sorted(by_organ.keys()):
            if organ_filter and organ_key != organ_filter:
                continue
            info = by_organ[organ_key]
            total = info.get("total", 0)
            eco = info.get("with_ecosystem_yaml", 0)
            print(f"  {organ_key:<20} {total:>6} {eco:>10}")
        print()

    # Show archetypes reference
    print("  Organ Archetypes:")
    for organ_key, info in sorted(ORGAN_ARCHETYPES.items()):
        if organ_filter and organ_key != organ_filter:
            continue
        print(f"    {organ_key}: {info['archetype']} — {info['pillars']}")
    print()

    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_scan
# ---------------------------------------------------------------------------

def cmd_pulse_scan(args: Namespace) -> int:
    """Run all sensors, compute AMMOI, store snapshot."""
    from organvm_engine.pulse.rhythm import pulse_once

    workspace = _resolve_workspace_path(args)
    run_sensors = not getattr(args, "no_sensors", False)
    use_json = getattr(args, "json", False)

    try:
        ammoi = pulse_once(workspace=workspace, run_sensors=run_sensors)
    except Exception as exc:
        print(f"Error during pulse scan: {exc}", file=sys.stderr)
        return 1

    if use_json:
        json.dump(ammoi.to_dict(), sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    print()
    print(f"  Pulse #{ammoi.pulse_count + 1} complete")
    print(f"  System density: {ammoi.system_density:.1%}")
    print(f"  Hierarchy: 8 organs → {ammoi.total_entities} repos → {ammoi.total_modules} modules")
    print(f"  Active edges: {ammoi.active_edges}")
    print(f"  Events (24h): {ammoi.event_frequency_24h}")

    if ammoi.density_delta_24h:
        sign = "+" if ammoi.density_delta_24h > 0 else ""
        print(f"  Delta (24h): {sign}{ammoi.density_delta_24h:.1%}")

    print()
    print(f"  {ammoi.compressed_text}")
    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_ammoi
# ---------------------------------------------------------------------------

def cmd_pulse_ammoi(args: Namespace) -> int:
    """Show AMMOI density snapshot at system, organ, or repo scale."""
    from organvm_engine.pulse.ammoi import compute_ammoi

    workspace = _resolve_workspace_path(args)
    organ_filter = getattr(args, "organ", None)
    _repo_filter = getattr(args, "repo", None)  # reserved for future per-repo AMMOI
    use_json = getattr(args, "json", False)

    try:
        ammoi = compute_ammoi(workspace=workspace)
    except Exception as exc:
        print(f"Error computing AMMOI: {exc}", file=sys.stderr)
        return 1

    if use_json:
        if organ_filter and organ_filter in ammoi.organs:
            json.dump(ammoi.organs[organ_filter].to_dict(), sys.stdout, indent=2)
        else:
            json.dump(ammoi.to_dict(), sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    # Human-readable
    print()
    print(f"  AMMOI — System Density: {ammoi.system_density:.1%}")
    print(f"  {'─' * 50}")
    print(f"  Entities:  {ammoi.total_entities}")
    print(f"  Edges:     {ammoi.active_edges}")
    print(f"  Events:    {ammoi.event_frequency_24h} (24h)")

    if ammoi.density_delta_24h is not None or ammoi.density_delta_7d is not None:
        print()
        print("  Temporal:")
        if ammoi.density_delta_24h is not None:
            s = "+" if ammoi.density_delta_24h > 0 else ""
            print(f"     Δ24h: {s}{ammoi.density_delta_24h:.1%}")
        if ammoi.density_delta_7d is not None:
            s = "+" if ammoi.density_delta_7d > 0 else ""
            print(f"     Δ7d:  {s}{ammoi.density_delta_7d:.1%}")
        delta_30d = getattr(ammoi, "density_delta_30d", None)
        if delta_30d is not None:
            s = "+" if delta_30d > 0 else ""
            print(f"     Δ30d: {s}{delta_30d:.1%}")

    print()
    if ammoi.organs:
        print(f"  {'Organ':<20} {'Repos':>6} {'Edges':>8} {'Gate%':>6} {'Density':>8}")
        print(f"  {'─' * 20} {'─' * 6} {'─' * 8} {'─' * 6} {'─' * 8}")
        for oid in sorted(ammoi.organs.keys()):
            od = ammoi.organs[oid]
            if organ_filter and oid != organ_filter:
                continue
            total_edges = od.internal_edges + od.cross_edges
            print(
                f"  {oid:<20} {od.repo_count:>6} {total_edges:>8} "
                f"{od.avg_gate_pct:>5}% {od.density:>7.1%}",
            )
        print()

    print(f"  {ammoi.compressed_text}")
    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_history
# ---------------------------------------------------------------------------

def cmd_pulse_history(args: Namespace) -> int:
    """Show AMMOI history for temporal analysis."""
    from organvm_engine.pulse.rhythm import pulse_history

    days = getattr(args, "days", 30)
    use_json = getattr(args, "json", False)

    try:
        snapshots = pulse_history(days=days)
    except Exception as exc:
        print(f"Error reading history: {exc}", file=sys.stderr)
        return 1

    if use_json:
        json.dump(snapshots, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    if not snapshots:
        print("  No AMMOI history found. Run `organvm pulse scan` to start.")
        return 0

    print()
    print(f"  AMMOI History — last {days} days ({len(snapshots)} snapshots)")
    print(f"  {'─' * 60}")
    print(f"  {'Timestamp':<22} {'Density':>8} {'Entities':>9} {'Edges':>7} {'Ev24h':>6}")
    print(f"  {'─' * 22} {'─' * 8} {'─' * 9} {'─' * 7} {'─' * 6}")

    for snap in snapshots:
        ts = snap.get("timestamp", "")[:19]
        density = snap.get("system_density", 0.0)
        entities = snap.get("total_entities", 0)
        edges = snap.get("active_edges", 0)
        ev24h = snap.get("event_frequency_24h", 0)
        print(f"  {ts:<22} {density:>7.1%} {entities:>9} {edges:>7} {ev24h:>6}")

    # Trend summary
    if len(snapshots) >= 2:
        first = snapshots[0].get("system_density", 0.0)
        last = snapshots[-1].get("system_density", 0.0)
        delta = last - first
        direction = "↑" if delta > 0 else "↓" if delta < 0 else "→"
        sign = "+" if delta > 0 else ""
        print()
        print(f"  Trend: {direction} {sign}{delta:.1%} over {len(snapshots)} snapshots")

    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_tensions
# ---------------------------------------------------------------------------

def cmd_pulse_tensions(args: Namespace) -> int:
    """Show current tensions: orphans, naming conflicts, overcoupling."""
    from organvm_engine.pulse.inference_bridge import run_inference

    workspace = _resolve_workspace_path(args)
    use_json = getattr(args, "json", False)

    try:
        summary = run_inference(workspace)
    except Exception as exc:
        print(f"Error running inference: {exc}", file=sys.stderr)
        return 1

    if use_json:
        json.dump(summary.to_dict(), sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    if not summary.tensions:
        print("  No tensions detected.")
        return 0

    print()
    print(f"  Tensions: {summary.tension_count} detected")
    print(f"  Inference score: {summary.inference_score:.0%}")
    print(f"  {'─' * 50}")

    for t in summary.tensions:
        severity = t.get("severity", 0.0)
        ttype = t.get("type", "unknown")
        desc = t.get("description", "")
        bar = "!" * int(severity * 5)
        print(f"  [{ttype:<18}] {bar:<5} {desc}")

    if summary.orphaned_entities:
        print()
        print(f"  Orphaned entities ({len(summary.orphaned_entities)}):")
        for eid in summary.orphaned_entities[:10]:
            print(f"     {eid}")
        if len(summary.orphaned_entities) > 10:
            print(f"     ... and {len(summary.orphaned_entities) - 10} more")

    if summary.overcoupled_entities:
        print()
        print(f"  Overcoupled entities ({len(summary.overcoupled_entities)}):")
        for eid in summary.overcoupled_entities[:10]:
            print(f"     {eid}")

    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_clusters
# ---------------------------------------------------------------------------

def cmd_pulse_clusters(args: Namespace) -> int:
    """Show detected entity clusters with cohesion scores."""
    from organvm_engine.pulse.inference_bridge import run_inference

    workspace = _resolve_workspace_path(args)
    use_json = getattr(args, "json", False)

    try:
        summary = run_inference(workspace)
    except Exception as exc:
        print(f"Error running inference: {exc}", file=sys.stderr)
        return 1

    if use_json:
        json.dump({"clusters": summary.clusters, "count": summary.cluster_count},
                  sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    if not summary.clusters:
        print("  No clusters detected.")
        return 0

    print()
    print(f"  Entity Clusters: {summary.cluster_count} detected")
    print(f"  {'─' * 50}")

    for i, cluster in enumerate(summary.clusters, 1):
        size = cluster.get("size", len(cluster.get("entity_ids", [])))
        cohesion = cluster.get("cohesion", 0.0)
        print(f"\n  Cluster {i}: {size} entities, cohesion {cohesion:.2f}")
        for eid in cluster.get("entity_ids", [])[:8]:
            print(f"     {eid}")
        remaining = size - 8
        if remaining > 0:
            print(f"     ... and {remaining} more")

    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_advisories
# ---------------------------------------------------------------------------

def cmd_pulse_advisories(args: Namespace) -> int:
    """Show governance advisories, or acknowledge one."""
    from organvm_engine.pulse.advisories import acknowledge_advisory, read_advisories

    use_json = getattr(args, "json", False)

    # Handle "ack" sub-subcommand
    ack_id = getattr(args, "ack_id", None)
    if ack_id:
        ok = acknowledge_advisory(ack_id)
        if use_json:
            json.dump({"acknowledged": ok, "advisory_id": ack_id}, sys.stdout)
            sys.stdout.write("\n")
        elif ok:
            print(f"  Advisory {ack_id} acknowledged.")
        else:
            print(f"  Advisory {ack_id} not found.")
        return 0 if ok else 1

    limit = getattr(args, "limit", 20)
    unacked = getattr(args, "unacked", False)

    try:
        advisories = read_advisories(limit=limit, unacked_only=unacked)
    except Exception as exc:
        print(f"Error reading advisories: {exc}", file=sys.stderr)
        return 1

    if use_json:
        json.dump([a.to_dict() for a in advisories], sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    if not advisories:
        print("  No advisories found.")
        return 0

    print()
    print(f"  Governance Advisories ({len(advisories)} shown)")
    print(f"  {'─' * 60}")
    print(f"  {'ID':<14} {'Severity':<10} {'Action':<10} {'Entity':<20} Description")
    print(f"  {'─' * 14} {'─' * 10} {'─' * 10} {'─' * 20} {'─' * 20}")

    for adv in advisories:
        ack_mark = " [ack]" if adv.acknowledged else ""
        print(
            f"  {adv.advisory_id:<14} "
            f"{adv.severity:<10} "
            f"{adv.action:<10} "
            f"{adv.entity_name:<20} "
            f"{adv.description}{ack_mark}",
        )

    print()
    print("  Use `organvm pulse advisories --ack <id>` to acknowledge.")
    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_blast
# ---------------------------------------------------------------------------

def cmd_pulse_blast(args: Namespace) -> int:
    """Show blast radius for a specific entity."""
    from organvm_engine.pulse.inference_bridge import blast_radius

    entity = args.entity
    use_json = getattr(args, "json", False)

    result = blast_radius(entity)

    if use_json:
        json.dump(result, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    if "error" in result:
        print(f"  Error: {result['error']}")
        return 1

    print()
    print(f"  Blast Radius: {result.get('entity_name', entity)}")
    print(f"  UID: {result.get('entity_uid', '?')}")
    print(f"  Total affected: {result.get('total_affected', 0)}")
    print(f"  {'─' * 50}")
    print(f"  Upward:   {result.get('upward', 0)}")
    print(f"  Downward: {result.get('downward', 0)}")
    print(f"  Lateral:  {result.get('lateral', 0)}")

    paths = result.get("paths", [])
    if paths:
        print()
        for p in paths:
            direction = p.get("direction", "?")
            target = p.get("target_id", "?")
            distance = p.get("distance", 0)
            print(f"  [{direction:<10}] d={distance} → {target}")

    print()
    return 0


# ---------------------------------------------------------------------------
# LaunchAgent management: start / stop / status
# ---------------------------------------------------------------------------


def cmd_pulse_start(args: Namespace) -> int:
    """Install and start the pulse LaunchAgent."""
    from organvm_engine.pulse.rhythm import (
        PLIST_LABEL,
        install_launchagent,
        launchagent_status,
    )

    interval = getattr(args, "interval", 900)
    use_json = getattr(args, "json", False)

    # Install plist
    plist_path = install_launchagent(interval=interval)

    # Load via launchctl
    try:
        # Unload first if already loaded (idempotent)
        subprocess.run(
            ["launchctl", "unload", plist_path],
            capture_output=True,
            timeout=5,
            check=False,
        )
        result = subprocess.run(
            ["launchctl", "load", plist_path],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            msg = result.stderr.strip() or "unknown error"
            if use_json:
                json.dump({"error": msg}, sys.stdout)
                sys.stdout.write("\n")
            else:
                print(f"  Error loading LaunchAgent: {msg}", file=sys.stderr)
            return 1
    except Exception as exc:
        if use_json:
            json.dump({"error": str(exc)}, sys.stdout)
            sys.stdout.write("\n")
        else:
            print(f"  Error: {exc}", file=sys.stderr)
        return 1

    if use_json:
        json.dump(launchagent_status(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print()
        print("  Pulse LaunchAgent installed and started.")
        print(f"  Label:    {PLIST_LABEL}")
        print(f"  Interval: {interval}s ({interval // 60}m)")
        print(f"  Plist:    {plist_path}")
        print()

    return 0


def cmd_pulse_stop(args: Namespace) -> int:
    """Stop and uninstall the pulse LaunchAgent."""
    from organvm_engine.pulse.rhythm import (
        PLIST_PATH,
        uninstall_launchagent,
    )

    use_json = getattr(args, "json", False)

    # Unload if running
    if PLIST_PATH.exists():
        import contextlib

        with contextlib.suppress(Exception):
            subprocess.run(
                ["launchctl", "unload", str(PLIST_PATH)],
                capture_output=True,
                timeout=5,
                check=False,
            )

    removed = uninstall_launchagent()

    if use_json:
        json.dump({"stopped": True, "removed": removed}, sys.stdout)
        sys.stdout.write("\n")
    else:
        print()
        if removed:
            print("  Pulse LaunchAgent stopped and removed.")
        else:
            print("  Pulse LaunchAgent was not installed.")
        print()

    return 0


def cmd_pulse_status(args: Namespace) -> int:
    """Show pulse LaunchAgent status and recent log output."""
    from organvm_engine.pulse.rhythm import launchagent_status

    use_json = getattr(args, "json", False)
    status = launchagent_status()

    if use_json:
        json.dump(status, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    print()
    installed = status.get("installed", False)
    running = status.get("running", False)

    state = "RUNNING" if running else ("STOPPED" if installed else "NOT INSTALLED")
    color = "\033[32m" if running else ("\033[33m" if installed else "\033[31m")
    reset = "\033[0m"

    print(f"  Pulse Daemon: {color}{state}{reset}")
    print(f"  Plist:        {status.get('plist_path', 'N/A')}")
    print(f"  Log:          {status.get('log_path', 'N/A')}")

    if status.get("pid"):
        print(f"  PID:          {status['pid']}")

    if status.get("log_lines"):
        print(f"  Log entries:  {status['log_lines']}")

    if status.get("last_log"):
        print(f"  Last log:     {status['last_log']}")

    # Show last AMMOI snapshot
    try:
        from organvm_engine.pulse.ammoi import _read_history

        history = _read_history(limit=1)
        if history:
            last = history[-1]
            print()
            print(f"  Last pulse:   {last.timestamp[:19]}")
            print(f"  Density:      {last.system_density:.1%}")
            print(f"  Entities:     {last.total_entities}")
    except Exception:
        pass

    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_pulse_edges
# ---------------------------------------------------------------------------

def cmd_pulse_edges(args: Namespace) -> int:
    """Show structural edge counts or sync seed edges into ontologia."""
    sub_action = getattr(args, "edges_action", None)
    use_json = getattr(args, "json", False)

    if sub_action == "sync":
        return _cmd_pulse_edges_sync(args)

    # Default: show edge counts
    try:
        from ontologia.registry.store import open_store

        store = open_store()
        ei = store.edge_index
        hierarchy = ei.all_hierarchy_edges()
        relations = ei.all_relation_edges()
        active_h = [e for e in hierarchy if e.is_active()]
        active_r = [e for e in relations if e.is_active()]

        # Relation type breakdown
        by_type: dict[str, int] = {}
        for e in active_r:
            by_type[e.relation_type] = by_type.get(e.relation_type, 0) + 1

        # Cross-organ edge count
        cross_organ = 0

        # Build child→parent mapping for organ resolution
        child_to_organ: dict[str, str] = {}
        for edge in active_h:
            child_to_organ[edge.child_id] = edge.parent_id

        for edge in active_r:
            src_organ = child_to_organ.get(edge.source_id, "")
            tgt_organ = child_to_organ.get(edge.target_id, "")
            if src_organ and tgt_organ and src_organ != tgt_organ:
                cross_organ += 1

    except ImportError:
        if use_json:
            json.dump({"error": "ontologia not available"}, sys.stdout)
            sys.stdout.write("\n")
        else:
            print("  Error: ontologia not available.")
        return 1
    except Exception as exc:
        if use_json:
            json.dump({"error": str(exc)}, sys.stdout)
            sys.stdout.write("\n")
        else:
            print(f"  Error: {exc}", file=sys.stderr)
        return 1

    if use_json:
        data = {
            "hierarchy_edges": len(active_h),
            "relation_edges": len(active_r),
            "total_edges": len(active_h) + len(active_r),
            "cross_organ_edges": cross_organ,
            "by_relation_type": by_type,
        }
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print()
    print("  Structural Edges")
    print(f"  {'─' * 40}")
    print(f"  Hierarchy (organ→repo): {len(active_h)}")
    print(f"  Relations (repo→repo):  {len(active_r)}")
    print(f"  Total:                  {len(active_h) + len(active_r)}")
    print(f"  Cross-organ:            {cross_organ}")

    if by_type:
        print()
        print("  By relation type:")
        for rtype, count in sorted(by_type.items()):
            print(f"     {rtype:<20} {count}")

    print()
    return 0


def _cmd_pulse_edges_sync(args: Namespace) -> int:
    """Sync seed.yaml edges into ontologia."""
    from organvm_engine.pulse.edge_bridge import sync_seed_edges

    use_json = getattr(args, "json", False)
    workspace = _resolve_workspace_path(args)

    try:
        result = sync_seed_edges(workspace)
    except Exception as exc:
        if use_json:
            json.dump({"error": str(exc)}, sys.stdout)
            sys.stdout.write("\n")
        else:
            print(f"  Error syncing edges: {exc}", file=sys.stderr)
        return 1

    if use_json:
        json.dump(result.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print()
    print("  Edge Sync Result")
    print(f"  {'─' * 40}")
    print(f"  Created:    {result.created}")
    print(f"  Skipped:    {result.skipped}")
    print(f"  Unresolved: {result.unresolved}")
    print(f"  Total:      {result.created + result.skipped + result.unresolved}")
    print()
    return 0


def cmd_pulse_temporal(args: Namespace) -> int:
    """Show temporal profile — velocity, acceleration, and trends."""
    from organvm_engine.pulse.ammoi import _read_history, extract_timeseries
    from organvm_engine.pulse.temporal import compute_temporal_profile

    use_json = getattr(args, "json", False)
    window = getattr(args, "window", 7)
    limit = getattr(args, "limit", 50)

    history = _read_history(limit=limit)
    if len(history) < 3:
        if use_json:
            json.dump({"error": "insufficient history", "snapshots": len(history)}, sys.stdout)
            sys.stdout.write("\n")
        else:
            print(f"  Insufficient history ({len(history)} snapshots, need >= 3).")
            print("  Run `organvm pulse scan` a few times to build history.")
        return 0

    timeseries = extract_timeseries(history)
    profile = compute_temporal_profile(timeseries, window=window)

    if use_json:
        json.dump(profile.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print()
    print(f"  Temporal Profile ({len(history)} snapshots, window={window})")
    print(f"  {'─' * 60}")
    print(f"  Dominant trend: {profile.dominant_trend.value}")
    print(f"  Total momentum: {profile.total_momentum:.4f}")
    print()
    print(f"  {'Metric':<22} {'Current':>8} {'Velocity':>10} {'Accel':>10} {'Trend':<14}")
    print(f"  {'─' * 22} {'─' * 8} {'─' * 10} {'─' * 10} {'─' * 14}")
    for m in profile.metrics:
        vel_sign = "+" if m.velocity > 0 else ""
        print(
            f"  {m.name:<22} {m.current:>8.2f} "
            f"{vel_sign}{m.velocity:>9.4f} "
            f"{m.acceleration:>10.4f}  {m.trend.value:<14}",
        )
    print()
    return 0


def cmd_pulse_relations(args: Namespace) -> int:
    """Query multi-scale relations for an entity."""
    from organvm_engine.pulse.graph import query_relations

    entity = args.entity

    rmap = query_relations(
        entity,
        include_seed=not getattr(args, "no_seed", False),
        include_indexer=not getattr(args, "no_indexer", False),
        include_ontologia=not getattr(args, "no_ontologia", False),
    )

    if getattr(args, "json", False):
        print(json.dumps(rmap.to_dict(), indent=2))
        return 0

    print(f"  Relations for: {rmap.entity}")
    if rmap.entity_uid:
        print(f"  UID: {rmap.entity_uid}  Type: {rmap.entity_type}")
    print(f"  Total edges: {rmap.total_edges}")
    print()

    if rmap.seed_produces or rmap.seed_consumes:
        print("  Inter-Repo (seed graph)")
        print("  " + "─" * 50)
        for e in rmap.seed_produces:
            print(f"    produces → {e.target}  [{e.metadata.get('artifact_type', '')}]")
        for e in rmap.seed_consumes:
            print(f"    consumes ← {e.source}  [{e.metadata.get('artifact_type', '')}]")
        print()

    if rmap.imports_from or rmap.imported_by:
        print("  Intra-Repo (import graph)")
        print("  " + "─" * 50)
        for e in rmap.imports_from:
            print(f"    imports → {e.target}")
        for e in rmap.imported_by:
            print(f"    imported by ← {e.source}")
        print()

    if rmap.hierarchy_parents or rmap.hierarchy_children or rmap.ontologia_relations:
        print("  Entity-Level (ontologia)")
        print("  " + "─" * 50)
        for e in rmap.hierarchy_parents:
            print(f"    parent ↑ {e.source}")
        for e in rmap.hierarchy_children:
            print(f"    child  ↓ {e.target}")
        for e in rmap.ontologia_relations:
            print(f"    {e.relation_type} → {e.target}")
        print()

    return 0


def cmd_pulse_entity_memory(args: Namespace) -> int:
    """Aggregate all signals about an entity from every data source."""
    from organvm_engine.pulse.memory import aggregate_entity_memory

    entity = args.entity
    limit = getattr(args, "limit", 50)

    mem = aggregate_entity_memory(
        entity,
        include_pulse=not getattr(args, "no_pulse", False),
        include_insights=not getattr(args, "no_insights", False),
        include_ontologia=not getattr(args, "no_ontologia", False),
        include_continuity=not getattr(args, "no_continuity", False),
        include_metrics=not getattr(args, "no_metrics", False),
        limit=limit,
    )

    if getattr(args, "json", False):
        print(json.dumps(mem.to_dict(), indent=2))
        return 0

    print(f"  Entity Memory: {mem.entity}")
    if mem.entity_uid:
        print(f"  UID: {mem.entity_uid}  Type: {mem.entity_type}")
        print(f"  Lifecycle: {mem.lifecycle_status}")
    print(f"  Total signals: {mem.total_signals}")
    print()

    if mem.pulse_events:
        print(f"  Pulse Events ({mem.pulse_event_count})")
        print("  " + "─" * 50)
        for ev in mem.pulse_events[-10:]:
            print(f"    {ev['timestamp'][:19]}  {ev['event_type']:20s}  {ev['source']}")
        print()

    if mem.insights:
        print(f"  Shared Memory ({mem.insight_count})")
        print("  " + "─" * 50)
        for ins in mem.insights[-10:]:
            print(f"    [{ins['category']}] {ins['content'][:60]}")
        print()

    if mem.name_history:
        print(f"  Name History ({len(mem.name_history)})")
        print("  " + "─" * 50)
        for nr in mem.name_history:
            primary = "*" if nr["is_primary"] else " "
            print(f"    {primary} {nr['display_name']:30s}  from {nr['valid_from'][:19]}")
        print()

    if mem.ontologia_events:
        print(f"  Ontologia Events ({mem.ontologia_event_count})")
        print("  " + "─" * 50)
        for ev in mem.ontologia_events[-10:]:
            print(f"    {ev['timestamp'][:19]}  {ev['event_type']}")
        print()

    if mem.recent_claims:
        print(f"  Continuity Claims ({len(mem.recent_claims)})")
        print("  " + "─" * 50)
        for claim in mem.recent_claims[:5]:
            print(f"    {claim}")
        print()

    return 0
