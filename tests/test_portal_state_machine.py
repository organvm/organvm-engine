"""BIFRONS portal exchange lifecycle state machine."""

from __future__ import annotations

import pytest

from organvm_engine.portal.state_machine import (
    ExchangeState,
    InvalidTransition,
    PortalStateMachine,
)


def test_shared_prefix_then_fork():
    sm = PortalStateMachine
    assert sm.can_advance(ExchangeState.STARRED, ExchangeState.INDEXED)
    assert sm.can_advance(ExchangeState.MAPPED, ExchangeState.ABSORPTION_CANDIDATE)
    assert sm.can_advance(ExchangeState.MAPPED, ExchangeState.CONTRIBUTION_CANDIDATE)


def test_illegal_transition_raises():
    with pytest.raises(InvalidTransition):
        PortalStateMachine.advance(ExchangeState.STARRED, ExchangeState.MERGED)


def test_outbound_branch_reaches_backflow():
    sm = PortalStateMachine
    path = [
        ExchangeState.CONTRIBUTION_CANDIDATE,
        ExchangeState.UPSTREAM_POLICY_CHECKED,
        ExchangeState.REPRODUCED,
        ExchangeState.PATCH_PREPARED,
        ExchangeState.HUMAN_APPROVED,
        ExchangeState.UPSTREAM_SUBMITTED,
        ExchangeState.MERGED,
        ExchangeState.BACKFLOW_COMPLETE,
    ]
    for a, b in zip(path, path[1:], strict=True):
        assert sm.advance(a, b) == b


def test_external_write_requires_human_approval_predecessor():
    # The only edge into UPSTREAM_SUBMITTED comes from HUMAN_APPROVED.
    assert PortalStateMachine.can_advance(
        ExchangeState.HUMAN_APPROVED, ExchangeState.UPSTREAM_SUBMITTED,
    )
    assert not PortalStateMachine.can_advance(
        ExchangeState.PATCH_PREPARED, ExchangeState.UPSTREAM_SUBMITTED,
    )
    assert PortalStateMachine.requires_human_approval(ExchangeState.UPSTREAM_SUBMITTED)


def test_backflow_is_terminal():
    assert PortalStateMachine.is_terminal(ExchangeState.BACKFLOW_COMPLETE)
    assert not PortalStateMachine.is_terminal(ExchangeState.MAPPED)
