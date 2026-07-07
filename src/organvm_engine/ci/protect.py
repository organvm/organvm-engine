"""Branch protection scaffolding — generate ``gh api`` commands for repos.

Drives issue #61 of the Descent Protocol: expand branch protection to all
GRADUATED repos across organs I-VII.

Generates the ``gh api`` PUT command (and JSON payload) needed to enable
branch protection on a repo's default branch.  The solo-operator config:

- Require status checks to pass before merging
- Prevent force pushes
- Prevent branch deletion
- Do NOT enforce for admins (solo operator needs escape hatch)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ProtectionPayload:
    """Branch protection configuration for a repository."""

    org: str
    repo_name: str
    branch: str = "main"
    require_status_checks: bool = True
    strict_status_checks: bool = True
    enforce_admins: bool = False
    dismiss_stale_reviews: bool = False
    required_approving_review_count: int = 0
    no_force_push: bool = True
    no_delete_branch: bool = True

    def to_api_json(self) -> dict:
        """Build the JSON payload for ``gh api`` PUT."""
        payload: dict = {
            "required_status_checks": {
                "strict": self.strict_status_checks,
                "contexts": [],
            } if self.require_status_checks else None,
            "enforce_admins": self.enforce_admins,
            "required_pull_request_reviews": None,
            "restrictions": None,
            "allow_force_pushes": not self.no_force_push,
            "allow_deletions": not self.no_delete_branch,
        }
        return {k: v for k, v in payload.items()}

    def to_gh_command(self) -> str:
        """Generate the full ``gh api`` command string."""
        endpoint = f"repos/{self.org}/{self.repo_name}/branches/{self.branch}/protection"
        payload_json = json.dumps(self.to_api_json(), indent=2)
        return (
            f"gh api -X PUT \"{endpoint}\" "
            f"--input - <<'EOF'\n{payload_json}\nEOF"
        )

    def to_dict(self) -> dict:
        return {
            "org": self.org,
            "repo": self.repo_name,
            "branch": self.branch,
            "endpoint": f"repos/{self.org}/{self.repo_name}/branches/{self.branch}/protection",
            "payload": self.to_api_json(),
            "command": self.to_gh_command(),
        }


@dataclass
class ProtectionPlan:
    """Plan for applying branch protection across multiple repos."""

    repos: list[ProtectionPayload] = field(default_factory=list)
    already_protected: list[str] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "Branch Protection Plan",
            "=" * 50,
            f"  To protect:        {len(self.repos)} repo(s)",
            f"  Already protected: {len(self.already_protected)} repo(s)",
            f"  Skipped:           {len(self.skipped)} repo(s)",
            "",
        ]
        if self.repos:
            lines.append("  Repos to protect:")
            for p in self.repos:
                lines.append(f"    - {p.org}/{p.repo_name}")
        if self.skipped:
            lines.append("")
            lines.append("  Skipped (not GRADUATED or docs-only):")
            for s in self.skipped:
                lines.append(f"    - {s['repo']}: {s['reason']}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "to_protect": [p.to_dict() for p in self.repos],
            "already_protected": self.already_protected,
            "skipped": self.skipped,
            "total_to_protect": len(self.repos),
        }

    def commands(self) -> list[str]:
        """Return list of ``gh api`` commands for all repos."""
        return [p.to_gh_command() for p in self.repos]


# Already-protected repos (from issue #61)
_ALREADY_PROTECTED: set[str] = {
    "organvm-engine",
    "schema-definitions",
    "alchemia-ingestvm",
    "system-dashboard",
    "organvm-mcp-server",
    "organvm-ontologia",
    "stakeholder-portal",
    "praxis-perpetua",
    "materia-collider",
}


def plan_branch_protection(
    registry: dict,
    *,
    organ_filter: str | None = None,
    repo_filter: str | None = None,
) -> ProtectionPlan:
    """Build a branch protection plan from the registry.

    Targets all GRADUATED repos not already protected.  Skips ARCHIVED,
    LOCAL, and docs-only repos.

    Args:
        registry: Loaded registry dict.
        organ_filter: Optional organ key filter (e.g., 'ORGAN-I').
        repo_filter: Optional repo name filter.

    Returns:
        ProtectionPlan with commands and skip reasons.
    """
    plan = ProtectionPlan()

    organs = registry.get("organs", {})
    for organ_key, organ_data in organs.items():
        if organ_filter and organ_key != organ_filter:
            continue

        for repo in organ_data.get("repositories", []):
            org_name = repo.get("org", "")
            repo_name = repo.get("name", "")
            if not repo_name:
                continue
            if repo_filter and repo_name != repo_filter:
                continue

            promotion = repo.get("promotion_status", "LOCAL")

            # Already protected
            if repo_name in _ALREADY_PROTECTED:
                plan.already_protected.append(f"{org_name}/{repo_name}")
                continue

            # Skip non-GRADUATED repos
            if promotion != "GRADUATED":
                plan.skipped.append({
                    "repo": f"{org_name}/{repo_name}",
                    "reason": f"status is {promotion}, not GRADUATED",
                })
                continue

            # Skip archived
            if promotion == "ARCHIVED":
                plan.skipped.append({
                    "repo": f"{org_name}/{repo_name}",
                    "reason": "archived",
                })
                continue

            plan.repos.append(ProtectionPayload(
                org=org_name,
                repo_name=repo_name,
            ))

    return plan
