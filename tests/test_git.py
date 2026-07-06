"""Tests for the organvm git module — superproject management."""

import subprocess

import pytest


@pytest.fixture
def mock_workspace(tmp_path):
    """Create a mock workspace with fake organ dirs and repos."""
    ws = tmp_path / "Workspace"
    ws.mkdir()

    # Create a mock organ dir with two repos
    organ_dir = ws / "meta-organvm"
    organ_dir.mkdir()

    for repo_name in ["organvm-engine", "organvm-corpvs"]:
        repo = organ_dir / repo_name
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, capture_output=True, check=False)
        (repo / "seed.yaml").write_text(f"repo: {repo_name}\norgan: META\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=False)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=repo,
            capture_output=True,
            check=False,
            env={
                "GIT_AUTHOR_NAME": "test",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "test",
                "GIT_COMMITTER_EMAIL": "t@t",
                "HOME": str(tmp_path),
                "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            },
        )

    return ws


@pytest.fixture
def mock_registry():
    """Minimal registry for testing."""
    return {
        "version": "2.0",
        "organs": {
            "ORGAN-META": {
                "name": "Meta",
                "repositories": [
                    {"name": "organvm-engine", "org": "meta-organvm"},
                    {"name": "organvm-corpvs", "org": "meta-organvm"},
                ],
            },
        },
    }


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    """Ensure git has a user identity for commit operations in CI."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@test")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@test")


class TestSuperproject:
    """Tests for superproject initialization and management."""

    def test_organ_dir_map_has_all_organs(self):
        from organvm_engine.git.superproject import ORGAN_DIR_MAP

        expected = {"I", "II", "III", "IV", "V", "VI", "VII", "META", "LIMINAL", "SIGMA_E"}
        assert set(ORGAN_DIR_MAP.keys()) == expected

    def test_superproject_remotes_map(self):
        from organvm_engine.git.superproject import SUPERPROJECT_REMOTES

        assert "meta-organvm" in SUPERPROJECT_REMOTES
        assert "organvm-i-theoria" in SUPERPROJECT_REMOTES
        assert SUPERPROJECT_REMOTES["meta-organvm"].endswith("--superproject.git")

    def test_init_superproject_dry_run(self, mock_workspace, mock_registry, monkeypatch):
        from organvm_engine.git.superproject import init_superproject

        # Patch load_registry to return mock
        monkeypatch.setattr(
            "organvm_engine.git.superproject.load_registry",
            lambda *a, **kw: mock_registry,
        )

        result = init_superproject(
            organ="META",
            workspace=mock_workspace,
            dry_run=True,
        )

        assert result["organ_dir"] == "meta-organvm"
        assert result["repos_registered"] == 2
        assert "organvm-engine" in result["repos"]
        assert "organvm-corpvs" in result["repos"]

    def test_init_superproject_creates_files(self, mock_workspace, mock_registry, monkeypatch):
        from organvm_engine.git.superproject import init_superproject

        monkeypatch.setattr(
            "organvm_engine.git.superproject.load_registry",
            lambda *a, **kw: mock_registry,
        )

        result = init_superproject(
            organ="META",
            workspace=mock_workspace,
        )

        organ_path = mock_workspace / "meta-organvm"
        assert (organ_path / ".git").exists()
        assert (organ_path / ".gitmodules").exists()
        assert (organ_path / ".gitignore").exists()
        assert (organ_path / "README-superproject.md").exists()
        assert result["repos_registered"] == 2

    def test_init_superproject_gitmodules_content(self, mock_workspace, mock_registry, monkeypatch):
        from organvm_engine.git.superproject import init_superproject

        monkeypatch.setattr(
            "organvm_engine.git.superproject.load_registry",
            lambda *a, **kw: mock_registry,
        )

        init_superproject(organ="META", workspace=mock_workspace)

        gitmodules = (mock_workspace / "meta-organvm" / ".gitmodules").read_text()
        assert "organvm-engine" in gitmodules
        assert "organvm-corpvs" in gitmodules

    def test_init_superproject_unknown_organ(self):
        from organvm_engine.git.superproject import init_superproject

        with pytest.raises(ValueError, match="Unknown organ"):
            init_superproject(organ="NONEXISTENT")

    def test_sync_organ_no_changes(self, mock_workspace, mock_registry, monkeypatch):
        from organvm_engine.git.superproject import init_superproject, sync_organ

        monkeypatch.setattr(
            "organvm_engine.git.superproject.load_registry",
            lambda *a, **kw: mock_registry,
        )

        init_superproject(organ="META", workspace=mock_workspace)
        result = sync_organ(organ="META", workspace=mock_workspace)

        assert result["changed"] == []
        assert result["committed"] is False

    def test_run_git_checked_raises_on_failure(self, tmp_path):
        from organvm_engine.git.superproject import _run_git_checked

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, capture_output=True, check=False)

        with pytest.raises(RuntimeError, match="git not-a-command"):
            _run_git_checked(["not-a-command"], repo)

    def test_init_superproject_surfaces_git_failures(
        self, mock_workspace, mock_registry, monkeypatch,
    ):
        from organvm_engine.git import superproject as sp

        monkeypatch.setattr(
            "organvm_engine.git.superproject.load_registry",
            lambda *a, **kw: mock_registry,
        )

        real_run_checked = sp._run_git_checked

        def failing_run(args, cwd, timeout=30):
            if args[:2] == ["add", "-f"] and len(args) > 2 and args[2] == "organvm-engine":
                raise RuntimeError("simulated git add failure")
            return real_run_checked(args, cwd, timeout=timeout)

        monkeypatch.setattr("organvm_engine.git.superproject._run_git_checked", failing_run)

        with pytest.raises(RuntimeError, match="simulated git add failure"):
            sp.init_superproject(organ="META", workspace=mock_workspace)


class TestGetReposForOrgan:
    """Tests for repo discovery within organ directories."""

    def test_discovers_local_repos(self, mock_workspace):
        from organvm_engine.git.superproject import _get_repos_for_organ

        repos = _get_repos_for_organ("meta-organvm", mock_workspace, registry=None)
        names = [r["name"] for r in repos]
        assert "organvm-engine" in names
        assert "organvm-corpvs" in names

    def test_merges_registry_and_local(self, mock_workspace, mock_registry):
        from organvm_engine.git.superproject import _get_repos_for_organ

        repos = _get_repos_for_organ("meta-organvm", mock_workspace, registry=mock_registry)
        names = [r["name"] for r in repos]
        assert "organvm-engine" in names
        assert "organvm-corpvs" in names
