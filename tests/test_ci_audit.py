"""Tests for ci/audit.py — The Descent Protocol infrastructure audit."""

import json
from pathlib import Path

import pytest

from organvm_engine.ci.audit import (
    TIER_REQUIREMENTS,
    CheckStatus,
    InfraAuditReport,
    audit_repo,
    check_promotion_infrastructure,
    run_infra_audit,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def full_repo(tmp_path: Path) -> Path:
    """Create a fully-compliant repo structure."""
    repo = tmp_path / "test-repo"
    repo.mkdir()

    # src layout
    (repo / "src").mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname = 'test'")

    # .github structure
    gh = repo / ".github"
    gh.mkdir()
    wf = gh / "workflows"
    wf.mkdir()

    # CI workflow with all steps
    (wf / "ci.yml").write_text(
        "name: CI\non:\n  push:\n    branches: [main]\n"
        "jobs:\n  test:\n    steps:\n"
        "      - run: ruff check src/\n"
        "      - run: pytest tests/ -v\n"
        "      - run: pyright src/\n"
        "      - name: Secret scan\n"
        "        run: |\n"
        "          for pattern in 'sk-[a-zA-Z0-9]{20,}' 'ghp_[a-zA-Z0-9]{36}';\n",
    )

    # CodeQL
    (wf / "codeql.yml").write_text("name: CodeQL\non:\n  push:\n")

    # Release drafter
    (wf / "release-drafter.yml").write_text("name: Release Drafter\non:\n  push:\n")

    # Stale management
    (wf / "stale.yml").write_text("name: Stale\non:\n  schedule:\n")

    # Dependabot
    (gh / "dependabot.yml").write_text("version: 2\nupdates:\n  - package-ecosystem: pip\n")

    # CODEOWNERS
    (gh / "CODEOWNERS").write_text("* @4444j99\n")

    # PR template
    (gh / "pull_request_template.md").write_text("## Summary\n")

    # Issue templates
    it = gh / "ISSUE_TEMPLATE"
    it.mkdir()
    (it / "bug_report.md").write_text("---\nname: Bug\n---\n")
    (it / "feature_request.md").write_text("---\nname: Feature\n---\n")

    # Release drafter config
    (gh / "release-drafter.yml").write_text("name-template: v$RESOLVED_VERSION\n")

    return repo


@pytest.fixture()
def minimal_repo(tmp_path: Path) -> Path:
    """Create a bare-minimum repo (no infrastructure)."""
    repo = tmp_path / "bare-repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Bare repo\n")
    (repo / "pyproject.toml").write_text("[project]\nname = 'bare'")
    return repo


@pytest.fixture()
def docs_repo(tmp_path: Path) -> Path:
    """Create a docs-only repo."""
    repo = tmp_path / "docs-repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Docs\n")
    gh = repo / ".github"
    gh.mkdir()
    wf = gh / "workflows"
    wf.mkdir()
    (wf / "ci.yml").write_text("name: CI\non:\n  push:\nsteps:\n  - run: markdownlint\n")
    (gh / "dependabot.yml").write_text("version: 2\n")
    return repo


# ---------------------------------------------------------------------------
# Tier requirements
# ---------------------------------------------------------------------------

class TestTierRequirements:
    def test_tiers_are_cumulative(self):
        """Higher tiers should include all lower tier requirements."""
        local = TIER_REQUIREMENTS["LOCAL"]
        candidate = TIER_REQUIREMENTS["CANDIDATE"]
        public = TIER_REQUIREMENTS["PUBLIC_PROCESS"]
        graduated = TIER_REQUIREMENTS["GRADUATED"]

        assert local.issubset(candidate)
        assert candidate.issubset(public)
        assert public.issubset(graduated)

    def test_archived_has_no_requirements(self):
        assert TIER_REQUIREMENTS["ARCHIVED"] == set()

    def test_incubator_has_no_requirements(self):
        assert TIER_REQUIREMENTS["INCUBATOR"] == set()

    def test_graduated_includes_all_filesystem_checks(self):
        graduated = TIER_REQUIREMENTS["GRADUATED"]
        assert "ci_workflow" in graduated
        assert "dependabot" in graduated
        assert "codeowners" in graduated
        assert "codeql" in graduated
        assert "release_automation" in graduated
        assert "stale_management" in graduated
        assert "secret_scan" in graduated


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

