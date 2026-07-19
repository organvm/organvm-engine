"""Tests for cross-agent work coordination (punch-in/punch-out)."""

from __future__ import annotations

import json
import time

import pytest

from organvm_engine.coordination.claims import (
    WorkClaim,
    _build_active_claims,
    _generate_handle,
    active_claims,
    capacity_status,
    check_conflicts,
    prove_sweep,
    punch_in,
    punch_out,
    work_board,
)


@pytest.fixture(autouse=True)
def isolated_claims_file(tmp_path, monkeypatch):
    """Route all claims to a temp file."""
    claims_file = tmp_path / "claims.jsonl"
    monkeypatch.setenv("ORGANVM_CLAIMS_FILE", str(claims_file))
    return claims_file


class TestWorkClaim:
    def test_is_active_fresh(self):
        claim = WorkClaim(
            claim_id="abc", agent="claude", session_id="s1",
            timestamp=time.time(), organs=["ORGAN-I"],
        )
        assert claim.is_active
        assert not claim.is_expired
        assert not claim.released

    def test_is_expired(self):
        claim = WorkClaim(
            claim_id="abc", agent="claude", session_id="s1",
            timestamp=time.time() - 20000, ttl_seconds=100,
        )
        assert claim.is_expired
        assert not claim.is_active

    def test_is_released(self):
        claim = WorkClaim(
            claim_id="abc", agent="claude", session_id="s1",
            timestamp=time.time(), released=True,
        )
        assert not claim.is_active

    def test_areas(self):
        claim = WorkClaim(
            claim_id="abc", agent="claude", session_id="s1",
            timestamp=time.time(),
            organs=["ORGAN-I"], repos=["my-repo"],
            files=["src/main.py"], modules=["governance"],
        )
        areas = claim.areas
        assert "organ:ORGAN-I" in areas
        assert "repo:my-repo" in areas
        assert "file:src/main.py" in areas
        assert "module:governance" in areas

    def test_roundtrip(self):
        claim = WorkClaim(
            claim_id="abc", agent="gemini", session_id="s2",
            timestamp=12345.0, organs=["META"],
        )
        d = claim.to_dict()
        restored = WorkClaim.from_dict(d)
        assert restored.claim_id == "abc"
        assert restored.agent == "gemini"
        assert restored.organs == ["META"]


class TestBuildActiveClaims:
    def test_empty(self):
        assert _build_active_claims([]) == []

    def test_punch_in_creates_claim(self):
        events = [
            {
                "event_type": "claim.punch_in",
                "claim_id": "c1", "agent": "claude",
                "session_id": "s1", "timestamp": time.time(),
                "organs": ["ORGAN-I"], "repos": [], "files": [],
                "modules": [], "scope": "test", "ttl_seconds": 14400,
            },
        ]
        claims = _build_active_claims(events)
        assert len(claims) == 1
        assert claims[0].claim_id == "c1"

    def test_punch_out_releases(self):
        now = time.time()
        events = [
            {
                "event_type": "claim.punch_in",
                "claim_id": "c1", "agent": "claude",
                "session_id": "s1", "timestamp": now,
                "organs": [], "repos": [], "files": [],
                "modules": [], "ttl_seconds": 14400,
            },
            {
                "event_type": "claim.punch_out",
                "claim_id": "c1", "timestamp": now + 60,
            },
        ]
        claims = _build_active_claims(events)
        assert len(claims) == 0

    def test_expired_claim_filtered(self):
        events = [
            {
                "event_type": "claim.punch_in",
                "claim_id": "c1", "agent": "claude",
                "session_id": "s1", "timestamp": time.time() - 20000,
                "organs": [], "repos": [], "files": [],
                "modules": [], "ttl_seconds": 100,
            },
        ]
        claims = _build_active_claims(events)
        assert len(claims) == 0


