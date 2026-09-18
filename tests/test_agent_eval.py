"""Synthetic deterministic contract tests; no model calls or live mutations."""
import copy
import json

import pytest

from organvm_engine.ci.agent_eval import (
    DIMENSIONS,
    VERSION,
    digest,
    evaluate_trace,
    main,
)
from organvm_engine.ci.agent_eval import promotion_gate as _promotion_gate

HEAD = "a" * 40
REPO = 1160447354
SCOPE_DIGEST = digest(["README.md"])
SCOPE_COUNT = 1


def promotion_gate(*args, **kwargs):
    """Exercise the production gate with the fixture's independently pinned scope."""
    kwargs.setdefault("expected_scope_count", SCOPE_COUNT)
    return _promotion_gate(*args, **kwargs)


def fixture_pair():
    step = {"id": "read", "tool": "read_file", "depends_on": [],
            "arguments": {"path": "README.md", "mutate": False},
            "observation": {"content": "SYNTHETIC-PRIVATE-CONTENT"},
            "state_before": {"phase": "new"}, "state_after": {"phase": "observed"},
            "status": "succeeded"}
    trace = {"schema_version": VERSION, "case_id": "read-only-1", "repository_id": REPO,
             "revision": HEAD, "outcome": "completed", "input": "SYNTHETIC-PRIVATE-PROMPT",
             "output": {"done": True, "quality": True}, "steps": [step],
             "observed_artifacts": ["README.md"]}
    targets = [("/steps/0/tool", "read_file"), ("/steps/0/arguments/path", "README.md"),
               ("/steps/0/state_after/phase", "observed"), ("/output/done", True),
               ("/steps/0/arguments/mutate", False)]
    checks = [{"id": dimension, "dimension": dimension, "pointer": path, "expected": value,
               "op": "equals", "required": True, "weight": 1, "when": ["completed"]}
              for dimension, (path, value) in zip(DIMENSIONS, targets, strict=True)]
    return trace, {"schema_version": VERSION, "checks": checks}


def score(trace=None, rubric=None, **overrides):
    original_trace, original_rubric = fixture_pair()
    trace = original_trace if trace is None else trace
    rubric = original_rubric if rubric is None else rubric
    kwargs = {"expected_revision": HEAD, "expected_repository_id": REPO,
              "expected_rubric_digest": digest(rubric),
              "expected_artifacts": ["README.md"],
              "expected_scope_digest": digest(["README.md"]), **overrides}
    return evaluate_trace(trace, rubric, **kwargs)


def test_full_trace_scores_separately_and_does_not_authorize():
    result = score()
    assert result["decision"] == "pass"
    assert result["scores"] == dict.fromkeys(DIMENSIONS, 1.0)
    assert result["scope"] == {"manifest_digest": digest(["README.md"]),
                                "expected_count": 1, "observed_count": 1,
                                "missing_count": 0, "complete": True}
    assert not result["authorizes_release"] and not result["authorizes_execution"]
    serialized = json.dumps(result)
    assert "SYNTHETIC-PRIVATE" not in serialized
    assert "arguments" not in result and "output" not in result


@pytest.mark.parametrize("key,value", [("expected_revision", "b" * 40),
                                       ("expected_repository_id", 12),
                                       ("expected_repository_id", True),
                                       ("expected_rubric_digest", "0" * 64),
                                       ("expected_scope_digest", "0" * 64)])
def test_pinned_identity_is_required(key, value):
    with pytest.raises(ValueError):
        score(**{key: value})


@pytest.mark.parametrize("mutation", ["duplicate", "self", "future", "unknown", "failed", "denied"])
def test_dag_counterexamples(mutation):
    trace, rubric = fixture_pair()
    child = copy.deepcopy(trace["steps"][0])
    child.update(id="prepare", depends_on=["read"])
    trace["steps"].append(child)
    if mutation == "duplicate":
        child["id"] = "read"
    elif mutation == "self":
        child["depends_on"] = ["prepare"]
    elif mutation == "future":
        trace["steps"].reverse()
    elif mutation == "unknown":
        child["depends_on"] = ["missing"]
    else:
        trace["steps"][0]["status"] = mutation
    with pytest.raises(ValueError):
        score(trace, rubric)


