"""CLAUDE.md section generator.

Implements: SPEC-016, EPIS-003 (context injection and epistemic routing)

Takes registry data + seed data and produces the markdown content
for auto-generated sections at each level (repo, organ, workspace).
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from organvm_engine.plans.index import PlanIndex

from organvm_engine.contextmd import AUTO_END, AUTO_START
from organvm_engine.contextmd.templates import (
    AGENTS_SECTION,
    AMMOI_SECTION,
    ATOMS_NOT_RUN_HINT,
    ATOMS_REPO_QUEUE_SECTION,
    ECOSYSTEM_STATUS_SECTION,
    LOGOS_SECTION,
    NETWORK_STATUS_SECTION,
    ONTOLOGIA_STATUS_SECTION,
    ORGAN_SECTION,
    PLAN_CONTEXT_SECTION,
    REPO_SECTION,
    SESSION_REVIEW_SECTION,
    SOP_DIRECTIVES_SECTION,
    SYSTEM_LIBRARY_SECTION,
    TRIVIUM_SECTION,
    VARIABLE_STATUS_SECTION,
    WORKSPACE_SECTION,
    format_consumes_edge,
    format_no_edges,
    format_produces_edge,
)
from organvm_engine.registry.query import find_repo, resolve_entity


def generate_repo_section(
    repo_name: str,
    org: str,
    registry: dict,
    seed: dict | None = None,
    plan_index: "PlanIndex | None" = None,
    sop_entries: list | None = None,
    agent: str | None = None,
    handoff_status_block: str = "",
) -> str:
    """Generate the auto-generated section for a repo-level CLAUDE.md / GEMINI.md."""

    resolved = resolve_entity(repo_name, registry=registry)
    if resolved and resolved.get("registry_entry"):
        organ_key, repo_data = resolved["organ_key"], resolved["registry_entry"]
    else:
        result = find_repo(registry, repo_name)
        if not result:
            return f"{AUTO_START}\n<!-- ERROR: Repo '{repo_name}' not found -->\n{AUTO_END}"
        organ_key, repo_data = result
    organ_data = registry.get("organs", {}).get(organ_key, {})

    # Format edges
    edges = []
    if seed:
        for p in seed.get("produces", []) or []:
            if isinstance(p, dict):
                target = p.get("target") or _format_consumers(p.get("consumers")) or "unspecified"
                artifact = p.get("artifact") or p.get("type") or "unspecified"
                edges.append(format_produces_edge(target, artifact, p.get("event", "")))
            else:
                edges.append(f"- **Produces** → `{p}`")
        for c in seed.get("consumes", []) or []:
            if isinstance(c, dict):
                source = c.get("source") or "unspecified"
                artifact = c.get("artifact") or c.get("type") or "unspecified"
                edges.append(format_consumes_edge(source, artifact, c.get("event", "")))
            else:
                edges.append(f"- **Consumes** ← `{c}`")

    edges_block = "\n".join(edges) if edges else format_no_edges()

    # Format siblings
    all_repos = organ_data.get("repositories", [])
    siblings = [r.get("name") for r in all_repos if r.get("name") != repo_name]
    siblings_block = ", ".join(f"`{s}`" for s in siblings[:15])
    if len(siblings) > 15:
        siblings_block += f" ... and {len(siblings) - 15} more"

    # Governance notes
    gov = []
    if organ_key == "ORGAN-III":
        gov.append("- Strictly unidirectional flow: I→II→III. No dependencies on Theory (I).")
    elif organ_key == "ORGAN-II":
        gov.append("- Consumes Theory (I) concepts, produces artifacts for Commerce (III).")
    elif organ_key == "ORGAN-I":
        gov.append("- Foundational theory layer. No upstream dependencies.")

    governance_block = "\n".join(gov) if gov else "- *Standard ORGANVM governance applies*"

    section = REPO_SECTION.format(
        organ_key=organ_key,
        organ_name=organ_data.get("name", organ_key),
        tier=repo_data.get("tier", "standard"),
        promotion_status=repo_data.get("promotion_status", "LOCAL"),
        org=org,
        repo_name=repo_name,
        edges_block=edges_block,
        siblings_block=siblings_block,
        governance_block=governance_block,
        handoff_status_block=handoff_status_block.rstrip(),
        timestamp=_timestamp(),
    )

    # Inject session review protocol before the AUTO:END marker
    end_marker = "<!-- ORGANVM:AUTO:END -->"
    if end_marker in section:
        # Build plan context if plan_index is provided
        system_library_section = _build_system_library_context()
        plan_section = _build_plan_context(repo_name, organ_key, plan_index)
        atoms_section = _build_atoms_context(repo_name, organ_key)
        sop_section = _build_sop_directives(sop_entries)
        prompting_hint = _build_prompting_hint(agent)
        ecosystem_section = _build_ecosystem_context(repo_name, organ_key)
        network_section = _build_network_context(repo_name, organ_key)
        ontologia_section = _build_ontologia_context(repo_name)
        injected = SESSION_REVIEW_SECTION
        if system_library_section:
            injected += "\n" + system_library_section
        if sop_section:
            injected += "\n" + sop_section
        if prompting_hint:
            injected += "\n" + prompting_hint
        if ecosystem_section:
            injected += "\n" + ecosystem_section
        if network_section:
            injected += "\n" + network_section
        if plan_section:
            injected += "\n" + plan_section
        if atoms_section:
            injected += "\n" + atoms_section
        if ontologia_section:
            injected += "\n" + ontologia_section
        variable_section = _build_variable_context()
        if variable_section:
            injected += "\n" + variable_section
        ammoi_section = _build_ammoi_context()
        if ammoi_section:
            injected += "\n" + ammoi_section
        trivium_section = _build_trivium_context(organ_key)
        if trivium_section:
            injected += "\n" + trivium_section
        logos_section = _build_logos_context(repo_name, repo_data)
        if logos_section:
            injected += "\n" + logos_section
        section = section.replace(
            end_marker,
            injected + "\n" + end_marker,
        )

    return section


def generate_agents_section(
    repo_name: str,
    org: str,
    registry: dict,
    seed: dict | None = None,
) -> str:
    """Generate the auto-generated section for AGENTS.md."""

    result = find_repo(registry, repo_name)
    if not result:
        return f"{AUTO_START}\n<!-- ERROR: Repo '{repo_name}' not found -->\n{AUTO_END}"

    organ_key, _ = result
    organ_data = registry.get("organs", {}).get(organ_key, {})

    # Format subscriptions
    subs = []
    if seed:
        for s in seed.get("subscriptions", []) or []:
            if isinstance(s, dict):
                subs.append(f"- Event: `{s.get('event')}` → Action: {s.get('action')}")
            else:
                subs.append(f"- Event: `{s}`")
    subs_block = "\n".join(subs) if subs else "- *No active event subscriptions*"

    # Format produces/consumes for agents
    prod = []
    cons = []
    if seed:
        for p in seed.get("produces", []) or []:
            if isinstance(p, dict):
                art = p.get("artifact") or p.get("type") or "unknown"
                target = p.get("target")
                if not target and p.get("consumers"):
                    targets = []
                    for consumer in p.get("consumers") or []:
                        if isinstance(consumer, dict):
                            # Link to the consumer repo context if possible
                            repo_n = consumer.get("repo")
                            if repo_n:
                                targets.append(f"[`{repo_n}`](../{repo_n}/CLAUDE.md)")
                            else:
                                targets.append(consumer.get("organ") or "unknown")
                        else:
                            targets.append(str(consumer))
                    target = ", ".join(targets)
                target = target or "unspecified"
                prod.append(f"- **Produce** `{art}` for {target}")
            else:
                prod.append(f"- **Produce** `{p}`")
        for c in seed.get("consumes", []) or []:
            if isinstance(c, dict):
                art = c.get("artifact") or c.get("type") or "unknown"
                source = c.get("source") or "unspecified"
                # If source is org/repo, try to link it
                if "/" in source:
                    org_n, repo_n = source.split("/", 1)
                    source_link = f"[`{source}`](../../{org_n}/{repo_n}/CLAUDE.md)"
                else:
                    source_link = f"`{source}`"
                cons.append(f"- **Consume** `{art}` from {source_link}")
            else:
                cons.append(f"- **Consume** `{c}`")

    produces_block = "\n".join(prod) if prod else "- *No production responsibilities*"
    consumes_block = "\n".join(cons) if cons else "- *No external dependencies*"

    # Simple governance for agents
    gov = ["- Adhere to unidirectional flow: I→II→III", "- Never commit secrets or credentials"]

    return AGENTS_SECTION.format(
        organ_key=organ_key,
        organ_name=organ_data.get("name", organ_key),
        subscriptions_block=subs_block,
        produces_block=produces_block,
        consumes_block=consumes_block,
        governance_block="\n".join(gov),
        timestamp=_timestamp(),
    )


def _build_organ_edges(organ_key: str, seeds: list[dict] | None = None) -> str:
    """Build inter-organ edge lines from the seed graph for one organ."""
    if not seeds:
        return "- *No seed data available*"

    try:
        from organvm_engine.organ_config import dir_to_registry_key
        from organvm_engine.seed.graph import SeedGraph
        from organvm_engine.seed.reader import seed_identity

        d2k = dir_to_registry_key()

        # Build a lightweight graph from the passed seeds
        graph = SeedGraph()
        for seed in seeds:
            identity = seed_identity(seed)
            graph.nodes.append(identity)
            for entry in seed.get("consumes", []) or []:
                source = entry.get("source", "") if isinstance(entry, dict) else str(entry)
                ctype = entry.get("type", "data") if isinstance(entry, dict) else "data"
                if source and isinstance(source, str):
                    graph.edges.append((source, identity, ctype))
            for entry in seed.get("produces", []) or []:
                if isinstance(entry, dict):
                    ptype = entry.get("type", "artifact")
                    # Handle "target" (singular string)
                    target = entry.get("target")
                    if isinstance(target, str) and target:
                        graph.edges.append((identity, target, ptype))
                    # Handle "targets" (list of strings)
                    for t in entry.get("targets", []) or []:
                        if isinstance(t, str):
                            graph.edges.append((identity, t, ptype))
                    # Handle "consumers" — string or dict with "organ" key
                    for consumer in entry.get("consumers", []) or []:
                        if isinstance(consumer, str) and consumer != "ALL":
                            graph.edges.append((identity, consumer, ptype))
                        elif isinstance(consumer, dict) and consumer.get("organ"):
                            graph.edges.append((identity, consumer["organ"], ptype))

        # Resolve org part of identity → registry key
        # Handles: "organvm-i-theoria/repo", "meta-organvm", "ORGAN-IV", "META-ORGANVM"
        def _organ_of(identity: str) -> str:
            org_part = identity.split("/", maxsplit=1)[0] if "/" in identity else identity
            # Direct dir→key lookup
            if org_part in d2k:
                return d2k[org_part]
            # Already a registry key (e.g., "ORGAN-IV", "META-ORGANVM")
            if org_part.startswith("ORGAN-") or org_part == "META-ORGANVM":
                return org_part
            return "UNKNOWN"

        # Filter to edges involving this organ where the other end is different
        lines: list[str] = []
        seen: set[str] = set()
        for src, tgt, etype in graph.edges:
            src_organ = _organ_of(src)
            tgt_organ = _organ_of(tgt)
            if src_organ == tgt_organ:
                continue
            if "UNKNOWN" in (src_organ, tgt_organ):
                continue
            if organ_key not in (src_organ, tgt_organ):
                continue
            key = f"{src_organ}→{tgt_organ}"
            if key in seen:
                continue
            seen.add(key)
            src_name = src.split("/")[-1] if "/" in src else src
            tgt_name = tgt.split("/")[-1] if "/" in tgt else tgt
            if src_organ == organ_key:
                lines.append(f"- {src_name} → {tgt_organ} ({etype})")
            else:
                lines.append(f"- {src_organ} → {tgt_name} ({etype})")

        if not lines:
            return "- *No inter-organ edges detected*"
        return "\n".join(sorted(lines))
    except Exception:
        return "- *Edges computed from system-wide seed graph*"


def generate_organ_section(
    organ_key: str,
    registry: dict,
    seeds: list[dict] | None = None,
) -> str:
    """Generate the auto-generated section for an organ-level CLAUDE.md."""

    organ_data = registry.get("organs", {}).get(organ_key, {})
    if not organ_data:
        return f"{AUTO_START}\n<!-- ERROR: Organ '{organ_key}' not found -->\n{AUTO_END}"

    repos = organ_data.get("repositories", [])

    # Format repo list
    repo_lines = []
    for r in repos[:20]:
        repo_lines.append(f"- `{r.get('name')}` ({r.get('tier')}, {r.get('promotion_status')})")
    repo_list_block = "\n".join(repo_lines)
    if len(repos) > 20:
        repo_list_block += f"\n- ... and {len(repos) - 20} more"

    # Aggregate promotion distribution
    dist = {}
    for r in repos:
        s = r.get("promotion_status", "LOCAL")
        dist[s] = dist.get(s, 0) + 1
    promotion_block = ", ".join(f"{k}: {v}" for k, v in sorted(dist.items()))

    # Compute inter-organ edges from seed graph
    organ_edges_block = _build_organ_edges(organ_key, seeds)

    section = ORGAN_SECTION.format(
        organ_key=organ_key,
        organ_name=organ_data.get("name", organ_key),
        repo_count=len(repos),
        flagship_count=len([r for r in repos if r.get("tier") == "flagship"]),
        standard_count=len([r for r in repos if r.get("tier") == "standard"]),
        infra_count=len([r for r in repos if r.get("tier") == "infrastructure"]),
        organ_edges_block=organ_edges_block,
        repo_list_block=repo_list_block,
        promotion_block=promotion_block,
        timestamp=_timestamp(),
    )
    end_marker = "<!-- ORGANVM:AUTO:END -->"
    system_library_section = _build_system_library_context()
    if system_library_section and end_marker in section:
        section = section.replace(end_marker, system_library_section + "\n" + end_marker)
    return section


def generate_workspace_section(
    registry: dict,
    seeds: list[dict] | None = None,
) -> str:
    """Generate the auto-generated section for the workspace-level CLAUDE.md."""

    organs = registry.get("organs", {})
    total_repos = 0
    rows = []

    for key, data in organs.items():
        repos = data.get("repositories", [])
        total_repos += len(repos)
        flagship = len([r for r in repos if r.get("tier") == "flagship"])
        # Status distribution
        s_dist = {}
        for r in repos:
            s = r.get("promotion_status", "LOCAL")
            s_dist[s] = s_dist.get(s, 0) + 1
        status_str = f"{s_dist.get('GRADUATED', 0)}G, {s_dist.get('PUBLIC_PROCESS', 0)}P"

        rows.append(f"| {key} | {len(repos)} | {flagship} | {status_str} |")

    omega_met, omega_total = _read_omega_counts()

    section = WORKSPACE_SECTION.format(
        total_repos=total_repos,
        organ_count=len(organs),
        organ_table_rows="\n".join(rows),
        seed_coverage=f"{len(seeds) if seeds else 0}/{total_repos}",
        ci_count="TBD",
        omega_met=omega_met,
        omega_total=omega_total,
        timestamp=_timestamp(),
    )
    end_marker = "<!-- ORGANVM:AUTO:END -->"
    system_library_section = _build_system_library_context()
    if system_library_section and end_marker in section:
        section = section.replace(end_marker, system_library_section + "\n" + end_marker)
    return section


def _build_sop_directives(sop_entries: list | None) -> str:
    """Build the Active Directives section from resolved SOP entries."""
    if not sop_entries:
        return ""

    rows = []
    all_complements: list[str] = []
    for e in sop_entries:
        desc = e.title or e.sop_name or e.filename
        rows.append(f"| {e.scope} | {e.phase} | {e.sop_name or e.filename} | {desc} |")
        all_complements.extend(e.complements or [])

    if not rows:
        return ""

    table = (
        "| Scope | Phase | Name | Description |\n"
        "|-------|-------|------|-------------|\n" + "\n".join(rows)
    )

    skills_line = ""
    if all_complements:
        unique = sorted(set(all_complements))
        skills_line = f"Linked skills: {', '.join(unique)}"

    return SOP_DIRECTIVES_SECTION.format(
        directives_table=table,
        linked_skills_line=skills_line,
    )


def _build_plan_context(
    repo_name: str,
    organ_key: str,
    plan_index: "PlanIndex | None",
) -> str:
    """Build the plan context section for a repo's CLAUDE.md.

    Shows up to 5 active plans in this repo + up to 5 related plans from
    other repos/agents that share the same organ.
    """
    if plan_index is None:
        return ""

    entries = plan_index.entries if hasattr(plan_index, "entries") else []
    if not entries:
        return ""

    # Plans in this repo
    repo_plans = [e for e in entries if e.repo == repo_name and e.status == "active"]
    # Related plans: same organ, different repo or different agent
    related = [
        e for e in entries if e.organ == organ_key and e.repo != repo_name and e.status == "active"
    ]

    if not repo_plans and not related:
        return ""

    # Format repo plans (max 5)
    plan_lines = []
    for e in repo_plans[:5]:
        pct = f"{e.completed_count}/{e.task_count}" if e.task_count else "0/0"
        plan_lines.append(f"- `{e.slug}` ({e.agent}, {e.date}) — {pct} tasks complete")
    if len(repo_plans) > 5:
        plan_lines.append(f"- ... and {len(repo_plans) - 5} more")
    plan_list = "\n".join(plan_lines) if plan_lines else "- *No active plans in this repo*"

    # Format related plans (max 5)
    related_lines = []
    for e in related[:5]:
        related_lines.append(
            f"- `{e.repo}/{e.slug}` ({e.agent}) — {e.title[:50]}",
        )
    if len(related) > 5:
        related_lines.append(f"- ... and {len(related) - 5} more")
    no_related = "- *No related plans in this organ*"
    related_plans = "\n".join(related_lines) if related_lines else no_related

    return PLAN_CONTEXT_SECTION.format(
        plan_list=plan_list,
        related_plans=related_plans,
    )


@lru_cache(maxsize=1)
def _system_library_stats() -> tuple[str, str, str, str]:
    """Return cached counts and path for the system library."""
    import re

    from organvm_engine.paths import corpus_dir, workspace_root

    plan_count = "unknown"
    chain_count = "unknown"
    sop_count = "unknown"
    library_path = "meta-organvm/praxis-perpetua/library/"

    try:
        ws = workspace_root()
        library_root = corpus_dir().parent / "praxis-perpetua" / "library"
    except Exception:
        return plan_count, chain_count, sop_count, library_path

    try:
        library_path = f"{library_root.relative_to(ws).as_posix()}/"
    except ValueError:
        library_path = str(library_root)

    if not library_root.exists():
        return plan_count, chain_count, sop_count, library_path

    chains_dir = library_root / "chains"
    if chains_dir.is_dir():
        chain_count = str(len(list(chains_dir.glob("*.yaml"))))

    plans_index = library_root / "plans" / "INDEX.md"
    if plans_index.is_file():
        text = plans_index.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"\*\*Plan files discovered:\*\*\s*(\d+)", text)
        if match:
            plan_count = match.group(1)

    if plan_count == "unknown":
        try:
            from organvm_engine.session.plans import discover_plans

            plan_count = str(len(discover_plans(workspace=ws)))
        except Exception:
            pass

    try:
        from organvm_engine.sop.discover import discover_sops

        sop_count = str(len(discover_sops(workspace=ws)))
    except Exception:
        pass

    return plan_count, chain_count, sop_count, library_path


def _build_system_library_context() -> str:
    """Build the system library discovery section for repo context files."""
    plans_count, chains_count, sops_count, library_path = _system_library_stats()
    return SYSTEM_LIBRARY_SECTION.format(
        plans_count=plans_count,
        chains_count=chains_count,
        sops_count=sops_count,
        library_path=library_path,
    )


def _build_atoms_context(repo_name: str, organ_key: str) -> str:
    """Build the atoms task queue section for a repo's CLAUDE.md.

    Reads pre-computed rollup JSON (not raw JSONL) so context sync stays fast.
    """
    from organvm_engine.atoms.rollup import load_repo_task_queue, load_rollup
    from organvm_engine.organ_config import registry_key_to_dir
    from organvm_engine.paths import workspace_root

    rk_to_dir = registry_key_to_dir()
    organ_dir_name = rk_to_dir.get(organ_key)
    if not organ_dir_name:
        return ""

    organ_dir = workspace_root() / organ_dir_name
    rollup = load_rollup(organ_dir)
    if rollup is None:
        return ATOMS_NOT_RUN_HINT

    queue = load_repo_task_queue(rollup, repo_name)
    if queue is None or queue["pending_count"] == 0:
        return ""

    # Format task list (max 8)
    task_lines = []
    for t in queue["tasks"][:8]:
        tags = ", ".join(t.get("tags", [])[:3])
        tag_str = f" [{tags}]" if tags else ""
        task_lines.append(f"- `{t.get('id', '?')}` {t.get('title', 'untitled')}{tag_str}")
    if queue["pending_count"] > 8:
        task_lines.append(f"- ... and {queue['pending_count'] - 8} more")
    task_list = "\n".join(task_lines)

    # Cross-organ link count
    cross_links = rollup.get("cross_organ_links", [])

    # Top tags from all pending tasks across all repos
    from collections import Counter

    tag_counter: Counter[str] = Counter()
    for repo_tasks in rollup.get("pending_by_repo", {}).values():
        for t in repo_tasks:
            tag_counter.update(t.get("tags", []))
    top_tags = ", ".join(f"`{t}`" for t, _ in tag_counter.most_common(5)) or "none"

    # Last run timestamp from manifest (if available)
    import json

    manifest_path = organ_dir / ".atoms" / "pipeline-manifest.json"
    last_run = "unknown"
    if manifest_path.exists():
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            last_run = m.get("generated", "unknown")[:19]
        except (json.JSONDecodeError, OSError):
            pass

    return ATOMS_REPO_QUEUE_SECTION.format(
        pending_count=queue["pending_count"],
        last_run=last_run,
        task_list=task_list,
        cross_link_count=len(cross_links),
        top_tags=top_tags,
    )


def _build_ecosystem_context(repo_name: str, organ_key: str) -> str:
    """Build ecosystem status snippet for a repo if ecosystem.yaml exists."""
    from organvm_engine.organ_config import registry_key_to_dir
    from organvm_engine.paths import workspace_root

    rk_to_dir = registry_key_to_dir()
    organ_dir_name = rk_to_dir.get(organ_key)
    if not organ_dir_name:
        return ""

    eco_path = workspace_root() / organ_dir_name / repo_name / "ecosystem.yaml"
    if not eco_path.is_file():
        return ""

    try:
        from organvm_engine.ecosystem.reader import get_pillars, read_ecosystem

        data = read_ecosystem(eco_path)
        pillars = get_pillars(data)
    except Exception:
        return ""

    if not pillars:
        return ""

    lines = []
    for pillar_name, arms in pillars.items():
        total = len(arms)
        live = sum(1 for a in arms if a.get("status") in ("live", "active"))
        planned = sum(1 for a in arms if a.get("status") == "planned")
        lines.append(f"- **{pillar_name}**: {live}/{total} live, {planned} planned")

    if not lines:
        return ""

    # Derive organ short key for CLI hint
    organ_short = organ_key.replace("ORGAN-", "").replace("META-ORGANVM", "META")

    return ECOSYSTEM_STATUS_SECTION.format(
        pillar_summary="\n".join(lines),
        repo_name=repo_name,
        organ_short=organ_short,
    )


def _build_network_context(repo_name: str, organ_key: str) -> str:
    """Build network mirror snippet for a repo if network-map.yaml exists."""
    from organvm_engine.organ_config import registry_key_to_dir
    from organvm_engine.paths import workspace_root

    rk_to_dir = registry_key_to_dir()
    organ_dir_name = rk_to_dir.get(organ_key)
    if not organ_dir_name:
        return ""

    nmap_path = workspace_root() / organ_dir_name / repo_name / "network-map.yaml"
    if not nmap_path.is_file():
        return ""

    try:
        from organvm_engine.network.mapper import read_network_map
        from organvm_engine.network.metrics import convergence_points

        nmap = read_network_map(nmap_path)
    except Exception:
        return ""

    if nmap.mirror_count == 0:
        return ""

    lines = []
    for lens in ("technical", "parallel", "kinship"):
        entries = nmap.mirrors_by_lens(lens)
        if entries:
            projects = ", ".join(e.project for e in entries[:5])
            suffix = f" +{len(entries) - 5} more" if len(entries) > 5 else ""
            lines.append(f"- **{lens}** ({len(entries)}): {projects}{suffix}")

    if not lines:
        return ""

    # Count convergences across all maps for context
    try:
        from organvm_engine.network.mapper import discover_network_maps

        all_maps = [m for _, m in discover_network_maps(workspace_root())]
        conv_count = len(convergence_points(all_maps))
    except Exception:
        conv_count = 0

    return NETWORK_STATUS_SECTION.format(
        mirror_summary="\n".join(lines),
        convergence_count=conv_count,
        repo_name=repo_name,
    )


def _build_ontologia_context(repo_name: str) -> str:
    """Resolve repo's ontologia UID and return a short status snippet."""
    try:
        from ontologia.registry.store import open_store
    except ImportError:
        return ""

    try:
        store = open_store()
        resolver = store.resolver()
        result = resolver.resolve(repo_name)
        if not result:
            return ""
        return ONTOLOGIA_STATUS_SECTION.format(
            entity_uid=result.identity.uid,
            matched_by=result.matched_by,
            repo_name=repo_name,
        )
    except Exception:
        return ""


