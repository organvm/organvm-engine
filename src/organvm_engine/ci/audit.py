"""Infrastructure audit — The Descent Protocol enforcement.

Verifies that repositories have the required GitHub infrastructure
deployed on disk, mapped against promotion-tier requirements.
Extends ci/mandate.py (which checks CI workflows only) to audit
all 15 mechanisms defined in SOP--the-descent-protocol.md.

Filesystem-checkable mechanisms (12): ci_workflow, dependabot,
secret_scan, linting, testing, type_checking, codeql, codeowners,
pr_template, issue_templates, release_automation, stale_management.

API-only mechanisms (3): branch_protection, required_status_checks,
merge_queues — reported as 'requires_api' and excluded from scoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from organvm_engine.ci.mandate import _check_ci_workflows, _resolve_repo_path
from organvm_engine.organ_config import (
    get_topology_source,
    load_organ_topology,
    registry_key_to_dir,
)
from organvm_engine.paths import workspace_root


class CheckStatus(str, Enum):
    """Result of a single infrastructure check."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"  # not applicable (e.g., CodeQL on docs-only repo)
    API = "API"  # requires GitHub API, can't check from filesystem


# ---------------------------------------------------------------------------
# Tier requirements — maps promotion_status to required mechanism set
# ---------------------------------------------------------------------------

# Mechanisms required at each tier (cumulative — higher tiers include lower)
TIER_REQUIREMENTS: dict[str, set[str]] = {
    "INCUBATOR": set(),
    "LOCAL": {
        "ci_workflow",
        "dependabot",
    },
    "CANDIDATE": {
        "ci_workflow",
        "dependabot",
        "linting",
        "testing",
        "pr_template",
        "issue_templates",
    },
    "PUBLIC_PROCESS": {
        "ci_workflow",
        "dependabot",
        "linting",
        "testing",
        "pr_template",
        "issue_templates",
        "type_checking",
        "codeowners",
        "codeql",
    },
    "GRADUATED": {
        "ci_workflow",
        "dependabot",
        "linting",
        "testing",
        "pr_template",
        "issue_templates",
        "type_checking",
        "codeowners",
        "codeql",
        "release_automation",
        "stale_management",
        "secret_scan",
    },
    "ARCHIVED": set(),  # no requirements for archived repos
}

# Repos that are docs-only — skip code-specific checks (override: always docs-only)
_DOCS_ONLY_INDICATORS = {"praxis-perpetua", ".github"}

# Files whose presence indicates a code repo (not docs-only)
_CODE_INDICATOR_FILES = {
    "pyproject.toml",
    "package.json",
    "setup.py",
    "setup.cfg",
    "go.mod",
    "Cargo.toml",
    "Makefile",
    "CMakeLists.txt",
    "build.gradle",
    "pom.xml",
    "requirements.txt",
    "seed.yaml",
}

# Directories whose presence indicates a code repo (not docs-only)
_CODE_INDICATOR_DIRS = {
    "src",
    "lib",
    "cmd",
    "pkg",
    "internal",
    "app",
    "bin",
}


@dataclass
class InfraCheck:
    """Result of checking one mechanism for one repo."""

    mechanism: str
    status: CheckStatus
    detail: str = ""