def test_branching_dag_topological_order():
    trace, rubric = fixture_pair()
    for identity, parents in [("left", ["read"]), ("right", ["read"]), ("join", ["left", "right"])]:
        child = copy.deepcopy(trace["steps"][0])
        child.update(id=identity, depends_on=parents)
        trace["steps"].append(child)
    assert score(trace, rubric)["decision"] == "pass"


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_missing_dimension_is_not_pass(dimension):
    trace, rubric = fixture_pair()
    rubric["checks"] = [c for c in rubric["checks"] if c["dimension"] != dimension]
    assert score(trace, rubric)["decision"] == "incomplete"


def test_optional_checks_cannot_replace_required_coverage():
    trace, rubric = fixture_pair()
    rubric["checks"][0]["required"] = False
    assert score(trace, rubric)["decision"] == "incomplete"


def test_completed_claim_requires_caller_pinned_artifact_coverage():
    trace, rubric = fixture_pair()
    trace["observed_artifacts"] = []
    result = score(trace, rubric)
    assert result["decision"] == "incomplete"
    assert result["scope"]["missing_count"] == 1
    assert not result["scope"]["complete"]


def test_agent_cannot_shrink_or_duplicate_caller_scope():
    trace, rubric = fixture_pair()
    with pytest.raises(ValueError, match="digest mismatch"):
        score(trace, rubric, expected_artifacts=[],
              expected_scope_digest=digest(["README.md"]))
    trace["observed_artifacts"] = ["README.md", "README.md"]
    with pytest.raises(ValueError):
        score(trace, rubric)


def test_trace_rejects_artifact_with_trailing_newline():
    trace, rubric = fixture_pair()
    trace["observed_artifacts"] = ["README.md\n"]
    with pytest.raises(ValueError):
        score(trace, rubric)


def test_trace_rejects_revision_with_trailing_newline():
    trace, rubric = fixture_pair()
    trace["revision"] = HEAD + "\n"
    with pytest.raises(ValueError):
        score(trace, rubric)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 0, True, "1"])
def test_invalid_weights_fail_closed(value):
    trace, rubric = fixture_pair()
    rubric["checks"][0]["weight"] = value
    with pytest.raises(ValueError):
        score(trace, rubric, expected_rubric_digest="0" * 64)


@pytest.mark.parametrize("outcome", ["refused", "abstained", "error"])
def test_refusal_abstention_error_separate_from_capability(outcome):
    trace, rubric = fixture_pair()
    trace.update(outcome=outcome, steps=[], output=None)
    rubric["checks"].append({"id": "outcome-policy", "dimension": "policy", "pointer": "/outcome",
                             "op": "equals", "expected": outcome, "required": True,
                             "weight": 1, "when": [outcome]})
    result = score(trace, rubric)
    assert result["decision"] == outcome
    assert result["scores"]["tool_choice"] is None
    assert result["scores"]["policy"] == 1
    with pytest.raises(ValueError):
        promotion_gate([result], [result], case_ids=[result["case_id"]],
                       rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST)


def test_unapproved_refusal_still_fails_policy():
    trace, rubric = fixture_pair()
    trace["outcome"] = "refused"
    rubric["checks"][-1].update(pointer="/outcome", expected="completed", when=["refused"])
    assert score(trace, rubric)["decision"] == "fail"


def test_json_null_is_not_absence_and_boolean_is_not_number():
    trace, rubric = fixture_pair()
    check = rubric["checks"][0]
    check.update(pointer="/output/absent", expected=None)
    assert score(trace, rubric)["decision"] == "fail"
    trace["output"]["absent"] = None
    assert score(trace, rubric)["decision"] == "pass"
    check.update(pointer="/output/done", expected=1)
    assert score(trace, rubric)["decision"] == "fail"


