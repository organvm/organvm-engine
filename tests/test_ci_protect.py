"""Tests for ci/protect.py — branch protection plan generation."""

import json

import pytest

from organvm_engine.ci.protect import (
    ProtectionPayload,
    plan_branch_protection,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def registry_with_graduated() -> dict:
    """Registry with a mix of statuses for testing protection planning."""
    return {
        "version": "2.0",
        "organs": {
            "ORGAN-I": {
                "name": "Theory",
                "repositories": [
                    {
                        "name": "graduated-repo-a",
                        "org": "ivviiviivvi",
                        "promotion_status": "GRADUATED",
                        "tier": "standard",
                    },
                    {
                        "name": "local-repo",
                        "org": "ivviiviivvi",
                        "promotion_status": "LOCAL",
                        "tier": "standard",
                    },
                    {
                        "name": "candidate-repo",
                        "org": "ivviiviivvi",
                        "promotion_status": "CANDIDATE",
                        "tier": "standard",
                    },
                ],
            },
            "ORGAN-II": {
                "name": "Art",
                "repositories": [
                    {
                        "name": "graduated-repo-b",
                        "org": "omni-dromenon-machina",
                        "promotion_status": "GRADUATED",
                        "tier": "flagship",
                    },
                ],
            },
            "META-ORGANVM": {
                "name": "Meta",
                "repositories": [
                    {
                        "name": "organvm-engine",
                        "org": "meta-organvm",
                        "promotion_status": "GRADUATED",
                        "tier": "flagship",
                    },
                ],
            },
        },
    }


# ---------------------------------------------------------------------------
# ProtectionPayload
# ---------------------------------------------------------------------------

class TestProtectionPayload:
    def test_default_config(self):
        p = ProtectionPayload(org="my-org", repo_name="my-repo")
        assert p.branch == "main"
        assert p.enforce_admins is False
        assert p.no_force_push is True
        assert p.no_delete_branch is True

    def test_api_json_structure(self):
        p = ProtectionPayload(org="my-org", repo_name="my-repo")
        payload = p.to_api_json()
        assert payload["enforce_admins"] is False
        assert payload["allow_force_pushes"] is False
        assert payload["allow_deletions"] is False
        assert payload["required_status_checks"]["strict"] is True

    def test_gh_command_format(self):
        p = ProtectionPayload(org="my-org", repo_name="my-repo")
        cmd = p.to_gh_command()
        assert "gh api -X PUT" in cmd
        assert "repos/my-org/my-repo/branches/main/protection" in cmd
        assert "EOF" in cmd

    def test_to_dict_contains_all_fields(self):
        p = ProtectionPayload(org="my-org", repo_name="my-repo")
        d = p.to_dict()
        assert d["org"] == "my-org"
        assert d["repo"] == "my-repo"
        assert d["branch"] == "main"
        assert "endpoint" in d
        assert "payload" in d
        assert "command" in d


# ---------------------------------------------------------------------------
# plan_branch_protection
# ---------------------------------------------------------------------------

class TestPlanBranchProtection:
    def test_graduated_repos_are_planned(self, registry_with_graduated):
        plan = plan_branch_protection(registry_with_graduated)
        repo_names = {p.repo_name for p in plan.repos}
        assert "graduated-repo-a" in repo_names
        assert "graduated-repo-b" in repo_names

    def test_non_graduated_repos_are_skipped(self, registry_with_graduated):
        plan = plan_branch_protection(registry_with_graduated)
        repo_names = {p.repo_name for p in plan.repos}
        assert "local-repo" not in repo_names
        assert "candidate-repo" not in repo_names

    def test_already_protected_repos_excluded(self, registry_with_graduated):
        plan = plan_branch_protection(registry_with_graduated)
        # organvm-engine is in _ALREADY_PROTECTED
        repo_names = {p.repo_name for p in plan.repos}
        assert "organvm-engine" not in repo_names
        assert "meta-organvm/organvm-engine" in plan.already_protected

    def test_skipped_has_reason(self, registry_with_graduated):
        plan = plan_branch_protection(registry_with_graduated)
        skip_repos = {s["repo"] for s in plan.skipped}
        assert "ivviiviivvi/local-repo" in skip_repos

    def test_organ_filter(self, registry_with_graduated):
        plan = plan_branch_protection(
            registry_with_graduated, organ_filter="ORGAN-I",
        )
        repo_names = {p.repo_name for p in plan.repos}
        assert "graduated-repo-a" in repo_names
        assert "graduated-repo-b" not in repo_names

    def test_repo_filter(self, registry_with_graduated):
        plan = plan_branch_protection(
            registry_with_graduated, repo_filter="graduated-repo-b",
        )
        assert len(plan.repos) == 1
        assert plan.repos[0].repo_name == "graduated-repo-b"

    def test_empty_registry(self):
        plan = plan_branch_protection({"organs": {}})
        assert len(plan.repos) == 0
        assert len(plan.skipped) == 0


# ---------------------------------------------------------------------------
# ProtectionPlan
# ---------------------------------------------------------------------------

class TestProtectionPlan:
    def test_summary_output(self, registry_with_graduated):
        plan = plan_branch_protection(registry_with_graduated)
        summary = plan.summary()
        assert "Branch Protection Plan" in summary
        assert "To protect:" in summary

    def test_to_dict(self, registry_with_graduated):
        plan = plan_branch_protection(registry_with_graduated)
        d = plan.to_dict()
        assert "to_protect" in d
        assert "already_protected" in d
        assert "skipped" in d
        assert "total_to_protect" in d

    def test_commands_list(self, registry_with_graduated):
        plan = plan_branch_protection(registry_with_graduated)
        cmds = plan.commands()
        assert len(cmds) == len(plan.repos)
        for cmd in cmds:
            assert "gh api -X PUT" in cmd

    def test_to_dict_is_json_serializable(self, registry_with_graduated):
        plan = plan_branch_protection(registry_with_graduated)
        # Should not raise
        serialized = json.dumps(plan.to_dict())
        assert isinstance(serialized, str)
