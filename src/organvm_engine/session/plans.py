"""Plan file discovery and inventory across the workspace.

Discovers plan files from multiple AI agents (.claude/plans, .gemini/plans,
.codex/plans) at project, global, and governance levels. Extracts metadata
from filenames and content, resolves organ/repo attribution, and renders
inventories and matrices.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CLAUDE_PLANS_GLOBAL = Path.home() / ".claude" / "plans"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Agent plan directory patterns: agent name → relative dir under a project
AGENT_PLAN_DIRS: dict[str, str] = {
    "claude": ".claude/plans",
    "gemini": ".gemini/plans",
    "codex": ".codex/plans",
}


@dataclass
class PlanFile:
    """Metadata for a single plan file."""

    path: Path
    project: str  # decoded project path or "global"
    slug: str  # from filename after date
    date: str  # YYYY-MM-DD
    title: str  # first H1 from content
    size_bytes: int
    has_verification: bool  # contains "## Verification" section
    status: str = "unknown"  # annotatable by audit
    agent: str = "claude"  # claude | gemini | codex | governance
    organ: str | None = None  # resolved from path via organ_config
    repo: str | None = None  # directory name between organ dir and .agent/plans/
    version: int = 1  # extracted from -vN.md suffix
    location_tier: str = "project"  # project | global | governance

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def qualified_id(self) -> str:
        """Unique identifier: agent:organ:repo:slug."""
        parts = [self.agent, self.organ or "?", self.repo or "?", self.slug]
        return ":".join(parts)

    @property
    def is_agent_subplan(self) -> bool:
        """True if filename matches agent sub-plan pattern (-agent-aXXX)."""
        return bool(re.search(r"-agent-a[0-9a-f]+$", self.slug, re.IGNORECASE))


def _resolve_organ_repo(
    plan_path: Path, workspace: Path,
) -> tuple[str | None, str | None]:
    """Resolve organ key and repo name from a plan file path.

    Given a path like <workspace>/organvm-iii-ergon/some-repo/.claude/plans/plan.md,
    returns ("III", "some-repo").

    For global plans (e.g. ~/.claude/plans/) that can't be resolved from path,
    falls back to content-based heuristics using known repo names.
    """
    from organvm_engine.organ_config import ORGANS

    dir_to_key = {v["dir"]: k for k, v in ORGANS.items()}

    try:
        rel = plan_path.relative_to(workspace)
    except ValueError:
        # Path is outside workspace — try content-based fallback
        return _resolve_organ_repo_from_content(plan_path)

    parts = rel.parts
    if not parts:
        return _resolve_organ_repo_from_content(plan_path)

    # First component should be an organ directory
    organ_dir = parts[0]
    organ_key = dir_to_key.get(organ_dir)
    if organ_key is None:
        return _resolve_organ_repo_from_content(plan_path)

    # Find the .agent/plans/ segment to determine repo
    # Path structure: organ_dir / [repo_name /] .agent / plans / file.md
    # If plan is directly in organ_dir/.agent/plans/, repo is None (organ-level plan)
    path_str = str(rel)
    for agent_dir in AGENT_PLAN_DIRS.values():
        idx = path_str.find(agent_dir)
        if idx > 0:
            # Everything between organ_dir/ and .agent/plans/ is the repo path
            between = path_str[len(organ_dir) + 1:idx].rstrip("/")
            if between:
                # Could be nested: repo/subdir — take first component as repo
                repo = between.split("/")[0]
                return organ_key, repo
            return organ_key, None
    # Also check governance pattern
    if "praxis-perpetua" in path_str:
        return organ_key, "praxis-perpetua"

    return organ_key, None


def _resolve_organ_repo_from_content(
    plan_path: Path,
) -> tuple[str | None, str | None]:
    """Attempt to resolve organ/repo from plan file content.

    Scans headings and file paths in the plan for known repo names
    from the registry. Returns ("_root", "_global") if nothing matches.
    """
    from organvm_engine.organ_config import ORGANS

    # Build a lookup: repo_name → organ_key
    # We look for organ directory names in file paths mentioned in the plan
    dir_to_key = {v["dir"]: k for k, v in ORGANS.items()}

    try:
        text = plan_path.read_text(encoding="utf-8", errors="replace")[:8192]
    except OSError:
        return "_root", "_global"

    # Look for organ directory references in file paths (e.g. organvm-engine/src/...)
    for organ_dir, organ_key in dir_to_key.items():
        if organ_dir in text:
            # Try to extract repo name from paths like "organ-dir/repo-name/..."
            import re

            pattern = re.escape(organ_dir) + r"/([a-zA-Z0-9_-]+)"
            m = re.search(pattern, text)
            if m:
                return organ_key, m.group(1)
            return organ_key, None

    # Check for common engine path patterns
    if "organvm_engine/" in text or "organvm-engine/" in text:
        return "META", "organvm-engine"

    return "_root", "_global"


def discover_plans(
    workspace: Path | None = None,
    project_filter: str | None = None,
    since: str | None = None,
    include_global: bool | None = None,
    agent: str | None = None,
    organ: str | None = None,
    include_governance: bool = False,
) -> list[PlanFile]:
    """Find all plan files across workspace and global dirs.

    Args:
        workspace: Workspace root (default ~/Workspace).
        project_filter: Substring filter on project path.
        since: Only include plans on or after this date (YYYY-MM-DD).
        include_global: Include ~/.claude/plans/ and ~/.claude/projects/ plans.
            Default True when workspace is None, False when explicit workspace given.
        agent: Filter to a specific agent (claude, gemini, codex, governance).
        organ: Filter to a specific organ key (I, II, ..., META).
        include_governance: Include praxis-perpetua governance plans.
    """
    results: list[PlanFile] = []

    # When an explicit workspace is provided, skip global dirs by default
    if include_global is None:
        include_global = workspace is None

    ws = workspace or Path.home() / "Workspace"

    # Determine which agents to scan
    agents_to_scan = (
        {agent: AGENT_PLAN_DIRS[agent]}
        if agent and agent in AGENT_PLAN_DIRS
        else AGENT_PLAN_DIRS
    )

    # 1. Project-level plans: <workspace>/**/.{agent}/plans/*.md
    if ws.is_dir():
        for agent_name, agent_dir in agents_to_scan.items():
            for plans_dir in ws.rglob(agent_dir):
                if not plans_dir.is_dir():
                    continue
                project_path = str(plans_dir.parent.parent)
                if project_filter and project_filter not in project_path:
                    continue
                for md in sorted(plans_dir.glob("*.md")):
                    plan = _parse_plan_file(
                        md, project_path, agent=agent_name, workspace=ws,
                    )
                    if plan:
                        results.append(plan)

    # 2. Project plans inside ~/.claude/projects/*/plans/ (Claude-only)
    if include_global and CLAUDE_PROJECTS_DIR.is_dir() and agent in (None, "claude"):
        for proj_dir in CLAUDE_PROJECTS_DIR.iterdir():
            if not proj_dir.is_dir():
                continue
            plans_dir = proj_dir / "plans"
            if not plans_dir.is_dir():
                continue
            project_path = proj_dir.name
            if project_filter and project_filter not in project_path:
                continue
            for md in sorted(plans_dir.glob("*.md")):
                plan = _parse_plan_file(
                    md, project_path, agent="claude", workspace=ws,
                    location_tier="global",
                )
                if plan:
                    results.append(plan)

    # 3. Global plans: ~/.claude/plans/*.md (Claude-only)
    if include_global and CLAUDE_PLANS_GLOBAL.is_dir() and agent in (None, "claude"):
        for md in sorted(CLAUDE_PLANS_GLOBAL.glob("*.md")):
            plan = _parse_plan_file(
                md, "global", agent="claude", workspace=ws,
                location_tier="global",
            )
            if plan:
                results.append(plan)

    # 4. Governance plans: praxis-perpetua/sessions/*/plans/*.md
    if include_governance and agent in (None, "governance") and ws.is_dir():
        results.extend(_discover_governance_plans(ws, project_filter))

    # Apply date filter
    if since:
        results = [p for p in results if p.date >= since]

    # Apply organ filter
    if organ:
        results = [p for p in results if p.organ == organ]

    # Deduplicate by path
    seen: set[str] = set()
    deduped: list[PlanFile] = []
    for p in results:
        key = str(p.path.resolve())
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    # Infer lifecycle status
    _infer_lifecycle_statuses(deduped)

    # Sort by date descending
    deduped.sort(key=lambda p: p.date, reverse=True)
    return deduped


def _discover_governance_plans(
    workspace: Path, project_filter: str | None = None,
) -> list[PlanFile]:
    """Walk praxis-perpetua/sessions/*/plans/ for governance plan files."""
    results: list[PlanFile] = []
    praxis_sessions = workspace / "meta-organvm" / "praxis-perpetua" / "sessions"
    if not praxis_sessions.is_dir():
        return results

    for session_dir in sorted(praxis_sessions.iterdir()):
        if not session_dir.is_dir():
            continue
        plans_dir = session_dir / "plans"
        if not plans_dir.is_dir():
            continue
        project_path = str(plans_dir.parent)
        if project_filter and project_filter not in project_path:
            continue
        for md in sorted(plans_dir.glob("*.md")):
            plan = _parse_plan_file(
                md, project_path, agent="governance", workspace=workspace,
                location_tier="governance",
            )
            if plan:
                if plan.organ is None:
                    plan.organ = "META"
                if plan.repo is None:
                    plan.repo = "praxis-perpetua"
                results.append(plan)

    return results


_DATE_SLUG_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+?)(?:-v\d+)?\.md$")
_VERSION_RE = re.compile(r"-v(\d+)\.md$")


def _parse_plan_file(
    md_path: Path,
    project: str,
    agent: str = "claude",
    workspace: Path | None = None,
    location_tier: str = "project",
) -> PlanFile | None:
    """Extract metadata from a plan markdown file."""
    try:
        size = md_path.stat().st_size
    except OSError:
        return None

    # Parse date and slug from filename
    m = _DATE_SLUG_RE.match(md_path.name)
    if m:
        date = m.group(1)
        slug = m.group(2)
    else:
        # Non-dated plan files — use mtime as date
        try:
            mtime = md_path.stat().st_mtime
            from datetime import datetime

            date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
        except OSError:
            date = "unknown"
        slug = md_path.stem

    # Extract version from -vN suffix
    version = 1
    vm = _VERSION_RE.search(md_path.name)
    if vm:
        version = int(vm.group(1))

    # Resolve organ and repo from path
    organ_key, repo_name = None, None
    if workspace:
        organ_key, repo_name = _resolve_organ_repo(md_path, workspace)

    # Extract title and verification section
    title = ""
    has_verification = False
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if not title and stripped.startswith("# "):
                title = stripped[2:].strip()
            if stripped.lower().startswith("## verification"):
                has_verification = True
            if title and has_verification:
                break
    except OSError:
        pass

    return PlanFile(
        path=md_path,
        project=project,
        slug=slug,
        date=date,
        title=title or slug,
        size_bytes=size,
        has_verification=has_verification,
        agent=agent,
        organ=organ_key,
        repo=repo_name,
        version=version,
        location_tier=location_tier,
    )


def _infer_lifecycle_statuses(plans: list[PlanFile]) -> None:
    """Post-discovery pass to set lifecycle status on each plan.

    Rules:
    - Path contains /archive/ → "archived"
    - A higher version (-vN+1) exists for same slug → "superseded"
    - Otherwise → "active"
    """
    # Build slug→max_version map
    slug_versions: dict[str, int] = {}
    for p in plans:
        base_slug = re.sub(r"-v\d+$", "", p.slug)
        slug_versions[base_slug] = max(slug_versions.get(base_slug, 0), p.version)

    for p in plans:
        if "/archive/" in str(p.path):
            p.status = "archived"
        else:
            base_slug = re.sub(r"-v\d+$", "", p.slug)
            if slug_versions.get(base_slug, 1) > p.version:
                p.status = "superseded"
            else:
                p.status = "active"


def render_plan_inventory(plans: list[PlanFile]) -> str:
    """Render a readable inventory of discovered plans."""
    if not plans:
        return "No plan files found."

    # Determine if we have multi-agent data
    agents = set(p.agent for p in plans)
    multi_agent = len(agents) > 1 or "claude" not in agents

    if multi_agent:
        lines = [
            f"{'Date':<12} {'Agent':<10} {'Size':>6} {'V':>1} {'Project':<30} {'Title'}",
            "-" * 95,
        ]
        for p in plans:
            size_str = f"{p.size_bytes / 1024:.0f}K" if p.size_bytes >= 1024 else f"{p.size_bytes}B"
            v = "Y" if p.has_verification else " "
            proj = p.project[-30:] if len(p.project) > 30 else p.project
            title = p.title[:35] if len(p.title) > 35 else p.title
            lines.append(
                f"{p.date:<12} {p.agent:<10} {size_str:>6} {v:>1} {proj:<30} {title}",
            )
    else:
        lines = [
            f"{'Date':<12} {'Size':>6} {'V':>1} {'Project':<35} {'Title'}",
            "-" * 90,
        ]
        for p in plans:
            size_str = f"{p.size_bytes / 1024:.0f}K" if p.size_bytes >= 1024 else f"{p.size_bytes}B"
            v = "Y" if p.has_verification else " "
            proj = p.project[-35:] if len(p.project) > 35 else p.project
            title = p.title[:40] if len(p.title) > 40 else p.title
            lines.append(f"{p.date:<12} {size_str:>6} {v:>1} {proj:<35} {title}")

    lines.append(f"\n{len(plans)} plans across {len(set(p.project for p in plans))} projects")
    verified = sum(1 for p in plans if p.has_verification)
    lines.append(f"Verification sections: {verified}/{len(plans)}")

    if multi_agent:
        agent_counts = {}
        for p in plans:
            agent_counts[p.agent] = agent_counts.get(p.agent, 0) + 1
        parts = [f"{a}: {c}" for a, c in sorted(agent_counts.items())]
        lines.append(f"By agent: {', '.join(parts)}")

    return "\n".join(lines)


def render_plan_audit(plans: list[PlanFile]) -> str:
    """Render a markdown audit scaffold for plan-vs-reality review."""
    if not plans:
        return "No plan files found."

    lines = ["# Plan Audit Report", "", f"Generated from {len(plans)} discovered plans.", ""]

    # Group by project
    by_project: dict[str, list[PlanFile]] = {}
    for p in plans:
        by_project.setdefault(p.project, []).append(p)

    for project, project_plans in sorted(by_project.items()):
        lines.append(f"## {project}")
        lines.append("")
        for p in sorted(project_plans, key=lambda x: x.date, reverse=True):
            lines.append(f"### {p.date} — {p.title}")
            lines.append(f"- **File:** `{p.path}`")
            lines.append(f"- **Slug:** {p.slug}")
            lines.append(f"- **Verification:** {'Yes' if p.has_verification else 'No'}")
            lines.append(f"- **Status:** {p.status}")
            lines.append(
                "- **Reality:** Run `organvm atoms reconcile` to cross-reference"
                " planned tasks against git commit history"
                " (see `organvm_engine.atoms.reconciler`)",
            )
            lines.append("")

    return "\n".join(lines)


def render_plan_matrix(plans: list[PlanFile]) -> str:
    """Render an agent × organ count matrix."""
    if not plans:
        return "No plan files found."

    # Collect agents and organs
    agents = sorted(set(p.agent for p in plans))
    organs = sorted(set(p.organ or "?" for p in plans))

    # Build counts
    counts: dict[tuple[str, str], int] = {}
    for p in plans:
        key = (p.agent, p.organ or "?")
        counts[key] = counts.get(key, 0) + 1

    # Render
    col_w = max(6, *(len(o) for o in organs)) + 2
    header = f"{'Agent':<12}" + "".join(f"{o:>{col_w}}" for o in organs) + f"{'Total':>{col_w}}"
    lines = [header, "-" * len(header)]

    for agent in agents:
        row = f"{agent:<12}"
        total = 0
        for organ in organs:
            c = counts.get((agent, organ), 0)
            total += c
            row += f"{c:>{col_w}}"
        row += f"{total:>{col_w}}"
        lines.append(row)

    # Totals row
    row = f"{'Total':<12}"
    grand = 0
    for organ in organs:
        col_total = sum(counts.get((a, organ), 0) for a in agents)
        grand += col_total
        row += f"{col_total:>{col_w}}"
    row += f"{grand:>{col_w}}"
    lines.append("-" * len(header))
    lines.append(row)

    return "\n".join(lines)