class TestAuditRepo:
    def test_full_repo_all_pass(self, full_repo: Path):
        result = audit_repo(
            repo_path=full_repo,
            repo_name="test-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="GRADUATED",
            tier="flagship",
        )
        assert result.repo_name == "test-repo"
        assert result.is_docs_only is False
        # All filesystem-checkable mechanisms should pass
        for check in result.checks:
            if check.status != CheckStatus.API:
                assert check.status in (CheckStatus.PASS, CheckStatus.SKIP), (
                    f"{check.mechanism} should pass: {check.detail}"
                )

    def test_minimal_repo_many_fail(self, minimal_repo: Path):
        result = audit_repo(
            repo_path=minimal_repo,
            repo_name="bare-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="LOCAL",
            tier="standard",
        )
        assert result.failing > 0
        assert result.is_docs_only is False

    def test_docs_repo_skips_code_checks(self, docs_repo: Path):
        result = audit_repo(
            repo_path=docs_repo,
            repo_name="praxis-perpetua",  # in _DOCS_ONLY_INDICATORS
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="GRADUATED",
            tier="standard",
        )
        assert result.is_docs_only is True
        skipped = [c for c in result.checks if c.status == CheckStatus.SKIP]
        skip_names = {c.mechanism for c in skipped}
        assert "linting" in skip_names
        assert "testing" in skip_names
        assert "type_checking" in skip_names
        assert "codeql" in skip_names

    def test_check_count(self, full_repo: Path):
        """Audit should produce exactly 15 checks."""
        result = audit_repo(
            repo_path=full_repo,
            repo_name="test-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="GRADUATED",
            tier="standard",
        )
        assert len(result.checks) == 15

    def test_api_checks_present(self, full_repo: Path):
        result = audit_repo(
            repo_path=full_repo,
            repo_name="test-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="GRADUATED",
            tier="standard",
        )
        api_checks = [c for c in result.checks if c.status == CheckStatus.API]
        api_names = {c.mechanism for c in api_checks}
        assert "branch_protection" in api_names
        assert "required_status_checks" in api_names
        assert "merge_queues" in api_names


# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------

class TestRepoCompliance:
    def test_tier_compliant_full_repo(self, full_repo: Path):
        result = audit_repo(
            repo_path=full_repo,
            repo_name="test-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="GRADUATED",
            tier="standard",
        )
        assert result.tier_compliant is True
        assert result.failed_requirements == []

    def test_tier_non_compliant_minimal(self, minimal_repo: Path):
        result = audit_repo(
            repo_path=minimal_repo,
            repo_name="bare-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="CANDIDATE",
            tier="standard",
        )
        assert result.tier_compliant is False
        assert len(result.failed_requirements) > 0

    def test_archived_always_compliant(self, minimal_repo: Path):
        result = audit_repo(
            repo_path=minimal_repo,
            repo_name="bare-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="ARCHIVED",
            tier="archive",
        )
        assert result.tier_compliant is True

    def test_compliance_rate(self, full_repo: Path):
        result = audit_repo(
            repo_path=full_repo,
            repo_name="test-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="GRADUATED",
            tier="standard",
        )
        assert result.compliance_rate > 0.8

    def test_summary_line(self, full_repo: Path):
        result = audit_repo(
            repo_path=full_repo,
            repo_name="test-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="GRADUATED",
            tier="standard",
        )
        line = result.summary_line()
        assert "test-repo" in line
        assert "GRADUATED" in line

    def test_to_dict(self, full_repo: Path):
        result = audit_repo(
            repo_path=full_repo,
            repo_name="test-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="GRADUATED",
            tier="standard",
        )
        d = result.to_dict()
        assert d["repo"] == "test-repo"
        assert d["organ"] == "META-ORGANVM"
        assert isinstance(d["checks"], list)
        assert len(d["checks"]) == 15
        # Verify JSON serializable
        json.dumps(d)


# ---------------------------------------------------------------------------
# Full audit report
# ---------------------------------------------------------------------------