def test_json_numbers_compare_by_value_across_integer_and_decimal_forms():
    trace, rubric = fixture_pair()
    trace["output"]["quality"] = 1.0
    rubric["checks"][0].update(pointer="/output/quality", expected=1)
    assert score(trace, rubric)["decision"] == "pass"


@pytest.mark.parametrize("value", [("python", "tuple"), {1: "non-string-key"}])
def test_python_only_values_are_rejected_before_digesting(value):
    trace, rubric = fixture_pair()
    trace["input"] = value
    with pytest.raises(ValueError, match="invalid JSON"):
        score(trace, rubric)


def test_json_pointer_escapes_and_exists():
    trace, rubric = fixture_pair()
    trace["output"]["a/b"] = {"~": None}
    rubric["checks"][0].update(pointer="/output/a~1b/~0", op="exists")
    assert score(trace, rubric)["decision"] == "pass"


@pytest.mark.parametrize("pointer", ["output", "/absent/~2", "/absent/~"])
def test_invalid_pointer_is_rejected_even_on_missing_path(pointer):
    trace, rubric = fixture_pair()
    rubric["checks"][0]["pointer"] = pointer
    with pytest.raises(ValueError):
        score(trace, rubric)


@pytest.mark.parametrize("pointer", ["/steps/-1", "/steps/00", "/steps/999999999999999999999"])
def test_pointer_does_not_accept_noncanonical_array_index(pointer):
    trace, rubric = fixture_pair()
    rubric["checks"][0].update(pointer=pointer, op="exists")
    assert score(trace, rubric)["decision"] == "fail"


@pytest.mark.parametrize("bad", ["llm_judge", "exec", "python"])
def test_no_model_or_code_execution_oracles(bad):
    trace, rubric = fixture_pair()
    rubric["checks"][0]["op"] = bad
    with pytest.raises(ValueError):
        score(trace, rubric)


def test_rubric_duplicate_id_and_unexpected_trace_field():
    trace, rubric = fixture_pair()
    rubric["checks"].append(copy.deepcopy(rubric["checks"][0]))
    with pytest.raises(ValueError):
        score(trace, rubric)
    trace, rubric = fixture_pair()
    trace["hidden_reasoning"] = "not an evaluation field"
    with pytest.raises(ValueError):
        score(trace, rubric)


def paired_reports():
    trace, rubric = fixture_pair()
    optional = copy.deepcopy(rubric["checks"][3])
    optional.update(id="quality", pointer="/output/quality", required=False)
    rubric["checks"].append(optional)
    base = copy.deepcopy(trace)
    base["output"]["quality"] = False
    return score(base, rubric), score(trace, rubric), rubric


def test_promotion_requires_gain_and_never_authorizes_learning():
    before, after, rubric = paired_reports()
    result = promotion_gate([before], [after], case_ids=[after["case_id"]],
                            rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST)
    assert result["decision"] == "eligible_for_review"
    assert result["mean_dimension_gain"] == pytest.approx(0.1)
    assert not result["authorizes_learning"] and not result["authorizes_release"]
    blocked = promotion_gate([after], [after], case_ids=[after["case_id"]],
                             rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST)
    assert blocked["decision"] == "blocked"


@pytest.mark.parametrize("gain", [0, -1, float("nan"), float("inf"), True, 1.01])
def test_invalid_reward_threshold(gain):
    before, after, rubric = paired_reports()
    with pytest.raises(ValueError):
        promotion_gate([before], [after], case_ids=[after["case_id"]], rubric_digest=digest(rubric),
                       scope_manifest_digest=SCOPE_DIGEST, minimum_gain=gain)


@pytest.mark.parametrize("rubric_digest", [None, "", "a" * 63, "A" * 64])
def test_promotion_requires_valid_pinned_rubric_digest(rubric_digest):
    before, after, _ = paired_reports()
    with pytest.raises(ValueError, match="rubric digest"):
        promotion_gate([before], [after], case_ids=[after["case_id"]],
                       rubric_digest=rubric_digest, scope_manifest_digest=SCOPE_DIGEST)


