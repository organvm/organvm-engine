"""Tests for organvm_engine.pulse.advisories — advisory policy evaluation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from organvm_engine.pulse.advisories import (
    Advisory,
    _build_repo_state,
    _make_advisory_id,
    _severity_from_action,
    acknowledge_advisory,
    read_advisories,
    store_advisories,
)

# A validation timestamp inside the 30-day staleness window (relative, never rots).
_RECENT_TS = datetime.now(timezone.utc).isoformat()


@pytest.fixture(autouse=True)
def _isolated_advisories(tmp_path, monkeypatch):
    """Route advisory storage to temp directory."""
    advisories_file = tmp_path / "advisories.jsonl"
    monkeypatch.setattr(
        "organvm_engine.pulse.advisories._advisories_path",
        lambda: advisories_file,
    )
    return advisories_file


# ---------------------------------------------------------------------------
# Advisory dataclass
# ---------------------------------------------------------------------------


class TestAdvisory:
    def test_roundtrip(self):
        a = Advisory(
            advisory_id="abc123",
            policy_id="flag-orphan",
            action="flag",
            entity_id="ORGAN-I/some-repo",
            entity_name="some-repo",
            description="flag-orphan: some-repo",
            severity="warning",
            timestamp="2026-03-13T10:00:00Z",
            evidence={"is_orphan": True},
        )
        restored = Advisory.from_dict(a.to_dict())
        assert restored.advisory_id == "abc123"
        assert restored.policy_id == "flag-orphan"
        assert restored.evidence == {"is_orphan": True}


class TestHelpers:
    def test_advisory_id_deterministic(self):
        id1 = _make_advisory_id("pol-1", "ent-a")
        id2 = _make_advisory_id("pol-1", "ent-a")
        assert id1 == id2

    def test_advisory_id_differs_for_different_inputs(self):
        id1 = _make_advisory_id("pol-1", "ent-a")
        id2 = _make_advisory_id("pol-2", "ent-a")
        assert id1 != id2

    def test_severity_mapping(self):
        assert _severity_from_action("flag") == "warning"
        assert _severity_from_action("deprecate") == "critical"
        assert _severity_from_action("promote") == "info"
        assert _severity_from_action("unknown") == "info"


# ---------------------------------------------------------------------------
# _build_repo_state — inference-aware (Stream 2)
# ---------------------------------------------------------------------------


class TestBuildRepoState:
    def test_basic_fields(self):
        repo = {
            "name": "test-repo",
            "promotion_status": "CANDIDATE",
            "ci_workflow": True,
            "platinum_status": True,
            "implementation_status": "ACTIVE",
            "last_validated": _RECENT_TS,
        }
        state = _build_repo_state(repo)
        assert state["promotion_status"] == "CANDIDATE"
        assert state["ci_workflow"] is True
        assert state["is_stale"] is False

    def test_stale_detection(self):
        repo = {"last_validated": "2025-01-01T00:00:00Z"}
        state = _build_repo_state(repo)
        assert state["is_stale"] is True

    def test_default_structural_fields_without_context(self):
        """Without inference context, structural fields default to safe zeros."""
        state = _build_repo_state({})
        assert state["is_orphan"] is False
        assert state["incoming_relations"] == 0
        assert state["cluster_size"] == 0
        assert state["cohesion"] == 0.0

    def test_inference_context_overrides_defaults(self):
        """When inference context is provided, it overrides the zeros."""
        repo = {"name": "orphan-repo", "promotion_status": "CANDIDATE"}
        state = _build_repo_state(repo)
        # Apply inference context (simulating what evaluate_all_policies does)
        inference_ctx = {
            "is_orphan": True,
            "incoming_relations": 0,
            "cluster_size": 1,
            "cohesion": 0.0,
        }
        state.update(inference_ctx)
        assert state["is_orphan"] is True
        assert state["cluster_size"] == 1


# ---------------------------------------------------------------------------
# _build_inference_context (Stream 2 — new function)
# ---------------------------------------------------------------------------


class TestBuildInferenceContext:
    def test_returns_dict(self, monkeypatch):
        """_build_inference_context returns a dict mapping entity IDs to context."""
        from organvm_engine.pulse.advisories import _build_inference_context
        from organvm_engine.pulse.inference_bridge import InferenceSummary

        mock_summary = InferenceSummary(
            orphaned_entities=["ent_repo_AAA"],
            overcoupled_entities=["ent_repo_BBB"],
            clusters=[
                {"entity_ids": ["ent_repo_AAA", "ent_repo_CCC"], "cohesion": 0.8, "size": 2},
            ],
            cluster_count=1,
        )
        monkeypatch.setattr(
            "organvm_engine.pulse.inference_bridge.run_inference",
            lambda ws=None: mock_summary,
        )
        ctx = _build_inference_context()
        assert isinstance(ctx, dict)

    def test_orphan_flagged(self, monkeypatch):
        from organvm_engine.pulse.advisories import _build_inference_context
        from organvm_engine.pulse.inference_bridge import InferenceSummary

        mock_summary = InferenceSummary(
            orphaned_entities=["ent_repo_AAA"],
            overcoupled_entities=[],
            clusters=[],
            cluster_count=0,
        )
        monkeypatch.setattr(
            "organvm_engine.pulse.inference_bridge.run_inference",
            lambda ws=None: mock_summary,
        )
        ctx = _build_inference_context()
        assert ctx.get("ent_repo_AAA", {}).get("is_orphan") is True

    def test_overcoupled_flagged(self, monkeypatch):
        from organvm_engine.pulse.advisories import _build_inference_context
        from organvm_engine.pulse.inference_bridge import InferenceSummary

        mock_summary = InferenceSummary(
            orphaned_entities=[],
            overcoupled_entities=["ent_repo_BBB"],
            clusters=[],
            cluster_count=0,
        )
        monkeypatch.setattr(
            "organvm_engine.pulse.inference_bridge.run_inference",
            lambda ws=None: mock_summary,
        )
        ctx = _build_inference_context()
        entity_ctx = ctx.get("ent_repo_BBB", {})
        assert entity_ctx.get("incoming_relations", 0) > 0

    def test_cluster_membership(self, monkeypatch):
        from organvm_engine.pulse.advisories import _build_inference_context
        from organvm_engine.pulse.inference_bridge import InferenceSummary

        mock_summary = InferenceSummary(
            orphaned_entities=[],
            overcoupled_entities=[],
            clusters=[
                {"entity_ids": ["ent_A", "ent_B"], "cohesion": 0.9, "size": 2},
            ],
            cluster_count=1,
        )
        monkeypatch.setattr(
            "organvm_engine.pulse.inference_bridge.run_inference",
            lambda ws=None: mock_summary,
        )
        ctx = _build_inference_context()
        assert ctx.get("ent_A", {}).get("cluster_size") == 2
        assert ctx.get("ent_B", {}).get("cohesion") == 0.9

    def test_graceful_on_inference_failure(self, monkeypatch):
        """Returns empty dict when inference fails."""
        from organvm_engine.pulse.advisories import _build_inference_context

        monkeypatch.setattr(
            "organvm_engine.pulse.inference_bridge.run_inference",
            lambda ws=None: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        ctx = _build_inference_context()
        assert ctx == {}


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


class TestStorage:
    def test_store_and_read(self, _isolated_advisories):
        advs = [
            Advisory(
                advisory_id="a1", policy_id="p1", action="flag",
                entity_id="X/r", entity_name="r", description="test",
                severity="warning", timestamp="2026-03-13T10:00:00Z",
            ),
        ]
        store_advisories(advs)
        loaded = read_advisories()
        assert len(loaded) == 1
        assert loaded[0].advisory_id == "a1"

    def test_empty_store(self):
        store_advisories([])
        loaded = read_advisories()
        assert loaded == []

    def test_acknowledge(self, _isolated_advisories):
        advs = [
            Advisory(
                advisory_id="ack1", policy_id="p1", action="flag",
                entity_id="X/r", entity_name="r", description="test",
                severity="warning", timestamp="2026-03-13T10:00:00Z",
            ),
        ]
        store_advisories(advs)
        assert acknowledge_advisory("ack1") is True
        loaded = read_advisories()
        assert loaded[0].acknowledged is True

    def test_acknowledge_nonexistent(self):
        assert acknowledge_advisory("nope") is False

    def test_unacked_only_filter(self, _isolated_advisories):
        advs = [
            Advisory(
                advisory_id="u1", policy_id="p1", action="flag",
                entity_id="X/r1", entity_name="r1", description="d1",
                severity="warning", timestamp="2026-03-13T10:00:00Z",
            ),
            Advisory(
                advisory_id="u2", policy_id="p1", action="flag",
                entity_id="X/r2", entity_name="r2", description="d2",
                severity="warning", timestamp="2026-03-13T10:00:00Z",
                acknowledged=True,
            ),
        ]
        store_advisories(advs)
        all_advs = read_advisories()
        assert len(all_advs) == 2
        unacked = read_advisories(unacked_only=True)
        assert len(unacked) == 1
        assert unacked[0].advisory_id == "u1"