class TestRunInfraAudit:
    def test_audit_with_minimal_registry(self, tmp_path: Path):
        """Test audit against a minimal registry with repos on disk."""
        # Create two repos
        repo_a = tmp_path / "meta-organvm" / "repo-a"
        repo_a.mkdir(parents=True)
        (repo_a / "pyproject.toml").write_text("[project]\nname = 'a'")
        gh_a = repo_a / ".github" / "workflows"
        gh_a.mkdir(parents=True)
        (gh_a / "ci.yml").write_text("name: CI\nsteps:\n  - run: pytest\n")
        (repo_a / ".github" / "dependabot.yml").write_text("version: 2\n")

        registry = {
            "organs": {
                "META-ORGANVM": {
                    "repositories": [
                        {
                            "name": "repo-a",
                            "org": "meta-organvm",
                            "promotion_status": "LOCAL",
                            "tier": "standard",
                        },
                    ],
                },
            },
        }

        report = run_infra_audit(registry, workspace=tmp_path)
        assert report.total_repos == 1
        assert len(report.repos) == 1

    def test_audit_resolves_consolidated_a_organvm_layout(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Audit uses loaded topology orgs for post-consolidation flat checkouts."""
        from organvm_engine.organ_config import reset_topology

        corpus = tmp_path / "a-organvm" / "organvm-corpvs-testamentvm"
        corpus.mkdir(parents=True)
        (corpus / "repo-registry.json").write_text("{}")
        (corpus / "organ-topology.json").write_text(json.dumps({
            "I": {"dir": "organvm", "registry_key": "ORGAN-I", "org": "a-organvm"},
        }))
        monkeypatch.setenv("ORGANVM_CORPUS_DIR", str(corpus))

        repo = tmp_path / "a-organvm" / "repo-a"
        repo.mkdir(parents=True)
        (repo / "pyproject.toml").write_text("[project]\nname = 'repo-a'")
        workflows = repo / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text(
            "name: CI\njobs:\n  test:\n    steps:\n      - run: pyright src/\n",
        )
        (repo / ".github" / "dependabot.yml").write_text("version: 2\n")

        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {
                            "name": "repo-a",
                            "org": "organvm-i-theoria",
                            "promotion_status": "LOCAL",
                            "tier": "standard",
                        },
                    ],
                },
            },
        }

        try:
            report = run_infra_audit(registry, workspace=tmp_path, repo_filter="repo-a")
            assert report.total_repos == 1
            result = report.repos[0]
            assert result.repo_path == repo
            typecheck = next(c for c in result.checks if c.mechanism == "type_checking")
            assert typecheck.status == CheckStatus.PASS
        finally:
            reset_topology()

    def test_organ_filter(self, tmp_path: Path):
        registry = {
            "organs": {
                "META-ORGANVM": {
                    "repositories": [
                        {"name": "r1", "org": "meta-organvm", "promotion_status": "LOCAL", "tier": "standard"},
                    ],
                },
                "ORGAN-I": {
                    "repositories": [
                        {"name": "r2", "org": "organvm-i-theoria", "promotion_status": "LOCAL", "tier": "standard"},
                    ],
                },
            },
        }
        report = run_infra_audit(registry, workspace=tmp_path, organ_filter="META-ORGANVM")
        # Should only include META repos
        assert all(r.organ == "META-ORGANVM" for r in report.repos)

    def test_archived_repos_skipped(self, tmp_path: Path):
        registry = {
            "organs": {
                "META-ORGANVM": {
                    "repositories": [
                        {"name": "old", "org": "meta-organvm", "promotion_status": "ARCHIVED", "tier": "archive"},
                    ],
                },
            },
        }
        report = run_infra_audit(registry, workspace=tmp_path)
        assert report.total_repos == 0

    def test_report_summary(self, tmp_path: Path):
        report = InfraAuditReport(total_repos=10, compliant_repos=7, non_compliant_repos=3)
        summary = report.summary()
        assert "7/10" in summary
        assert "70%" in summary

    def test_report_to_dict(self, tmp_path: Path):
        report = InfraAuditReport(total_repos=5, compliant_repos=3, non_compliant_repos=2)
        d = report.to_dict()
        assert d["total_repos"] == 5
        assert d["compliance_rate"] == 0.6
        json.dumps(d)


# ---------------------------------------------------------------------------
# Promotion gate
# ---------------------------------------------------------------------------

class TestPromotionInfrastructure:
    def test_full_repo_passes_graduated(self, full_repo: Path):
        ok, failures = check_promotion_infrastructure(
            repo_path=full_repo,
            repo_name="test-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            current_status="PUBLIC_PROCESS",
            target_status="GRADUATED",
            tier="standard",
        )
        assert ok is True
        assert failures == []

    def test_minimal_repo_fails_candidate(self, minimal_repo: Path):
        ok, failures = check_promotion_infrastructure(
            repo_path=minimal_repo,
            repo_name="bare-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            current_status="LOCAL",
            target_status="CANDIDATE",
            tier="standard",
        )
        assert ok is False
        assert len(failures) > 0
        assert "ci_workflow" in failures

    def test_minimal_repo_passes_incubator_target(self, minimal_repo: Path):
        """Promoting to INCUBATOR has no infrastructure requirements."""
        ok, failures = check_promotion_infrastructure(
            repo_path=minimal_repo,
            repo_name="bare-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            current_status="INCUBATOR",
            target_status="INCUBATOR",  # INCUBATOR has no requirements
            tier="standard",
        )
        assert ok is True
        assert failures == []

    def test_local_target_requires_ci_and_dependabot(self, minimal_repo: Path):
        """LOCAL tier requires ci_workflow + dependabot."""
        ok, failures = check_promotion_infrastructure(
            repo_path=minimal_repo,
            repo_name="bare-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            current_status="INCUBATOR",
            target_status="LOCAL",
            tier="standard",
        )
        assert ok is False
        assert "ci_workflow" in failures
        assert "dependabot" in failures


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_nonexistent_repo_path(self, tmp_path: Path):
        result = audit_repo(
            repo_path=tmp_path / "does-not-exist",
            repo_name="ghost",
            organ="ORGAN-I",
            org="ivviiviivvi",
            promotion_status="LOCAL",
            tier="standard",
        )
        # Should fail gracefully
        assert result.failing > 0

    def test_empty_github_dir(self, tmp_path: Path):
        repo = tmp_path / "empty-gh"
        repo.mkdir()
        (repo / ".github").mkdir()
        (repo / "pyproject.toml").write_text("[project]\nname = 'e'")
        result = audit_repo(
            repo_path=repo,
            repo_name="empty-gh",
            organ="ORGAN-I",
            org="ivviiviivvi",
            promotion_status="LOCAL",
            tier="standard",
        )
        assert result.failing > 0

    def test_check_status_enum_values(self):
        assert CheckStatus.PASS.value == "PASS"
        assert CheckStatus.FAIL.value == "FAIL"
        assert CheckStatus.SKIP.value == "SKIP"
        assert CheckStatus.API.value == "API"

    def test_docs_only_detection_by_name(self, tmp_path: Path):
        """Repos in _DOCS_ONLY_INDICATORS are flagged as docs-only."""
        repo = tmp_path / ".github"
        repo.mkdir()
        result = audit_repo(
            repo_path=repo,
            repo_name=".github",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="GRADUATED",
            tier="infrastructure",
        )
        assert result.is_docs_only is True

    def test_docs_only_detection_by_content(self, tmp_path: Path):
        """Repos without any code-indicator files or dirs are docs-only."""
        repo = tmp_path / "pure-docs"
        repo.mkdir()
        (repo / "README.md").write_text("# Docs only\n")
        result = audit_repo(
            repo_path=repo,
            repo_name="pure-docs",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="LOCAL",
            tier="standard",
        )
        assert result.is_docs_only is True

    @pytest.mark.parametrize(
        "indicator_file",
        [
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
        ],
    )
    def test_code_indicator_file_prevents_docs_only(self, tmp_path: Path, indicator_file: str):
        """Any code-indicator file should mark the repo as not docs-only."""
        from organvm_engine.ci.audit import _is_docs_only

        repo = tmp_path / "code-repo"
        repo.mkdir()
        (repo / "README.md").write_text("# Has code\n")
        (repo / indicator_file).write_text("")
        assert _is_docs_only("code-repo", repo) is False

    @pytest.mark.parametrize(
        "indicator_dir",
        ["src", "lib", "cmd", "pkg", "internal", "app", "bin"],
    )
    def test_code_indicator_dir_prevents_docs_only(self, tmp_path: Path, indicator_dir: str):
        """Any code-indicator directory should mark the repo as not docs-only."""
        from organvm_engine.ci.audit import _is_docs_only

        repo = tmp_path / "code-repo"
        repo.mkdir()
        (repo / "README.md").write_text("# Has code\n")
        (repo / indicator_dir).mkdir()
        assert _is_docs_only("code-repo", repo) is False

    def test_override_set_trumps_code_indicators(self, tmp_path: Path):
        """Repos in _DOCS_ONLY_INDICATORS are docs-only even with code files."""
        from organvm_engine.ci.audit import _is_docs_only

        repo = tmp_path / ".github"
        repo.mkdir()
        (repo / "pyproject.toml").write_text("[project]\nname = 'gh'")
        (repo / "src").mkdir()
        assert _is_docs_only(".github", repo) is True

    def test_none_repo_path_is_not_docs_only(self):
        """None repo_path (can't inspect disk) defaults to not docs-only."""
        from organvm_engine.ci.audit import _is_docs_only

        assert _is_docs_only("unknown-repo", None) is False


# ---------------------------------------------------------------------------
# Individual mechanism checks (direct unit tests)
# ---------------------------------------------------------------------------

class TestIndividualChecks:
    """Direct tests for each private check function."""

    def test_check_dependabot_present(self, tmp_path: Path):
        from organvm_engine.ci.audit import _check_dependabot

        repo = tmp_path / "r"
        repo.mkdir()
        (repo / ".github").mkdir()
        (repo / ".github" / "dependabot.yml").write_text("version: 2\n")
        result = _check_dependabot(repo)
        assert result.status == CheckStatus.PASS

    def test_check_dependabot_yaml_extension(self, tmp_path: Path):
        from organvm_engine.ci.audit import _check_dependabot

        repo = tmp_path / "r"
        repo.mkdir()
        (repo / ".github").mkdir()
        (repo / ".github" / "dependabot.yaml").write_text("version: 2\n")
        result = _check_dependabot(repo)
        assert result.status == CheckStatus.PASS

    def test_check_dependabot_missing(self, tmp_path: Path):
        from organvm_engine.ci.audit import _check_dependabot

        repo = tmp_path / "r"
        repo.mkdir()
        (repo / ".github").mkdir()
        result = _check_dependabot(repo)
        assert result.status == CheckStatus.FAIL

    def test_check_codeowners_in_github_dir(self, tmp_path: Path):
        from organvm_engine.ci.audit import _check_codeowners

        repo = tmp_path / "r"
        repo.mkdir()
        (repo / ".github").mkdir()
        (repo / ".github" / "CODEOWNERS").write_text("* @owner\n")
        result = _check_codeowners(repo)
        assert result.status == CheckStatus.PASS

    def test_check_codeowners_at_root(self, tmp_path: Path):
        from organvm_engine.ci.audit import _check_codeowners

        repo = tmp_path / "r"
        repo.mkdir()
        (repo / "CODEOWNERS").write_text("* @owner\n")
        result = _check_codeowners(repo)
        assert result.status == CheckStatus.PASS

    def test_check_codeowners_missing(self, tmp_path: Path):
        from organvm_engine.ci.audit import _check_codeowners

        repo = tmp_path / "r"
        repo.mkdir()
        result = _check_codeowners(repo)
        assert result.status == CheckStatus.FAIL

    def test_check_codeql_present(self, tmp_path: Path):
        from organvm_engine.ci.audit import _check_codeql

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "codeql.yml").write_text("name: CodeQL\n")
        result = _check_codeql(repo)
        assert result.status == CheckStatus.PASS

    def test_check_codeql_missing(self, tmp_path: Path):
        from organvm_engine.ci.audit import _check_codeql

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("name: CI\n")
        result = _check_codeql(repo)
        assert result.status == CheckStatus.FAIL

    def test_check_pr_template_directory(self, tmp_path: Path):
        from organvm_engine.ci.audit import _check_pr_template

        repo = tmp_path / "r"
        tpl_dir = repo / ".github" / "PULL_REQUEST_TEMPLATE"
        tpl_dir.mkdir(parents=True)
        (tpl_dir / "default.md").write_text("## PR\n")
        result = _check_pr_template(repo)
        assert result.status == CheckStatus.PASS

    def test_check_issue_templates_single_file(self, tmp_path: Path):
        from organvm_engine.ci.audit import _check_issue_templates

        repo = tmp_path / "r"
        (repo / ".github").mkdir(parents=True)
        (repo / ".github" / "ISSUE_TEMPLATE.md").write_text("## Issue\n")
        result = _check_issue_templates(repo)
        assert result.status == CheckStatus.PASS

    def test_check_release_config_fallback(self, tmp_path: Path):
        from organvm_engine.ci.audit import _check_release_automation

        repo = tmp_path / "r"
        gh = repo / ".github"
        gh.mkdir(parents=True)
        (gh / "workflows").mkdir()
        (gh / "release-drafter.yml").write_text("name-template: v$V\n")
        result = _check_release_automation(repo)
        assert result.status == CheckStatus.PASS

    def test_check_stale_present(self, tmp_path: Path):
        from organvm_engine.ci.audit import _check_stale_management

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "stale.yml").write_text("name: Stale\n")
        result = _check_stale_management(repo)
        assert result.status == CheckStatus.PASS

    def test_check_ci_content_non_yaml_skipped(self, tmp_path: Path):
        from organvm_engine.ci.audit import _check_ci_content

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "notes.txt").write_text("ruff check src/\n")
        result = _check_ci_content(repo, "linting", [r"ruff\s+check"])
        assert result.status == CheckStatus.FAIL


