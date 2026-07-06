#!/usr/bin/env python3
"""
ORGANVM Workspace Topology Consolidation

Migrates from 8-org directory structure to 2-entity flat pool:
  ~/Workspace/organvm/    — all system repos
  ~/Workspace/4444j99/    — personal repos

Run with --dry-run (default) to preview, --execute to perform the migration.
"""
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE = Path.home() / "Workspace"
TARGET_SYSTEM = WORKSPACE / "organvm"
TARGET_PERSONAL = WORKSPACE / "4444j99"

# Directories that are organ superprojects (contain git repos as subdirs)
ORGAN_DIRS = [
    "organvm-i-theoria",
    "organvm-i-theria",  # typo variant — check if real
    "organvm-ii-poiesis",
    "organvm-iii-ergon",
    "organvm-iv-taxis",
    "organvm-v-logos",
    "organvm-vi-koinonia",
    "organvm-vii-kerygma",
    "meta-organvm",
]

# Standalone repos that belong to the system (not in an organ dir)
SYSTEM_STANDALONE = [
    "a-i--skills",
    "alchemia-ingestvm",
    "blender-mcp",
    "fastmcp",
    "k6-contrib",
    "openai-agents-contrib",
    "python-sdk",
    "dwv",
    "gemini-cli-blender-extension",
]

# Personal repos (stay in 4444j99/)
PERSONAL_DIR = "4444J99"

# Files/dirs that stay at workspace root
ROOT_KEEPS = [
    "intake",
    "CLAUDE.md",
    "AGENTS.md",
    "GEMINI.md",
    "INSTANCE.toml",
    "workspace-manifest.json",
]

# Files at root to clean up (move to intake or remove)
ROOT_CLEANUP_PATTERNS = [
    "export-*.md",
    "2026-*.txt",
    "2026-*.md",
    "session-*.md",
    "*.sh",
    "text-based--relevance.md",
]


def is_git_repo(path: Path) -> bool:
    """Check if a directory is a git repository."""
    return (path / ".git").exists()


def find_repos_in_dir(parent: Path) -> list[Path]:
    """Find all git repos directly inside a directory (not nested)."""
    repos = []
    if not parent.exists():
        return repos
    for child in sorted(parent.iterdir()):
        if child.is_dir() and is_git_repo(child):
            repos.append(child)
    return repos