class TestPunchIn:
    def test_basic_punch_in(self):
        result = punch_in(
            agent="claude", session_id="s1",
            organs=["ORGAN-I"], scope="working on theory",
        )
        assert "claim_id" in result
        assert result["conflict_count"] == 0
        assert "organ:ORGAN-I" in result["areas"]

    def test_conflict_detection(self):
        # First punch in
        punch_in(
            agent="claude", session_id="s1",
            repos=["organvm-engine"], scope="engine refactor",
        )
        # Second punch in on same repo
        result = punch_in(
            agent="gemini", session_id="s2",
            repos=["organvm-engine"], scope="engine tests",
        )
        assert result["conflict_count"] == 1
        assert result["conflicts"][0]["with_agent"] == "claude"
        assert result["conflicts"][0]["overlap_type"] == "repo"

    def test_no_conflict_different_areas(self):
        punch_in(
            agent="claude", session_id="s1",
            organs=["ORGAN-I"],
        )
        result = punch_in(
            agent="gemini", session_id="s2",
            organs=["ORGAN-III"],
        )
        assert result["conflict_count"] == 0


class TestPunchOut:
    def test_basic_punch_out(self):
        result = punch_in(
            agent="claude", session_id="s1",
            organs=["ORGAN-I"],
        )
        claim_id = result["claim_id"]
        release = punch_out(claim_id)
        assert release["released"] is True
        assert release["claim_id"] == claim_id

    def test_punch_out_nonexistent(self):
        result = punch_out("nonexistent")
        assert "error" in result

    def test_double_punch_out(self):
        result = punch_in(
            agent="claude", session_id="s1",
            organs=["ORGAN-I"],
        )
        claim_id = result["claim_id"]
        punch_out(claim_id)
        second = punch_out(claim_id)
        assert "already released" in second.get("note", "")

    def test_punch_out_clears_conflict(self):
        r1 = punch_in(agent="claude", session_id="s1", repos=["engine"])
        punch_out(r1["claim_id"])
        r2 = punch_in(agent="gemini", session_id="s2", repos=["engine"])
        assert r2["conflict_count"] == 0


class TestCheckConflicts:
    def test_organ_conflict(self):
        punch_in(agent="claude", session_id="s1", organs=["ORGAN-I"])
        conflicts = check_conflicts(organs=["ORGAN-I"])
        assert len(conflicts) == 1
        assert conflicts[0].overlap_type == "organ"

    def test_file_conflict(self):
        punch_in(agent="claude", session_id="s1", files=["src/main.py"])
        conflicts = check_conflicts(files=["src/main.py", "src/other.py"])
        assert len(conflicts) == 1
        assert "src/main.py" in conflicts[0].overlap_values

    def test_no_conflicts_when_empty(self):
        assert check_conflicts(organs=["ORGAN-I"]) == []


class TestWorkBoard:
    def test_empty_board(self):
        board = work_board()
        assert board["active_claims"] == 0
        assert board["agents_working"] == 0

    def test_board_with_claims(self):
        punch_in(agent="claude", session_id="s1", organs=["ORGAN-I"], scope="theory work")
        punch_in(agent="gemini", session_id="s2", repos=["styx"], scope="research")
        board = work_board()
        assert board["active_claims"] == 2
        assert board["agents_working"] == 2
        assert "claude" in board["by_agent"]
        assert "gemini" in board["by_agent"]

    def test_board_excludes_released(self):
        r = punch_in(agent="claude", session_id="s1", organs=["ORGAN-I"])
        punch_out(r["claim_id"])
        board = work_board()
        assert board["active_claims"] == 0


class TestActiveClaims:
    def test_returns_only_active(self):
        punch_in(agent="claude", session_id="s1", organs=["ORGAN-I"])
        r2 = punch_in(agent="gemini", session_id="s2", organs=["ORGAN-II"])
        punch_out(r2["claim_id"])
        claims = active_claims()
        assert len(claims) == 1
        assert claims[0].agent == "claude"


class TestResourceWeight:
    def test_default_weight_is_medium(self):
        result = punch_in(agent="claude", session_id="s1", organs=["ORGAN-I"])
        assert result["resource_weight"] == "medium"
        assert result["cost"] == 2

    def test_light_weight(self):
        result = punch_in(
            agent="claude", session_id="s1",
            organs=["ORGAN-I"], resource_weight="light",
        )
        assert result["resource_weight"] == "light"
        assert result["cost"] == 1

    def test_heavy_weight(self):
        result = punch_in(
            agent="claude", session_id="s1",
            organs=["ORGAN-I"], resource_weight="heavy",
        )
        assert result["resource_weight"] == "heavy"
        assert result["cost"] == 3

    def test_invalid_weight_defaults_to_medium(self):
        result = punch_in(
            agent="claude", session_id="s1",
            organs=["ORGAN-I"], resource_weight="extreme",
        )
        assert result["resource_weight"] == "medium"

    def test_capacity_in_punch_in_response(self):
        result = punch_in(
            agent="claude", session_id="s1",
            organs=["ORGAN-I"], resource_weight="medium",
        )
        assert "capacity" in result
        assert result["capacity"]["current_load"] == 2
        assert result["capacity"]["max_capacity"] == 6