# ---------------------------------------------------------------------------
# Tier-aware requirements
# ---------------------------------------------------------------------------

class TestTierAwareRequirements:
    def test_infrastructure_tier_reduces_requirements(self, full_repo: Path):
        result = audit_repo(
            repo_path=full_repo,
            repo_name="infra-repo",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="GRADUATED",
            tier="infrastructure",
        )
        reqs = result.required_mechanisms
        assert "release_automation" not in reqs
        assert "type_checking" not in reqs
        assert "codeql" not in reqs
        assert "ci_workflow" in reqs

    def test_archive_tier_clears_all(self, minimal_repo: Path):
        result = audit_repo(
            repo_path=minimal_repo,
            repo_name="old",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="GRADUATED",
            tier="archive",
        )
        assert result.required_mechanisms == set()
        assert result.tier_compliant is True

    def test_standard_tier_full_requirements(self, full_repo: Path):
        result = audit_repo(
            repo_path=full_repo,
            repo_name="std",
            organ="META-ORGANVM",
            org="meta-organvm",
            promotion_status="GRADUATED",
            tier="standard",
        )
        reqs = result.required_mechanisms
        assert "release_automation" in reqs
        assert "type_checking" in reqs


# ---------------------------------------------------------------------------
# run_infra_audit edge cases
# ---------------------------------------------------------------------------

