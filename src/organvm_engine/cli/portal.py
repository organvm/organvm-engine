"""CLI commands for the BIFRONS portal (engine half).

    organvm portal status                       Show portal store counts
    organvm portal import-stars [--write]       Compile star dossiers -> resonance edges
    organvm portal convergences [--min-repos N] Cross-organ convergence points
    organvm portal propose <external> <target>  Generate a transmutation proposal

  Loop-driving verbs (the exchange lifecycle, end to end):

    organvm portal prepare  <external>          Inbound: proposal -> draft internal PR
    organvm portal candidate <external> --kind K --rationale R
                                                Outbound: evidence -> contribution candidate
    organvm portal package  <external>          Outbound: worktree+checks -> prepared packet
    organvm portal submit   <external> [--approve --checks-passing] [--execute]
                                                The single human-gated external-write boundary
    organvm portal backflow <external> --outcome {merged|declined|dormant} [--write]
                                                Seven-organ backflow -> BACKFLOW_COMPLETE

BIFRONS (Janus, two-faced) is the star<->contribution portal; distinct from
IANVA (the MCP doorway). The same starred repo is both absorbed (inbound) and
contributed-to (outbound); one exchange_id threads the whole traversal.
"""

from __future__ import annotations

import argparse

from organvm_engine.network.convergence import convergence_report, find_convergences
from organvm_engine.network.resonance import InternalRepo
from organvm_engine.network.star_importer import import_stars
from organvm_engine.portal import store
from organvm_engine.portal.proposals import prepare_internal_pr, propose_transmutation


def _internal_repos_from_registry() -> list[InternalRepo]:
    """Best-effort ORGANVM repo descriptors from the registry (for mapping)."""
    try:
        from organvm_engine.registry.loader import load_registry
        from organvm_engine.registry.query import list_repos

        registry = load_registry()
        repos: list[InternalRepo] = []
        for organ, entry in list_repos(registry):
            name = entry.get("name") or entry.get("repo") or ""
            if not name:
                continue
            lang = entry.get("language") or entry.get("primary_language") or ""
            topics = set(entry.get("topics") or [])
            repos.append(InternalRepo(
                name=name,
                organ=str(organ),
                languages={lang} if lang else set(),
                topics={t.lower() for t in topics},
                description=entry.get("description", "") or "",
            ))
        return repos
    except Exception:
        return []


def cmd_portal_status(args: argparse.Namespace) -> int:
    conn = store.connect(getattr(args, "db", None))
    store.init_exchange_schema(conn)
    counts = store.counts(conn)
    print("BIFRONS PORTAL —")
    print(f"  db: {getattr(args, 'db', None) or store.default_db_path()}")
    try:
        ex = conn.execute(
            "SELECT state, COUNT(*) n FROM exchange GROUP BY state ORDER BY n DESC",
        ).fetchall()
        print("  exchanges by state:")
        for row in ex:
            print(f"    {row['state']}: {row['n']}")
    except Exception:
        pass
    for key, val in counts.items():
        print(f"  {key}: {val}")
    conn.close()
    return 0


def cmd_portal_import_stars(args: argparse.Namespace) -> int:
    conn = store.connect(getattr(args, "db", None))
    internal = _internal_repos_from_registry()
    print(f"BIFRONS IMPORT-STARS — mapping against {len(internal)} internal repos...")
    if not internal:
        print("  (no internal repos resolved from registry; edges will be unresolved)")
    summary = import_stars(conn, internal)
    s = summary.as_dict()
    print(f"  dossiers={s['dossiers']}  edges={s['edges']}  "
          f"mapped={s['mapped']}  unresolved={s['unresolved']}")
    conn.close()
    return 0


def cmd_portal_convergences(args: argparse.Namespace) -> int:
    conn = store.connect(getattr(args, "db", None))
    min_repos = getattr(args, "min_repos", 2)
    if getattr(args, "json", False):
        import json
        convs = find_convergences(conn, min_repos=min_repos)
        print(json.dumps([c.as_dict() for c in convs], indent=2))
    else:
        print(convergence_report(conn, min_repos=min_repos))
    conn.close()
    return 0