class TestCapacityStatus:
    def test_empty_capacity(self):
        cap = capacity_status()
        assert cap["current_load"] == 0
        assert cap["available"] == 6
        assert cap["at_capacity"] is False
        assert cap["active_streams"] == 0

    def test_capacity_accumulates(self):
        punch_in(agent="claude", session_id="s1", resource_weight="medium")
        punch_in(agent="gemini", session_id="s2", resource_weight="heavy")
        cap = capacity_status()
        assert cap["current_load"] == 5  # 2 + 3
        assert cap["available"] == 1
        assert cap["active_streams"] == 2
        assert cap["by_weight"]["medium"] == 1
        assert cap["by_weight"]["heavy"] == 1

    def test_at_capacity(self):
        punch_in(agent="claude", session_id="s1", resource_weight="heavy")
        punch_in(agent="gemini", session_id="s2", resource_weight="heavy")
        cap = capacity_status()
        assert cap["current_load"] == 6
        assert cap["at_capacity"] is True

    def test_capacity_warning_on_overload(self):
        punch_in(agent="claude", session_id="s1", resource_weight="heavy")
        punch_in(agent="gemini", session_id="s2", resource_weight="medium")
        # 3 + 2 = 5, adding another heavy (3) would exceed 6
        result = punch_in(
            agent="codex", session_id="s3",
            resource_weight="heavy",
        )
        assert "capacity_warning" in result

    def test_no_warning_when_room(self):
        result = punch_in(
            agent="claude", session_id="s1",
            resource_weight="light",
        )
        assert "capacity_warning" not in result

    def test_capacity_freed_on_punch_out(self):
        r = punch_in(agent="claude", session_id="s1", resource_weight="heavy")
        punch_out(r["claim_id"])
        cap = capacity_status()
        assert cap["current_load"] == 0
        assert cap["available"] == 6

    def test_work_board_includes_capacity(self):
        punch_in(agent="claude", session_id="s1", resource_weight="medium")
        board = work_board()
        assert "capacity" in board
        assert board["capacity"]["current_load"] == 2


class TestHandleGeneration:
    def test_handle_format(self):
        result = punch_in(agent="claude", session_id="s1", organs=["ORGAN-I"])
        assert result["handle"].startswith("claude-")
        assert len(result["handle"].split("-")) == 2

    def test_gemini_handle(self):
        result = punch_in(agent="gemini", session_id="s1", organs=["ORGAN-II"])
        assert result["handle"].startswith("gemini-")

    def test_unknown_agent_gets_default_pool(self):
        result = punch_in(agent="grok", session_id="s1", organs=["ORGAN-I"])
        assert result["handle"].startswith("grok-")

    def test_handles_unique_across_agents(self):
        r1 = punch_in(agent="claude", session_id="s1", organs=["ORGAN-I"])
        r2 = punch_in(agent="claude", session_id="s2", organs=["ORGAN-II"])
        assert r1["handle"] != r2["handle"]

    def test_handle_in_conflict_report(self):
        r1 = punch_in(agent="claude", session_id="s1", repos=["engine"])
        r2 = punch_in(agent="gemini", session_id="s2", repos=["engine"])
        assert r2["conflicts"][0]["with_handle"] == r1["handle"]

    def test_handle_in_punch_out(self):
        r = punch_in(agent="claude", session_id="s1", organs=["ORGAN-I"])
        out = punch_out(r["claim_id"])
        assert out["handle"] == r["handle"]

    def test_generate_handle_direct(self):
        h = _generate_handle("claude", set())
        assert h == "claude-forge"  # first in pool

    def test_generate_handle_avoids_collision(self):
        existing = {"claude-forge"}
        h = _generate_handle("claude", existing)
        assert h == "claude-anvil"  # second in pool

    def test_generate_handle_pool_exhaustion(self):
        # Fill entire claude pool (15 words)
        existing = {f"claude-{w}" for w in [
            "forge", "anvil", "helm", "loom", "quill",
            "vault", "prism", "blade", "torch", "crown",
            "reed", "stone", "tide", "crest", "glyph",
        ]}
        h = _generate_handle("claude", existing)
        assert h == "claude-01"  # numbered fallback