class TestRunInfraAuditEdgeCases:
    def test_repo_filter(self, tmp_path: Path):
        registry = {
            "organs": {
                "META-ORGANVM": {
                    "repositories": [
                        {"name": "r1", "org": "o", "promotion_status": "LOCAL", "tier": "standard"},
                        {"name": "r2", "org": "o", "promotion_status": "LOCAL", "tier": "standard"},
                    ],
                },
            },
        }
        report = run_infra_audit(registry, workspace=tmp_path, repo_filter="r1")
        assert all(r.repo_name == "r1" for r in report.repos)

    def test_repo_not_on_disk(self, tmp_path: Path):
        registry = {
            "organs": {
                "META-ORGANVM": {
                    "repositories": [
                        {"name": "ghost", "org": "o", "promotion_status": "LOCAL", "tier": "standard"},
                    ],
                },
            },
        }
        report = run_infra_audit(registry, workspace=tmp_path)
        assert report.total_repos == 1
        assert report.non_compliant_repos == 1

    def test_empty_name_skipped(self, tmp_path: Path):
        registry = {
            "organs": {
                "META-ORGANVM": {
                    "repositories": [{"name": "", "org": "o", "promotion_status": "LOCAL"}],
                },
            },
        }
        report = run_infra_audit(registry, workspace=tmp_path)
        assert report.total_repos == 0

    def test_summary_with_organ_data(self):
        report = InfraAuditReport(
            total_repos=10,
            compliant_repos=6,
            non_compliant_repos=4,
            by_organ={"META": {"total": 5, "compliant": 3, "non_compliant": 2}},
        )
        summary = report.summary()
        assert "META" in summary
        assert "6/10" in summary

    def test_compliance_rate_zero_repos(self):
        report = InfraAuditReport()
        assert report.compliance_rate == 0.0