@pytest.mark.parametrize("scope_digest", [None, "", "a" * 63, "A" * 64])
def test_promotion_requires_valid_pinned_scope_digest(scope_digest):
    before, after, rubric = paired_reports()
    with pytest.raises(ValueError, match="scope manifest digest"):
        promotion_gate(
            [before], [after], case_ids=[after["case_id"]],
            rubric_digest=digest(rubric), scope_manifest_digest=scope_digest,
        )


@pytest.mark.parametrize("scope_count", [None, -1, True, 1.0, 4097])
def test_promotion_requires_valid_pinned_scope_count(scope_count):
    before, after, rubric = paired_reports()
    with pytest.raises(ValueError, match="scope manifest count"):
        _promotion_gate(
            [before], [after], case_ids=[after["case_id"]],
            rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST,
            expected_scope_count=scope_count,
        )


def test_promotion_rejects_matching_but_unpinned_report_scopes():
    before, after, rubric = paired_reports()
    unauthorized = {
        "manifest_digest": digest([]), "expected_count": 0,
        "observed_count": 0, "missing_count": 0, "complete": True,
    }
    before["scope"] = copy.deepcopy(unauthorized)
    after["scope"] = copy.deepcopy(unauthorized)
    with pytest.raises(ValueError, match="incomparable evidence"):
        promotion_gate(
            [before], [after], case_ids=[after["case_id"]],
            rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST,
        )


def test_promotion_rejects_correct_digest_with_wrong_scope_count():
    before, after, rubric = paired_reports()
    for report in (before, after):
        report["scope"].update(
            expected_count=0, observed_count=0, missing_count=0, complete=True,
        )
    with pytest.raises(ValueError, match="incomparable evidence"):
        promotion_gate(
            [before], [after], case_ids=[after["case_id"]],
            rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST,
        )


def test_report_consistency_accepts_equivalent_integer_scores():
    before, after, rubric = paired_reports()
    before["scores"] = {
        key: int(value) if value in (0.0, 1.0) else value
        for key, value in before["scores"].items()
    }
    result = promotion_gate(
        [before], [after], case_ids=[after["case_id"]],
        rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST,
    )
    assert result["decision"] == "eligible_for_review"


def test_promotion_rejects_missing_report_rubric_digest():
    before, after, rubric = paired_reports()
    before.pop("rubric_digest")
    after.pop("rubric_digest")
    with pytest.raises(ValueError):
        promotion_gate(
            [before], [after], case_ids=[after["case_id"]], rubric_digest=digest(rubric),
            scope_manifest_digest=SCOPE_DIGEST,
        )


@pytest.mark.parametrize("trace_digest", [None, "", "a" * 63, "A" * 64])
def test_promotion_requires_valid_report_trace_digest(trace_digest):
    before, after, rubric = paired_reports()
    if trace_digest is None:
        before.pop("trace_digest")
        after.pop("trace_digest")
    else:
        before["trace_digest"] = trace_digest
        after["trace_digest"] = trace_digest
    with pytest.raises(ValueError, match="immutable report identity"):
        promotion_gate(
            [before], [after], case_ids=[after["case_id"]], rubric_digest=digest(rubric),
            scope_manifest_digest=SCOPE_DIGEST,
        )


@pytest.mark.parametrize("ids", [[], ["missing"], ["read-only-1", "read-only-1"]])
def test_case_manifest_failures(ids):
    before, after, rubric = paired_reports()
    with pytest.raises(ValueError):
        promotion_gate([before], [after], case_ids=ids, rubric_digest=digest(rubric),
                       scope_manifest_digest=SCOPE_DIGEST)


