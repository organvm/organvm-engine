"""Git status reporting for organ superprojects."""

from pathlib import Path

from organvm_engine.git.superproject import ORGAN_DIR_MAP, _run_git
from organvm_engine.seed.discover import DEFAULT_WORKSPACE


def show_drift(
    organ: str | None = None,
    workspace: Path | str | None = None,
) -> list[dict]:
    """Show submodule pointer drift across organ superprojects.

    Drift means the local repo's HEAD differs from what the superproject
    has pinned (the gitlink SHA).

    Args:
        organ: Specific organ to check. If None, checks all.
        workspace: Workspace root.

    Returns:
        List of dicts with: organ, repo, pinned_sha, current_sha, ahead, behind.
    """
    ws = Path(workspace) if workspace else DEFAULT_WORKSPACE

    organs_to_check = {}
    if organ:
        key = organ.upper()
        if key in ORGAN_DIR_MAP:
            organs_to_check[key] = ORGAN_DIR_MAP[key]
        else:
            raise ValueError(f"Unknown organ: {organ}")
    else:
        organs_to_check = dict(ORGAN_DIR_MAP)

    drift_reports = []

    for _organ_key, organ_dir in organs_to_check.items():
        organ_path = ws / organ_dir
        if not (organ_path / ".git").exists():
            continue

        # Get submodule status
        result = _run_git(["submodule", "status"], organ_path)
        if result.returncode != 0:
            continue

        for line in result.stdout.rstrip("\n").split("\n"):
            if not line.strip():
                continue

            # Format: " <sha> <path> (<describe>)" or "+<sha> <path>" (modified)
            # or "-<sha> <path>" (not initialized)
            prefix = line[0]
            parts = line[1:].strip().split()
            if len(parts) < 2:
                continue

            pinned_sha = parts[0]
            repo_name = parts[1]
            repo_path = organ_path / repo_name

            if not (repo_path / ".git").exists():
                drift_reports.append(
                    {
                        "organ": organ_dir,
                        "repo": repo_name,
                        "pinned_sha": pinned_sha[:8],
                        "current_sha": "NOT_INIT",
                        "status": "not-initialized",
                    },
                )
                continue

            # Get current HEAD of the local repo
            head_result = _run_git(["rev-parse", "HEAD"], repo_path)
            if head_result.returncode != 0:
                continue

            current_sha = head_result.stdout.strip()

            if current_sha == pinned_sha:
                continue  # No drift

            # Count commits ahead/behind
            ahead_result = _run_git(
                ["rev-list", "--count", f"{pinned_sha}..{current_sha}"],
                repo_path,
            )
            behind_result = _run_git(
                ["rev-list", "--count", f"{current_sha}..{pinned_sha}"],
                repo_path,
            )

            ahead = int(ahead_result.stdout.strip()) if ahead_result.returncode == 0 else 0
            behind = int(behind_result.stdout.strip()) if behind_result.returncode == 0 else 0

            drift_reports.append(
                {
                    "organ": organ_dir,
                    "repo": repo_name,
                    "pinned_sha": pinned_sha[:8],
                    "current_sha": current_sha[:8],
                    "ahead": ahead,
                    "behind": behind,
                    "status": "modified" if prefix == "+" else "diverged",
                },
            )

    return drift_reports


def diff_pinned(
    organ: str | None = None,
    workspace: Path | str | None = None,
) -> list[dict]:
    """Show detailed diff between pinned and current submodule SHAs.

    Args:
        organ: Specific organ. If None, checks all.
        workspace: Workspace root.

    Returns:
        List of dicts with: organ, repo, pinned_sha, current_sha,
        commit_log (list of commits between pinned and current).
    """
    ws = Path(workspace) if workspace else DEFAULT_WORKSPACE

    organs_to_check = {}
    if organ:
        key = organ.upper()
        if key in ORGAN_DIR_MAP:
            organs_to_check[key] = ORGAN_DIR_MAP[key]
        else:
            raise ValueError(f"Unknown organ: {organ}")
    else:
        organs_to_check = dict(ORGAN_DIR_MAP)

    diffs = []

    for _organ_key, organ_dir in organs_to_check.items():
        organ_path = ws / organ_dir
        if not (organ_path / ".git").exists():
            continue

        result = _run_git(["submodule", "status"], organ_path)
        if result.returncode != 0:
            continue

        for line in result.stdout.rstrip("\n").split("\n"):
            if not line.strip() or line[0] not in ("+", "-"):
                continue

            parts = line[1:].strip().split()
            if len(parts) < 2:
                continue

            pinned_sha = parts[0]
            repo_name = parts[1]
            repo_path = organ_path / repo_name

            if not (repo_path / ".git").exists():
                continue

            head_result = _run_git(["rev-parse", "HEAD"], repo_path)
            if head_result.returncode != 0:
                continue
            current_sha = head_result.stdout.strip()

            # Get log between pinned and current
            log_result = _run_git(
                ["log", "--oneline", f"{pinned_sha}..{current_sha}"],
                repo_path,
            )
            commits = []
            if log_result.returncode == 0:
                commits = [
                    line.strip() for line in log_result.stdout.strip().split("\n") if line.strip()
                ]

            diffs.append(
                {
                    "organ": organ_dir,
                    "repo": repo_name,
                    "pinned_sha": pinned_sha[:8],
                    "current_sha": current_sha[:8],
                    "commit_log": commits,
                },
            )

    return diffs


def check_uncommitted_files(workspace: Path | str | None = None) -> list[dict]:
    """Check for uncommitted files across all repos in the workspace.

    Enforces the 'Nothing Local Only' covenant.
    """
    ws = Path(workspace) if workspace else DEFAULT_WORKSPACE
    uncommitted_reports = []

    if not ws.exists():
        return uncommitted_reports

    organs_to_check = dict(ORGAN_DIR_MAP)
    for _organ_key, organ_dir in organs_to_check.items():
        organ_path = ws / organ_dir
        if not (organ_path / ".git").exists():
            continue

        result = _run_git(["submodule", "status"], organ_path)
        if result.returncode != 0:
            continue

        for line in result.stdout.rstrip("\n").split("\n"):
            if not line.strip():
                continue
            parts = line[1:].strip().split()
            if len(parts) < 2:
                continue

            repo_name = parts[1]
            repo_path = organ_path / repo_name

            if not (repo_path / ".git").exists():
                continue

            status_result = _run_git(["status", "--porcelain"], repo_path)
            if status_result.returncode != 0:
                continue

            files = [line for line in status_result.stdout.strip().split("\n") if line.strip()]
            if files:
                uncommitted_reports.append(
                    {
                        "organ": organ_dir,
                        "repo": repo_name,
                        "uncommitted_count": len(files),
                        "files": files[:5] + (["..."] if len(files) > 5 else []),
                    },
                )

    return uncommitted_reports