def cmd_portal_propose(args: argparse.Namespace) -> int:
    conn = store.connect(getattr(args, "db", None))
    store.init_exchange_schema(conn)
    dossier = store.get_dossier(conn, args.external)
    if dossier is None:
        print(f"  no dossier for {args.external} — run 'alchemia stars dossier' first.")
        conn.close()
        return 1
    proposal = propose_transmutation(dossier, args.target)
    store.insert_transmutation_proposal(conn, proposal)
    print(f"BIFRONS PROPOSE — {proposal.external_repo} -> {proposal.target_repo}")
    print(f"  class: {proposal.klass}  license: {proposal.license_decision}")
    print(f"  abstraction: {proposal.abstraction_level}  copied_code: {proposal.copied_code}")
    print(f"  finding: {proposal.finding}")
    print(f"  proposed: {proposal.proposed_change}")
    conn.close()
    return 0


def cmd_portal_prepare(args: argparse.Namespace) -> int:
    """Inbound: realize the latest transmutation proposal as a draft internal PR."""
    conn = store.connect(getattr(args, "db", None))
    store.init_exchange_schema(conn)
    proposal = store.get_latest_proposal(conn, args.external)
    if proposal is None:
        print(f"  no transmutation proposal for {args.external} — run 'portal propose' first.")
        conn.close()
        return 1
    artifact, final_state = prepare_internal_pr(
        conn, proposal, out_dir=getattr(args, "out_dir", None),
    )
    print(f"BIFRONS PREPARE (inbound) — {args.external} -> {proposal['target_repo']}")
    print(f"  exchange: {proposal['exchange_id']}  state: {final_state}")
    print(f"  draft internal PR: {artifact}")
    print("  posture: draft-internal-PR-only (no default-branch write)")
    conn.close()
    return 0


def cmd_portal_candidate(args: argparse.Namespace) -> int:
    """Outbound: turn dossier evidence into a contribution candidate."""
    from organvm_engine.contrib.planner import InvalidCandidate, plan_candidate

    conn = store.connect(getattr(args, "db", None))
    store.init_exchange_schema(conn)
    dossier = store.get_dossier(conn, args.external)
    if dossier is None:
        print(f"  no dossier for {args.external} — run 'alchemia stars dossier' first.")
        conn.close()
        return 1
    try:
        candidate = plan_candidate(
            conn, dossier,
            kind=args.kind,
            rationale=args.rationale,
            tractability=getattr(args, "tractability", 0.5),
            testability=getattr(args, "testability", 0.5),
        )
    except InvalidCandidate as exc:
        print(f"  {exc}")
        conn.close()
        return 1
    print(f"BIFRONS CANDIDATE (outbound) — {candidate.external_repo}")
    print(f"  kind: {candidate.kind}  score: {candidate.contribution_score:.3f}")
    print(f"  exchange: {candidate.exchange_id}  status: {candidate.status}")
    conn.close()
    return 0


def cmd_portal_package(args: argparse.Namespace) -> int:
    """Outbound: plan an ephemeral workspace + checks and assemble the packet (sends nothing)."""
    from organvm_engine.contrib.executor import build_packet
    from organvm_engine.contrib.executor import prepare as prepare_contribution
    from organvm_engine.contrib.validator import plan_validation
    from organvm_engine.contrib.worktree import plan_workspace

    conn = store.connect(getattr(args, "db", None))
    store.init_exchange_schema(conn)
    candidate = store.get_latest_candidate(conn, args.external)
    if candidate is None:
        print(f"  no contribution candidate for {args.external} — run 'portal candidate' first.")
        conn.close()
        return 1
    dossier = store.get_dossier(conn, args.external) or {}
    ref = getattr(args, "ref", None) or dossier.get("snapshot_ref", "") or "HEAD"
    workspace = plan_workspace(candidate.external_repo, ref)
    manifests = dossier.get("architecture", {}).get("manifests", [])
    validation = plan_validation(
        workspace, manifests=manifests, reproduction=candidate.rationale,
    )
    packet = build_packet(candidate, dossier, workspace, validation)
    prepare_contribution(conn, candidate, packet)
    print(f"BIFRONS PACKAGE (outbound) — {candidate.external_repo}")
    print(f"  workspace: {workspace.worktree_path} @ {workspace.ref}")
    print(f"  checks: {', '.join(validation.commands)}")
    print(f"  posture: {packet['default_posture']}  (nothing sent)")
    print("  exchange advanced to PATCH_PREPARED")
    conn.close()
    return 0