def _build_variable_context() -> str:
    """Render live system variables from ontologia's VariableStore into a markdown table.

    Completely fault-tolerant — returns empty string on any failure,
    including ontologia not being installed or having no variables.
    """
    try:
        from ontologia.registry.store import open_store
        from ontologia.variables.variable import Scope
    except ImportError:
        return ""

    try:
        store = open_store()
        vs = store.variable_store
        variables = vs.list_at_scope(Scope.GLOBAL)

        if not variables:
            return ""

        rows = []
        for var in sorted(variables, key=lambda v: v.key):
            updated = var.updated_at[:10] if var.updated_at else "unknown"
            value_str = str(var.value) if var.value is not None else ""
            rows.append(f"| `{var.key}` | {value_str} | {var.scope.value} | {updated} |")

        metric_count = len(store.list_metrics())
        observation_count = store.observation_store.count

        return VARIABLE_STATUS_SECTION.format(
            variable_rows="\n".join(rows),
            metric_count=metric_count,
            observation_count=observation_count,
        )
    except Exception:
        return ""


# Module-level AMMOI cache for context sync (computed once per sync_all)
_ammoi_cache: dict = {"ammoi": None}


def precompute_ammoi() -> None:
    """Pre-compute AMMOI for context injection. Called once per sync_all."""
    try:
        from organvm_engine.pulse.ammoi import compute_ammoi

        _ammoi_cache["ammoi"] = compute_ammoi(include_events=True)
    except Exception:
        _ammoi_cache["ammoi"] = None