class TestTestObligations:
    def test_obligations_in_punch_in(self):
        result = punch_in(
            agent="claude", session_id="s1",
            repos=["organvm-engine"],
            test_obligations=["pytest organvm-engine/tests/ -v"],
        )
        assert "claim_id" in result

    def test_obligations_returned_on_punch_out(self):
        r = punch_in(
            agent="claude", session_id="s1",
            repos=["engine"],
            test_obligations=["pytest tests/ -v", "ruff check src/"],
        )
        out = punch_out(r["claim_id"])
        assert out["test_obligations"] == ["pytest tests/ -v", "ruff check src/"]
        assert "test obligation" in out["note"].lower()

    def test_no_obligations_no_note(self):
        r = punch_in(agent="claude", session_id="s1", repos=["engine"])
        out = punch_out(r["claim_id"])
        assert "test_obligations" not in out

    def test_obligations_in_work_board(self):
        punch_in(
            agent="claude", session_id="s1",
            repos=["engine"],
            test_obligations=["pytest engine/tests/ -v"],
        )
        board = work_board()
        assert board["test_obligation_count"] >= 1
        assert "pytest engine/tests/ -v" in board["pending_test_obligations"]

    def test_obligations_roundtrip_in_workclaim(self):
        claim = WorkClaim(
            claim_id="abc", agent="claude", session_id="s1",
            timestamp=time.time(),
            test_obligations=["pytest tests/ -v"],
        )
        d = claim.to_dict()
        restored = WorkClaim.from_dict(d)
        assert restored.test_obligations == ["pytest tests/ -v"]


class TestProveSweep:
    def test_empty_sweep(self):
        result = prove_sweep()
        assert result["total"] == 0
        assert result["obligations"] == []
        assert "No pending" in result["note"]

    def test_sweep_collects_obligations(self):
        punch_in(
            agent="claude", session_id="s1",
            test_obligations=["pytest engine/ -v"],
        )
        punch_in(
            agent="gemini", session_id="s2",
            test_obligations=["pytest mcp/ -v"],
        )
        result = prove_sweep()
        assert result["total"] == 2
        assert "pytest engine/ -v" in result["obligations"]
        assert "pytest mcp/ -v" in result["obligations"]

    def test_sweep_deduplicates(self):
        punch_in(
            agent="claude", session_id="s1",
            test_obligations=["pytest tests/ -v"],
        )
        punch_in(
            agent="gemini", session_id="s2",
            test_obligations=["pytest tests/ -v"],
        )
        result = prove_sweep()
        assert result["total"] == 1

    def test_sweep_includes_released_claims(self):
        r = punch_in(
            agent="claude", session_id="s1",
            test_obligations=["pytest engine/ -v"],
        )
        punch_out(r["claim_id"])
        result = prove_sweep()
        assert result["total"] == 1
        assert "pytest engine/ -v" in result["obligations"]

    def test_sweep_sources_track_origin(self):
        punch_in(
            agent="claude", session_id="s1",
            scope="engine refactor",
            test_obligations=["pytest engine/ -v"],
        )
        result = prove_sweep()
        assert result["sources"][0]["from_agent"] == "claude"
        assert result["sources"][0]["from_scope"] == "engine refactor"

    def test_sweep_ignores_old_claims(self, tmp_path, monkeypatch):
        """Claims older than 8 hours should not appear in sweep."""
        claims_file = tmp_path / "old_claims.jsonl"
        monkeypatch.setenv("ORGANVM_CLAIMS_FILE", str(claims_file))
        old_event = {
            "event_type": "claim.punch_in",
            "claim_id": "old1",
            "agent": "claude",
            "session_id": "s-old",
            "timestamp": time.time() - 10 * 3600,  # 10 hours ago
            "handle": "claude-forge",
            "organs": [],
            "repos": [],
            "files": [],
            "modules": [],
            "test_obligations": ["pytest old/ -v"],
            "ttl_seconds": 14400,
        }
        claims_file.write_text(json.dumps(old_event) + "\n")
        result = prove_sweep()
        assert result["total"] == 0