@dataclass
class RepoCompliance:
    """All infrastructure checks for a single repo."""

    organ: str
    repo_name: str
    org: str
    promotion_status: str
    tier: str
    is_docs_only: bool
    repo_path: Path | None
    checks: list[InfraCheck] = field(default_factory=list)

    @property
    def required_mechanisms(self) -> set[str]:
        """Mechanisms required for this repo's promotion status and tier."""
        reqs = TIER_REQUIREMENTS.get(self.promotion_status, set()).copy()
        if self.is_docs_only:
            # Docs-only repos: skip code-specific checks
            reqs.discard("linting")
            reqs.discard("testing")
            reqs.discard("type_checking")
            reqs.discard("codeql")
        if self.tier == "infrastructure":
            # Infrastructure repos: reduced requirements — no release automation,
            # no type checking, no CodeQL (supporting tooling, not portfolio-facing)
            reqs.discard("release_automation")
            reqs.discard("type_checking")
            reqs.discard("codeql")
        if self.tier == "archive":
            # Archive repos: no requirements
            reqs.clear()
        return reqs

    @property
    def passing(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.PASS)

    @property
    def failing(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)

    @property
    def total_checkable(self) -> int:
        return sum(1 for c in self.checks if c.status != CheckStatus.API)

    @property
    def compliance_rate(self) -> float:
        t = self.total_checkable
        return self.passing / t if t > 0 else 1.0

    @property
    def tier_compliant(self) -> bool:
        """True if all required mechanisms for this tier pass."""
        required = self.required_mechanisms
        for check in self.checks:
            if check.mechanism in required and check.status == CheckStatus.FAIL:
                return False
        return True

    @property
    def failed_requirements(self) -> list[str]:
        """Mechanisms required at this tier that are failing."""
        required = self.required_mechanisms
        return [
            c.mechanism
            for c in self.checks
            if c.mechanism in required and c.status == CheckStatus.FAIL
        ]

    def summary_line(self) -> str:
        status = "COMPLIANT" if self.tier_compliant else "NON-COMPLIANT"
        return (
            f"  {self.repo_name:<40} "
            f"{self.promotion_status:<18} "
            f"{self.passing}/{self.total_checkable} "
            f"[{status}]"
        )

    def to_dict(self) -> dict:
        return {
            "organ": self.organ,
            "repo": self.repo_name,
            "org": self.org,
            "promotion_status": self.promotion_status,
            "tier": self.tier,
            "is_docs_only": self.is_docs_only,
            "passing": self.passing,
            "failing": self.failing,
            "total_checkable": self.total_checkable,
            "compliance_rate": round(self.compliance_rate, 4),
            "tier_compliant": self.tier_compliant,
            "failed_requirements": self.failed_requirements,
            "checks": [
                {"mechanism": c.mechanism, "status": c.status.value, "detail": c.detail}
                for c in self.checks
            ],
        }


@dataclass
class InfraAuditReport:
    """Full infrastructure audit report across the system."""

    total_repos: int = 0
    compliant_repos: int = 0
    non_compliant_repos: int = 0
    repos: list[RepoCompliance] = field(default_factory=list)
    by_organ: dict[str, dict] = field(default_factory=dict)

    @property
    def compliance_rate(self) -> float:
        return self.compliant_repos / self.total_repos if self.total_repos > 0 else 0.0

    def summary(self) -> str:
        lines = [
            "Infrastructure Audit — The Descent Protocol",
            "═" * 60,
            f"  {self.compliant_repos}/{self.total_repos} repos tier-compliant "
            f"({self.compliance_rate:.0%})",
            "",
        ]

        if self.by_organ:
            lines.append("  By Organ")
            lines.append(f"  {'─' * 55}")
            for organ, stats in sorted(self.by_organ.items()):
                total = stats["total"]
                compliant = stats["compliant"]
                pct = compliant / total if total > 0 else 0.0
                lines.append(f"    {organ:<20} {compliant}/{total} ({pct:.0%})")

        # Non-compliant repos
        non_compliant = [r for r in self.repos if not r.tier_compliant]
        if non_compliant:
            lines.append("")
            lines.append(f"  Non-Compliant Repos ({len(non_compliant)})")
            lines.append(f"  {'─' * 55}")
            for repo in non_compliant:
                lines.append(repo.summary_line())
                for mech in repo.failed_requirements:
                    lines.append(f"    ✗ {mech}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "total_repos": self.total_repos,
            "compliant_repos": self.compliant_repos,
            "non_compliant_repos": self.non_compliant_repos,
            "compliance_rate": round(self.compliance_rate, 4),
            "by_organ": self.by_organ,
            "repos": [r.to_dict() for r in self.repos],
        }


# ---------------------------------------------------------------------------
# Individual mechanism checks
# ---------------------------------------------------------------------------

