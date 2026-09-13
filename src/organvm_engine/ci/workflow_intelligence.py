"""Read-only workflow diagnosis alongside ci.audit; no GitHub or shell effectors.

Consume exact-revision files from the existing inventory. Caller supplies the
independently enumerated path set; unavailable files are never clean/deleted.
Reports retain repository/path metadata and are restricted until the existing
reader-mode privacy gate approves publication. Static findings are not exploits,
execution results, verified remediation patches, or release authorization.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath
from statistics import median
from typing import Any

import yaml

from organvm_engine.ci.agent_eval import digest, load_json

VERSION = "organvm.workflow-intelligence.v1"
MAX_BYTES = 262144
MAX_NODES = 20000
MAX_DEPTH = 64
PIN = re.compile(r"@[0-9a-fA-F]{40}$")
DIGEST_PIN = re.compile(r"@sha256:[0-9a-fA-F]{64}$")
UNTRUSTED = re.compile(r"\$\{\{[^}]*github\.event\.(?:issue|pull_request|comment|review)\b[^}]*\}\}")
SEVERITIES = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
REPAIRS = {
    "permissions_unspecified": "Review effective token permissions; declare least privilege explicitly.",
    "write_all": "Replace write-all with reviewed, job-specific permissions.",
    "mutable_action": "Resolve and review an immutable upstream commit/digest before pinning.",
    "timeout_unspecified": "Set a measured finite job timeout; do not guess a production limit.",
    "failure_tolerated": "Review whether this job/step may fail without masking required evidence.",
    "untrusted_run_expression": "Move untrusted event values out of generated shell source and validate usage.",
    "privileged_head_checkout": "Do not execute pull-request-head code in a privileged target context.",
    "reusable_workflow_unresolved": "Inventory the referenced workflow at an immutable revision before claiming transitive coverage.",
}


class _WorkflowLoader(yaml.SafeLoader):
    pass


# Copy, never mutate the process-global YAML resolver. GitHub's 'on' is a key,
# not the YAML 1.1 boolean True. Keep actual true/false values as booleans.
_WorkflowLoader.yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for _char, _rules in _WorkflowLoader.yaml_implicit_resolvers.items():
    _WorkflowLoader.yaml_implicit_resolvers[_char] = [
        (tag, regex) for tag, regex in _rules if tag != "tag:yaml.org,2002:bool"
    ]
_WorkflowLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.I),
                                      list("tTfF"))


def _mapping(loader: _WorkflowLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise ValueError("workflow: duplicate or non-string key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_WorkflowLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _load(text: str) -> dict:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("workflow: invalid input size")
    try:
        depth = 0
        for count, event in enumerate(yaml.parse(text)):
            if isinstance(event, yaml.AliasEvent):
                raise ValueError("workflow: aliases require manual review")
            if isinstance(event, (yaml.SequenceStartEvent, yaml.MappingStartEvent)):
                depth += 1
            elif isinstance(event, (yaml.SequenceEndEvent, yaml.MappingEndEvent)):
                depth -= 1
            if count > MAX_NODES or depth > MAX_DEPTH:
                raise ValueError("workflow: structural budget exceeded")
        doc = yaml.load(text, Loader=_WorkflowLoader)
        digest(doc)  # reject timestamps, non-finite numbers and non-JSON objects
    except (yaml.YAMLError, TypeError, RecursionError):
        raise ValueError("workflow: invalid YAML/JSON shape") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), dict) or not doc["jobs"]:
        raise ValueError("workflow: jobs mapping required")
    triggers = doc.get("on")
    if not isinstance(triggers, (str, list, dict)) or not triggers:
        raise ValueError("workflow: triggers required")
    if isinstance(triggers, list) and not all(isinstance(t, str) for t in triggers):
        raise ValueError("workflow: invalid trigger list")
    return doc


def _path(path: str) -> str:
    if (not isinstance(path, str) or "\\" in path or "\x00" in path
            or not path.startswith(".github/workflows/")
            or PurePosixPath(path).suffix not in {".yaml", ".yml"}
            or str(PurePosixPath(path)) != path or ".." in PurePosixPath(path).parts
            or len(PurePosixPath(path).parts) != 3):
        raise ValueError("inventory: invalid workflow path")
    return path


def _time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("evidence: timestamp required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("evidence: timezone required")
    return parsed


def analyze_workflow(text: str) -> dict:
    """Bounded static checks; this is deliberately not a full Actions validator."""
    doc = _load(text)
    findings = []
    reusable = []

    def add(code: str, severity: str, location: str) -> None:
        findings.append({"code": code, "severity": severity, "location": location,
                         "basis": "static_source", "requires_review": True,
                         "proposed_action": REPAIRS[code]})

    def action(value: Any, location: str) -> None:
        if not isinstance(value, str):
            raise ValueError("workflow: invalid action reference")
        if value.startswith("./"):
            return
        pinned = DIGEST_PIN.search(value) if value.startswith("docker://") else PIN.search(value)
        if not pinned:
            add("mutable_action", "medium", location)

    def validate_permissions(value: Any) -> None:
        if value in ("read-all", "write-all"):
            return
        if not isinstance(value, dict) or any(v not in ("read", "write", "none") for v in value.values()):
            raise ValueError("workflow: invalid permissions")

    if "permissions" in doc:
        validate_permissions(doc["permissions"])
    if doc.get("permissions") == "write-all":
        add("write_all", "high", "permissions")
    trigger_names = {doc["on"]} if isinstance(doc["on"], str) else set(doc["on"])
    for job_id, job in doc["jobs"].items():
        if not isinstance(job, dict):
            raise ValueError("workflow: invalid job")
        location = f"jobs/{job_id}"
        permissions = job.get("permissions", doc.get("permissions"))
        if permissions is None:
            add("permissions_unspecified", "medium", location)
        else:
            validate_permissions(permissions)
        if job.get("permissions") == "write-all":
            add("write_all", "high", location)
        if job.get("continue-on-error") not in (None, False):
            add("failure_tolerated", "medium", location)
        if "uses" in job:
            if "steps" in job:
                raise ValueError("workflow: reusable job also contains steps")
            action(job["uses"], location)
            reusable.append(job["uses"])
            add("reusable_workflow_unresolved", "info", location)
            continue
        steps = job.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError("workflow: steps required")
        timeout = job.get("timeout-minutes")
        if timeout is None:
            add("timeout_unspecified", "low", location)
        elif not ((type(timeout) in (int, float) and timeout > 0)
                  or (isinstance(timeout, str) and timeout.startswith("${{") and timeout.endswith("}}"))):
            raise ValueError("workflow: invalid timeout")
        for index, step in enumerate(steps):
            sloc = f"{location}/steps/{index}"
            if not isinstance(step, dict) or (("uses" in step) == ("run" in step)):
                raise ValueError("workflow: step must contain exactly one of run/uses")
            if step.get("continue-on-error") not in (None, False):
                add("failure_tolerated", "medium", sloc)
            if "uses" in step:
                action(step["uses"], sloc)
                checkout = step["uses"].lower().startswith("actions/checkout@")
                settings = step.get("with", {})
                if not isinstance(settings, dict):
                    raise ValueError("workflow: invalid action inputs")
                if (checkout and "pull_request_target" in trigger_names
                        and "github.event.pull_request.head" in json.dumps(settings)):
                    add("privileged_head_checkout", "critical", sloc)
            if "run" in step:
                if not isinstance(step["run"], str):
                    raise ValueError("workflow: invalid run script")
                if UNTRUSTED.search(step["run"]):
                    add("untrusted_run_expression", "high", sloc)
    return {"source_digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "normalized_digest": digest(doc), "job_count": len(doc["jobs"]),
            "triggers": sorted(trigger_names), "findings": findings,
            "transitive_coverage": "unresolved" if reusable else "not_requested",
            "reusable_references": reusable}


def inventory(repository_id: int, revision: str, files: dict[str, str], *,
              expected_paths: list[str], observed_at: str,
              enumeration_complete: bool = False) -> dict:
    """Diagnose provided files, preserving failed/partial retrieval coverage."""
    if type(repository_id) is not int or repository_id <= 0:
        raise ValueError("inventory: stable repository ID required")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
        raise ValueError("inventory: immutable revision required")
    _time(observed_at)
    if type(enumeration_complete) is not bool:
        raise ValueError("inventory: enumeration completeness must be boolean")
    if len(set(expected_paths)) != len(expected_paths):
        raise ValueError("inventory: duplicate expected paths")
    for path in [*expected_paths, *files]:
        _path(path)
    if not set(files) <= set(expected_paths):
        raise ValueError("inventory: files outside declared enumeration")
    records = {}
    for path in sorted(expected_paths):
        if path not in files:
            records[path] = {"status": "unavailable"}
            continue
        try:
            records[path] = {"status": "analyzed", **analyze_workflow(files[path])}
        except (ValueError, RecursionError):
            records[path] = {"status": "invalid_or_unsupported"}
            if isinstance(files[path], str):
                records[path]["source_digest"] = hashlib.sha256(files[path].encode("utf-8")).hexdigest()
    analyzed = sum(r["status"] == "analyzed" for r in records.values())
    return {"schema_version": VERSION, "evidence_class": "static_source_analysis",
            "repository_id": repository_id, "revision": revision, "observed_at": observed_at,
            "expected_paths": sorted(expected_paths), "enumerated_count": len(expected_paths),
            "enumeration_complete": enumeration_complete,
            "analyzed_count": analyzed, "coverage": "complete" if analyzed == len(records) else "partial",
            "workflows": records, "authorizes_mutation": False, "authorizes_release": False}


def _validate_snapshot(snapshot: dict) -> None:
    """Validate record consistency, not collection authenticity or permissions."""
    try:
        if (snapshot.get("schema_version") != VERSION
                or type(snapshot["repository_id"]) is not int
                or snapshot["repository_id"] <= 0
                or not isinstance(snapshot["revision"], str)
                or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", snapshot["revision"])):
            raise ValueError("snapshot: invalid identity")
        _time(snapshot["observed_at"])
        paths = snapshot["expected_paths"]
        records = snapshot["workflows"]
        if (not isinstance(paths, list) or not isinstance(records, dict)
                or len(paths) != len(set(paths)) or set(paths) != set(records)):
            raise ValueError("snapshot: inconsistent enumeration")
        for path, record in records.items():
            _path(path)
            if record["status"] not in {"analyzed", "unavailable", "invalid_or_unsupported"}:
                raise ValueError("snapshot: invalid analysis status")
            if record["status"] == "analyzed":
                for field in ("source_digest", "normalized_digest"):
                    if not re.fullmatch(r"[0-9a-f]{64}", record[field]):
                        raise ValueError("snapshot: invalid digest")
        analyzed = sum(record["status"] == "analyzed" for record in records.values())
        coverage = "complete" if analyzed == len(records) else "partial"
        if (type(snapshot["analyzed_count"]) is not int
                or type(snapshot["enumerated_count"]) is not int
                or snapshot["analyzed_count"] != analyzed
                or snapshot["enumerated_count"] != len(records)
                or snapshot["coverage"] != coverage
                or type(snapshot.get("enumeration_complete", False)) is not bool):
            raise ValueError("snapshot: inconsistent coverage")
    except (KeyError, TypeError, AttributeError):
        raise ValueError("snapshot: invalid shape") from None


def drift(previous: dict, current: dict) -> dict:
    _validate_snapshot(previous)
    _validate_snapshot(current)
    if (previous.get("schema_version") != VERSION or current.get("schema_version") != VERSION
            or previous.get("repository_id") != current.get("repository_id")):
        raise ValueError("drift: incompatible snapshots")
    if _time(current["observed_at"]) < _time(previous["observed_at"]):
        raise ValueError("drift: reversed observation chronology")
    changes = []
    old, new = previous["workflows"], current["workflows"]
    for path in sorted(set(old) | set(new)):
        before, after = old.get(path), new.get(path)
        if ((before and before["status"] != "analyzed")
                or (after and after["status"] != "analyzed")):
            kind = "unavailable_comparison"
        elif before is None:
            kind = "added" if previous.get("enumeration_complete") is True else "unavailable_comparison"
        elif after is None:
            kind = ("removed_from_enumeration" if current.get("enumeration_complete") is True
                    else "unavailable_comparison")
        elif before["source_digest"] == after["source_digest"]:
            continue
        elif before["normalized_digest"] == after["normalized_digest"]:
            kind = "representation_only"
        else:
            kind = "declaration_changed"
        changes.append({"path": path, "kind": kind})
    return {"schema_version": VERSION, "repository_id": current["repository_id"],
            "base_revision": previous["revision"], "head_revision": current["revision"],
            "base_snapshot_digest": digest(previous), "head_snapshot_digest": digest(current),
            "changes": changes, "intent_classification": "requires_review"}


def proposals(snapshot: dict, *, owner_refs: list[str], criticality: int = 1,
              downstream_count: int = 0) -> list[dict]:
    """Risk routing hints; ownership resolution stays in the canonical registry."""
    if type(criticality) is not int or not 1 <= criticality <= 5:
        raise ValueError("review: invalid criticality")
    if type(downstream_count) is not int or downstream_count < 0:
        raise ValueError("review: invalid downstream count")
    result = []
    for path, record in snapshot["workflows"].items():
        for finding in record.get("findings", []):
            proposal = {"repository_id": snapshot["repository_id"], "revision": snapshot["revision"],
                        "path": path, "source_digest": record["source_digest"], **finding,
                        "owner_refs": sorted(set(owner_refs)),
                        "owner_status": "resolved_by_caller" if owner_refs else "unresolved",
                        "risk_vector": [SEVERITIES[finding["severity"]], criticality, downstream_count],
                        "requires_human_approval": True, "authorizes_mutation": False}
            proposal["proposal_digest"] = digest(proposal)
            result.append(proposal)
    return sorted(result, key=lambda p: (-p["risk_vector"][0], -criticality, -downstream_count,
                                         p["path"], p["location"], p["code"]))


def review_metrics(records: list[dict], *, observed_at: str) -> dict:
    """Descriptive observed latency/rework/load; not review-quality scores."""
    now = _time(observed_at)
    latencies, pending_ages = [], []
    reviewers: Counter = Counter()
    rework = 0
    seen = set()
    for record in records:
        identity = record["id"]
        if identity in seen:
            raise ValueError("reviews: duplicate identity")
        seen.add(identity)
        requested = _time(record["requested_at"])
        reviewed = _time(record["first_review_at"]) if record.get("first_review_at") else None
        if requested > now or (reviewed and not requested <= reviewed <= now):
            raise ValueError("reviews: invalid chronology")
        target = latencies if reviewed else pending_ages
        target.append(((reviewed or now) - requested).total_seconds())
        count = record.get("changes_requested", 0)
        if type(count) is not int or count < 0:
            raise ValueError("reviews: invalid rework count")
        rework += count
        reviewers.update(set(record.get("reviewer_ids", [])))
    total = sum(reviewers.values())
    return {"observed_at": observed_at, "records": len(records), "reviewed": len(latencies),
            "pending": len(pending_ages), "median_first_review_seconds": median(latencies) if latencies else None,
            "oldest_pending_seconds": max(pending_ages) if pending_ages else None,
            "changes_requested": rework,
            "largest_reviewer_share": max(reviewers.values()) / total if total else None,
            "reviewer_participations": total, "quality_inference": "not_measured"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON inventory arguments, not a shell command")
    args = parser.parse_args(argv)
    try:
        report = inventory(**load_json(args.input))
    except (OSError, ValueError, TypeError, RecursionError):
        print(json.dumps({"coverage": "invalid", "authorizes_mutation": False}))
        return 2
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 0 if report["coverage"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
