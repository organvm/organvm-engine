"""Tests for CI mandate filesystem verification."""

from __future__ import annotations

from organvm_engine.ci.mandate import (
    CIMandateEntry,
    CIMandateReport,
    _check_ci_workflows,
    _resolve_repo_path,
    verify_ci_mandate,
)


class TestCheckCIWorkflows:
    def test_no_github_dir(self, tmp_path):
        assert _check_ci_workflows(tmp_path) == []

    def test_no_workflows_dir(self, tmp_path):
        (tmp_path / ".github").mkdir()
        assert _check_ci_workflows(tmp_path) == []

    def test_empty_workflows_dir(self, tmp_path):
        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        assert _check_ci_workflows(tmp_path) == []

    def test_finds_yaml_files(self, tmp_path):
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("name: CI")
        (wf / "deploy.yaml").write_text("name: Deploy")
        (wf / "README.md").write_text("not a workflow")
        result = _check_ci_workflows(tmp_path)
        assert sorted(result) == ["ci.yml", "deploy.yaml"]


class TestResolveRepoPath:
    def test_organ_dir_mapping(self, tmp_path):
        repo = tmp_path / "organvm-i-theoria" / "my-repo"
        repo.mkdir(parents=True)
        key_to_dir = {"ORGAN-I": "organvm-i-theoria"}
        result = _resolve_repo_path("ivviiviivvi", "my-repo", "ORGAN-I", tmp_path, key_to_dir)
        assert result == repo

    def test_fallback_to_org_name(self, tmp_path):
        repo = tmp_path / "my-org" / "my-repo"
        repo.mkdir(parents=True)
        result = _resolve_repo_path("my-org", "my-repo", "ORGAN-X", tmp_path, {})
        assert result == repo

    def test_fallback_to_flat_workspace_repo(self, tmp_path):
        repo = tmp_path / "my-repo"
        repo.mkdir()
        result = _resolve_repo_path("legacy-org", "my-repo", "ORGAN-X", tmp_path, {})
        assert result == repo

    def test_not_found(self, tmp_path):
        result = _resolve_repo_path("no-org", "no-repo", "ORGAN-X", tmp_path, {})
        assert result is None


class TestVerifyCIMandate:
    def test_empty_registry(self, tmp_path):
        report = verify_ci_mandate({"organs": {}}, workspace=tmp_path)
        assert report.total == 0
        assert report.adherence_rate == 0.0

    def test_repo_with_ci(self, tmp_path):
        repo_path = tmp_path / "my-org" / "my-repo" / ".github" / "workflows"
        repo_path.mkdir(parents=True)
        (repo_path / "ci.yml").write_text("name: CI")

        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {"name": "my-repo", "org": "my-org", "promotion_status": "CANDIDATE"},
                    ],
                },
            },
        }
        report = verify_ci_mandate(registry, workspace=tmp_path)
        assert report.total == 1
        assert report.has_ci == 1
        assert report.missing_ci == 0
        assert report.adherence_rate == 1.0

    def test_repo_without_ci(self, tmp_path):
        repo_path = tmp_path / "my-org" / "my-repo"
        repo_path.mkdir(parents=True)

        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {"name": "my-repo", "org": "my-org", "promotion_status": "CANDIDATE"},
                    ],
                },
            },
        }
        report = verify_ci_mandate(registry, workspace=tmp_path)
        assert report.total == 1
        assert report.has_ci == 0
        assert report.missing_ci == 1
        assert len(report.missing_repos()) == 1

    def test_repo_not_found_on_disk(self, tmp_path):
        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {"name": "ghost-repo", "org": "ghost-org"},
                    ],
                },
            },
        }
        report = verify_ci_mandate(registry, workspace=tmp_path)
        assert report.total == 1
        assert not report.entries[0].repo_path_found
        assert not report.entries[0].has_ci

    def test_by_organ_stats(self, tmp_path):
        (tmp_path / "org-a" / "repo-1" / ".github" / "workflows").mkdir(parents=True)
        (tmp_path / "org-a" / "repo-1" / ".github" / "workflows" / "ci.yml").write_text("x")
        (tmp_path / "org-b" / "repo-2").mkdir(parents=True)

        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [{"name": "repo-1", "org": "org-a"}],
                },
                "ORGAN-II": {
                    "repositories": [{"name": "repo-2", "org": "org-b"}],
                },
            },
        }
        report = verify_ci_mandate(registry, workspace=tmp_path)
        assert report.by_organ["ORGAN-I"]["has_ci"] == 1
        assert report.by_organ["ORGAN-II"]["missing_ci"] == 1


class TestDriftDetection:
    def test_registry_says_ci_but_no_files(self, tmp_path):
        (tmp_path / "org" / "repo").mkdir(parents=True)

        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {"name": "repo", "org": "org", "ci_workflow": True},
                    ],
                },
            },
        }
        report = verify_ci_mandate(registry, workspace=tmp_path)
        drift = report.drift_from_registry(registry)
        assert len(drift) == 1
        assert drift[0]["registry_says"] is True
        assert drift[0]["filesystem_says"] is False

    def test_no_drift_when_aligned(self, tmp_path):
        wf = tmp_path / "org" / "repo" / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("x")

        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {"name": "repo", "org": "org", "ci_workflow": True},
                    ],
                },
            },
        }
        report = verify_ci_mandate(registry, workspace=tmp_path)
        drift = report.drift_from_registry(registry)
        assert len(drift) == 0


class TestCIMandateReportToDict:
    def test_serialization(self):
        report = CIMandateReport(
            total=2, has_ci=1, missing_ci=1,
            entries=[
                CIMandateEntry(
                    organ="ORGAN-I", repo_name="r1", org="o",
                    has_ci=True, workflows=["ci.yml"],
                ),
                CIMandateEntry(
                    organ="ORGAN-II", repo_name="r2", org="o",
                    has_ci=False, repo_path_found=False,
                ),
            ],
        )
        d = report.to_dict()
        assert d["total"] == 2
        assert d["adherence_rate"] == 0.5
        assert len(d["entries"]) == 2
        assert d["entries"][0]["has_ci"] is True
        assert d["entries"][1]["repo_path_found"] is False
