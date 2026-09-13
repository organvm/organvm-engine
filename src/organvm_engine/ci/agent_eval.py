"""Deterministic agent-trace checks, not execution attestations or release authority.

The trace is evaluator-visible input, not hidden model reasoning. Reports omit
raw prompts, arguments, observations and outputs. Keep source traces restricted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

VERSION = "organvm.agent-eval.v1"
MAX_JSON_BYTES = 2_097_152
DIMENSIONS = ("tool_choice", "parameters", "state", "outcome", "policy")
OUTCOMES = ("completed", "refused", "abstained", "error")
TOKEN = {"type": "string", "pattern": r"^[A-Za-z0-9_.:-]{1,128}$"}
SHA = {"type": "string", "pattern": r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$"}
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
                 "input", "output", "steps"],
    "properties": {
        "schema_version": {"const": VERSION}, "case_id": TOKEN,
        "repository_id": {"type": "integer", "minimum": 1}, "revision": SHA,
        "outcome": {"enum": list(OUTCOMES)}, "input": {}, "output": {},
        "steps": {"type": "array", "items": STEP_SCHEMA, "maxItems": 256},
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


def digest(value: Any) -> str:
    """Version-local canonical JSON digest; NOT an RFC 8785 signature."""
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


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
                   expected_repository_id: int, expected_rubric_digest: str) -> dict:
    """Check a recorded trace against a caller-pinned rubric and source identity.

    Every dimension needs an applicable required check before a completed trace
    passes. The caller, not the trace producer, owns the expected values/rubric.
    Absence is never equality with JSON null. Equality is JSON-type-sensitive.
    """
    _validate(trace, TRACE_SCHEMA, "trace")
    _validate(rubric, RUBRIC_SCHEMA, "rubric")
    if (type(expected_repository_id) is not int or type(trace["repository_id"]) is not int
            or trace["repository_id"] != expected_repository_id):
        raise ValueError("trace: repository identity mismatch")
    if trace["revision"] != expected_revision:
        raise ValueError("trace: stale revision")
    if digest(rubric) != expected_rubric_digest:
        raise ValueError("rubric: digest mismatch")
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
    # v1 has no recovery/compensation contract. A successful-looking output
    # cannot erase an unsuccessful recorded step or invent tool execution.
    if outcome == "completed" and (
        not trace["steps"] or any(step["status"] != "succeeded" for step in trace["steps"])
    ):
        raise ValueError("trace: completed workflow lacks successful step evidence")
    results = []
    for check in checks:
        exists, value = _pointer(trace, check["pointer"])
        applicable = outcome in check["when"]
        passed = exists and (check["op"] == "exists" or digest(value) == digest(check["expected"]))
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
    complete = all(coverage[d] for d in needed)
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
            "failed_required": failures, "checks": results,
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
    if len({r["id"] for r in results}) != len(results):
        raise ValueError("gate: duplicate check results")
    failures = [r["id"] for r in results if r["required"] and r["status"] == "fail"]
    scores, coverage = {}, {}
    for dimension in DIMENSIONS:
        measured = [r for r in results if r["dimension"] == dimension
                    and r["status"] != "not_applicable"]
        weight = sum(r["weight"] for r in measured)
        scores[dimension] = (sum(r["weight"] for r in measured if r["status"] == "pass") / weight
                             if weight else None)
        coverage[dimension] = any(r["required"] for r in measured)
    decision = "fail" if failures else ("pass" if all(coverage.values()) else "incomplete")
    expected = [scores, coverage, failures, decision]
    actual = [report.get("scores"), report.get("coverage"), report.get("failed_required"),
              report.get("decision")]
    if digest(expected) != digest(actual):
        raise ValueError("gate: inconsistent score evidence")


def promotion_gate(baseline: list[dict], candidate: list[dict], *, case_ids: list[str],
                   rubric_digest: str, minimum_gain: float = 0.01) -> dict:
    """Paired held-out eligibility, never automatic learning or promotion.

    Caller must freeze the held-out case manifest separately from generation.
    All cases/dimensions must be comparable; refusal/abstention is not scored as
    failure. No per-case dimension regression may hide inside an average gain.
    """
    if (type(minimum_gain) not in (int, float) or not math.isfinite(minimum_gain)
            or not 0 < minimum_gain <= 1):
        raise ValueError("gate: minimum_gain must be finite and in (0, 1]")
    if not case_ids or len(set(case_ids)) != len(case_ids):
        raise ValueError("gate: empty or duplicate held-out cases")
    for reports in (baseline, candidate):
        ids = [r.get("case_id") for r in reports]
        if len(ids) != len(case_ids) or set(ids) != set(case_ids):
            raise ValueError("gate: paired case coverage mismatch")
        for report in reports:
            _validate_report(report)
            if (report.get("rubric_digest") != rubric_digest
                    or report.get("evidence_class") != "recorded_trace_consistency"
                    or report.get("outcome") != "completed"):
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
                [(r["id"], r["dimension"], r["required"], r["weight"],
                  r["status"] != "not_applicable") for r in result["checks"]],
                key=lambda row: row[0],
            )

        if digest(signature(old)) != digest(signature(report)):
            raise ValueError("gate: paired check contract mismatch")
        if report.get("repository_id") != old.get("repository_id"):
            raise ValueError("gate: repository identity mismatch")
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
    args = parser.parse_args(argv)
    try:
        result = evaluate_trace(load_json(args.trace), load_json(args.rubric),
                                expected_revision=args.revision,
                                expected_repository_id=args.repository_id,
                                expected_rubric_digest=args.rubric_digest)
    except (OSError, ValueError, RecursionError):
        print(json.dumps({"decision": "invalid", "authorizes_release": False}))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result["decision"] in {"pass", "refused", "abstained"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