def _is_docs_only(repo_name: str, repo_path: Path | None) -> bool:
    """Heuristic: is this repo docs-only (no code to lint/test)?

    Detection strategy:
    1. Override set — repos in _DOCS_ONLY_INDICATORS are always docs-only.
    2. Code-indicator files — presence of any build/config file (pyproject.toml,
       go.mod, Cargo.toml, Makefile, etc.) means it has code.
    3. Code-indicator directories — presence of src/, lib/, cmd/, pkg/, etc.
       means it has code.
    4. If none found, assume docs-only.
    """
    if repo_name in _DOCS_ONLY_INDICATORS:
        return True
    if repo_path is None:
        return False
    # Any code-indicator file present means this is a code repo
    if any((repo_path / f).is_file() for f in _CODE_INDICATOR_FILES):
        return False
    # Any code-indicator directory present means this is a code repo
    return all(not (repo_path / d).is_dir() for d in _CODE_INDICATOR_DIRS)


def _check_dependabot(repo_path: Path) -> InfraCheck:
    """Check for .github/dependabot.yml or .github/dependabot.yaml."""
    for name in ("dependabot.yml", "dependabot.yaml"):
        dep_path = repo_path / ".github" / name
        if dep_path.is_file():
            return InfraCheck("dependabot", CheckStatus.PASS, str(dep_path.name))
    return InfraCheck("dependabot", CheckStatus.FAIL, "no dependabot config found")


def _check_codeowners(repo_path: Path) -> InfraCheck:
    """Check for CODEOWNERS in .github/ or repo root."""
    for location in (repo_path / ".github" / "CODEOWNERS", repo_path / "CODEOWNERS"):
        if location.is_file():
            return InfraCheck("codeowners", CheckStatus.PASS, str(location.relative_to(repo_path)))
    return InfraCheck("codeowners", CheckStatus.FAIL, "no CODEOWNERS file")


_CODEQL_CONTENT_PATTERNS = [
    r"github/codeql-action/init",
    r"github/codeql-action/analyze",
    r"github/codeql-action/autobuild",
    r"github/codeql-action/upload-sarif",
    r"codeql[_-]analysis",
]


def _check_codeql(repo_path: Path) -> InfraCheck:
    """Check for CodeQL workflow.

    Uses a two-pass approach:
    1. Fast path: filename contains "codeql" (explicit CodeQL workflow file).
    2. Content fallback: scan all workflow YAML files for CodeQL action
       references (catches repos using codeql-action without a dedicated file).
    """
    wf_dir = repo_path / ".github" / "workflows"
    if not wf_dir.is_dir():
        return InfraCheck("codeql", CheckStatus.FAIL, "no workflows directory")

    # Fast path — filename match
    for f in wf_dir.iterdir():
        if f.is_file() and "codeql" in f.name.lower():
            return InfraCheck("codeql", CheckStatus.PASS, f.name)

    # Content fallback — scan workflow file contents for CodeQL action references
    for wf in wf_dir.iterdir():
        if not wf.is_file() or wf.suffix not in (".yml", ".yaml"):
            continue
        try:
            content = wf.read_text(errors="replace")
        except OSError:
            continue
        for pattern in _CODEQL_CONTENT_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return InfraCheck("codeql", CheckStatus.PASS, f"codeql action in {wf.name}")

    return InfraCheck("codeql", CheckStatus.FAIL, "no CodeQL workflow found")


def _check_pr_template(repo_path: Path) -> InfraCheck:
    """Check for PR template."""
    candidates = [
        repo_path / ".github" / "pull_request_template.md",
        repo_path / ".github" / "PULL_REQUEST_TEMPLATE.md",
        repo_path / "pull_request_template.md",
    ]
    # Also check PULL_REQUEST_TEMPLATE/ directory
    template_dir = repo_path / ".github" / "PULL_REQUEST_TEMPLATE"
    if template_dir.is_dir() and any(template_dir.iterdir()):
        return InfraCheck("pr_template", CheckStatus.PASS, "PULL_REQUEST_TEMPLATE/ directory")
    for c in candidates:
        if c.is_file():
            return InfraCheck("pr_template", CheckStatus.PASS, str(c.relative_to(repo_path)))
    return InfraCheck("pr_template", CheckStatus.FAIL, "no PR template found")


