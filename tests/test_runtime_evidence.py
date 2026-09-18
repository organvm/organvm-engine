"""GitHub API shape fixtures are synthetic unless in the live evidence record."""
import copy
import json

import pytest

from organvm_engine.ci.runtime_evidence import evaluate_run, main

HEAD = "a" * 40


def payload():
    run = {"repository": {"id": 1}, "workflow_id": 2, "id": 3, "run_attempt": 1,
           "head_sha": HEAD, "status": "completed", "conclusion": "success"}
    job = {"id": 4, "run_id": 3, "run_attempt": 1, "head_sha": HEAD, "name": "test",
           "runner_id": 5, "status": "completed", "conclusion": "success",
           "steps": [{"number": 1, "name": "Run tests", "status": "completed", "conclusion": "success"}]}
    return {"run": run, "jobs_pages": [{"total_count": 1, "jobs": [job]}],
            "expected_repository_id": 1, "expected_workflow_id": 2, "expected_run_id": 3,
            "expected_attempt": 1, "expected_revision": HEAD,
            "required_steps": {"test": ["Run tests"]}, "observed_at": "2026-09-13T14:00:00Z"}


def test_executed_pass_has_no_authority():
    result = evaluate_run(**payload())
    assert result["decision"] == "executed_pass"
    assert result["enumeration_complete"]
    assert not result["authorizes_release"] and not result["authorizes_execution"]
    assert result["producer_authentication"] == "outside_adapter"


@pytest.mark.parametrize("field,value", [("expected_repository_id", 9), ("expected_run_id", 9),
    ("expected_workflow_id", 9), ("expected_attempt", 2), ("expected_revision", "b" * 40),
    ("expected_repository_id", True), ("expected_revision", "main")])
def test_independently_pinned_identity(field, value):
    data = payload()
    data[field] = value
    with pytest.raises(ValueError):
        evaluate_run(**data)


@pytest.mark.parametrize("field,value", [("run_id", 9), ("run_attempt", 2), ("head_sha", "b" * 40)])
def test_mixed_attempt_or_head_job_is_invalid(field, value):
    data = payload()
    data["jobs_pages"][0]["jobs"][0][field] = value
    with pytest.raises(ValueError):
        evaluate_run(**data)


def test_actual_shape_of_zero_step_failure_is_not_executed_test_failure():
    data = payload()
    data["run"]["conclusion"] = "failure"
    data["jobs_pages"][0]["jobs"][0].update(runner_id=0, steps=[], conclusion="failure")
    result = evaluate_run(**data)
    assert result["decision"] == "not_executed"
    assert result["jobs"][0]["executed_required"] == 0


@pytest.mark.parametrize("status", ["queued", "in_progress"])
@pytest.mark.parametrize("runner_id", [None, 0])
def test_active_zero_step_job_is_pending(status, runner_id):
    data = payload()
    data["run"].update(status=status, conclusion=None)
    data["jobs_pages"][0]["jobs"][0].update(
        status=status, conclusion=None, runner_id=runner_id, steps=[],
    )
    assert evaluate_run(**data)["decision"] == "pending"


def test_completed_zero_step_job_allows_null_runner():
    data = payload()
    data["jobs_pages"][0]["jobs"][0].update(runner_id=None, steps=[])
    assert evaluate_run(**data)["decision"] == "not_executed"


def test_null_runner_cannot_claim_recorded_steps():
    data = payload()
    data["jobs_pages"][0]["jobs"][0]["runner_id"] = None
    with pytest.raises(ValueError, match="invalid runner identity"):
        evaluate_run(**data)


@pytest.mark.parametrize("change,decision", [
    ({"steps": []}, "not_executed"),
    ({"status": "in_progress"}, "pending"), ({"conclusion": "failure"}, "executed_failure"),
])
def test_job_execution_states(change, decision):
    data = payload()
    data["jobs_pages"][0]["jobs"][0].update(change)
    assert evaluate_run(**data)["decision"] == decision


def test_runner_without_execution_cannot_hide_recorded_steps():
    data = payload()
    data["jobs_pages"][0]["jobs"][0]["runner_id"] = 0
    with pytest.raises(ValueError, match="runner and steps contradict"):
        evaluate_run(**data)


def test_executed_failure_wins_over_unexecuted_sibling():
    data = payload()
    failed = data["jobs_pages"][0]["jobs"][0]
    failed.update(conclusion="failure")
    failed["steps"][0]["conclusion"] = "failure"
    unexecuted = copy.deepcopy(failed)
    unexecuted.update(id=6, name="lint", runner_id=0, steps=[])
    data["jobs_pages"][0].update(total_count=2, jobs=[failed, unexecuted])
    data["required_steps"]["lint"] = ["Run lint"]
    assert evaluate_run(**data)["decision"] == "executed_failure"