def _build_ammoi_context() -> str:
    """Build the AMMOI density line for context injection."""
    ammoi = _ammoi_cache.get("ammoi")
    if ammoi is None:
        return ""

    organ_parts = []
    for oid in sorted(ammoi.organs.keys()):
        od = ammoi.organs[oid]
        organ_parts.append(f"{oid}:{od.density:.0%}")
    organ_line = ", ".join(organ_parts[:4])
    if len(organ_parts) > 4:
        organ_line += f" +{len(organ_parts) - 4} more"

    d24h = ammoi.density_delta_24h
    d7d = ammoi.density_delta_7d
    d24h_str = f"{'+' if d24h > 0 else ''}{d24h:.1%}" if d24h is not None else "vacuum"
    d7d_str = f"{'+' if d7d > 0 else ''}{d7d:.1%}" if d7d is not None else "vacuum"
    ts = ammoi.timestamp[:19] if len(ammoi.timestamp) >= 19 else ammoi.timestamp

    # Advisory count (best-effort)
    adv_count = 0
    try:
        from organvm_engine.pulse.advisories import read_advisories

        adv_count = len(read_advisories(limit=100, unacked_only=True))
    except Exception:
        pass

    # Scale line: organs / repos / components
    if ammoi.total_components:
        scale_line = (
            f"8 organs / {ammoi.total_entities} repos / {ammoi.total_components} components"
        )
    else:
        scale_line = f"8 organs / {ammoi.total_entities} repos"
    if ammoi.hierarchy_depth > 2:
        scale_line += f" (depth {ammoi.hierarchy_depth})"

    return AMMOI_SECTION.format(
        density_pct=f"{ammoi.system_density:.0%}",
        edges=ammoi.active_edges,
        tensions=ammoi.tension_count,
        clusters=ammoi.cluster_count,
        advisories=adv_count,
        events_24h=ammoi.event_frequency_24h,
        inference_score=f"{ammoi.inference_score:.0%}",
        scale_line=scale_line,
        organ_density_line=organ_line,
        last_pulse=ts,
        delta_24h=d24h_str,
        delta_7d=d7d_str,
    )