def _check_issue_templates(repo_path: Path) -> InfraCheck:
    """Check for issue templates."""
    template_dir = repo_path / ".github" / "ISSUE_TEMPLATE"
    if template_dir.is_dir():
        templates = [f for f in template_dir.iterdir() if f.is_file()]
        if templates:
            return InfraCheck(
                "issue_templates",
                CheckStatus.PASS,
                f"{len(templates)} template(s) in ISSUE_TEMPLATE/",
            )
    # Check for single issue template
    for name in ("ISSUE_TEMPLATE.md", "issue_template.md"):
        if (repo_path / ".github" / name).is_file() or (repo_path / name).is_file():
            return InfraCheck("issue_templates", CheckStatus.PASS, name)
    return InfraCheck("issue_templates", CheckStatus.FAIL, "no issue templates found")


_RELEASE_CONTENT_PATTERNS = [
    r"release-drafter/release-drafter",
    r"semantic-release",
    r"changesets/action",
    r"goreleaser/goreleaser-action",
    r"softprops/action-gh-release",
    r"ncipollo/release-action",
    r"pypa/gh-action-pypi-publish",
    r"actions/create-release",
    r"google-github-actions/release-please-action",
]


def _check_release_automation(repo_path: Path) -> InfraCheck:
    """Check for release drafter or similar release workflow.

    Uses a three-pass approach:
    1. Fast path: workflow filename contains release/publish keywords.
    2. Config fallback: release-drafter.yml in .github/.
    3. Content fallback: scan all workflow YAML files for known release
       action references (catches repos embedding release steps in CI).
    """
    wf_dir = repo_path / ".github" / "workflows"
    if not wf_dir.is_dir():
        return InfraCheck("release_automation", CheckStatus.FAIL, "no workflows directory")

    # Fast path — filename match
    release_keywords = {"release", "publish", "deploy-release"}
    for f in wf_dir.iterdir():
        if f.is_file() and any(kw in f.stem.lower() for kw in release_keywords):
            return InfraCheck("release_automation", CheckStatus.PASS, f.name)

    # Config fallback — release-drafter config file
    if (repo_path / ".github" / "release-drafter.yml").is_file():
        return InfraCheck("release_automation", CheckStatus.PASS, "release-drafter.yml config")

    # Content fallback — scan workflow file contents for release action references
    for wf in wf_dir.iterdir():
        if not wf.is_file() or wf.suffix not in (".yml", ".yaml"):
            continue
        try:
            content = wf.read_text(errors="replace")
        except OSError:
            continue
        for pattern in _RELEASE_CONTENT_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return InfraCheck(
                    "release_automation", CheckStatus.PASS, f"release action in {wf.name}",
                )

    return InfraCheck("release_automation", CheckStatus.FAIL, "no release automation found")


def _check_stale_management(repo_path: Path) -> InfraCheck:
    """Check for stale issue/PR management workflow."""
    wf_dir = repo_path / ".github" / "workflows"
    if not wf_dir.is_dir():
        return InfraCheck("stale_management", CheckStatus.FAIL, "no workflows directory")
    for f in wf_dir.iterdir():
        if f.is_file() and "stale" in f.stem.lower():
            return InfraCheck("stale_management", CheckStatus.PASS, f.name)
    return InfraCheck("stale_management", CheckStatus.FAIL, "no stale management workflow")


def _check_ci_content(
    repo_path: Path,
    mechanism: str,
    patterns: list[str],
) -> InfraCheck:
    """Check CI workflow content for specific step patterns.

    Reads all workflow files and searches for patterns indicating
    a specific CI capability (linting, testing, type checking, secret scanning).
    """
    wf_dir = repo_path / ".github" / "workflows"
    if not wf_dir.is_dir():
        return InfraCheck(mechanism, CheckStatus.FAIL, "no workflows directory")

    for wf in wf_dir.iterdir():
        if not wf.is_file() or wf.suffix not in (".yml", ".yaml"):
            continue
        try:
            content = wf.read_text(errors="replace")
        except OSError:
            continue
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return InfraCheck(mechanism, CheckStatus.PASS, f"found in {wf.name}")

    return InfraCheck(mechanism, CheckStatus.FAIL, f"no {mechanism} step in any workflow")


