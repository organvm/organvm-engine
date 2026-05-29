"""Tests for organvm_engine.pulse.rhythm — pulse cycle orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from organvm_engine.pulse.ammoi import AMMOI, OrganDensity
from organvm_engine.pulse.rhythm import (
    HeartbeatState,
    _compute_heartbeat_diff,
    _load_heartbeat,
    _save_heartbeat,
    pulse_history,
    pulse_once,
)

# A timestamp safely inside the 30-day pulse_history window (relative, never rots).
_RECENT_TS = datetime.now(timezone.utc).isoformat()


@pytest.fixture(autouse=True)
def _isolated_pulse(tmp_path, monkeypatch):
    """Route all pulse I/O to temp directory."""
    # Isolate AMMOI history
    history_file = tmp_path / "ammoi-history.jsonl"
    monkeypatch.setattr(
        "organvm_engine.pulse.ammoi._history_path",
        lambda: history_file,
    )

    # Isolate engine events
    events_file = tmp_path / "events.jsonl"
    monkeypatch.setattr(
        "organvm_engine.pulse.events._events_path",
        lambda: events_file,
    )

    # Isolate heartbeat state
    heartbeat_file = tmp_path / "last-heartbeat.json"
    monkeypatch.setattr(
        "organvm_engine.pulse.rhythm._heartbeat_path",
        lambda: heartbeat_file,
    )

    # Isolate advisories
    advisories_file = tmp_path / "advisories.jsonl"
    monkeypatch.setattr(
        "organvm_engine.pulse.advisories._advisories_path",
        lambda: advisories_file,
    )

    return {
        "history": history_file,
        "events": events_file,
        "heartbeat": heartbeat_file,
    }


@pytest.fixture
def _mock_ammoi(monkeypatch):
    """Replace compute_ammoi with a deterministic stub."""
    fake = AMMOI(
        timestamp="2026-03-13T15:00:00Z",
        system_density=0.42,
        total_entities=112,
        active_edges=87,
    )
    monkeypatch.setattr(
        "organvm_engine.pulse.rhythm.compute_ammoi",
        lambda **kwargs: fake,
    )
    return fake


# ---------------------------------------------------------------------------
# pulse_once
# ---------------------------------------------------------------------------


class TestPulseOnce:
    def test_returns_ammoi(self, _mock_ammoi):
        """pulse_once returns an AMMOI snapshot."""
        result = pulse_once(run_sensors=False)
        assert isinstance(result, AMMOI)
        assert result.system_density == 0.42

    def test_appends_to_history(self, _mock_ammoi, _isolated_pulse):
        """pulse_once writes one entry to AMMOI history."""
        pulse_once(run_sensors=False)
        content = _isolated_pulse["history"].read_text().strip()
        assert content, "history file should not be empty"
        lines = content.splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["system_density"] == 0.42

    def test_multiple_pulses_accumulate(self, _mock_ammoi, _isolated_pulse):
        """Multiple pulse_once calls append multiple history entries."""
        for _ in range(3):
            pulse_once(run_sensors=False)
        lines = _isolated_pulse["history"].read_text().strip().splitlines()
        assert len(lines) == 3

    def test_sensors_skipped_when_disabled(self, _mock_ammoi):
        """run_sensors=False skips sensor scanning."""
        # If scan_and_emit were called, it would fail (ontologia blocked by conftest).
        # This test passes because sensors are skipped.
        result = pulse_once(run_sensors=False)
        assert result is not None

    def test_sensor_import_failure_graceful(self, _mock_ammoi, monkeypatch):
        """When ontologia.sensing is not importable, pulse_once still works."""
        import builtins
        real_import = builtins.__import__

        def _block_sensing(name, *args, **kwargs):
            if "sensing" in name:
                raise ImportError("no sensing")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _block_sensing)
        result = pulse_once(run_sensors=True)
        assert isinstance(result, AMMOI)


# ---------------------------------------------------------------------------
# pulse_history
# ---------------------------------------------------------------------------


class TestPulseHistory:
    def test_empty_history(self):
        """Returns empty list when no snapshots exist."""
        result = pulse_history()
        assert result == []

    def test_returns_dicts(self, _isolated_pulse):
        """Returns list of plain dicts (not AMMOI objects)."""
        from organvm_engine.pulse.ammoi import _append_history

        _append_history(AMMOI(
            timestamp=_RECENT_TS,
            system_density=0.5,
        ))
        result = pulse_history()
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["system_density"] == 0.5

    def test_days_filter(self, _isolated_pulse):
        """days parameter filters old snapshots."""
        from organvm_engine.pulse.ammoi import _append_history

        # Add an old snapshot (well before the cutoff)
        _append_history(AMMOI(
            timestamp="2020-01-01T00:00:00Z",
            system_density=0.1,
        ))
        # And a recent one
        from datetime import datetime, timezone
        _append_history(AMMOI(
            timestamp=datetime.now(timezone.utc).isoformat(),
            system_density=0.5,
        ))
        result = pulse_history(days=1)
        assert len(result) == 1
        assert result[0]["system_density"] == 0.5


# ---------------------------------------------------------------------------
# HeartbeatState (Stream 3)
# ---------------------------------------------------------------------------


class TestHeartbeatState:
    def test_defaults(self):
        hb = HeartbeatState()
        assert hb.sys_pct == 0
        assert hb.gate_rates == {}
        assert hb.repo_states == {}

    def test_roundtrip(self):
        hb = HeartbeatState(
            sys_pct=42,
            gate_rates={"ORGAN-I": 35, "META-ORGANVM": 80},
            repo_states={"ORGAN-I": {"pct": 35}},
        )
        restored = HeartbeatState.from_dict(hb.to_dict())
        assert restored.sys_pct == 42
        assert restored.gate_rates["META-ORGANVM"] == 80

    def test_from_ammoi(self):
        ammoi = AMMOI(
            system_density=0.42,
            organs={
                "ORGAN-I": OrganDensity(
                    organ_id="ORGAN-I", organ_name="Theory",
                    repo_count=20, avg_gate_pct=35, density=0.38,
                ),
                "META-ORGANVM": OrganDensity(
                    organ_id="META-ORGANVM", organ_name="Meta",
                    repo_count=8, avg_gate_pct=80, density=0.65,
                ),
            },
        )
        hb = HeartbeatState.from_ammoi(ammoi)
        assert hb.sys_pct == 42
        assert hb.gate_rates["ORGAN-I"] == 35
        assert hb.gate_rates["META-ORGANVM"] == 80

    def test_save_and_load(self, _isolated_pulse):
        hb = HeartbeatState(sys_pct=50, gate_rates={"X": 100})
        _save_heartbeat(hb)
        loaded = _load_heartbeat()
        assert loaded is not None
        assert loaded.sys_pct == 50
        assert loaded.gate_rates == {"X": 100}

    def test_load_missing(self):
        result = _load_heartbeat()
        assert result is None


class TestHeartbeatDiff:
    def test_no_change(self):
        state = HeartbeatState(sys_pct=42, gate_rates={"X": 50})
        diff = _compute_heartbeat_diff(state, state)
        assert diff is None

    def test_sys_pct_change(self):
        prev = HeartbeatState(sys_pct=40)
        curr = HeartbeatState(sys_pct=45)
        diff = _compute_heartbeat_diff(prev, curr)
        assert diff is not None
        assert diff["sys_pct_delta"] == 5

    def test_gate_rate_change(self):
        prev = HeartbeatState(gate_rates={"X": 30, "Y": 50})
        curr = HeartbeatState(gate_rates={"X": 35, "Y": 50})
        diff = _compute_heartbeat_diff(prev, curr)
        assert diff is not None
        assert diff["gate_deltas"]["X"] == 5
        assert "Y" not in diff["gate_deltas"]

    def test_new_organ_detected(self):
        prev = HeartbeatState(repo_states={"X": {"pct": 30}})
        curr = HeartbeatState(repo_states={"X": {"pct": 30}, "Y": {"pct": 50}})
        diff = _compute_heartbeat_diff(prev, curr)
        assert diff is not None
        assert "Y" in diff["new_organs"]

    def test_removed_organ_detected(self):
        prev = HeartbeatState(repo_states={"X": {}, "Y": {}})
        curr = HeartbeatState(repo_states={"X": {}})
        diff = _compute_heartbeat_diff(prev, curr)
        assert diff is not None
        assert "Y" in diff["removed_organs"]

    def test_first_pulse_no_diff(self, _mock_ammoi, _isolated_pulse):
        """First pulse saves state but doesn't emit diff (no previous state)."""
        pulse_once(run_sensors=False)
        # Heartbeat file should exist after first pulse
        assert _isolated_pulse["heartbeat"].exists()
