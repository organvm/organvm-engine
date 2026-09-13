"""Synthetic deterministic contract tests; no model calls or live mutations."""
import copy
import json

import pytest

from organvm_engine.ci.agent_eval import DIMENSIONS, VERSION, digest, evaluate_trace, main, promotion_gate

HEAD = "a" * 40
REPO = 1160447354


def fixture_pair():
    step = {"id": "read", "tool": "read_file", "depends_on": [],
            "arguments": {"path": "README.md", "mutate": False},
            "observation": {"content": "SYNTHETIC-PRIVATE-CONTENT"},
            "state_before": {"phase": "new"}, "state_after": {"phase": "observed"},
            "status": "succeeded"}
    trace = {"schema_version": VERSION, "case_id": "read-only-1", "repository_id": REPO,
             "revision": HEAD, "outcome": "completed", "input": "SYNTHETIC-PRIVATE-PROMPT",
             "output": {"done": True, "quality": True}, "steps": [step]}
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
              "expected_rubric_digest": digest(rubric), **overrides}
    return evaluate_trace(trace, rubric, **kwargs)


def test_full_trace_scores_separately_and_does_not_authorize():
    result = score()
    assert result["decision"] == "pass"
    assert result["scores"] == dict.fromkeys(DIMENSIONS, 1.0)
    assert not result["authorizes_release"] and not result["authorizes_execution"]
    serialized = json.dumps(result)
    assert "SYNTHETIC-PRIVATE" not in serialized
    assert "arguments" not in result and "output" not in result


@pytest.mark.parametrize("key,value", [("expected_revision", "b" * 40),
                                       ("expected_repository_id", 12),
                                       ("expected_repository_id", True),
                                       ("expected_rubric_digest", "0" * 64)])
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
        promotion_gate([result], [result], case_ids=[result["case_id"]], rubric_digest=digest(rubric))


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
    result = promotion_gate([before], [after], case_ids=[after["case_id"]], rubric_digest=digest(rubric))
    assert result["decision"] == "eligible_for_review"
    assert result["mean_dimension_gain"] == pytest.approx(0.1)
    assert not result["authorizes_learning"] and not result["authorizes_release"]
    blocked = promotion_gate([after], [after], case_ids=[after["case_id"]], rubric_digest=digest(rubric))
    assert blocked["decision"] == "blocked"


@pytest.mark.parametrize("gain", [0, -1, float("nan"), float("inf"), True, 1.01])
def test_invalid_reward_threshold(gain):
    before, after, rubric = paired_reports()
    with pytest.raises(ValueError):
        promotion_gate([before], [after], case_ids=[after["case_id"]], rubric_digest=digest(rubric),
                       minimum_gain=gain)


@pytest.mark.parametrize("ids", [[], ["missing"], ["read-only-1", "read-only-1"]])
def test_case_manifest_failures(ids):
    before, after, rubric = paired_reports()
    with pytest.raises(ValueError):
        promotion_gate([before], [after], case_ids=ids, rubric_digest=digest(rubric))


def test_tampered_scores_do_not_enter_reward_gate():
    before, after, rubric = paired_reports()
    after["scores"]["policy"] = 0.9
    with pytest.raises(ValueError, match="inconsistent"):
        promotion_gate([before], [after], case_ids=[after["case_id"]], rubric_digest=digest(rubric))


def test_candidate_required_failures_and_regression_cannot_hide():
    trace, rubric = fixture_pair()
    before = score(trace, rubric)
    trace["steps"][0]["arguments"]["mutate"] = True
    after = score(trace, rubric)
    result = promotion_gate([before], [after], case_ids=[after["case_id"]], rubric_digest=digest(rubric))
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
    tpath.write_text(json.dumps(trace))
    rpath.write_text(json.dumps(rubric))
    result = main([str(tpath), str(rpath), "--repository-id", str(REPO), "--revision", HEAD,
                   "--rubric-digest", digest(rubric)])
    assert result == 2
    assert "SYNTHETIC-PRIVATE" not in capsys.readouterr().out