# ---------------------------------------------------------------------------
# Promotion gate integration
# ---------------------------------------------------------------------------

class TestPromotionGateIntegration:
    def test_gate_blocks_missing_infra(self, minimal_repo: Path):
        from organvm_engine.governance.state_machine import (
            execute_transition,
            reset_loaded_transitions,
        )

        reset_loaded_transitions()
        ok, msg = execute_transition(
            repo_name="bare",
            current_state="LOCAL",
            target_state="CANDIDATE",
            repo_path=minimal_repo,
            organ="META-ORGANVM",
            org="meta-organvm",
            tier="standard",
        )
        assert ok is False
        assert "Infrastructure requirements not met" in msg
        reset_loaded_transitions()

    def test_gate_allows_with_infra(self, full_repo: Path):
        from organvm_engine.governance.state_machine import (
            execute_transition,
            reset_loaded_transitions,
        )

        reset_loaded_transitions()
        ok, _ = execute_transition(
            repo_name="full",
            current_state="LOCAL",
            target_state="CANDIDATE",
            repo_path=full_repo,
            organ="META-ORGANVM",
            org="meta-organvm",
            tier="standard",
        )
        assert ok is True
        reset_loaded_transitions()

    def test_gate_skipped_without_repo_path(self):
        from organvm_engine.governance.state_machine import (
            execute_transition,
            reset_loaded_transitions,
        )

        reset_loaded_transitions()
        ok, _ = execute_transition(
            repo_name="any",
            current_state="LOCAL",
            target_state="CANDIDATE",
        )
        assert ok is True
        reset_loaded_transitions()

    def test_gate_skipped_for_archival(self, minimal_repo: Path):
        from organvm_engine.governance.state_machine import (
            execute_transition,
            reset_loaded_transitions,
        )

        reset_loaded_transitions()
        ok, _ = execute_transition(
            repo_name="old",
            current_state="GRADUATED",
            target_state="ARCHIVED",
            repo_path=minimal_repo,
            organ="META-ORGANVM",
            org="meta-organvm",
            tier="standard",
        )
        assert ok is True
        reset_loaded_transitions()

    def test_gate_disabled_with_flag(self, minimal_repo: Path):
        from organvm_engine.governance.state_machine import (
            execute_transition,
            reset_loaded_transitions,
        )

        reset_loaded_transitions()
        ok, _ = execute_transition(
            repo_name="bare",
            current_state="LOCAL",
            target_state="CANDIDATE",
            repo_path=minimal_repo,
            organ="META-ORGANVM",
            org="meta-organvm",
            tier="standard",
            enforce_infrastructure=False,
        )
        assert ok is True
        reset_loaded_transitions()