# Pattern sets for CI content checks
_LINT_PATTERNS = [
    r"ruff\s+check",
    r"eslint",
    r"npm\s+run\s+lint",
    r"flake8",
    r"pylint",
    r"markdownlint",
]

_TEST_PATTERNS = [
    r"pytest",
    r"npm\s+(run\s+)?test",
    r"vitest",
    r"jest",
    r"mocha",
    r"python.*-m\s+unittest",
]

_TYPECHECK_PATTERNS = [
    r"pyright",
    r"mypy",
    r"tsc\s+--noEmit",
    r"npm\s+run\s+typecheck",
    r"type-check",
]

_SECRET_SCAN_PATTERNS = [
    r"secret.?scan",
    r"gitleaks",
    r"trufflehog",
    r"detect-secrets",
    r"sk-\[a-zA-Z",  # the ci-minimal pattern
    r"ghp_\[a-zA-Z",
    r"AKIA\[A-Z",
]


# ---------------------------------------------------------------------------
# Main audit function
# ---------------------------------------------------------------------------

def audit_repo(
    repo_path: Path,
    repo_name: str,
    organ: str,
    org: str,
    promotion_status: str,
    tier: str,
) -> RepoCompliance:
    """Run all infrastructure checks on a single repository.

    Args:
        repo_path: Filesystem path to the repo root.
        repo_name: Repository name.
        organ: Organ registry key (e.g., 'META-ORGANVM').
        org: GitHub org name.
        promotion_status: Current promotion status.
        tier: Repository tier (flagship, standard, infrastructure, archive).

    Returns:
        RepoCompliance with all check results.
    """
    docs_only = _is_docs_only(repo_name, repo_path)

    compliance = RepoCompliance(
        organ=organ,
        repo_name=repo_name,
        org=org,
        promotion_status=promotion_status,
        tier=tier,
        is_docs_only=docs_only,
        repo_path=repo_path,
    )

    # 1. CI workflow exists
    workflows = _check_ci_workflows(repo_path)
    compliance.checks.append(InfraCheck(
        "ci_workflow",
        CheckStatus.PASS if workflows else CheckStatus.FAIL,
        f"{len(workflows)} workflow(s)" if workflows else "no workflows",
    ))

    # 2. Dependabot
    compliance.checks.append(_check_dependabot(repo_path))

    # 3. Secret scanning in CI
    if docs_only:
        compliance.checks.append(InfraCheck("secret_scan", CheckStatus.SKIP, "docs-only repo"))
    else:
        compliance.checks.append(
            _check_ci_content(repo_path, "secret_scan", _SECRET_SCAN_PATTERNS),
        )

    # 4. Linting in CI
    if docs_only:
        compliance.checks.append(InfraCheck("linting", CheckStatus.SKIP, "docs-only repo"))
    else:
        compliance.checks.append(
            _check_ci_content(repo_path, "linting", _LINT_PATTERNS),
        )

    # 5. Testing in CI
    if docs_only:
        compliance.checks.append(InfraCheck("testing", CheckStatus.SKIP, "docs-only repo"))
    else:
        compliance.checks.append(
            _check_ci_content(repo_path, "testing", _TEST_PATTERNS),
        )

    # 6. Type checking in CI
    if docs_only:
        compliance.checks.append(InfraCheck("type_checking", CheckStatus.SKIP, "docs-only repo"))
    else:
        compliance.checks.append(
            _check_ci_content(repo_path, "type_checking", _TYPECHECK_PATTERNS),
        )

    # 7. CodeQL
    if docs_only:
        compliance.checks.append(InfraCheck("codeql", CheckStatus.SKIP, "docs-only repo"))
    else:
        compliance.checks.append(_check_codeql(repo_path))

    # 8. CODEOWNERS
    compliance.checks.append(_check_codeowners(repo_path))

    # 9. Branch protection (API only)
    compliance.checks.append(InfraCheck(
        "branch_protection", CheckStatus.API, "requires GitHub API",
    ))

    # 10. Required status checks (API only)
    compliance.checks.append(InfraCheck(
        "required_status_checks", CheckStatus.API, "requires GitHub API",
    ))

    # 11. PR template
    compliance.checks.append(_check_pr_template(repo_path))

    # 12. Issue templates
    compliance.checks.append(_check_issue_templates(repo_path))

    # 13. Release automation
    if docs_only:
        compliance.checks.append(InfraCheck(
            "release_automation", CheckStatus.SKIP, "docs-only repo",
        ))
    else:
        compliance.checks.append(_check_release_automation(repo_path))

    # 14. Stale management
    compliance.checks.append(_check_stale_management(repo_path))

    # 15. Merge queues (API only)
    compliance.checks.append(InfraCheck(
        "merge_queues", CheckStatus.API, "requires GitHub API",
    ))

    return compliance


