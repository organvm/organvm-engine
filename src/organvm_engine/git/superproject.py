"""Superproject initialization and submodule management.

Each organ directory becomes a git superproject that tracks its child repos
as submodules. The workspace root (~/Workspace) is NOT a git repo.
"""

import contextlib
import subprocess
from pathlib import Path

import yaml

from organvm_engine.organ_config import organ_dir_map, registry_key_to_dir
from organvm_engine.paths import PathConfig
from organvm_engine.registry.loader import load_registry
from organvm_engine.registry.query import all_repos
from organvm_engine.seed.discover import DEFAULT_WORKSPACE

# Derived from canonical organ_config — mutable for governance-config.yaml overlay
ORGAN_DIR_MAP = organ_dir_map()
REGISTRY_KEY_MAP = registry_key_to_dir()


def load_governance_config(workspace: Path | None = None) -> None:
    """Load organ mappings from governance-config.yaml if available."""
    global ORGAN_DIR_MAP, REGISTRY_KEY_MAP
    ws = workspace or DEFAULT_WORKSPACE
    config_path = PathConfig(workspace_dir=ws).corpus_dir() / "governance-config.yaml"

    if config_path.is_file():
        try:
            with config_path.open() as f:
                data = yaml.safe_load(f)
            if "organ_directory_map" in data:
                REGISTRY_KEY_MAP.update(data["organ_directory_map"])
            if "short_key_map" in data:
                ORGAN_DIR_MAP.update(data["short_key_map"])
        except Exception as e:
            import warnings

            warnings.warn(f"Failed to load governance-config.yaml: {e}", stacklevel=2)


# Load config immediately on import
load_governance_config()

# Superproject GitHub remote URLs
SUPERPROJECT_REMOTES = {
    "organvm-i-theoria": "git@github.com:organvm-i-theoria/organvm-i-theoria--superproject.git",
    "organvm-ii-poiesis": "git@github.com:organvm-ii-poiesis/organvm-ii-poiesis--superproject.git",
    "organvm-iii-ergon": "git@github.com:organvm-iii-ergon/organvm-iii-ergon--superproject.git",
    "organvm-iv-taxis": "git@github.com:organvm-iv-taxis/organvm-iv-taxis--superproject.git",
    "organvm-v-logos": "git@github.com:organvm-v-logos/organvm-v-logos--superproject.git",
    "organvm-vi-koinonia": (
        "git@github.com:organvm-vi-koinonia/organvm-vi-koinonia--superproject.git"
    ),
    "organvm-vii-kerygma": (
        "git@github.com:organvm-vii-kerygma/organvm-vii-kerygma--superproject.git"
    ),
    "meta-organvm": "git@github.com:meta-organvm/meta-organvm--superproject.git",
    "4444J99": "git@github.com:4444J99/workspace--superproject.git",
}


def _run_git(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
    )