# ---------------------------------------------------------------------------
# Content-based detection (CodeQL and release automation)
# ---------------------------------------------------------------------------

class TestCodeQLContentDetection:
    """Tests for content-based CodeQL detection (fallback path)."""

    def test_codeql_action_init_in_ci_workflow(self, tmp_path: Path):
        """CodeQL detected via github/codeql-action/init in a non-codeql-named file."""
        from organvm_engine.ci.audit import _check_codeql

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text(
            "name: CI\n"
            "jobs:\n"
            "  analyze:\n"
            "    steps:\n"
            "      - uses: github/codeql-action/init@v3\n"
            "        with:\n"
            "          languages: python\n"
            "      - uses: github/codeql-action/analyze@v3\n",
        )
        result = _check_codeql(repo)
        assert result.status == CheckStatus.PASS
        assert "codeql action in ci.yml" in result.detail

    def test_codeql_action_analyze_only(self, tmp_path: Path):
        """CodeQL detected via analyze action alone."""
        from organvm_engine.ci.audit import _check_codeql

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "security.yml").write_text(
            "name: Security\n"
            "jobs:\n"
            "  scan:\n"
            "    steps:\n"
            "      - uses: github/codeql-action/analyze@v2\n",
        )
        result = _check_codeql(repo)
        assert result.status == CheckStatus.PASS

    def test_codeql_upload_sarif(self, tmp_path: Path):
        """CodeQL detected via upload-sarif action."""
        from organvm_engine.ci.audit import _check_codeql

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "analysis.yml").write_text(
            "name: Analysis\n"
            "steps:\n"
            "  - uses: github/codeql-action/upload-sarif@v3\n",
        )
        result = _check_codeql(repo)
        assert result.status == CheckStatus.PASS

    def test_codeql_analysis_keyword(self, tmp_path: Path):
        """CodeQL detected via codeql_analysis or codeql-analysis keyword."""
        from organvm_engine.ci.audit import _check_codeql

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "scan.yml").write_text(
            "name: Scan\n"
            "jobs:\n"
            "  codeql-analysis:\n"
            "    runs-on: ubuntu-latest\n",
        )
        result = _check_codeql(repo)
        assert result.status == CheckStatus.PASS

    def test_filename_fast_path_takes_precedence(self, tmp_path: Path):
        """When filename matches, content scanning is skipped -- detail is filename."""
        from organvm_engine.ci.audit import _check_codeql

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "codeql-analysis.yml").write_text("name: CodeQL\n")
        result = _check_codeql(repo)
        assert result.status == CheckStatus.PASS
        assert result.detail == "codeql-analysis.yml"

    def test_no_codeql_in_content_still_fails(self, tmp_path: Path):
        """Workflow without CodeQL references still fails."""
        from organvm_engine.ci.audit import _check_codeql

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text(
            "name: CI\n"
            "jobs:\n"
            "  test:\n"
            "    steps:\n"
            "      - run: pytest tests/ -v\n",
        )
        result = _check_codeql(repo)
        assert result.status == CheckStatus.FAIL

    def test_non_yaml_files_ignored_in_content_scan(self, tmp_path: Path):
        """Non-YAML files in workflows/ are not scanned for content."""
        from organvm_engine.ci.audit import _check_codeql

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "notes.txt").write_text("github/codeql-action/init\n")
        result = _check_codeql(repo)
        assert result.status == CheckStatus.FAIL

    def test_codeql_autobuild_action(self, tmp_path: Path):
        """CodeQL detected via autobuild action reference."""
        from organvm_engine.ci.audit import _check_codeql

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "build.yaml").write_text(
            "steps:\n"
            "  - uses: github/codeql-action/autobuild@v3\n",
        )
        result = _check_codeql(repo)
        assert result.status == CheckStatus.PASS


