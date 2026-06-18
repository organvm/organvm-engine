"""CI mandate enforcement — filesystem-based CI workflow verification.

Walks the workspace to verify that repositories actually have CI workflow
files on disk, independent of what the registry claims. This catches
drift between registry metadata and ground truth.

Derived from ORGAN-IV's enforce-ci-mandate.py, folded into the engine
so it can be consumed by governance audit, MCP server, and CLI.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from organvm_engine.organ_config import (
    get_organ_map,
    get_topology_source,
    load_organ_topology,
    registry_key_to_dir,
)
from organvm_engine.paths import additional_workspace_roots, corpus_dir, workspace_root


@dataclass
class CIMandateEntry:
    """CI verification result for a single repository."""

    organ: str
    repo_name: str
    org: str
    has_ci: bool
    workflows: list[str] = field(default_factory=list)
    promotion_status: str = ""
    repo_path_found: bool = True


@dataclass
class CIMandateReport:
    """Full CI mandate verification report."""

    total: int = 0
    has_ci: int = 0
    missing_ci: int = 0
    entries: list[CIMandateEntry] = field(default_factory=list)
    by_organ: dict[str, dict] = field(default_factory=dict)

    @property
    def adherence_rate(self) -> float:
        return self.has_ci / self.total if self.total > 0 else 0.0

    def missing_repos(self) -> list[CIMandateEntry]:
        return [e for e in self.entries if not e.has_ci]

    def drift_from_registry(self, registry: dict) -> list[dict]:
        """Find repos where filesystem truth differs from registry ci_workflow."""
        drift = []
        registry_ci = {}
        for organ_data in registry.get("organs", {}).values():
            for repo in organ_data.get("repositories", []):
                registry_ci[repo.get("name", "")] = bool(repo.get("ci_workflow"))

        for entry in self.entries:
            reg_val = registry_ci.get(entry.repo_name)
            if reg_val is not None and reg_val != entry.has_ci:
                drift.append({
                    "repo": entry.repo_name,
                    "organ": entry.organ,
                    "registry_says": reg_val,
                    "filesystem_says": entry.has_ci,
                })
        return drift

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "has_ci": self.has_ci,
            "missing_ci": self.missing_ci,
            "adherence_rate": round(self.adherence_rate, 4),
            "by_organ": self.by_organ,
            "entries": [
                {
                    "organ": e.organ,
                    "repo": e.repo_name,
                    "org": e.org,
                    "has_ci": e.has_ci,
                    "workflows": e.workflows,
                    "promotion_status": e.promotion_status,
                    "repo_path_found": e.repo_path_found,
                }
                for e in self.entries
            ],
        }


def _resolve_repo_path(
    org: str,
    repo_name: str,
    organ_key: str,
    ws: Path,
    key_to_dir: dict[str, str],
) -> Path | None:
    """Resolve the filesystem path for a repository.

    Strategy:
    1. Use organ directory mapping from organ_config
    2. Use the loaded topology's GitHub org directory, if present
    3. Fall back to registry org name as directory
    4. Fall back to the corpus parent and any configured flat workspace roots
    """
    candidates: list[Path] = []

    def add(candidate: Path) -> None:
        if candidate not in candidates:
            candidates.append(candidate)

    organ_dir = key_to_dir.get(organ_key)
    if organ_dir:
        add(ws / organ_dir / repo_name)

    for entry in get_organ_map().values():
        if entry.get("registry_key") != organ_key:
            continue
        topo_dir = entry.get("dir")
        topo_org = entry.get("org")
        if topo_dir:
            add(ws / topo_dir / repo_name)
        if topo_org:
            add(ws / topo_org / repo_name)

    if org:
        add(ws / org / repo_name)

    with suppress(OSError):
        add(corpus_dir().parent / repo_name)

    for root in additional_workspace_roots(workspace=ws):
        add(root / repo_name)

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    # Special case: .github repos may be at org level
    if repo_name == ".github" and organ_dir:
        candidate = ws / organ_dir / ".github"
        if candidate.is_dir():
            return candidate

    return None


def _check_ci_workflows(repo_path: Path) -> list[str]:
    """Check for CI workflow files in a repository."""
    ci_dir = repo_path / ".github" / "workflows"
    if not ci_dir.is_dir():
        return []
    return [
        f.name for f in ci_dir.iterdir()
        if f.is_file() and f.suffix in (".yml", ".yaml")
    ]


def verify_ci_mandate(
    registry: dict,
    workspace: Path | None = None,
) -> CIMandateReport:
    """Verify CI workflow presence on the filesystem for all repos.

    Walks the workspace and checks each repo listed in the registry
    for actual `.github/workflows/*.yml` files.

    Args:
        registry: Loaded registry dict.
        workspace: Workspace root. Defaults to paths.workspace_root().

    Returns:
        CIMandateReport with per-repo verification results.
    """
    ws = workspace or workspace_root()
    if get_topology_source() == "fallback":
        load_organ_topology()
    key_to_dir = registry_key_to_dir()
    report = CIMandateReport()

    organs = registry.get("organs", {})
    for organ_key, organ_data in organs.items():
        organ_stats = {"total": 0, "has_ci": 0, "missing_ci": 0, "missing_repos": []}

        for repo in organ_data.get("repositories", []):
            org = repo.get("org", "")
            repo_name = repo.get("name", "")
            if not repo_name:
                continue

            repo_path = _resolve_repo_path(org, repo_name, organ_key, ws, key_to_dir)
            if repo_path is None:
                entry = CIMandateEntry(
                    organ=organ_key,
                    repo_name=repo_name,
                    org=org,
                    has_ci=False,
                    repo_path_found=False,
                    promotion_status=repo.get("promotion_status", ""),
                )
            else:
                workflows = _check_ci_workflows(repo_path)
                entry = CIMandateEntry(
                    organ=organ_key,
                    repo_name=repo_name,
                    org=org,
                    has_ci=bool(workflows),
                    workflows=workflows,
                    promotion_status=repo.get("promotion_status", ""),
                )

            report.entries.append(entry)
            report.total += 1
            organ_stats["total"] += 1

            if entry.has_ci:
                report.has_ci += 1
                organ_stats["has_ci"] += 1
            else:
                report.missing_ci += 1
                organ_stats["missing_ci"] += 1
                organ_stats["missing_repos"].append(repo_name)

        report.by_organ[organ_key] = organ_stats

    return report