def cmd_portal_submit(args: argparse.Namespace) -> int:
    """The single external-write boundary. Default posture A2: prepare, never submit."""
    from organvm_engine.contrib.executor import submit as submit_contribution
    from organvm_engine.contrib.policy import AutonomyLevel, ContributionPolicy

    conn = store.connect(getattr(args, "db", None))
    store.init_exchange_schema(conn)
    candidate = store.get_latest_candidate(conn, args.external)
    if candidate is None:
        print(f"  no contribution candidate for {args.external} — run 'portal package' first.")
        conn.close()
        return 1
    autonomy = (
        AutonomyLevel.SUBMIT_WITH_APPROVAL if args.approve else AutonomyLevel.PREPARE
    )
    policy = ContributionPolicy(autonomy=autonomy)
    result = submit_contribution(
        conn, policy, candidate, candidate.packet,
        human_approved=bool(args.approve),
        checks_passing=bool(getattr(args, "checks_passing", False)),
        execute=bool(getattr(args, "execute", False)),
    )
    print(f"BIFRONS SUBMIT (gate) — {result['external_repo']}")
    print(f"  allowed: {result['allowed']}  submitted: {result['submitted']}")
    print(f"  reason: {result['reason']}")
    if result.get("requires_human"):
        print("  requires_human: the external write is the single human-gated atom (A2 default).")
    if result.get("pr_number"):
        print(f"  upstream PR: #{result['pr_number']}")
    conn.close()
    # A refusal is a valid, successful outcome. Only a requested-but-blocked
    # external write is an error.
    if getattr(args, "execute", False) and not result["submitted"]:
        return 1
    return 0


def cmd_portal_backflow(args: argparse.Namespace) -> int:
    """Metabolize an exchange outcome through the seven organs -> BACKFLOW_COMPLETE."""
    from organvm_engine.contrib.backflow import metabolize_exchange

    conn = store.connect(getattr(args, "db", None))
    store.init_exchange_schema(conn)
    exchange = store.exchange_for_repo(conn, args.external)
    if exchange is None:
        print(f"  no exchange for {args.external}.")
        conn.close()
        return 1
    dossier = store.get_dossier(conn, args.external) or {}
    language = dossier.get("identity", {}).get("primary_language")
    signals = metabolize_exchange(
        conn,
        exchange_id=exchange["exchange_id"],
        external_repo=args.external,
        outcome=args.outcome,
        title=f"contribution to {args.external}",
        language=language,
    )
    print(f"BIFRONS BACKFLOW — {args.external}  outcome={args.outcome}")
    print(f"  exchange: {exchange['exchange_id']} -> BACKFLOW_COMPLETE")
    print(f"  {len(signals)} signals across organs:")
    for signal in signals:
        print(f"    ORGAN-{signal.organ_key}: {signal.signal_type.value} — {signal.content}")
    if getattr(args, "write", False):
        from pathlib import Path

        from organvm_engine.contrib.backflow import write_backflow_manifest

        report: dict[str, list] = {k: [] for k in ("I", "II", "III", "IV", "V", "VI", "VII")}
        for signal in signals:
            report[signal.organ_key].append(signal)
        out_dir = Path(
            getattr(args, "out_dir", None) or "~/.organvm/bifrons/backflow",
        ).expanduser()
        path = write_backflow_manifest(report, out_dir)
        print(f"  manifest: {path}")
    conn.close()
    return 0


def _best_internal_repo(conn, exchange_id: str) -> str:
    """The highest-resonance internal repo for an exchange (target for absorption)."""
    row = conn.execute(
        "SELECT internal_repo FROM resonance_edge WHERE exchange_id=? "
        "ORDER BY score DESC LIMIT 1",
        (exchange_id,),
    ).fetchone()
    return row["internal_repo"] if row else "organvm-engine"