class TestReleaseAutomationContentDetection:
    """Tests for content-based release automation detection (fallback path)."""

    def test_semantic_release_in_ci(self, tmp_path: Path):
        """Release automation detected via semantic-release in CI workflow."""
        from organvm_engine.ci.audit import _check_release_automation

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text(
            "name: CI\n"
            "jobs:\n"
            "  deploy:\n"
            "    steps:\n"
            "      - run: npx semantic-release\n",
        )
        result = _check_release_automation(repo)
        assert result.status == CheckStatus.PASS
        assert "release action in ci.yml" in result.detail

    def test_changesets_action(self, tmp_path: Path):
        """Release automation detected via changesets/action."""
        from organvm_engine.ci.audit import _check_release_automation

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text(
            "steps:\n"
            "  - uses: changesets/action@v1\n",
        )
        result = _check_release_automation(repo)
        assert result.status == CheckStatus.PASS

    def test_goreleaser_action(self, tmp_path: Path):
        """Release automation detected via goreleaser."""
        from organvm_engine.ci.audit import _check_release_automation

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "build.yml").write_text(
            "steps:\n"
            "  - uses: goreleaser/goreleaser-action@v5\n",
        )
        result = _check_release_automation(repo)
        assert result.status == CheckStatus.PASS

    def test_softprops_gh_release(self, tmp_path: Path):
        """Release automation detected via softprops/action-gh-release."""
        from organvm_engine.ci.audit import _check_release_automation

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "deploy.yaml").write_text(
            "steps:\n"
            "  - uses: softprops/action-gh-release@v1\n"
            "    with:\n"
            "      files: dist/*\n",
        )
        result = _check_release_automation(repo)
        assert result.status == CheckStatus.PASS

    def test_pypi_publish_action(self, tmp_path: Path):
        """Release automation detected via pypa/gh-action-pypi-publish."""
        from organvm_engine.ci.audit import _check_release_automation

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text(
            "steps:\n"
            "  - uses: pypa/gh-action-pypi-publish@release/v1\n",
        )
        result = _check_release_automation(repo)
        assert result.status == CheckStatus.PASS

    def test_release_please_action(self, tmp_path: Path):
        """Release automation detected via release-please."""
        from organvm_engine.ci.audit import _check_release_automation

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text(
            "steps:\n"
            "  - uses: google-github-actions/release-please-action@v4\n",
        )
        result = _check_release_automation(repo)
        assert result.status == CheckStatus.PASS

    def test_release_drafter_action_in_content(self, tmp_path: Path):
        """Release automation via release-drafter action in workflow content."""
        from organvm_engine.ci.audit import _check_release_automation

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "drafter.yml").write_text(
            "steps:\n"
            "  - uses: release-drafter/release-drafter@v5\n",
        )
        result = _check_release_automation(repo)
        assert result.status == CheckStatus.PASS

    def test_filename_fast_path_takes_precedence(self, tmp_path: Path):
        """When filename matches, content scanning is skipped -- detail is filename."""
        from organvm_engine.ci.audit import _check_release_automation

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "release.yml").write_text("name: Release\n")
        result = _check_release_automation(repo)
        assert result.status == CheckStatus.PASS
        assert result.detail == "release.yml"

    def test_no_release_in_content_still_fails(self, tmp_path: Path):
        """Workflow without release references still fails."""
        from organvm_engine.ci.audit import _check_release_automation

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text(
            "name: CI\n"
            "steps:\n"
            "  - run: pytest tests/ -v\n",
        )
        result = _check_release_automation(repo)
        assert result.status == CheckStatus.FAIL

    def test_non_yaml_files_ignored_in_content_scan(self, tmp_path: Path):
        """Non-YAML files in workflows/ are not scanned for content."""
        from organvm_engine.ci.audit import _check_release_automation

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "readme.md").write_text("Uses semantic-release for publishing\n")
        result = _check_release_automation(repo)
        assert result.status == CheckStatus.FAIL

    def test_actions_create_release(self, tmp_path: Path):
        """Release automation detected via actions/create-release."""
        from organvm_engine.ci.audit import _check_release_automation

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "tag.yml").write_text(
            "steps:\n"
            "  - uses: actions/create-release@v1\n",
        )
        result = _check_release_automation(repo)
        assert result.status == CheckStatus.PASS

    def test_ncipollo_release_action(self, tmp_path: Path):
        """Release automation detected via ncipollo/release-action."""
        from organvm_engine.ci.audit import _check_release_automation

        repo = tmp_path / "r"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yaml").write_text(
            "steps:\n"
            "  - uses: ncipollo/release-action@v1\n",
        )
        result = _check_release_automation(repo)
        assert result.status == CheckStatus.PASS