def _build_prompting_hint(agent: str | None) -> str:
    """Build a one-line prompting standards hint for the given agent."""
    if not agent:
        return ""
    try:
        from organvm_engine.prompting.loader import format_guidelines_hint, load_guidelines

        guidelines = load_guidelines(agent)
        if guidelines:
            return "\n" + format_guidelines_hint(guidelines) + "\n"
    except ImportError:
        pass
    return ""


def _format_consumers(consumers: list | None) -> str:
    """Format a list of consumer entries into a comma-separated string."""
    if not consumers:
        return ""
    parts = []
    for c in consumers:
        if isinstance(c, dict):
            parts.append(c.get("repo") or c.get("organ") or str(c))
        else:
            parts.append(str(c))
    return ", ".join(parts)


def _read_omega_counts() -> tuple[int, int]:
    """Read omega criteria met/total from the evidence map.

    Parses the summary table in omega-evidence-map.md looking for
    '| MET | N |', '| IN PROGRESS | N |', '| NOT STARTED | N |' rows.
    Falls back to (0, 17) if the file is unreadable.
    """
    import re

    from organvm_engine.paths import corpus_dir

    evidence_path = corpus_dir() / "docs" / "evaluation" / "omega-evidence-map.md"
    try:
        text = evidence_path.read_text()
    except (FileNotFoundError, OSError):
        return 0, 17

    counts = {}
    for line in text.splitlines():
        m = re.match(r"\|\s*(MET|IN PROGRESS|NOT STARTED)\s*\|\s*(\d+)\s*\|", line)
        if m:
            counts[m.group(1)] = int(m.group(2))

    met = counts.get("MET", 0)
    total = met + counts.get("IN PROGRESS", 0) + counts.get("NOT STARTED", 0)
    return met, total if total > 0 else 17


