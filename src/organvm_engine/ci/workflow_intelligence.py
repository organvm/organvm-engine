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
UNTRUSTED_CONTEXT = re.compile(
    r"(?:github\.event(?=\s*(?:[),]|\}\}))|"
    r"github\.event\.issue\.(?:title|body)\b|"
    r"github\.event\.pull_request\.(?:title|body|head\.(?:ref|label)|head\.repo\.full_name)\b|"
    r"github\.event\.discussion\.(?:title|body)\b|"
    r"github\.event\.(?:comment|review)\.body\b|"
    r"github\.event\.head_commit\.(?:message|author|committer)\b|"
    r"github\.event\.commits(?:\s*\[[^\]]+\]|\.\*)\.(?:message|author|committer)\b|"
    r"github\.head_ref\b)",
)
PR_HEAD = re.compile(r"github\.event\.pull_request\.head\b")
PR_HEAD_REF = re.compile(r"github\.head_ref\b")
PR_MERGE_SHA = re.compile(r"github\.event\.pull_request\.merge_commit_sha\b")
WORKFLOW_RUN_HEAD_SHA = re.compile(r"github\.event\.workflow_run\.head_sha\b")
WORKFLOW_RUN_HEAD_REPOSITORY = re.compile(
    r"github\.event\.workflow_run\.head_repository\.full_name\b",
)
PR_SYNTHETIC_REF = re.compile(
    r"refs/pull/(?:[0-9]+|\$\{\{.*?github\.event\.(?:pull_request\.)?number\b.*?\}\})/(?:head|merge)\b",
    re.DOTALL,
)
PR_SYNTHETIC_FORMAT_REF = re.compile(
    r"format\(\s*(['\"])refs/pull/\{(?P<placeholder>[0-9]+)\}/(?:head|merge)\1\s*,"
    r"(?P<arguments>[^)]*)\)",
    re.DOTALL,
)
PR_SYNTHETIC_FORMAT_COMPONENT_REF = re.compile(
    r"format\(\s*(['\"])(?P<template>refs/pull/\{[0-9]+\}/\{[0-9]+\})\1\s*,"
    r"(?P<arguments>[^)]*)\)",
    re.DOTALL,
)
BRACKET_SEGMENT = re.compile(r"\[\s*(['\"])([A-Za-z_][A-Za-z0-9_]*)\1\s*\]")
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
FINDING_SEVERITIES = {
    "permissions_unspecified": "medium",
    "write_all": "high",
    "mutable_action": "medium",
    "timeout_unspecified": "low",
    "failure_tolerated": "medium",
    "untrusted_run_expression": "high",
    "privileged_head_checkout": "critical",
    "reusable_workflow_unresolved": "info",
}


def _normalize_event_paths(value: str) -> str:
    """Normalize quoted bracket property access for bounded GitHub expressions."""
    return BRACKET_SEGMENT.sub(lambda match: "." + match.group(2), value)