def test_executed_failure_wins_despite_incomplete_pagination():
    data = payload()
    data["run"]["conclusion"] = "failure"
    data["jobs_pages"][0]["total_count"] = 2
    data["jobs_pages"][0]["jobs"][0]["conclusion"] = "failure"
    data["jobs_pages"][0]["jobs"][0]["steps"][0]["conclusion"] = "failure"
    assert evaluate_run(**data)["decision"] == "executed_failure"


@pytest.mark.parametrize("target,field", [
    ("run", "created_at"), ("run", "run_started_at"), ("run", "updated_at"),
    ("job", "created_at"), ("job", "started_at"), ("job", "completed_at"),
    ("job", "updated_at"),
    ("step", "started_at"), ("step", "completed_at"),
])
def test_observation_cannot_predate_execution_timestamp(target, field):
    data = payload()
    if target == "run":
        record = data["run"]
    elif target == "job":
        record = data["jobs_pages"][0]["jobs"][0]
    else:
        record = data["jobs_pages"][0]["jobs"][0]["steps"][0]
    record[field] = "2026-09-13T15:00:00Z"
    with pytest.raises(ValueError, match="chronology"):
        evaluate_run(**data)


def test_job_cannot_predate_parent_run():
    data = payload()
    data["run"].update(
        created_at="2026-09-13T13:00:00Z",
        run_started_at="2026-09-13T13:01:00Z",
        updated_at="2026-09-13T13:30:00Z",
    )
    data["jobs_pages"][0]["jobs"][0].update(
        created_at="2026-09-13T12:00:00Z",
        started_at="2026-09-13T12:01:00Z",
        completed_at="2026-09-13T12:10:00Z",
        updated_at="2026-09-13T12:10:00Z",
    )
    with pytest.raises(ValueError, match="parent run"):
        evaluate_run(**data)


def test_step_cannot_escape_parent_job_timestamps():
    data = payload()
    job = data["jobs_pages"][0]["jobs"][0]
    job.update(started_at="2026-09-13T13:00:00Z", completed_at="2026-09-13T13:10:00Z")
    job["steps"][0].update(
        started_at="2026-09-13T12:59:00Z", completed_at="2026-09-13T13:01:00Z",
    )
    with pytest.raises(ValueError, match="parent job"):
        evaluate_run(**data)


@pytest.mark.parametrize("bound", ["created_at", "updated_at"])
def test_step_uses_available_parent_job_bounds_when_optional_times_are_absent(bound):
    data = payload()
    job = data["jobs_pages"][0]["jobs"][0]
    job[bound] = "2026-09-13T13:00:00Z" if bound == "created_at" else "2026-09-13T13:30:00Z"
    if bound == "created_at":
        job["steps"][0].update(
            started_at="2026-09-13T12:00:00Z", completed_at="2026-09-13T12:10:00Z",
        )
    else:
        job["steps"][0].update(
            started_at="2026-09-13T13:20:00Z", completed_at="2026-09-13T13:40:00Z",
        )
    with pytest.raises(ValueError, match="parent job"):
        evaluate_run(**data)


@pytest.mark.parametrize("bound", ["created_at", "run_started_at", "updated_at"])
def test_step_uses_parent_run_bounds_when_job_times_are_absent(bound):
    data = payload()
    run = data["run"]
    if bound == "created_at":
        run[bound] = "2026-09-13T13:00:00Z"
        data["jobs_pages"][0]["jobs"][0]["steps"][0].update(
            started_at="2026-09-13T12:00:00Z", completed_at="2026-09-13T12:10:00Z",
        )
    elif bound == "run_started_at":
        run[bound] = "2026-09-13T13:00:00Z"
        data["jobs_pages"][0]["jobs"][0]["steps"][0].update(
            started_at="2026-09-13T12:59:00Z", completed_at="2026-09-13T13:01:00Z",
        )
    else:
        run[bound] = "2026-09-13T13:30:00Z"
        data["jobs_pages"][0]["jobs"][0]["steps"][0].update(
            started_at="2026-09-13T13:20:00Z", completed_at="2026-09-13T13:40:00Z",
        )
    with pytest.raises(ValueError, match="parent run"):
        evaluate_run(**data)


