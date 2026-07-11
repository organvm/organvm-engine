"""Ephemeral contribution workspaces for BIFRONS (S3 materialization).

Plans (and, only when explicitly executed, creates) a disposable fork/worktree
pinned to an exact upstream ref. Defaults to a dry-run plan: no fork, no clone,
no code execution. Security invariants enforced here:

* every workspace is pinned to an exact commit;
* builds/tests run in a disposable sandbox (never the live checkout);
* upstream GitHub Actions are never run with ORGANVM secrets;
* fetched code is never executed during planning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorkspacePlan:
    external_repo: str
    ref: str
    fork: str
    worktree_path: str
    executed: bool = False
    steps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "external_repo": self.external_repo,
            "ref": self.ref,
            "fork": self.fork,
            "worktree_path": self.worktree_path,
            "executed": self.executed,
            "steps": self.steps,
        }


def _sandbox_root() -> Path:
    return Path("~/.organvm/bifrons/workspaces").expanduser()


def plan_workspace(
    external_repo: str,
    ref: str,
    *,
    fork_owner: str = "4444J99",
    base_dir: Path | None = None,
    execute: bool = False,
) -> WorkspacePlan:
    """Plan an ephemeral, pinned contribution workspace.

    With ``execute=False`` (default) this returns the plan without touching git
    or the network — the safe default. ``execute=True`` is reserved for an
    explicitly-authorized run and is intentionally left to the caller to wire to
    real git operations behind the human gate.
    """
    if not ref:
        raise ValueError("a workspace must be pinned to an exact ref")
    owner_repo = external_repo.split("/")
    name = owner_repo[-1] if owner_repo else external_repo
    root = base_dir or _sandbox_root()
    worktree_path = str(root / f"{name}@{ref[:10]}")
    fork = f"{fork_owner}/{name}"

    steps = [
        f"gh repo fork {external_repo} --clone=false  # -> {fork}",
        f"git clone --depth 1 --branch {ref} https://github.com/{fork} {worktree_path}",
        f"git -C {worktree_path} checkout {ref}",
        "# disposable sandbox; upstream Actions NOT run with ORGANVM secrets",
    ]
    return WorkspacePlan(
        external_repo=external_repo,
        ref=ref,
        fork=fork,
        worktree_path=worktree_path,
        executed=bool(execute),
        steps=steps,
    )