def cmd_portal_metabolize(args: argparse.Namespace) -> int:
    """One bounded, idempotent BIFRONS beat: absorb -> map -> prepare -> surface.

    The autopoietic effector. Reuses the loop verbs, does the inbound face
    autonomously (proposals + draft internal PRs), and NEVER submits — the outbound
    contribution gate stays human-held. Fail-open: a missing alchemia CLI or a slow
    upstream degrades gracefully; the beat never breaks.
    """
    import shutil
    import subprocess
    import time

    from organvm_engine.portal.models import PortalHealthSnapshot
    from organvm_engine.portal.proposals import prepare_internal_pr
    from organvm_engine.portal.state import write_state
    from organvm_engine.portal.state_machine import ExchangeState

    started = time.monotonic()
    db = getattr(args, "db", None)
    db_path = str(db) if db else str(store.default_db_path())
    budget = int(getattr(args, "budget", 5) or 5)
    threshold = float(getattr(args, "threshold", 0.15) or 0.15)

    conn = store.connect(db)
    store.init_exchange_schema(conn)

    # 1. Absorb: sync new stars + dossier the next N (only if alchemia is present).
    absorbed = False
    if not getattr(args, "no_absorb", False) and shutil.which("alchemia"):
        for cmd in (
            ["alchemia", "stars", "sync", "--db", db_path],
            ["alchemia", "stars", "dossier", "--new", "--limit", str(budget), "--db", db_path],
        ):
            try:
                subprocess.run(cmd, check=False, capture_output=True, timeout=300)  # noqa: S603
                absorbed = True
            except (OSError, subprocess.SubprocessError):
                pass

    # 2. Map: dossiers -> resonance edges (idempotent upsert).
    internal = _internal_repos_from_registry()
    summary = import_stars(conn, internal)

    # 3. Prepare (inbound only, bounded): auto-realize draft internal PRs for the
    #    next `budget` high-resonance exchanges still at MAPPED. Converges: each is
    #    moved off MAPPED, so re-runs pick up only genuinely new stars. Never submits.
    prepared = 0
    rows = conn.execute(
        "SELECT DISTINCT e.exchange_id AS xid, e.external_repo AS repo "
        "FROM exchange e JOIN resonance_edge r ON r.exchange_id = e.exchange_id "
        "WHERE e.state = ? AND r.score >= ? LIMIT ?",
        (ExchangeState.MAPPED.value, threshold, budget),
    ).fetchall()
    for row in rows:
        dossier = store.get_dossier(conn, row["repo"])
        if not dossier:
            continue
        proposal = propose_transmutation(dossier, _best_internal_repo(conn, row["xid"]))
        store.insert_transmutation_proposal(conn, proposal)
        latest = store.get_latest_proposal(conn, row["repo"])
        if latest is not None:
            prepare_internal_pr(conn, latest, out_dir=getattr(args, "out_dir", None))
            prepared += 1

    # 4. Surface: write the observable state (organ-health probes this).
    by_state = {
        r["state"]: r["n"]
        for r in conn.execute(
            "SELECT state, COUNT(*) AS n FROM exchange GROUP BY state",
        ).fetchall()
    }
    awaiting = sum(
        by_state.get(s.value, 0)
        for s in (ExchangeState.PATCH_PREPARED, ExchangeState.HUMAN_APPROVED)
    )
    snapshot = PortalHealthSnapshot(
        generated_at=store.now_iso(),
        stars_absorbed=summary.dossiers,
        dossiers=summary.dossiers,
        resonance_edges=summary.edges,
        proposals_prepared=prepared,
        prepared_awaiting_gate=awaiting,
        exchanges_by_state=by_state,
        last_run_seconds=round(time.monotonic() - started, 3),
    )
    state_path = write_state(snapshot, directory=getattr(args, "state_dir", None))
    conn.close()

    print(f"BIFRONS METABOLIZE — absorbed={'yes' if absorbed else 'skip'}  "
          f"dossiers={summary.dossiers}  edges={summary.edges}  "
          f"prepared={prepared}  awaiting_gate={awaiting}")
    print(f"  state: {state_path}")
    return 0
