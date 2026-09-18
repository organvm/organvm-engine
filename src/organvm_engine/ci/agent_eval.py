"""Deterministic agent-trace checks, not execution attestations or release authority.

The trace is evaluator-visible input, not hidden model reasoning. Reports omit
raw prompts, arguments, observations and outputs. Keep source traces restricted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

VERSION = "organvm.agent-eval.v2"
MAX_JSON_BYTES = 2_097_152
DIMENSIONS = ("tool_choice", "parameters", "state", "outcome", "policy")
OUTCOMES = ("completed", "refused", "abstained", "error")
TOKEN = {"type": "string", "pattern": r"\A[A-Za-z0-9_.:-]{1,128}\Z"}
ARTIFACT = {"type": "string", "minLength": 1, "maxLength": 1024,
            "pattern": r"\A[^\x00-\x1f\x7f]+\Z"}
SHA = {"type": "string", "pattern": r"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\Z"}
STEP_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["id", "tool", "depends_on", "arguments", "observation",
                 "state_before", "state_after", "status"],
    "properties": {
        "id": TOKEN, "tool": TOKEN,
        "depends_on": {"type": "array", "items": TOKEN, "uniqueItems": True, "maxItems": 256},
        "arguments": {"type": "object"}, "observation": {},
        "state_before": {"type": "object"}, "state_after": {"type": "object"},
        "status": {"enum": ["succeeded", "failed", "denied"]},
    },
}
TRACE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["schema_version", "case_id", "repository_id", "revision", "outcome",
                 "input", "output", "steps", "observed_artifacts"],
    "properties": {
        "schema_version": {"const": VERSION}, "case_id": TOKEN,
        "repository_id": {"type": "integer", "minimum": 1}, "revision": SHA,
        "outcome": {"enum": list(OUTCOMES)}, "input": {}, "output": {},
        "steps": {"type": "array", "items": STEP_SCHEMA, "maxItems": 256},
        "observed_artifacts": {"type": "array", "items": ARTIFACT,
                               "uniqueItems": True, "maxItems": 4096},
    },
}
CHECK_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["id", "dimension", "pointer", "op", "required", "weight", "when"],
    "properties": {
        "id": TOKEN, "dimension": {"enum": list(DIMENSIONS)},
        "pointer": {"type": "string", "maxLength": 1024},
        "op": {"enum": ["equals", "exists"]}, "expected": {},
        "required": {"type": "boolean"},
        "weight": {"type": "number", "exclusiveMinimum": 0, "maximum": 1000000},
        "when": {"type": "array", "items": {"enum": list(OUTCOMES)},
                 "minItems": 1, "uniqueItems": True},
    },
    "allOf": [{"if": {"properties": {"op": {"const": "equals"}}},
               "then": {"required": ["expected"]}}],
}
RUBRIC_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["schema_version", "checks"],
    "properties": {
        "schema_version": {"const": VERSION},
        "checks": {"type": "array", "items": CHECK_SCHEMA, "minItems": 1, "maxItems": 1024},
    },
}


def _require_json_native(value: Any) -> None:
    """Reject Python-only values before they can collapse into identical JSON."""
    if value is None or type(value) in (str, int, float, bool):
        return
    if type(value) is list:
        for item in value:
            _require_json_native(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("non-string JSON object key")
            _require_json_native(item)
        return
    raise TypeError("non-JSON-native value")


def digest(value: Any) -> str:
    """Version-local canonical JSON digest; NOT an RFC 8785 signature."""
    _require_json_native(value)
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _json_equal(left: Any, right: Any) -> bool:
    """Compare JSON values semantically while keeping booleans distinct from numbers."""
    if type(left) is bool or type(right) is bool:
        return type(left) is type(right) and left == right
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    return left == right


def _validate(value: Any, schema: dict, label: str) -> None:
    # Do not echo schema validation messages: they can contain private input.
    try:
        digest(value)
        valid = Draft202012Validator(schema).is_valid(value)
    except (TypeError, ValueError, RecursionError):
        raise ValueError(f"{label}: invalid JSON") from None
    if not valid:
        raise ValueError(f"{label}: invalid schema")


def _pointer(document: Any, pointer: str) -> tuple[bool, Any]:
    if pointer == "":
        return True, document
    if not pointer.startswith("/"):
        raise ValueError("rubric: invalid JSON pointer")
    current = document
    for raw in pointer[1:].split("/"):
        # RFC 6901 escapes; reject invalid syntax even on absent paths.
        remainder = raw.replace("~1", "").replace("~0", "")
        if "~" in remainder:
            raise ValueError("rubric: invalid JSON pointer escape")
    for raw in pointer[1:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and (key == "0" or (key.isascii() and key.isdigit()
                                                         and not key.startswith("0"))):
            if len(key) > 9 or int(key) >= len(current):
                return False, None
            current = current[int(key)]
        else:
            return False, None
    return True, current


def evaluate_trace(trace: dict, rubric: dict, *, expected_revision: str,
                   expected_repository_id: int, expected_rubric_digest: str,
                   expected_artifacts: list[str], expected_scope_digest: str) -> dict:
    """Check a recorded trace against a caller-pinned rubric and source identity.

    Every dimension needs an applicable required check before a completed trace
    passes. The caller, not the trace producer, owns the expected values/rubric.
    Absence is never equality with JSON null. Equality is JSON-type-sensitive.
    """
    _validate(trace, TRACE_SCHEMA, "trace")
    _validate(rubric, RUBRIC_SCHEMA, "rubric")
    _validate(expected_artifacts, {"type": "array", "items": ARTIFACT,
                                   "uniqueItems": True, "maxItems": 4096},
              "scope manifest")
    if (type(expected_repository_id) is not int or type(trace["repository_id"]) is not int
            or trace["repository_id"] != expected_repository_id):
        raise ValueError("trace: repository identity mismatch")
    if trace["revision"] != expected_revision:
        raise ValueError("trace: stale revision")
    if digest(rubric) != expected_rubric_digest:
        raise ValueError("rubric: digest mismatch")
    if digest(expected_artifacts) != expected_scope_digest:
        raise ValueError("scope manifest: digest mismatch")
    seen: dict[str, str] = {}
    for step in trace["steps"]:
        if step["id"] in seen:
            raise ValueError("trace: duplicate step identity")
        if any(seen.get(parent) != "succeeded" for parent in step["depends_on"]):
            raise ValueError("trace: unsatisfied dependency")
        seen[step["id"]] = step["status"]
    checks = rubric["checks"]
    if len({check["id"] for check in checks}) != len(checks):
        raise ValueError("rubric: duplicate check identity")
    outcome = trace["outcome"]
    # v2 has no recovery/compensation contract. A successful-looking output
    # cannot erase an unsuccessful recorded step or invent tool execution.
    if outcome == "completed" and (
        not trace["steps"] or any(step["status"] != "succeeded" for step in trace["steps"])
    ):
        raise ValueError("trace: completed workflow lacks successful step evidence")
    results = []
    for check in checks:
        exists, value = _pointer(trace, check["pointer"])
        applicable = outcome in check["when"]
        passed = exists and (
            check["op"] == "exists" or _json_equal(value, check["expected"])
        )
        results.append({"id": check["id"], "dimension": check["dimension"],
                        "required": check["required"], "weight": check["weight"],
                        "status": ("pass" if passed else "fail") if applicable else "not_applicable"})
    scores = {}
    coverage = {}
    for dimension in DIMENSIONS:
        measured = [r for r in results if r["dimension"] == dimension
                    and r["status"] != "not_applicable"]
        total = sum(r["weight"] for r in measured)
        scores[dimension] = (sum(r["weight"] for r in measured if r["status"] == "pass") / total
                             if total else None)
        coverage[dimension] = any(r["required"] for r in measured)
    failures = [r["id"] for r in results if r["required"] and r["status"] == "fail"]
    needed = DIMENSIONS if outcome == "completed" else ("policy",)
    missing_artifacts = set(expected_artifacts) - set(trace["observed_artifacts"])
    scope = {"manifest_digest": expected_scope_digest,
             "expected_count": len(expected_artifacts),
             "observed_count": len(trace["observed_artifacts"]),
             "missing_count": len(missing_artifacts),
             "complete": not missing_artifacts}
    complete = all(coverage[d] for d in needed) and (outcome != "completed" or scope["complete"])
    if failures:
        decision = "fail"
    elif not complete:
        decision = "incomplete"
    else:
        decision = "pass" if outcome == "completed" else outcome
    return {"schema_version": VERSION, "evidence_class": "recorded_trace_consistency",
            "case_id": trace["case_id"], "repository_id": trace["repository_id"],
            "revision": trace["revision"], "trace_digest": digest(trace),
            "rubric_digest": expected_rubric_digest, "outcome": outcome,
            "decision": decision, "scores": scores, "coverage": coverage,
            "scope": scope, "failed_required": failures, "checks": results,
            "authorizes_execution": False, "authorizes_release": False}


def load_json(path: Path) -> Any:
    """Bounded JSON file loading; duplicate keys are ambiguous, not last-wins."""
    def unique(pairs: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("JSON: duplicate key")
            result[key] = value
        return result

    with path.open("rb") as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("JSON: size budget exceeded")
    return json.loads(data, object_pairs_hook=unique)


def _validate_report(report: dict) -> None:
    """Check internal score consistency, not producer authenticity."""
    if report.get("schema_version") != VERSION:
        raise ValueError("gate: unsupported report version")
    if (not Draft202012Validator(TOKEN).is_valid(report.get("case_id"))
            or type(report.get("repository_id")) is not int or report["repository_id"] <= 0
            or not isinstance(report.get("revision"), str)
            or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", report["revision"])
            or not isinstance(report.get("trace_digest"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", report["trace_digest"])):
        raise ValueError("gate: immutable report identity required")
    results = report.get("checks")
    result_schema = {
        "type": "object", "additionalProperties": False,
        "required": ["id", "dimension", "required", "weight", "status"],
        "properties": {
            "id": TOKEN, "dimension": {"enum": list(DIMENSIONS)},
            "required": {"type": "boolean"},
            "weight": CHECK_SCHEMA["properties"]["weight"],
            "status": {"enum": ["pass", "fail", "not_applicable"]},
        },
    }
    _validate(results, {"type": "array", "items": result_schema,
                        "minItems": 1, "maxItems": 1024}, "gate checks")
    # jsonschema validates this at runtime; retain an explicit guard so static
    # analysis and future validator substitutions preserve the same boundary.
    if not isinstance(results, list):
        raise ValueError("gate: invalid check results")
    if len({r["id"] for r in results}) != len(results):
        raise ValueError("gate: duplicate check results")
    scope_schema = {
        "type": "object", "additionalProperties": False,
        "required": ["manifest_digest", "expected_count", "observed_count",
                     "missing_count", "complete"],
        "properties": {
            "manifest_digest": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
            "expected_count": {"type": "integer", "minimum": 0, "maximum": 4096},
            "observed_count": {"type": "integer", "minimum": 0, "maximum": 4096},
            "missing_count": {"type": "integer", "minimum": 0, "maximum": 4096},
            "complete": {"type": "boolean"},
        },
    }
    scope = report.get("scope")
    _validate(scope, scope_schema, "gate scope")
    if (not isinstance(scope, dict)
            or scope["missing_count"] > scope["expected_count"]
            or scope["observed_count"] < scope["expected_count"] - scope["missing_count"]
            or scope["complete"] != (scope["missing_count"] == 0)):
        raise ValueError("gate: inconsistent scope evidence")
    failures = [r["id"] for r in results if r["required"] and r["status"] == "fail"]
    scores, coverage = {}, {}
    for dimension in DIMENSIONS:
        measured = [r for r in results if r["dimension"] == dimension
                    and r["status"] != "not_applicable"]
        weight = sum(r["weight"] for r in measured)
        scores[dimension] = (sum(r["weight"] for r in measured if r["status"] == "pass") / weight
                             if weight else None)
        coverage[dimension] = any(r["required"] for r in measured)
    decision = ("fail" if failures else
                ("pass" if all(coverage.values()) and scope["complete"] else "incomplete"))
    expected = [scores, coverage, failures, decision]
    actual = [report.get("scores"), report.get("coverage"), report.get("failed_required"),
              report.get("decision")]
    if not _json_equal(expected, actual):
        raise ValueError("gate: inconsistent score evidence")


def promotion_gate(baseline: list[dict], candidate: list[dict], *, case_ids: list[str],
                   rubric_digest: str, scope_manifest_digest: str, expected_scope_count: int,
                   minimum_gain: float = 0.01) -> dict:
    """Paired held-out eligibility, never automatic learning or promotion.

    Caller must freeze the held-out case manifest separately from generation.
    All cases/dimensions must be comparable; refusal/abstention is not scored as
    failure. No per-case dimension regression may hide inside an average gain.
    """
    if (type(minimum_gain) not in (int, float) or not math.isfinite(minimum_gain)
            or not 0 < minimum_gain <= 1):
        raise ValueError("gate: minimum_gain must be finite and in (0, 1]")
    if not isinstance(rubric_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", rubric_digest):
        raise ValueError("gate: valid pinned rubric digest required")
    if (not isinstance(scope_manifest_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", scope_manifest_digest)):
        raise ValueError("gate: valid pinned scope manifest digest required")
    if type(expected_scope_count) is not int or not 0 <= expected_scope_count <= 4096:
        raise ValueError("gate: valid pinned scope manifest count required")
    if (not Draft202012Validator({"type": "array", "items": TOKEN, "minItems": 1,
                                  "maxItems": 4096, "uniqueItems": True}).is_valid(case_ids)):
        raise ValueError("gate: empty or duplicate held-out cases")
    trace_cases: dict[str, str] = {}
    for reports in (baseline, candidate):
        ids = [r.get("case_id") for r in reports]
        if len(ids) != len(case_ids) or set(ids) != set(case_ids):
            raise ValueError("gate: paired case coverage mismatch")
        for report in reports:
            _validate_report(report)
            trace_digest = report["trace_digest"]
            previous_case = trace_cases.setdefault(trace_digest, report["case_id"])
            if previous_case != report["case_id"]:
                raise ValueError("gate: trace digest reused across held-out cases")
            if (not isinstance(report.get("rubric_digest"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", report["rubric_digest"])
                    or report["rubric_digest"] != rubric_digest
                    or report.get("scope", {}).get("manifest_digest") != scope_manifest_digest
                    or report.get("scope", {}).get("expected_count") != expected_scope_count
                    or report.get("evidence_class") != "recorded_trace_consistency"
                    or report.get("outcome") != "completed"
                    or not report.get("scope", {}).get("complete")):
                raise ValueError("gate: incomparable evidence")
            for dimension in DIMENSIONS:
                value = report.get("scores", {}).get(dimension)
                if (type(value) not in (int, float) or not math.isfinite(value)
                        or not 0 <= value <= 1 or not report.get("coverage", {}).get(dimension)):
                    raise ValueError("gate: incomplete dimension evidence")
    before = {r["case_id"]: r for r in baseline}
    deltas = []
    reasons = set()
    for report in candidate:
        old = before[report["case_id"]]
        # A digest claim alone does not make two result sets comparable.
        # Ignore order, but require identical observable check definitions.
        def signature(result: dict) -> list:
            return sorted(
                [[r["id"], r["dimension"], r["required"], r["weight"],
                  r["status"] != "not_applicable"] for r in result["checks"]],
                key=lambda row: row[0],
            )

        if digest(signature(old)) != digest(signature(report)):
            raise ValueError("gate: paired check contract mismatch")
        if report.get("repository_id") != old.get("repository_id"):
            raise ValueError("gate: repository identity mismatch")
        if report.get("revision") != old.get("revision"):
            raise ValueError("gate: paired revision mismatch")
        if (report["scope"]["manifest_digest"] != old["scope"]["manifest_digest"]
                or report["scope"]["expected_count"] != old["scope"]["expected_count"]):
            raise ValueError("gate: paired scope manifest mismatch")
        outcome_fields = ("checks", "scores", "coverage", "failed_required", "decision", "scope")
        if (report["trace_digest"] == old["trace_digest"]
                and digest({field: report[field] for field in outcome_fields})
                != digest({field: old[field] for field in outcome_fields})):
            raise ValueError("gate: trace digest contradicts evaluation outcome")
        if report.get("decision") != "pass" or report.get("failed_required") != []:
            reasons.add("candidate_required_check_failure")
        for dimension in DIMENSIONS:
            delta = report["scores"][dimension] - old["scores"][dimension]
            deltas.append(delta)
            if delta < 0:
                reasons.add("per_case_dimension_regression")
    gain = sum(deltas) / len(deltas)
    if gain < minimum_gain:
        reasons.add("insufficient_measured_gain")
    return {"schema_version": VERSION, "decision": "blocked" if reasons else "eligible_for_review",
            "case_manifest_digest": digest(sorted(case_ids)), "rubric_digest": rubric_digest,
            "scope_manifest_digest": scope_manifest_digest,
            "expected_scope_count": expected_scope_count,
            "baseline_digest": digest(baseline), "candidate_digest": digest(candidate),
            "paired_cases": len(case_ids), "mean_dimension_gain": gain,
            "minimum_gain": minimum_gain, "reasons": sorted(reasons),
            "authorizes_learning": False, "authorizes_release": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("rubric", type=Path)
    parser.add_argument("--repository-id", type=int, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--rubric-digest", required=True)
    parser.add_argument("--scope-manifest", type=Path, required=True)
    parser.add_argument("--scope-digest", required=True)
    args = parser.parse_args(argv)
    try:
        result = evaluate_trace(load_json(args.trace), load_json(args.rubric),
                                expected_revision=args.revision,
                                expected_repository_id=args.repository_id,
                                expected_rubric_digest=args.rubric_digest,
                                expected_artifacts=load_json(args.scope_manifest),
                                expected_scope_digest=args.scope_digest)
    except (OSError, ValueError, RecursionError):
        print(json.dumps({"decision": "invalid", "authorizes_release": False}))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result["decision"] in {"pass", "refused", "abstained"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