def _build_trivium_context(registry_organ_key: str) -> str:
    """Build trivium dialect identity section for a repo's context file.

    Args:
        registry_organ_key: Registry-format key like "ORGAN-I" or "META-ORGANVM".
    """
    try:
        from organvm_engine.organ_config import get_organ_map
        from organvm_engine.trivium.dialects import (
            dialect_for_organ,
            dialect_profile,
            organ_for_dialect,
        )
        from organvm_engine.trivium.taxonomy import pairs_for_organ
    except ImportError:
        return ""

    try:
        # Convert registry key ("ORGAN-I") to CLI key ("I")
        reg_to_cli = {
            v.get("registry_key", ""): k
            for k, v in get_organ_map().items()
            if v.get("registry_key")
        }
        organ_key = reg_to_cli.get(registry_organ_key)
        if not organ_key:
            return ""
        dialect = dialect_for_organ(organ_key)
        profile = dialect_profile(dialect)
        pairs = pairs_for_organ(dialect)

        tier_order = {"formal": 0, "structural": 1, "analogical": 2, "emergent": 3}
        ranked = sorted(pairs, key=lambda p: tier_order.get(p.tier.value, 9))
        top_3 = ranked[:3]

        strongest = ", ".join(
            f"{organ_for_dialect(p.target if p.source == dialect else p.source)} ({p.tier.value})"
            for p in top_3
        )

        return TRIVIUM_SECTION.format(
            dialect_name=dialect.name,
            classical_parallel=profile.classical_parallel,
            translation_role=profile.translation_role,
            strongest_pairs=strongest,
            organ_key=organ_key,
        )
    except Exception:
        return ""