def _contains_pr_head(value: Any) -> bool:
    if isinstance(value, str):
        normalized = _normalize_event_paths(value)
        literal_stripped = normalized
        for expression in _github_expressions(normalized):
            literal_stripped = literal_stripped.replace(
                expression, _strip_quoted_literals(expression),
            )
        return (any(pattern.search(literal_stripped) is not None
                    for pattern in (PR_HEAD, PR_HEAD_REF, PR_MERGE_SHA,
                                    PR_SYNTHETIC_REF))
                or _contains_synthetic_format_ref(normalized)
                or _contains_synthetic_format_component_ref(normalized))
    if isinstance(value, dict):
        return any(_contains_pr_head(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_pr_head(item) for item in value)
    return False


def _contains_workflow_run_head(value: dict[str, Any]) -> bool:
    """Require both the workflow-run head SHA and its contributor repository."""
    ref_value = value.get("ref", "")
    repository_value = value.get("repository", "")
    if not isinstance(ref_value, str) or not isinstance(repository_value, str):
        return False
    ref = _normalize_event_paths(ref_value)
    repository = _normalize_event_paths(repository_value)
    return (WORKFLOW_RUN_HEAD_SHA.search(ref) is not None
            and WORKFLOW_RUN_HEAD_REPOSITORY.search(repository) is not None)


def _contains_untrusted_run_expression(value: str) -> bool:
    """Scan complete GitHub expressions; braces inside quoted format strings are data."""
    normalized = _normalize_event_paths(value)
    return any(UNTRUSTED_CONTEXT.search(_strip_quoted_literals(expression))
               for expression in _github_expressions(normalized))


def _strip_quoted_literals(expression: str) -> str:
    """Remove expression string-literal content before scanning context references."""
    result: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(expression):
        char = expression[index]
        if quote is not None:
            result.append(" ")
            if char == quote:
                if index + 1 < len(expression) and expression[index + 1] == quote:
                    result.append(" ")
                    index += 2
                    continue
                quote = None
        elif char in {"'", '"'}:
            quote = char
            result.append(" ")
        else:
            result.append(char)
        index += 1
    return "".join(result)


def _split_format_arguments(arguments: str) -> list[str]:
    """Split the bounded scalar arguments used by synthetic-ref format calls."""
    result: list[str] = []
    start = 0
    quote: str | None = None
    index = 0
    while index < len(arguments):
        char = arguments[index]
        if quote is not None:
            if char == quote:
                if index + 1 < len(arguments) and arguments[index + 1] == quote:
                    index += 2
                    continue
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == ",":
            result.append(arguments[start:index].strip())
            start = index + 1
        index += 1
    result.append(arguments[start:].strip())
    return result


def _contains_synthetic_format_component_ref(value: str) -> bool:
    """Resolve placeholder positions in refs/pull/{n}/{m} format expressions."""
    for match in PR_SYNTHETIC_FORMAT_COMPONENT_REF.finditer(value):
        template = match.group("template")
        arguments = _split_format_arguments(match.group("arguments"))
        parts = template.split("/")
        if len(parts) != 4 or parts[:2] != ["refs", "pull"]:
            continue
        placeholders = []
        for part in parts[2:]:
            placeholder = re.fullmatch(r"\{([0-9]+)\}", part)
            if placeholder is None:
                placeholders = []
                break
            placeholders.append(int(placeholder.group(1)))
        if len(placeholders) != 2 or max(placeholders) >= len(arguments):
            continue
        number_arg = arguments[placeholders[0]]
        kind_arg = arguments[placeholders[1]]
        if (re.search(r"github\.event\.(?:pull_request\.)?number\b", number_arg)
                and re.fullmatch(r"(['\"])(?:head|merge)\1", kind_arg)):
            return True
    return False


def _contains_synthetic_format_ref(value: str) -> bool:
    """Resolve the numbered placeholder in refs/pull/{n}/kind format calls."""
    for match in PR_SYNTHETIC_FORMAT_REF.finditer(value):
        arguments = _split_format_arguments(match.group("arguments"))
        placeholder = int(match.group("placeholder"))
        if (placeholder < len(arguments)
                and re.search(r"github\.event\.(?:pull_request\.)?number\b",
                              arguments[placeholder])):
            return True
    return False


def _github_expressions(value: str) -> list[str]:
    """Return delimiter-complete expressions while ignoring delimiters inside quotes."""
    expressions = []
    cursor = 0
    while (start := value.find("${{", cursor)) >= 0:
        quote = None
        index = start + 3
        while index < len(value) - 1:
            char = value[index]
            if quote is not None:
                if char == quote:
                    if index + 1 < len(value) and value[index + 1] == quote:
                        index += 2
                        continue
                    quote = None
            elif char in {"'", '"'}:
                quote = char
            elif char == "}" and value[index + 1] == "}":
                expressions.append(value[start:index + 2])
                cursor = index + 2
                break
            index += 1
        else:
            break
    return expressions


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
        if FINDING_SEVERITIES.get(code) != severity:
            raise ValueError("workflow: inconsistent finding severity")
        findings.append({"code": code, "severity": severity, "location": location,
                         "basis": "static_source", "requires_review": True,
                         "proposed_action": REPAIRS[code]})

    def action(value: Any, location: str) -> None:
        if not isinstance(value, str):
            raise ValueError("workflow: invalid action reference")
        self_repository = value.startswith("$/") and len(value) > 2 and "@" not in value
        if value.startswith("./") or self_repository:
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
    normalized_doc = copy.deepcopy(doc)
    if isinstance(normalized_doc["on"], list):
        normalized_doc["on"] = sorted(normalized_doc["on"])
    elif isinstance(normalized_doc["on"], dict):
        for event_config in normalized_doc["on"].values():
            if (isinstance(event_config, dict)
                    and isinstance(event_config.get("types"), list)
                    and all(isinstance(item, str) for item in event_config["types"])):
                event_config["types"] = sorted(event_config["types"])
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
                content_selectors = {
                    key: settings[key] for key in ("ref", "repository") if key in settings
                }
                privileged_pull_request = (
                    "pull_request_target" in trigger_names
                    and _contains_pr_head(content_selectors)
                )
                privileged_workflow_run = (
                    "workflow_run" in trigger_names
                    and _contains_workflow_run_head(content_selectors)
                )
                if checkout and (privileged_pull_request or privileged_workflow_run):
                    add("privileged_head_checkout", "critical", sloc)
            if "run" in step:
                if not isinstance(step["run"], str):
                    raise ValueError("workflow: invalid run script")
                if _contains_untrusted_run_expression(step["run"]):
                    add("untrusted_run_expression", "high", sloc)
    return {"source_digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "normalized_digest": digest(normalized_doc), "job_count": len(doc["jobs"]),
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
    if not isinstance(files, dict):
        raise ValueError("inventory: files mapping required")
    if len(set(expected_paths)) != len(expected_paths):
        raise ValueError("inventory: duplicate expected paths")
    for path in [*expected_paths, *files]:
        _path(path)
    if not set(files) <= set(expected_paths):
        raise ValueError("inventory: files outside declared enumeration")
    if any(not isinstance(content, str) for content in files.values()):
        raise ValueError("inventory: workflow contents must be strings")
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
    complete = enumeration_complete and analyzed == len(records)
    return {"schema_version": VERSION, "evidence_class": "static_source_analysis",
            "repository_id": repository_id, "revision": revision, "observed_at": observed_at,
            "expected_paths": sorted(expected_paths), "enumerated_count": len(expected_paths),
            "enumeration_complete": enumeration_complete,
            "analyzed_count": analyzed, "coverage": "complete" if complete else "partial",
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
                job_count = record["job_count"]
                triggers = record["triggers"]
                transitive_coverage = record["transitive_coverage"]
                reusable_references = record["reusable_references"]
                if (type(job_count) is not int or not 0 <= job_count <= MAX_NODES
                        or not isinstance(triggers, list) or len(triggers) > MAX_NODES
                        or any(not isinstance(trigger, str) or not trigger for trigger in triggers)
                        or triggers != sorted(set(triggers))
                        or transitive_coverage not in {"not_requested", "unresolved"}
                        or not isinstance(reusable_references, list)
                        or len(reusable_references) > MAX_NODES
                        or any(not isinstance(reference, str) or not reference
                               for reference in reusable_references)
                        or (transitive_coverage == "unresolved") != bool(reusable_references)):
                    raise ValueError("snapshot: invalid analysis metadata")
                findings = record.get("findings")
                expected_fields = {
                    "code", "severity", "location", "basis", "requires_review", "proposed_action",
                }
                if not isinstance(findings, list) or len(findings) > MAX_NODES:
                    raise ValueError("snapshot: invalid findings")
                finding_identities: set[tuple[Any, ...]] = set()
                for finding in findings:
                    if not isinstance(finding, dict) or set(finding) != expected_fields:
                        raise ValueError("snapshot: invalid finding")
                    code = finding.get("code")
                    if (not isinstance(code, str) or code not in REPAIRS
                            or finding.get("severity") != FINDING_SEVERITIES[code]
                            or not isinstance(finding.get("location"), str)
                            or not 0 < len(finding["location"]) <= 1024
                            or finding.get("basis") != "static_source"
                            or finding.get("requires_review") is not True
                            or finding.get("proposed_action") != REPAIRS[code]):
                        raise ValueError("snapshot: invalid finding")
                    identity = tuple(finding[field] for field in sorted(expected_fields))
                    if identity in finding_identities:
                        raise ValueError("snapshot: duplicate finding")
                    finding_identities.add(identity)
            elif record["status"] == "invalid_or_unsupported":
                if record.get("findings"):
                    raise ValueError("snapshot: findings require analyzed source")
                if not re.fullmatch(r"[0-9a-f]{64}", record.get("source_digest", "")):
                    raise ValueError("snapshot: invalid digest")
            else:
                if record.get("findings"):
                    raise ValueError("snapshot: findings require analyzed source")
                if "source_digest" in record:
                    raise ValueError("snapshot: unavailable source has digest")
        analyzed = sum(record["status"] == "analyzed" for record in records.values())
        enumeration_complete = snapshot.get("enumeration_complete", False)
        if type(enumeration_complete) is not bool:
            raise ValueError("snapshot: inconsistent coverage")
        coverage = "complete" if enumeration_complete and analyzed == len(records) else "partial"
        if (type(snapshot["analyzed_count"]) is not int
                or type(snapshot["enumerated_count"]) is not int
                or snapshot["analyzed_count"] != analyzed
                or snapshot["enumerated_count"] != len(records)
                or snapshot["coverage"] != coverage):
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
    if previous["revision"] == current["revision"]:
        previous_paths = set(previous["expected_paths"])
        current_paths = set(current["expected_paths"])
        if ((previous["enumeration_complete"] and not current_paths <= previous_paths)
                or (current["enumeration_complete"] and not previous_paths <= current_paths)):
            raise ValueError("drift: conflicting complete enumeration")
        for path in set(previous["workflows"]) & set(current["workflows"]):
            before, after = previous["workflows"][path], current["workflows"][path]
            before_digest = before.get("source_digest")
            after_digest = after.get("source_digest")
            if (before_digest is not None and after_digest is not None
                    and before_digest != after_digest):
                raise ValueError("drift: content changed at unchanged revision")
    changes = []
    old, new = previous["workflows"], current["workflows"]
    for path in sorted(set(old) | set(new)):
        before, after = old.get(path), new.get(path)
        if (before and after
                and before.get("source_digest") is not None
                and before.get("source_digest") == after.get("source_digest")
                and before["status"] != after["status"]):
            raise ValueError("drift: inconsistent analysis status")
        if (before and after and before["status"] == after["status"] == "analyzed"
                and before["source_digest"] == after["source_digest"]):
            deterministic_fields = (
                "normalized_digest", "job_count", "triggers", "findings",
                "transitive_coverage", "reusable_references",
            )
            if any(before[field] != after[field] for field in deterministic_fields):
                raise ValueError("drift: inconsistent analysis")
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
    _validate_snapshot(snapshot)
    if type(criticality) is not int or not 1 <= criticality <= 5:
        raise ValueError("review: invalid criticality")
    if type(downstream_count) is not int or downstream_count < 0:
        raise ValueError("review: invalid downstream count")
    if (not isinstance(owner_refs, list) or len(owner_refs) > 1024
            or any(not isinstance(value, str)
                   or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,256}", value)
                   for value in owner_refs)):
        raise ValueError("review: invalid owner references")
    owners = sorted(set(owner_refs))
    result = []
    for path, record in snapshot["workflows"].items():
        for finding in record.get("findings", []):
            proposal = {"repository_id": snapshot["repository_id"], "revision": snapshot["revision"],
                        "path": path, "source_digest": record["source_digest"],
                        "code": finding["code"], "severity": finding["severity"],
                        "location": finding["location"], "basis": finding["basis"],
                        "requires_review": finding["requires_review"],
                        "proposed_action": finding["proposed_action"],
                        "owner_refs": owners,
                        "owner_status": "resolved_by_caller" if owners else "unresolved",
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
        if type(identity) is not int or identity <= 0:
            raise ValueError("reviews: invalid identity")
        if identity in seen:
            raise ValueError("reviews: duplicate identity")
        seen.add(identity)
        requested = _time(record["requested_at"])
        reviewed_value = record.get("first_review_at")
        reviewed = None if reviewed_value is None else _time(reviewed_value)
        if requested > now or (reviewed and not requested <= reviewed <= now):
            raise ValueError("reviews: invalid chronology")
        target = latencies if reviewed else pending_ages
        target.append(((reviewed or now) - requested).total_seconds())
        count = record.get("changes_requested", 0)
        if type(count) is not int or count < 0:
            raise ValueError("reviews: invalid rework count")
        if count and reviewed is None:
            raise ValueError("reviews: rework requires a completed review")
        rework += count
        reviewer_ids = record.get("reviewer_ids", [])
        if (not isinstance(reviewer_ids, list) or len(reviewer_ids) > 1024
                or any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value)
                       for value in reviewer_ids)):
            raise ValueError("reviews: invalid reviewer identities")
        if reviewed is not None:
            reviewers.update(set(reviewer_ids))
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