def run_infra_audit(
    registry: dict,
    workspace: Path | None = None,
    organ_filter: str | None = None,
    repo_filter: str | None = None,
) -> InfraAuditReport:
    """Run infrastructure audit across the system.

    Args:
        registry: Loaded registry dict.
        workspace: Workspace root. Defaults to paths.workspace_root().
        organ_filter: Optional organ key filter (e.g., 'META-ORGANVM').
        repo_filter: Optional repo name filter.

    Returns:
        InfraAuditReport with per-repo compliance results.
    """
    ws = workspace or workspace_root()
    if get_topology_source() == "fallback":
        load_organ_topology()
    key_to_dir = registry_key_to_dir()
    report = InfraAuditReport()

    organs = registry.get("organs", {})
    for organ_key, organ_data in organs.items():
        if organ_filter and organ_key != organ_filter:
            continue

        organ_stats = {"total": 0, "compliant": 0, "non_compliant": 0}

        for repo in organ_data.get("repositories", []):
            org_name = repo.get("org", "")
            repo_name = repo.get("name", "")
            if not repo_name:
                continue
            if repo_filter and repo_name != repo_filter:
                continue

            promotion = repo.get("promotion_status", "LOCAL")
            tier = repo.get("tier", "standard")

            # Skip archived repos
            if promotion == "ARCHIVED":
                continue

            repo_path = _resolve_repo_path(org_name, repo_name, organ_key, ws, key_to_dir)
            if repo_path is None:
                # Repo not found on disk — can't audit
                compliance = RepoCompliance(
                    organ=organ_key,
                    repo_name=repo_name,
                    org=org_name,
                    promotion_status=promotion,
                    tier=tier,
                    is_docs_only=False,
                    repo_path=None,
                )
                compliance.checks.append(InfraCheck(
                    "filesystem", CheckStatus.FAIL, "repo not found on disk",
                ))
                report.repos.append(compliance)
                report.total_repos += 1
                report.non_compliant_repos += 1
                organ_stats["total"] += 1
                organ_stats["non_compliant"] += 1
                continue

            compliance = audit_repo(
                repo_path=repo_path,
                repo_name=repo_name,
                organ=organ_key,
                org=org_name,
                promotion_status=promotion,
                tier=tier,
            )

            report.repos.append(compliance)
            report.total_repos += 1
            organ_stats["total"] += 1

            if compliance.tier_compliant:
                report.compliant_repos += 1
                organ_stats["compliant"] += 1
            else:
                report.non_compliant_repos += 1
                organ_stats["non_compliant"] += 1

        if organ_stats["total"] > 0:
            report.by_organ[organ_key] = organ_stats

    return report


def check_promotion_infrastructure(
    repo_path: Path,
    repo_name: str,
    organ: str,
    org: str,
    current_status: str,
    target_status: str,
    tier: str,
) -> tuple[bool, list[str]]:
    """Check if a repo has sufficient infrastructure for promotion.

    Used as a gate in the promotion state machine.

    Args:
        repo_path: Filesystem path to the repo.
        repo_name: Repository name.
        organ: Organ registry key.
        org: GitHub org.
        current_status: Current promotion status.
        target_status: Target promotion status.
        tier: Repo tier.

    Returns:
        (passes, failures) — True if all required mechanisms pass,
        list of failing mechanism names if not.
    """
    compliance = audit_repo(
        repo_path=repo_path,
        repo_name=repo_name,
        organ=organ,
        org=org,
        promotion_status=target_status,  # check against TARGET tier
        tier=tier,
    )

    failures = compliance.failed_requirements
    return len(failures) == 0, failures
