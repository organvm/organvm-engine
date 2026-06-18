"""Tests for Conductor lifecycle ritual contract."""

from __future__ import annotations

import pytest

from organvm_engine.coordination.lifecycle import (
    CONDUCTOR_PHASE_ORDER,
    ConductorPhase,
    ConductorRitualStage,
    build_conductor_ritual_metadata,
    conductor_ritual_contract,
    conductor_ritual_stage,
    normalise_conductor_phase,
    valid_conductor_transition,
)


class TestConductorLifecycle:
    def test_phase_order(self):
        assert [phase.value for phase in CONDUCTOR_PHASE_ORDER] == [
            "FRAME",
            "SHAPE",
            "BUILD",
            "PROVE",
            "DONE",
        ]

    def test_valid_transitions_are_sequential(self):
        assert valid_conductor_transition("FRAME", "SHAPE")
        assert valid_conductor_transition(ConductorPhase.BUILD, ConductorPhase.PROVE)
        assert not valid_conductor_transition("FRAME", "BUILD")
        assert not valid_conductor_transition("DONE", "PROVE")

    def test_phase_normalization(self):
        assert normalise_conductor_phase("shape") == ConductorPhase.SHAPE
        with pytest.raises(ValueError, match="Unknown Conductor phase"):
            normalise_conductor_phase("PLAN")

    def test_ritual_stage_mapping(self):
        assert conductor_ritual_stage("FRAME") == ConductorRitualStage.SCORE
        assert conductor_ritual_stage("SHAPE") == ConductorRitualStage.SCORE
        assert conductor_ritual_stage("BUILD") == ConductorRitualStage.REHEARSE
        assert conductor_ritual_stage("PROVE") == ConductorRitualStage.REHEARSE
        assert conductor_ritual_stage("DONE") == ConductorRitualStage.PERFORM

    def test_contract_names_gates(self):
        contract = conductor_ritual_contract()

        assert contract["schema_version"] == "conductor-ritual/v1"
        assert contract["ritual_sequence"] == ["score", "rehearse", "perform"]
        assert contract["phase_to_ritual"]["SHAPE"] == "score"
        assert contract["phase_to_ritual"]["PROVE"] == "rehearse"
        assert contract["phase_to_ritual"]["DONE"] == "perform"
        assert "appetite_minutes" in contract["gates"]["SHAPE"]["required_metadata"]
        assert "test_obligations" in contract["gates"]["PROVE"]["required_metadata"]
        assert (
            "session_export.conductor_ritual"
            in contract["gates"]["DONE"]["required_metadata"]
        )


class TestConductorRitualMetadata:
    def test_builds_score_rehearse_perform_payload(self):
        metadata = build_conductor_ritual_metadata(
            phase="SHAPE",
            appetite_minutes=45,
            micro_spec={
                "outcome": "formalize ritual",
                "non_goals": ["implement ORGAN-IV server"],
                "acceptance_checks": ["pytest tests/test_conductor_lifecycle.py"],
            },
            test_obligations=["pytest tests/test_conductor_lifecycle.py"],
            regression_detected=False,
        )

        assert metadata["conductor_phase"] == "SHAPE"
        assert metadata["conductor_ritual_stage"] == "score"
        assert metadata["score"]["appetite_minutes"] == 45
        assert metadata["score"]["micro_spec"]["outcome"] == "formalize ritual"
        assert metadata["rehearse"]["test_obligations"] == [
            "pytest tests/test_conductor_lifecycle.py",
        ]
        assert metadata["perform"]["regression_detected"] is False
        assert metadata["perform"]["postmortem_required"] is False

    def test_regression_requires_postmortem(self):
        metadata = build_conductor_ritual_metadata(
            phase="DONE",
            regression_detected=True,
            postmortem="pytest regression in prove gate",
        )

        assert metadata["conductor_ritual_stage"] == "perform"
        assert metadata["perform"]["postmortem_required"] is True
        assert metadata["perform"]["postmortem"] == "pytest regression in prove gate"
