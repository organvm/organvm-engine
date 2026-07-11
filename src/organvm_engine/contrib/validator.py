"""Contribution validation for BIFRONS.

Plans (and, when explicitly executed, runs) the upstream project's own
formatting/linting/tests plus a reproduction of the problem, in the disposable
workspace. Defaults to a plan only: nothing is executed and no upstream code is
run during preparation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from organvm_engine.contrib.worktree import WorkspacePlan

# Common upstream check commands, probed by manifest presence.
_CHECK_COMMANDS = {
    "pyproject.toml": ["ruff check .", "pytest -q"],
    "package.json": ["npm test"],
    "go.mod": ["go test ./..."],
    "Cargo.toml": ["cargo test"],
}


@dataclass
class ValidationResult:
    external_repo: str
    ref: str
    reproduction: str = ""
    commands: list[str] = field(default_factory=list)
    executed: bool = False
    passing: bool | None = None

    def as_dict(self) -> dict:
        return {
            "external_repo": self.external_repo,
            "ref": self.ref,
            "reproduction": self.reproduction,
            "commands": self.commands,
            "executed": self.executed,
            "passing": self.passing,
        }


def plan_validation(
    workspace: WorkspacePlan,
    *,
    manifests: list[str] | None = None,
    reproduction: str = "",
    execute: bool = False,
) -> ValidationResult:
    """Plan the upstream check + reproduction. ``execute=False`` runs nothing."""
    commands: list[str] = []
    for manifest in manifests or []:
        commands.extend(_CHECK_COMMANDS.get(manifest, []))
    if not commands:
        commands = ["# no recognized upstream check commands detected"]
    return ValidationResult(
        external_repo=workspace.external_repo,
        ref=workspace.ref,
        reproduction=reproduction,
        commands=commands,
        executed=bool(execute),
        passing=None,  # unknown until an authorized execution runs them
    )
