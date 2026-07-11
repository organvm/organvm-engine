"""CLI commands for the BIFRONS portal (engine half).

    organvm portal status                       Show portal store counts
    organvm portal import-stars [--write]       Compile star dossiers -> resonance edges
    organvm portal convergences [--min-repos N] Cross-organ convergence points
    organvm portal propose <external> <target>  Generate a transmutation proposal

BIFRONS (Janus, two-faced) is the star<->contribution portal; distinct from
IANVA (the MCP doorway).
"""

from __future__ import annotations

import argparse

from organvm_engine.network.convergence import convergence_report, find_convergences
from organvm_engine.network.resonance import InternalRepo
from organvm_engine.network.star_importer import import_stars
from organvm_engine.portal import store
from organvm_engine.portal.proposals import propose_transmutation


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
