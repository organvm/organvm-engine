"""Regression witnesses for the false-evidence family, issue #183."""
import copy

import pytest
from test_agent_eval import SCOPE_DIGEST, fixture_pair, paired_reports, promotion_gate, score
from test_workflow_intelligence import HEAD, PATH, SAFE, WHEN, snapshot

from organvm_engine.ci.agent_eval import DIMENSIONS, digest
from organvm_engine.ci.workflow_intelligence import drift, inventory


@pytest.mark.parametrize("status", ["failed", "denied"])
def test_completed_trace_cannot_hide_unsuccessful_terminal_step(status):
    trace, rubric = fixture_pair()
    trace["steps"][0]["status"] = status
    with pytest.raises(ValueError):
        score(trace, rubric)


def test_completed_tool_workflow_needs_observed_steps():
    trace, rubric = fixture_pair()
    trace["steps"] = []
    for check in rubric["checks"]:
        check.update(pointer="/output/done", expected=True)
    with pytest.raises(ValueError):
        score(trace, rubric)


def test_retry_is_not_implicitly_recovery_in_v1():
    trace, rubric = fixture_pair()
    failed = copy.deepcopy(trace["steps"][0])
    failed.update(id="failed-attempt", status="failed")
    trace["steps"].append(failed)
    with pytest.raises(ValueError):
        score(trace, rubric)


def test_same_rubric_claim_does_not_hide_changed_check_identity():
    before, after, rubric = paired_reports()
    after["checks"][0]["id"] = "different-check"
    with pytest.raises(ValueError):
        promotion_gate([before], [after], case_ids=[after["case_id"]],
                       rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST)


def test_equivalent_check_order_is_not_a_regression():
    before, after, rubric = paired_reports()
    after["checks"].reverse()
    assert promotion_gate([before], [after], case_ids=[after["case_id"]],
                          rubric_digest=digest(rubric),
                          scope_manifest_digest=SCOPE_DIGEST)["decision"] == "eligible_for_review"


def test_weight_changes_with_identical_scores_are_not_comparable():
    before, after, rubric = paired_reports()
    after["checks"][0]["weight"] = 2
    with pytest.raises(ValueError):
        promotion_gate([before], [after], case_ids=[after["case_id"]],
                       rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST)


def test_mutated_partial_coverage_is_not_removal_evidence():
    previous = snapshot()
    current = snapshot(files={}, expected_paths=[])
    current["coverage"] = "partial"
    with pytest.raises(ValueError):
        drift(previous, current)


def test_undeclared_enumeration_completeness_is_unknown():
    previous = snapshot()
    current = inventory(1160447354, "b" * 40, {}, expected_paths=[], observed_at=WHEN)
    assert current["enumeration_complete"] is False
    assert drift(previous, current)["changes"] == [{"path": PATH, "kind": "unavailable_comparison"}]


def test_explicitly_incomplete_enumeration_cannot_prove_addition_or_removal():
    complete = snapshot()
    partial = inventory(1160447354, "b" * 40, {}, expected_paths=[], observed_at=WHEN,
                        enumeration_complete=False)
    assert drift(complete, partial)["changes"][0]["kind"] == "unavailable_comparison"
    assert drift(partial, complete)["changes"][0]["kind"] == "unavailable_comparison"


def test_complete_enumeration_can_prove_change():
    complete = snapshot()
    empty = inventory(1160447354, "b" * 40, {}, expected_paths=[], observed_at=WHEN,
                      enumeration_complete=True)
    assert drift(complete, empty)["changes"][0]["kind"] == "removed_from_enumeration"


@pytest.mark.parametrize("field,value", [("repository_id", True), ("analyzed_count", 0),
                                          ("enumerated_count", 0), ("expected_paths", []),
                                          ("revision", "main")])
def test_tampered_snapshot_is_rejected(field, value):
    previous, current = snapshot(), snapshot()
    current[field] = value
    with pytest.raises(ValueError):
        drift(previous, current)


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_enumeration_flag_is_not_truthiness(value):
    with pytest.raises(ValueError):
        inventory(1160447354, HEAD, {PATH: SAFE}, expected_paths=[PATH], observed_at=WHEN,
                  enumeration_complete=value)


def test_controls_still_score_each_dimension():
    result = score()
    assert result["decision"] == "pass"
    assert set(result["scores"]) == set(DIMENSIONS)


def test_scope_counts_cannot_be_tampered_for_promotion():
    before, after, rubric = paired_reports()
    after["scope"].update(observed_count=0, missing_count=0, complete=True)
    with pytest.raises(ValueError, match="scope"):
        promotion_gate([before], [after], case_ids=[after["case_id"]],
                       rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST)


@pytest.mark.parametrize("field,value", [
    ("repository_id", None), ("repository_id", 0), ("repository_id", True),
    ("revision", None), ("revision", "main"),
])
def test_unbound_report_identity_cannot_be_paired(field, value):
    before, after, rubric = paired_reports()
    before[field] = value
    after[field] = value
    with pytest.raises(ValueError, match="identity"):
        promotion_gate([before], [after], case_ids=[after["case_id"]],
                       rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST)


def test_same_revision_cannot_claim_changed_workflow_content():
    previous = snapshot()
    current = snapshot(SAFE.replace("contents: read", "contents: write"))
    with pytest.raises(ValueError, match="unchanged revision"):
        drift(previous, current)

def test_promotion_rejects_cross_revision_comparison():
    before, after, rubric = paired_reports()
    after["revision"] = "b" * 40
    with pytest.raises(ValueError, match="revision mismatch"):
        promotion_gate([before], [after], case_ids=[after["case_id"]],
                       rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST)


def test_incomplete_enumeration_never_reports_complete_coverage():
    partial = inventory(1160447354, HEAD, {PATH: SAFE}, expected_paths=[PATH],
                        observed_at=WHEN, enumeration_complete=False)
    assert partial["analyzed_count"] == 1
    assert partial["coverage"] == "partial"

    empty = inventory(1160447354, HEAD, {}, expected_paths=[], observed_at=WHEN,
                      enumeration_complete=False)
    assert empty["coverage"] == "partial"

    partial["coverage"] = "complete"
    with pytest.raises(ValueError, match="inconsistent coverage"):
        drift(snapshot(), partial)
