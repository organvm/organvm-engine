"""Autonomy + safety policy for BIFRONS outbound contributions.

The portal's outbound authority is bounded by an autonomy level. The default is
A2 — *prepare, never submit*: local branches, patches, tests, and contribution
packets are produced, but nothing is opened upstream without explicit human
authorization. A4 (allowlisted autonomy) is reserved for narrowly-defined
low-risk classes to explicitly allowlisted repos.

This is an operational quality constraint, not a moral one: indiscriminate
contributions would damage signal quality and relationship capital.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class AutonomyLevel(IntEnum):
    OBSERVE = 0     # A0 — index and monitor only
    INTERPRET = 1   # A1 — dossiers, mappings, suggestions
    PREPARE = 2     # A2 — local branches, patches, tests, packets (DEFAULT)
    SUBMIT_WITH_APPROVAL = 3  # A3 — open issue/PR only after explicit approval
    ALLOWLISTED = 4  # A4 — auto-submit predefined low-risk classes to allowlisted repos


DEFAULT_AUTONOMY = AutonomyLevel.PREPARE

# Contribution kinds A4 may ever auto-submit (narrow, deterministic, low-risk).
LOW_RISK_KINDS = frozenset({
    "documentation-ambiguity",       # typo / broken-doc-link corrections
    "missing-test-or-fixture",       # deterministic fixture/test additions
})


@dataclass
class ContributionPolicy:
    autonomy: AutonomyLevel = DEFAULT_AUTONOMY
    allowlist: set[str] = field(default_factory=set)  # owner/repo entries for A4
    open_pr_cap: int = 3          # max concurrent open PRs per repo
    submission_rate_cap: int = 5  # max submissions per run


@dataclass
class SubmitDecision:
    allowed: bool
    reason: str
    requires_human: bool = False


def is_allowlisted(policy: ContributionPolicy, repo: str) -> bool:
    return repo in policy.allowlist


def is_low_risk(kind: str) -> bool:
    return kind in LOW_RISK_KINDS


def authorize_submit(
    policy: ContributionPolicy,
    *,
    external_repo: str,
    kind: str,
    human_approved: bool = False,
    checks_passing: bool = False,
    duplicate_exists: bool = False,
    open_prs: int = 0,
    maintainer_opt_out: bool = False,
) -> SubmitDecision:
    """Decide whether an upstream submission is authorized.

    The external-write boundary. Everything before this is preparation.
    """
    if duplicate_exists:
        return SubmitDecision(False, "duplicate issue/PR already exists")
    if maintainer_opt_out:
        return SubmitDecision(False, "maintainer prohibits automated contributions")
    if open_prs >= policy.open_pr_cap:
        return SubmitDecision(False, f"open-PR cap reached ({policy.open_pr_cap})")

    # A4: allowlisted autonomy for low-risk classes only.
    if policy.autonomy >= AutonomyLevel.ALLOWLISTED:
        if not is_allowlisted(policy, external_repo):
            return SubmitDecision(False, f"{external_repo} is not allowlisted", requires_human=True)
        if not is_low_risk(kind):
            return SubmitDecision(
                False, f"kind '{kind}' is not a low-risk class", requires_human=True,
            )
        if not checks_passing:
            return SubmitDecision(False, "upstream checks not passing")
        return SubmitDecision(True, "A4 allowlisted low-risk auto-submit")

    # A3: submit only with explicit human approval.
    if policy.autonomy == AutonomyLevel.SUBMIT_WITH_APPROVAL:
        if human_approved and checks_passing:
            return SubmitDecision(True, "A3 human-approved submission")
        return SubmitDecision(
            False, "A3 requires explicit human approval + passing checks",
            requires_human=True,
        )

    # A2 and below: prepare only, never submit.
    return SubmitDecision(
        False, f"autonomy {policy.autonomy.name} (A{int(policy.autonomy)}) prepares, never submits",
        requires_human=True,
    )
