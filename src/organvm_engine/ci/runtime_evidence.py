"""Normalize captured GitHub execution evidence without granting authority.

The authenticated collector supplies payloads and independently pins expectations.
This pure adapter does not authenticate JSON, call GitHub, launch jobs, write checks,
merge, or authorize release. Zero-step failures are not executed test failures.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from organvm_engine.ci.agent_eval import digest, load_json

VERSION = "organvm.github-execution-evidence.v1"
MAX_JOBS = 5000
MAX_PAGES = 100
MAX_STEPS = 512


def _positive(value: object) -> bool:
    return type(value) is int and value > 0


def _names(values: object) -> bool:
    return (isinstance(values, list) and 0 < len(values) <= MAX_STEPS
            and all(isinstance(v, str) and 0 < len(v) <= 256 for v in values)
            and len(set(values)) == len(values))


def _execution_times(record: dict, fields: tuple[str, ...], observed: datetime) -> dict[str, datetime]:
    """Reject impossible capture chronology without requiring optional API fields."""
    parsed = []
    moments = {}
    for field in fields:
        value = record.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError("execution: invalid timestamp")
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None or moment.utcoffset() is None or moment > observed:
            raise ValueError("execution: impossible observation chronology")
        parsed.append(moment)
        moments[field] = moment
    if parsed != sorted(parsed):
        raise ValueError("execution: impossible execution chronology")
    return moments


def _pages(pages: list[dict]) -> tuple[list[dict], bool, int | None]:
    if not isinstance(pages, list) or len(pages) > MAX_PAGES:
        raise ValueError("execution: invalid page collection")
    jobs: list[dict] = []
    total = None
    for page in pages:
        count = page.get("total_count")
        rows = page.get("jobs")
        if (type(count) is not int or not 0 <= count <= MAX_JOBS
                or not isinstance(rows, list) or len(rows) > MAX_JOBS
                or (total is not None and count != total)):
            raise ValueError("execution: inconsistent page metadata")
        total = count
        jobs.extend(rows)
        if len(jobs) > count:
            raise ValueError("execution: extra or repeated page rows")
    ids = [job.get("id") for job in jobs]
    if any(not _positive(i) for i in ids) or len(ids) != len(set(ids)):
        raise ValueError("execution: invalid or duplicate job identity")
    return jobs, total is not None and len(jobs) == total, total


def evaluate_run(run: dict, jobs_pages: list[dict], *, expected_repository_id: int,
                 expected_revision: str, expected_workflow_id: int, expected_run_id: int,
                 expected_attempt: int, required_steps: dict[str, list[str]],
                 observed_at: str) -> dict:
    """Evaluate recorded required jobs/steps against independent expectations.

    Requirements must come from the reviewed source contract, not from whichever
    jobs happened to be returned. GitHub totals are cross-checked, not authenticated
    here. A passing result means only that supplied payloads contain the required
    successful execution observations. It is never a trusted check or release gate.
    """
    try:
        for value in (expected_repository_id, expected_workflow_id, expected_run_id, expected_attempt):
            if not _positive(value):
                raise ValueError("execution: invalid expected identity")
        if (not isinstance(expected_revision, str)
                or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", expected_revision)):
            raise ValueError("execution: immutable revision required")
        timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("execution: timezone required")
        if (not isinstance(required_steps, dict) or not 0 < len(required_steps) <= MAX_JOBS
                or any(not isinstance(name, str) or not 0 < len(name) <= 256
                       or not _names(steps) for name, steps in required_steps.items())):
            raise ValueError("execution: nonempty unique requirements needed")
        actual = [run["repository"]["id"], run["workflow_id"], run["id"], run["run_attempt"]]
        expected = [expected_repository_id, expected_workflow_id, expected_run_id, expected_attempt]
        if (any(not _positive(v) for v in actual) or actual != expected
                or run["head_sha"] != expected_revision):
            raise ValueError("execution: run identity mismatch")
        if run.get("status") not in {"queued", "in_progress", "completed", "waiting", "pending", "requested"}:
            raise ValueError("execution: unsupported run status")
        run_times = _execution_times(run, ("created_at", "run_started_at", "updated_at"), timestamp)
        jobs, complete, total = _pages(jobs_pages)
        by_name: dict[str, list[dict]] = {}
        for job in jobs:
            if (not _positive(job.get("run_id")) or not _positive(job.get("run_attempt"))
                    or job["run_id"] != expected_run_id or job["run_attempt"] != expected_attempt
                    or job["head_sha"] != expected_revision):
                raise ValueError("execution: job identity mismatch")
            if not isinstance(job.get("name"), str):
                raise ValueError("execution: invalid job name")
            job_times = _execution_times(
                job, ("created_at", "started_at", "completed_at", "updated_at"), timestamp,
            )
            run_created = run_times.get("created_at")
            run_started = run_times.get("run_started_at")
            run_updated = run_times.get("updated_at")
            if (run_created and any(moment < run_created for moment in job_times.values())):
                raise ValueError("execution: job predates parent run")
            if (run_started and any(job_times[field] < run_started
                                    for field in ("started_at", "completed_at", "updated_at")
                                    if field in job_times)):
                raise ValueError("execution: job predates parent run start")
            if (run_updated and any(moment > run_updated for moment in job_times.values())):
                raise ValueError("execution: job exceeds parent run observation")
            by_name.setdefault(job["name"], []).append(job)
        observations = []
        for name, required in required_steps.items():
            matches = by_name.get(name, [])
            if len(matches) > 1:
                raise ValueError("execution: ambiguous required job name")
            if not matches:
                observations.append({"name": name, "state": "missing", "executed_required": 0})
                continue
            job = matches[0]
            steps = job.get("steps")
            if not isinstance(steps, list) or len(steps) > MAX_STEPS:
                raise ValueError("execution: invalid step collection")
            numbers = [step.get("number") for step in steps]
            if any(not _positive(n) for n in numbers) or len(numbers) != len(set(numbers)):
                raise ValueError("execution: invalid or duplicate step number")
            step_map: dict[str, list[dict]] = {}
            for step in steps:
                if not isinstance(step.get("name"), str):
                    raise ValueError("execution: invalid step name")
                step_map.setdefault(step["name"], []).append(step)
            selected = []
            for step_name in required:
                rows = step_map.get(step_name, [])
                if len(rows) > 1:
                    raise ValueError("execution: ambiguous required step name")
                selected.append(rows[0] if rows else None)
            selected_step_times = []
            for step in selected:
                if step is not None:
                    step_times = _execution_times(step, ("started_at", "completed_at"), timestamp)
                    selected_step_times.append((step["number"], step_times))
                    if (job_times.get("created_at")
                            and any(moment < job_times["created_at"] for moment in step_times.values())):
                        raise ValueError("execution: step predates parent job")
                    if (job_times.get("started_at")
                            and any(moment < job_times["started_at"] for moment in step_times.values())):
                        raise ValueError("execution: step predates parent job")
                    if (job_times.get("completed_at")
                            and any(moment > job_times["completed_at"] for moment in step_times.values())):
                        raise ValueError("execution: step exceeds parent job")
                    if (job_times.get("updated_at")
                            and any(moment > job_times["updated_at"] for moment in step_times.values())):
                        raise ValueError("execution: step exceeds parent job")
                    if (run_created
                            and any(moment < run_created for moment in step_times.values())):
                        raise ValueError("execution: step predates parent run")
                    if (run_started
                            and any(moment < run_started for moment in step_times.values())):
                        raise ValueError("execution: step predates parent run")
                    if (run_updated
                            and any(moment > run_updated for moment in step_times.values())):
                        raise ValueError("execution: step exceeds parent run observation")
            ordered_step_times = sorted(selected_step_times, key=lambda item: item[0])
            for (_, earlier), (_, later) in zip(
                    ordered_step_times, ordered_step_times[1:], strict=False):
                if earlier and later and max(earlier.values()) > min(later.values()):
                    raise ValueError("execution: required step chronology is inconsistent")
            executed = sum(step is not None and step.get("status") == "completed"
                           and step.get("conclusion") in {"success", "failure"} for step in selected)
            runner = job.get("runner_id")
            if runner is None and steps:
                raise ValueError("execution: invalid runner identity")
            if runner is not None and (type(runner) is not int or runner < 0):
                raise ValueError("execution: invalid runner identity")
            if runner == 0 and steps:
                raise ValueError("execution: runner and steps contradict")
            if not steps and job.get("status") != "completed":
                state = "pending"
            elif not steps:
                state = "not_executed"
            elif any(step is not None and step.get("status") == "completed"
                     and step.get("conclusion") == "failure" for step in selected):
                state = "executed_failure"
            elif job.get("status") != "completed":
                state = "pending"
            elif any(step is None or step.get("status") != "completed"
                     or step.get("conclusion") not in {"success", "failure"} for step in selected):
                state = "incomplete"
            elif job.get("conclusion") != "success" or any(step["conclusion"] != "success" for step in selected):
                state = "executed_failure"
            else:
                state = "executed_pass"
            observations.append({"name": name, "job_id": job["id"], "state": state,
                                 "runner_id": runner, "observed_steps": len(steps),
                                 "executed_required": executed, "required_count": len(required)})
        states = {row["state"] for row in observations}
        if "executed_failure" in states:
            decision = "executed_failure"
        elif not complete or "missing" in states or "incomplete" in states:
            decision = "incomplete"
        elif "not_executed" in states:
            decision = "not_executed"
        elif "pending" in states or run["status"] != "completed":
            decision = "pending"
        elif run.get("conclusion") != "success":
            decision = "executed_failure"
        else:
            decision = "executed_pass"
        return {"schema_version": VERSION, "evidence_class": "github_api_payload_consistency",
                "repository_id": expected_repository_id, "revision": expected_revision,
                "workflow_id": expected_workflow_id, "run_id": expected_run_id,
                "run_attempt": expected_attempt, "observed_at": observed_at,
                "requirements_digest": digest(required_steps),
                "payload_digest": digest({"run": run, "jobs_pages": jobs_pages}),
                "enumeration_complete": complete, "reported_job_count": total,
                "observed_job_count": len(jobs), "decision": decision, "jobs": observations,
                "producer_authentication": "outside_adapter",
                "authorizes_execution": False, "authorizes_release": False}
    except (KeyError, TypeError, AttributeError, RecursionError):
        raise ValueError("execution: invalid payload shape") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Captured payload and independently pinned expectations")
    args = parser.parse_args(argv)
    try:
        report = evaluate_run(**load_json(args.input))
    except (OSError, ValueError, TypeError, RecursionError):
        print(json.dumps({"decision": "invalid", "authorizes_release": False}))
        return 2
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 0 if report["decision"] == "executed_pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