def _build_logos_context(repo_name: str, repo_data: dict) -> str:
    """Build the Logos Documentation Layer section.

    Args:
        repo_name: Repository name.
        repo_data: Registry entry for the repo.
    """
    from pathlib import Path

    # Standard workspace resolution
    workspace = Path.home() / "Workspace"

    from organvm_engine.organ_config import get_organ_map

    organ_map = get_organ_map()

    # Try to find the repo on disk
    repo_path = None
    for organ_info in organ_map.values():
        candidate = workspace / organ_info["dir"] / repo_name
        if candidate.exists():
            repo_path = candidate
            break

    if not repo_path:
        # Fallback to current directory if not found in workspace
        repo_path = Path.cwd()

    logos_dir = repo_path / "docs" / "logos"
    logos_status = "ACTIVE" if logos_dir.exists() else "MISSING"

    # Simple symmetry check — scan all top-level directories for code files
    code_extensions = ["*.py", "*.ts", "*.js", "*.go", "*.rs"]
    has_nature = False

    # Check common code directories and the repo root
    code_dirs = [
        repo_path / d
        for d in [
            "src",
            "lib",
            "app",
            "pkg",
            "titan",
            "tools",
            "runtime",
            "hive",
            "gateway",
            "dashboard",
            "adapters",
            "agents",
            "cli",
        ]
    ]
    code_dirs.append(repo_path)  # Also check repo root

    for code_dir in code_dirs:
        if code_dir.exists() and code_dir.is_dir():
            for ext in code_extensions:
                # Only check one level deep in each directory to avoid deep recursion
                if any(code_dir.glob(f"{ext}")):
                    has_nature = True
                    break
                # Also check one subdirectory level
                if any(code_dir.glob(f"*/{ext}")):
                    has_nature = True
                    break
            if has_nature:
                break

    # Counterpart exists if there are markdown files in docs/logos/
    has_counterpart = logos_dir.exists() and any(logos_dir.glob("*.md"))

    if has_nature and not has_counterpart:
        symmetry_score = "0.5 (GHOST)"
        logos_compliance_note = "Implementation exists without record."
    elif not has_nature and has_counterpart:
        symmetry_score = "0.5 (DREAM)"
        logos_compliance_note = "Record exists without implementation."
    elif has_nature and has_counterpart:
        symmetry_score = "1.0 (SYMMETRIC)"
        logos_compliance_note = "Nature and Counterpart are in balance."
    else:
        # Default for infrastructure/meta which might not have src/
        symmetry_score = "1.0 (SYMMETRIC)" if has_counterpart else "0.0 (VACUUM)"
        logos_compliance_note = (
            "Nature and Counterpart are in balance."
            if has_counterpart
            else "Formation is currently void."
        )

    # Essay link (if flagship or explicitly mapped)
    essay_link = ""
    if repo_data.get("tier") == "flagship":
        essay_link = "- **[Public Essay](https://organvm-v-logos.github.io/public-process/)** — System-wide narrative entry."

    return LOGOS_SECTION.format(
        logos_status=logos_status,
        symmetry_score=symmetry_score,
        logos_essay_link=essay_link,
        logos_compliance_note=logos_compliance_note,
    )


def _timestamp() -> str:
    """Return ISO 8601 timestamp for sync tracking."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