def test_required_step_timestamps_follow_step_number_order():
    data = payload()
    job = data["jobs_pages"][0]["jobs"][0]
    job["steps"][0].update(
        started_at="2026-09-13T13:10:00Z", completed_at="2026-09-13T13:20:00Z",
    )
    second = copy.deepcopy(job["steps"][0])
    second.update(
        number=2, name="Package", started_at="2026-09-13T13:00:00Z",
        completed_at="2026-09-13T13:05:00Z",
    )
    job["steps"].append(second)
    data["required_steps"]["test"].append("Package")
    with pytest.raises(ValueError, match="step chronology"):
        evaluate_run(**data)


def test_completed_required_failure_wins_while_job_is_still_running():
    data = payload()
    job = data["jobs_pages"][0]["jobs"][0]
    job.update(status="in_progress", conclusion=None)
    job["steps"][0]["conclusion"] = "failure"
    assert evaluate_run(**data)["decision"] == "executed_failure"


@pytest.mark.parametrize("value,state", [("skipped", "incomplete"), ("cancelled", "incomplete"),
                                         (None, "incomplete"), ("failure", "executed_failure")])
def test_required_step_status_not_job_badge_controls_evidence(value, state):
    data = payload()
    data["jobs_pages"][0]["jobs"][0]["steps"][0]["conclusion"] = value
    assert evaluate_run(**data)["decision"] == state


def test_bootstrap_only_is_not_test_execution():
    data = payload()
    data["jobs_pages"][0]["jobs"][0]["steps"][0]["name"] = "Set up job"
    assert evaluate_run(**data)["decision"] == "incomplete"


def test_no_pages_or_empty_jobs_do_not_pass():
    data = payload()
    data["jobs_pages"] = []
    assert evaluate_run(**data)["decision"] == "incomplete"
    data["jobs_pages"] = [{"total_count": 0, "jobs": []}]
    assert evaluate_run(**data)["decision"] == "incomplete"


def test_partial_and_full_pagination():
    data = payload()
    data["jobs_pages"][0]["total_count"] = 2
    assert evaluate_run(**data)["decision"] == "incomplete"
    other = copy.deepcopy(data["jobs_pages"][0]["jobs"][0])
    other.update(id=6, name="other")
    data["jobs_pages"].append({"total_count": 2, "jobs": [other]})
    assert evaluate_run(**data)["decision"] == "executed_pass"


@pytest.mark.parametrize("mutation", ["duplicate_id", "duplicate_name", "inconsistent_total", "extra_row",
                                       "duplicate_step_name", "duplicate_step_number"])
def test_ambiguous_evidence_is_invalid(mutation):
    data = payload()
    page = data["jobs_pages"][0]
    job = page["jobs"][0]
    if mutation.startswith("duplicate_step"):
        new = copy.deepcopy(job["steps"][0])
        if mutation.endswith("name"):
            new["number"] = 2
        else:
            new["name"] = "Other step"
        job["steps"].append(new)
    else:
        new = copy.deepcopy(job)
        if mutation != "duplicate_id":
            new["id"] = 6
        page["total_count"] = 1 if mutation == "extra_row" else 2
        data["jobs_pages"].append({"total_count": 3 if mutation == "inconsistent_total" else page["total_count"], "jobs": [new]})
    with pytest.raises(ValueError):
        evaluate_run(**data)


@pytest.mark.parametrize("requirements", [{}, {"test": []}, {"test": ["x", "x"]}, {"test": "Run tests"}])
def test_requirements_cannot_be_vacuous(requirements):
    data = payload()
    data["required_steps"] = requirements
    with pytest.raises(ValueError):
        evaluate_run(**data)


def test_nonjson_or_shape_errors_are_bounded():
    data = payload()
    data["jobs_pages"][0]["jobs"] = [None]
    with pytest.raises(ValueError):
        evaluate_run(**data)


def test_cli_does_not_echo_invalid_private_payload(tmp_path, capsys):
    path = tmp_path / "source.json"
    path.write_text(json.dumps({"private": "SYNTHETIC-PRIVATE"}))
    assert main([str(path)]) == 2
    assert "SYNTHETIC-PRIVATE" not in capsys.readouterr().out


def test_cli_success_and_nonexecuted_are_distinct(tmp_path, capsys):
    path = tmp_path / "source.json"
    data = payload()
    path.write_text(json.dumps(data))
    assert main([str(path)]) == 0
    capsys.readouterr()
    data["jobs_pages"][0]["jobs"][0].update(runner_id=0, steps=[])
    path.write_text(json.dumps(data))
    assert main([str(path)]) == 1
    assert json.loads(capsys.readouterr().out)["decision"] == "not_executed"