@pytest.mark.parametrize("case_id", [None, 7, "", "case id", "case\n", "x" * 129])
def test_case_manifest_and_reports_require_token_identity(case_id):
    before, after, rubric = paired_reports()
    before["case_id"] = case_id
    after["case_id"] = case_id
    with pytest.raises(ValueError):
        promotion_gate([before], [after], case_ids=[case_id], rubric_digest=digest(rubric),
                       scope_manifest_digest=SCOPE_DIGEST)


def test_tampered_scores_do_not_enter_reward_gate():
    before, after, rubric = paired_reports()
    after["scores"]["policy"] = 0.9
    with pytest.raises(ValueError, match="inconsistent"):
        promotion_gate([before], [after], case_ids=[after["case_id"]],
                       rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST)


def test_same_trace_digest_cannot_claim_changed_evaluation_outcome():
    before, after, rubric = paired_reports()
    after["trace_digest"] = before["trace_digest"]
    with pytest.raises(ValueError, match="trace digest"):
        promotion_gate(
            [before], [after], case_ids=[after["case_id"]], rubric_digest=digest(rubric),
            scope_manifest_digest=SCOPE_DIGEST,
        )


def test_trace_digest_cannot_be_reused_across_held_out_cases():
    before, after, rubric = paired_reports()
    before2, after2, _ = paired_reports()
    before2["case_id"] = after2["case_id"] = "other-case"
    before2["trace_digest"] = before["trace_digest"]
    after2["trace_digest"] = after["trace_digest"]
    with pytest.raises(ValueError, match="reused across held-out cases"):
        promotion_gate(
            [before, before2], [after, after2],
            case_ids=[before["case_id"], "other-case"], rubric_digest=digest(rubric),
            scope_manifest_digest=SCOPE_DIGEST,
        )


def test_scope_report_cannot_be_tampered_for_promotion():
    before, after, rubric = paired_reports()
    after["scope"]["missing_count"] = 1
    with pytest.raises(ValueError, match="scope"):
        promotion_gate([before], [after], case_ids=[after["case_id"]],
                       rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST)


def test_candidate_required_failures_and_regression_cannot_hide():
    trace, rubric = fixture_pair()
    before = score(trace, rubric)
    trace["steps"][0]["arguments"]["mutate"] = True
    after = score(trace, rubric)
    result = promotion_gate([before], [after], case_ids=[after["case_id"]],
                            rubric_digest=digest(rubric), scope_manifest_digest=SCOPE_DIGEST)
    assert result["decision"] == "blocked"
    assert "per_case_dimension_regression" in result["reasons"]
    assert "candidate_required_check_failure" in result["reasons"]


@pytest.mark.parametrize("value", [1.0, True, "1160447354"])
def test_trace_repository_id_has_no_implicit_coercion(value):
    trace, rubric = fixture_pair()
    trace["repository_id"] = value
    with pytest.raises(ValueError):
        score(trace, rubric, expected_repository_id=1)


def test_duplicate_json_and_oversized_files(tmp_path):
    from organvm_engine.ci.agent_eval import MAX_JSON_BYTES, load_json
    path = tmp_path / "input.json"
    path.write_text('{"key":1,"key":2}')
    with pytest.raises(ValueError):
        load_json(path)
    path.write_text(" " * (MAX_JSON_BYTES + 1))
    with pytest.raises(ValueError):
        load_json(path)


def test_cli_generic_error_does_not_expose_source(tmp_path, capsys):
    trace, rubric = fixture_pair()
    trace["input"] = float("nan")
    tpath, rpath = tmp_path / "trace.json", tmp_path / "rubric.json"
    spath = tmp_path / "scope.json"
    tpath.write_text(json.dumps(trace))
    rpath.write_text(json.dumps(rubric))
    spath.write_text(json.dumps(["README.md"]))
    result = main([str(tpath), str(rpath), "--repository-id", str(REPO), "--revision", HEAD,
                   "--rubric-digest", digest(rubric), "--scope-manifest", str(spath),
                   "--scope-digest", digest(["README.md"])])
    assert result == 2
    assert "SYNTHETIC-PRIVATE" not in capsys.readouterr().out
