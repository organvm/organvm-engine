"""Seed CLI commands."""

import argparse


def cmd_seed_ownership(args: argparse.Namespace) -> int:
    """Show ownership declarations for a repo's seed.yaml."""
    from organvm_engine.seed.discover import discover_seeds
    from organvm_engine.seed.ownership import (
        get_ai_agents,
        get_collaborators,
        get_lead,
        get_review_gates,
        has_ownership,
    )
    from organvm_engine.seed.reader import read_seed

    seeds = discover_seeds(args.workspace)
    target = args.repo

    for path in seeds:
        seed = read_seed(path)
        repo_name = seed.get("repo", "")
        org = seed.get("org", "")
        if target in (repo_name, f"{org}/{repo_name}"):
            if not has_ownership(seed):
                print(f"  {org}/{repo_name}: no ownership section (v1.0 seed — solo-operator mode)")
                return 0

            lead = get_lead(seed)
            collabs = get_collaborators(seed)
            agents = get_ai_agents(seed)
            gates = get_review_gates(seed)

            print(f"  Repo: {org}/{repo_name}")
            print(f"  Lead: {lead or '(none)'}")

            if collabs:
                print(f"\n  Collaborators ({len(collabs)}):")
                for c in collabs:
                    organs = ", ".join(c.get("organs", []))
                    access = ", ".join(c.get("access", []))
                    print(f"    {c['handle']:12s}  role={c.get('role', '?'):12s}  access=[{access}]")
                    if organs:
                        print(f"    {'':12s}  organs=[{organs}]  since={c.get('since', '?')}")

            if agents:
                print(f"\n  AI Agents ({len(agents)}):")
                for a in agents:
                    access = ", ".join(a.get("access", []))
                    print(f"    {a['type']:12s}  access=[{access}]  scope={a.get('scope', '?')}")

            if gates:
                print("\n  Review Gates:")
                for gate_name, requires in gates.items():
                    print(f"    {gate_name}: {', '.join(requires)}")

            return 0

    print(f"  ERROR: No seed.yaml found for '{target}'")
    return 1


def cmd_seed_discover(args: argparse.Namespace) -> int:
    from organvm_engine.seed.discover import discover_seeds

    seeds = discover_seeds(args.workspace)
    print(f"Found {len(seeds)} seed.yaml files:\n")
    for path in seeds:
        # Show as org/repo
        parts = path.parts
        repo = parts[-2]
        org = parts[-3]
        print(f"  {org}/{repo}")
    return 0


def cmd_seed_validate(args: argparse.Namespace) -> int:
    from organvm_engine.seed.discover import discover_seeds
    from organvm_engine.seed.reader import get_consumes, get_produces, read_seed

    seeds = discover_seeds(args.workspace)
    errors = 0

    for path in seeds:
        try:
            seed = read_seed(path)
            required = ["schema_version", "organ", "repo", "org"]
            missing = [f for f in required if f not in seed]
            if missing:
                print(f"  FAIL {path.parent.name}: missing {', '.join(missing)}")
                errors += 1
            else:
                produces = get_produces(seed)
                consumes = get_consumes(seed)
                
                if not produces and not consumes:
                    print(f"  WARN {seed.get('org')}/{seed.get('repo')}: zero produces/consumes edges (LEX-IV Metabolism violation)")
                else:
                    print(f"  PASS {seed.get('org')}/{seed.get('repo')}")
        except Exception as e:
            print(f"  FAIL {path}: {e}")
            errors += 1

    print(f"\n{len(seeds) - errors} passed, {errors} failed")
    return 1 if errors > 0 else 0


def cmd_seed_graph(args: argparse.Namespace) -> int:
    from organvm_engine.seed.graph import build_seed_graph

    graph = build_seed_graph(args.workspace)
    print(graph.summary())
    return 0