def get_remote_url(repo: Path) -> str:
    """Get the origin remote URL for a repo."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def plan_migration() -> dict:
    """Build the migration plan without executing."""
    plan = {
        "moves_to_system": [],      # (source, dest) tuples
        "moves_to_personal": [],
        "standalone_to_system": [],
        "root_cleanup": [],
        "superprojects_to_archive": [],
        "errors": [],
        "stats": {},
    }

    # 1. Repos inside organ superproject directories → system
    for organ_dir_name in ORGAN_DIRS:
        organ_path = WORKSPACE / organ_dir_name
        if not organ_path.exists():
            continue

        repos = find_repos_in_dir(organ_path)
        for repo in repos:
            # Skip the superproject itself (same name as dir)
            if repo.name == organ_dir_name:
                continue
            dest = TARGET_SYSTEM / repo.name
            if dest.exists():
                plan["errors"].append(f"COLLISION: {repo} → {dest} already exists")
            else:
                plan["moves_to_system"].append((str(repo), str(dest)))

        # The superproject dir itself gets archived after repos are moved
        if is_git_repo(organ_path):
            plan["superprojects_to_archive"].append(str(organ_path))

    # 2. Standalone system repos → system
    for standalone in SYSTEM_STANDALONE:
        src = WORKSPACE / standalone
        if not src.exists():
            continue
        if is_git_repo(src):
            dest = TARGET_SYSTEM / standalone
            if dest.exists():
                plan["errors"].append(f"COLLISION: {src} → {dest} already exists")
            else:
                plan["standalone_to_system"].append((str(src), str(dest)))

    # 3. Personal repos — already in 4444J99, just note the rename
    personal_path = WORKSPACE / PERSONAL_DIR
    if personal_path.exists():
        repos = find_repos_in_dir(personal_path)
        for repo in repos:
            # These stay — just noting them
            plan["moves_to_personal"].append(str(repo))

    # 4. Root cleanup candidates
    for item in WORKSPACE.iterdir():
        if item.name.startswith("export-") and item.name.endswith(".md") or item.name.startswith("2026-") and item.suffix in (".txt", ".md") or item.name.startswith("session-") and item.name.endswith(".md") or item.name in {"sync_interlinked_landing_pages.sh", "text-based--relevance.md"}:
            plan["root_cleanup"].append(str(item))

    # Stats
    plan["stats"] = {
        "repos_to_system": len(plan["moves_to_system"]) + len(plan["standalone_to_system"]),
        "repos_already_personal": len(plan["moves_to_personal"]),
        "superprojects_to_archive": len(plan["superprojects_to_archive"]),
        "root_items_to_clean": len(plan["root_cleanup"]),
        "collisions": len(plan["errors"]),
    }

    return plan


def execute_migration(plan: dict) -> None:
    """Execute the migration plan."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    # Create target directories
    TARGET_SYSTEM.mkdir(exist_ok=True)
    print(f"[OK] Created {TARGET_SYSTEM}")

    # Move repos to system
    for src, dest in plan["moves_to_system"] + plan["standalone_to_system"]:
        try:
            shutil.move(src, dest)
            print(f"[MOVED] {Path(src).name} → organvm/")
        except Exception as e:
            print(f"[ERROR] {src} → {dest}: {e}")

    # Archive superproject .git directories (keep metadata, remove .git tracking)
    archive_dir = WORKSPACE / ".archive" / f"superprojects-{timestamp}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for sp_path in plan["superprojects_to_archive"]:
        sp = Path(sp_path)
        if sp.exists() and is_git_repo(sp):
            # Move the entire superproject (now empty of repos) to archive
            archive_dest = archive_dir / sp.name
            try:
                shutil.move(str(sp), str(archive_dest))
                print(f"[ARCHIVED] {sp.name} → .archive/superprojects-{timestamp}/")
            except Exception as e:
                print(f"[ERROR] archiving {sp.name}: {e}")

    # Move root cleanup items to intake
    intake = WORKSPACE / "intake" / "workspace-cleanup" / timestamp
    if plan["root_cleanup"]:
        intake.mkdir(parents=True, exist_ok=True)
        for item_path in plan["root_cleanup"]:
            item = Path(item_path)
            if item.exists():
                try:
                    shutil.move(str(item), str(intake / item.name))
                    print(f"[CLEANED] {item.name} → intake/workspace-cleanup/")
                except Exception as e:
                    print(f"[ERROR] cleaning {item.name}: {e}")

    print("\n[DONE] Migration complete. Verify with: ls ~/Workspace/organvm/ | wc -l")


def print_plan(plan: dict) -> None:
    """Pretty-print the migration plan."""
    print("=" * 70)
    print("ORGANVM WORKSPACE CONSOLIDATION — DRY RUN")
    print("=" * 70)

    print("\n## Stats")
    for k, v in plan["stats"].items():
        print(f"  {k}: {v}")

    if plan["errors"]:
        print("\n## ERRORS (must resolve before executing)")
        for e in plan["errors"]:
            print(f"  ! {e}")

    print(f"\n## Repos → ~/Workspace/organvm/ ({len(plan['moves_to_system'])} from organs + {len(plan['standalone_to_system'])} standalone)")
    for src, dest in plan["moves_to_system"][:10]:
        print(f"  {Path(src).parent.name}/{Path(src).name} → organvm/{Path(dest).name}")
    if len(plan["moves_to_system"]) > 10:
        print(f"  ... and {len(plan['moves_to_system']) - 10} more")

    if plan["standalone_to_system"]:
        print("\n  Standalone:")
        for src, dest in plan["standalone_to_system"]:
            print(f"  {Path(src).name} → organvm/{Path(dest).name}")

    print(f"\n## Personal repos (staying in 4444j99/): {len(plan['moves_to_personal'])}")
    for p in plan["moves_to_personal"]:
        print(f"  {Path(p).name}")

    print(f"\n## Superprojects to archive: {len(plan['superprojects_to_archive'])}")
    for sp in plan["superprojects_to_archive"]:
        print(f"  {Path(sp).name}")

    print(f"\n## Root cleanup → intake/: {len(plan['root_cleanup'])}")
    for item in plan["root_cleanup"]:
        print(f"  {Path(item).name}")

    print("\n" + "=" * 70)
    print("To execute: python3 scripts/consolidate-workspace.py --execute")
    print("=" * 70)


if __name__ == "__main__":
    dry_run = "--execute" not in sys.argv

    plan = plan_migration()

    if dry_run:
        print_plan(plan)
    else:
        if plan["errors"]:
            print("Cannot execute — resolve collisions first:")
            for e in plan["errors"]:
                print(f"  ! {e}")
            sys.exit(1)
        execute_migration(plan)