def _run_git_checked(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a git command and raise RuntimeError on failure."""
    result = _run_git(args, cwd, timeout=timeout)
    if result.returncode == 0:
        return result

    cmd = "git " + " ".join(args)
    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    details = stderr or stdout or "unknown git error"
    raise RuntimeError(f"{cmd} failed in {cwd}: {details}")


def _get_repos_for_organ(
    organ_dir: str,
    workspace: Path,
    registry: dict | None = None,
) -> list[dict]:
    """Get list of repos belonging to an organ directory.

    Combines registry data with local filesystem discovery.
    Each entry has: name, org, url.
    """
    organ_path = workspace / organ_dir
    if not organ_path.is_dir():
        return []

    # Build org name from registry
    repos = []
    if registry:
        for organ_key, repo in all_repos(registry):
            dir_name = REGISTRY_KEY_MAP.get(organ_key, "")
            if dir_name == organ_dir:
                repo_name = repo["name"]
                org = repo.get("org", organ_dir)
                repos.append(
                    {
                        "name": repo_name,
                        "org": org,
                        "url": f"git@github.com:{org}/{repo_name}.git",
                    },
                )

    # Also discover local repos not yet in registry
    registry_names = {r["name"] for r in repos}
    for child in sorted(organ_path.iterdir()):
        if child.is_dir() and (child / ".git").exists() and child.name not in registry_names:
            repos.append(
                {
                    "name": child.name,
                    "org": organ_dir,
                    "url": _get_remote_url(child) or f"git@github.com:{organ_dir}/{child.name}.git",
                },
            )

    return repos


def _get_remote_url(repo_path: Path) -> str | None:
    """Get the origin remote URL for a repo."""
    result = _run_git(["remote", "get-url", "origin"], repo_path)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def init_superproject(
    organ: str,
    workspace: Path | str | None = None,
    registry_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Initialize a superproject for an organ directory.

    Creates .git, .gitmodules, .gitignore in the organ directory,
    registers all child repos as submodules, and makes the initial commit.

    Args:
        organ: Organ identifier (I, II, III, IV, V, VI, VII, META, LIMINAL).
        workspace: Workspace root. Defaults to ~/Workspace.
        registry_path: Path to registry-v2.json.
        dry_run: If True, report what would be done without doing it.

    Returns:
        Dict with keys: organ_dir, repos_registered, remote, already_initialized.
    """
    ws = Path(workspace) if workspace else DEFAULT_WORKSPACE
    organ_dir = ORGAN_DIR_MAP.get(organ.upper())
    if not organ_dir:
        raise ValueError(f"Unknown organ: {organ}. Valid: {', '.join(ORGAN_DIR_MAP.keys())}")

    organ_path = ws / organ_dir
    if not organ_path.is_dir():
        raise FileNotFoundError(f"Organ directory not found: {organ_path}")

    # Check if already a git repo (superproject)
    already_init = (organ_path / ".git").exists()

    registry = None
    if registry_path:
        registry = load_registry(registry_path)
    else:
        with contextlib.suppress(FileNotFoundError):
            registry = load_registry()

    repos = _get_repos_for_organ(organ_dir, ws, registry)

    result = {
        "organ_dir": organ_dir,
        "repos_registered": len(repos),
        "remote": SUPERPROJECT_REMOTES.get(organ_dir, ""),
        "already_initialized": already_init,
        "repos": [r["name"] for r in repos],
    }

    if dry_run:
        return result

    # Initialize git if needed
    if not already_init:
        _run_git_checked(["init", "-b", "main"], organ_path)

    # Write .gitignore — ignore everything except superproject files
    gitignore_content = (
        "# Superproject: only track superproject metadata files\n"
        "*\n"
        "!.gitmodules\n"
        "!.gitignore\n"
        "!CLAUDE.md\n"
        "!README-superproject.md\n"
    )
    (organ_path / ".gitignore").write_text(gitignore_content)

    # Write README
    readme_content = (
        f"# {organ_dir} — Superproject\n\n"
        f"This repo tracks {len(repos)} submodules for the {organ_dir} organ.\n\n"
        "## Usage\n\n"
        "```bash\n"
        f"git clone --recurse-submodules <this-repo-url> {organ_dir}\n"
        "# Or after cloning:\n"
        "git submodule update --init --recursive\n"
        "```\n\n"
        "## Submodules\n\n"
    )
    for repo in sorted(repos, key=lambda r: r["name"]):
        readme_content += f"- `{repo['name']}` — {repo['url']}\n"
    (organ_path / "README-superproject.md").write_text(readme_content)

    # Write .gitmodules and register submodules
    gitmodules_lines = []
    for repo in sorted(repos, key=lambda r: r["name"]):
        repo_path = organ_path / repo["name"]
        if not repo_path.is_dir():
            continue

        gitmodules_lines.append(f'[submodule "{repo["name"]}"]')
        gitmodules_lines.append(f"\tpath = {repo['name']}")
        gitmodules_lines.append(f"\turl = {repo['url']}")
        gitmodules_lines.append("")

        # Register in .git/config
        _run_git_checked(
            ["config", "--file", ".git/config", f"submodule.{repo['name']}.url", repo["url"]],
            organ_path,
        )
        _run_git_checked(
            ["config", "--file", ".git/config", f"submodule.{repo['name']}.active", "true"],
            organ_path,
        )

        # Stage the gitlink (mode 160000) — force needed because .gitignore has *
        _run_git_checked(["add", "-f", repo["name"]], organ_path)

    (organ_path / ".gitmodules").write_text(
        "\n".join(gitmodules_lines) + "\n" if gitmodules_lines else "",
    )

    # Stage superproject files
    _run_git_checked(["add", ".gitmodules", ".gitignore", "README-superproject.md"], organ_path)
    if (organ_path / "CLAUDE.md").exists():
        _run_git_checked(["add", "CLAUDE.md"], organ_path)

    # Commit
    _run_git_checked(
        ["commit", "-m", f"feat: initialize {organ_dir} superproject with {len(repos)} submodules"],
        organ_path,
    )

    # Set remote
    remote_url = SUPERPROJECT_REMOTES.get(organ_dir, "")
    if remote_url:
        existing = _run_git(["remote", "get-url", "origin"], organ_path)
        if existing.returncode != 0:
            _run_git_checked(["remote", "add", "origin", remote_url], organ_path)
        elif existing.stdout.strip() != remote_url:
            _run_git_checked(["remote", "set-url", "origin", remote_url], organ_path)

    return result


def add_submodule(
    organ: str,
    repo_name: str,
    repo_url: str | None = None,
    workspace: Path | str | None = None,
) -> dict:
    """Add a new submodule to an organ superproject.

    Args:
        organ: Organ identifier.
        repo_name: Name of the repo to add.
        repo_url: Git URL. Auto-derived from organ if not provided.
        workspace: Workspace root.

    Returns:
        Dict with operation results.
    """
    ws = Path(workspace) if workspace else DEFAULT_WORKSPACE
    organ_dir = ORGAN_DIR_MAP.get(organ.upper())
    if not organ_dir:
        raise ValueError(f"Unknown organ: {organ}")

    organ_path = ws / organ_dir
    if not (organ_path / ".git").exists():
        raise RuntimeError(f"Not a superproject: {organ_path}. Run init-superproject first.")

    url = repo_url or f"git@github.com:{organ_dir}/{repo_name}.git"
    repo_path = organ_path / repo_name

    if not repo_path.is_dir():
        return {"error": f"Directory {repo_path} does not exist locally"}

    if not (repo_path / ".git").exists():
        return {"error": f"{repo_path} is not a git repo"}

    # Add to .gitmodules
    _run_git_checked(
        ["config", "--file", ".gitmodules", f"submodule.{repo_name}.path", repo_name],
        organ_path,
    )
    _run_git_checked(
        ["config", "--file", ".gitmodules", f"submodule.{repo_name}.url", url],
        organ_path,
    )

    # Register in .git/config
    _run_git_checked(
        ["config", "--file", ".git/config", f"submodule.{repo_name}.url", url],
        organ_path,
    )
    _run_git_checked(
        ["config", "--file", ".git/config", f"submodule.{repo_name}.active", "true"],
        organ_path,
    )

    # Stage gitlink and .gitmodules — force needed because .gitignore has *
    _run_git_checked(["add", "-f", repo_name], organ_path)
    _run_git_checked(["add", ".gitmodules"], organ_path)
    _run_git_checked(
        ["commit", "-m", f"feat: add submodule {repo_name}"],
        organ_path,
    )

    return {"added": repo_name, "url": url, "organ": organ_dir}


def sync_organ(
    organ: str,
    message: str | None = None,
    workspace: Path | str | None = None,
    dry_run: bool = False,
) -> dict:
    """Advance submodule pointers in an organ superproject.

    Stages all submodule pointer changes and commits with the given message.
    Does NOT run `git submodule update --remote` — pointer advancement is
    based on whatever the local repos currently point to.

    Args:
        organ: Organ identifier.
        message: Commit message. Auto-generated if not provided.
        workspace: Workspace root.
        dry_run: If True, report without committing.

    Returns:
        Dict with changed submodules and commit info.
    """
    ws = Path(workspace) if workspace else DEFAULT_WORKSPACE
    organ_dir = ORGAN_DIR_MAP.get(organ.upper())
    if not organ_dir:
        raise ValueError(f"Unknown organ: {organ}")

    organ_path = ws / organ_dir
    if not (organ_path / ".git").exists():
        raise RuntimeError(f"Not a superproject: {organ_path}")

    # Check for submodule pointer changes (ignore dirty content inside submodules)
    result = _run_git(["status", "--porcelain", "--ignore-submodules=dirty"], organ_path)
    changed = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        status = line[:2].strip()
        path = line[3:].strip()
        # Submodule changes show as 'M'/'m' (modified gitlink) or '??' (untracked
        # gitlink — happens when .gitignore has '*' and the submodule wasn't staged
        # with -f during init).
        if status in ("M", "m") or status == "??" and (organ_path / path / ".git").exists():
            changed.append(path)

    if not changed:
        return {"organ": organ_dir, "changed": [], "committed": False}

    if dry_run:
        return {"organ": organ_dir, "changed": changed, "committed": False, "dry_run": True}

    # Stage all changes (-f needed because .gitignore has '*')
    for path in changed:
        _run_git_checked(["add", "-f", path], organ_path)

    commit_msg = message or f"chore: sync {organ_dir} submodule pointers ({len(changed)} updated)"
    _run_git_checked(["commit", "-m", commit_msg], organ_path)

    # Emit to Testament Chain
    from organvm_engine.ledger.emit import testament_emit
    testament_emit(
        event_type="git.sync",
        source_organ=organ.upper(),
        source_repo=organ_dir,
        actor="cli",
        payload={"submodules": changed, "message": commit_msg},
    )

    return {"organ": organ_dir, "changed": changed, "committed": True}


def install_hooks(
    organ: str | None = None,
    workspace: Path | str | None = None,
) -> dict:
    """Install post-commit hooks in superprojects to auto-sync context.

    Args:
        organ: Optional specific organ. If None, installs in all superprojects.
        workspace: Workspace root.

    Returns:
        Dict with success/error status.
    """
    ws = Path(workspace) if workspace else DEFAULT_WORKSPACE
    target_keys = [organ.upper()] if organ else list(ORGAN_DIR_MAP.keys())

    results = {"installed": [], "errors": []}

    # Template for the hook
    hook_content = """\
#!/usr/bin/env bash
# ORGANVM Auto-Sync Context Hook
# Automatically runs 'organvm context sync' after registry/seed changes

# Check if the canonical registry (or compatibility breadcrumb) or seed changed
FILES_CHANGED=$(git diff-tree --no-commit-id --name-only -r HEAD)

if echo "$FILES_CHANGED" | grep -qE "(repo-registry.json|registry-v2.json|seed.yaml)"; then
    echo ":: ORGANVM post-commit :: Registry/Seed change detected. Syncing context files..."
    organvm context sync
fi
"""

    for key in target_keys:
        organ_dir = ORGAN_DIR_MAP.get(key)
        if not organ_dir:
            continue

        repo_path = ws / organ_dir
        if not (repo_path / ".git").exists():
            continue

        hook_path = repo_path / ".git/hooks/post-commit"
        try:
            hook_path.write_text(hook_content)
            hook_path.chmod(0o755)  # Executable
            results["installed"].append(organ_dir)
        except Exception as e:
            results["errors"].append({"organ": organ_dir, "error": str(e)})

    return results
