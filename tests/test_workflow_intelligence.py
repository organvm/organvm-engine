"""Static workflow counterexamples; no scripts in these fixtures are executed."""
import copy
import json

import pytest
import yaml

from organvm_engine.ci.workflow_intelligence import (
    MAX_BYTES, analyze_workflow, drift, inventory, main, proposals, review_metrics,
)

PATH = ".github/workflows/ci.yml"
HEAD = "a" * 40
WHEN = "2026-09-13T14:00:00Z"
PIN = "a" * 40
SAFE = f"""name: CI
on: [push, pull_request]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@{PIN}
      - run: pytest tests/
"""


def snapshot(text=SAFE, **kwargs):
    data = {"repository_id": 1160447354, "revision": HEAD, "files": {PATH: text},
            "expected_paths": [PATH], "observed_at": WHEN, "enumeration_complete": True, **kwargs}
    return inventory(**data)


def codes(text):
    return {f["code"] for f in analyze_workflow(text)["findings"]}


def test_safe_fixture_and_yaml_global_resolver_unchanged():
    before = yaml.safe_load("on: push")
    result = analyze_workflow(SAFE)
    assert result["triggers"] == ["pull_request", "push"]
    assert result["findings"] == []
    assert yaml.safe_load("on: push") == before
    assert snapshot()["coverage"] == "complete"
    assert not snapshot()["authorizes_release"]


@pytest.mark.parametrize("text, expected", [
    (SAFE.replace(f"@{PIN}", "@v7"), "mutable_action"),
    (SAFE.replace("permissions:\n  contents: read\n", ""), "permissions_unspecified"),
    (SAFE.replace("permissions:\n  contents: read", "permissions: write-all"), "write_all"),
    (SAFE.replace("    timeout-minutes: 10\n", ""), "timeout_unspecified"),
    (SAFE.replace("    runs-on:", "    continue-on-error: true\n    runs-on:"), "failure_tolerated"),
    (SAFE.replace("- run: pytest tests/", "- run: echo ${{ github.event.issue.title }}"), "untrusted_run_expression"),
])
def test_selected_antipatterns(text, expected):
    assert expected in codes(text)


def test_privileged_target_head_checkout():
    text = SAFE.replace("[push, pull_request]", "pull_request_target")
    text = text.replace("      - run:", "        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n      - run:")
    assert "privileged_head_checkout" in codes(text)


def test_untrusted_expression_in_env_is_not_shell_source():
    text = SAFE.replace("      - run: pytest tests/", "      - run: printf '%s' \"$TITLE\"\n        env:\n          TITLE: ${{ github.event.issue.title }}")
    assert "untrusted_run_expression" not in codes(text)


def test_local_actions_and_digest_containers_do_not_require_commit_pin():
    assert "mutable_action" not in codes(SAFE.replace(f"actions/checkout@{PIN}", "./.github/actions/check"))
    container = "docker://example/image@sha256:" + "b" * 64
    assert "mutable_action" not in codes(SAFE.replace(f"actions/checkout@{PIN}", container))


def test_reusable_jobs_remain_unresolved_even_with_pin():
    text = f"on: workflow_dispatch\npermissions: read-all\njobs:\n  call:\n    uses: owner/repo/.github/workflows/ci.yml@{PIN}\n"
    result = analyze_workflow(text)
    assert result["transitive_coverage"] == "unresolved"
    assert "timeout_unspecified" not in codes(text)
    assert "reusable_workflow_unresolved" in codes(text)


@pytest.mark.parametrize("text", [
    "on: push\non: pull_request\njobs: {}", "on: push\njobs: {}", "jobs: {}", "[not, workflow]",
    SAFE.replace("    steps:", "    steps: &steps" ) + "extra: *steps\n",
    SAFE.replace("- run: pytest tests/", "- run: pytest\n        uses: owner/repo@main"),
    SAFE.replace("    timeout-minutes: 10", "    timeout-minutes: false"),
    SAFE.replace("    timeout-minutes: 10", "    timeout-minutes: -1"),
    SAFE.replace("- run: pytest tests/", "- run: [pytest]"),
    SAFE.replace("    steps:", "    uses: owner/repo@main\n    steps:"),
    "on: push\njobs: !unsafe anything", "on: [false]\njobs: {test: {}}",
    SAFE + "data: .nan\n", SAFE + "date: 2026-09-13\n",
])
def test_invalid_or_unsupported_input_never_passes(text):
    with pytest.raises(ValueError):
        analyze_workflow(text)
    result = snapshot(text)
    assert result["coverage"] == "partial"
    assert result["workflows"][PATH]["status"] == "invalid_or_unsupported"


def test_size_and_depth_budgets():
    with pytest.raises(ValueError):
        analyze_workflow("#" * (MAX_BYTES + 1))
    with pytest.raises(ValueError):
        analyze_workflow("extra: " + "[" * 65 + "0" + "]" * 65 + "\n" + SAFE)


@pytest.mark.parametrize("path", ["../ci.yml", ".github/workflows/../ci.yml", ".github/workflows/a/ci.yml",
                                  ".github/workflows//ci.yml", ".github/workflows/ci.txt",
                                  "/.github/workflows/ci.yml", ".github/workflows/ci\\x.yml"])
def test_inventory_path_boundaries(path):
    with pytest.raises(ValueError):
        snapshot(files={path: SAFE}, expected_paths=[path])


@pytest.mark.parametrize("identity", [True, 0, -1, "123", 1.0])
def test_repository_ids_are_stable_integer_ids(identity):
    with pytest.raises(ValueError):
        snapshot(repository_id=identity)


@pytest.mark.parametrize("revision", ["main", "shortsha", "A" * 40, "g" * 40])
def test_mutable_or_invalid_revisions_rejected(revision):
    with pytest.raises(ValueError):
        snapshot(revision=revision)


def test_missing_files_are_coverage_not_success_or_deletion():
    current = snapshot(files={})
    assert current["coverage"] == "partial"
    assert current["analyzed_count"] == 0
    assert current["workflows"][PATH]["status"] == "unavailable"
    assert drift(snapshot(), current)["changes"] == [{"path": PATH, "kind": "unavailable_comparison"}]


def test_expected_paths_are_independent_and_unique():
    with pytest.raises(ValueError):
        snapshot(expected_paths=[])
    with pytest.raises(ValueError):
        snapshot(expected_paths=[PATH, PATH])


def test_drift_separates_representation_from_declarations():
    original = snapshot()
    comment_only = snapshot(SAFE + "# comment\n", revision="b" * 40)
    assert drift(original, comment_only)["changes"][0]["kind"] == "representation_only"
    changed = snapshot(SAFE.replace("contents: read", "contents: write"), revision="c" * 40)
    assert drift(original, changed)["changes"][0]["kind"] == "declaration_changed"
    assert drift(original, original)["changes"] == []
    empty = snapshot(files={}, expected_paths=[], revision="d" * 40)
    assert drift(original, empty)["changes"][0]["kind"] == "removed_from_enumeration"
    assert drift(empty, original)["changes"][0]["kind"] == "added"


def test_drift_rejects_identity_and_time_mismatch():
    with pytest.raises(ValueError):
        drift(snapshot(), snapshot(repository_id=42))
    with pytest.raises(ValueError):
        drift(snapshot(), snapshot(observed_at="2026-09-12T14:00:00Z"))
    with pytest.raises(ValueError):
        snapshot(observed_at="2026-09-13T14:00:00")


def test_remediations_bound_to_source_and_human_gate():
    current = snapshot(SAFE.replace(f"@{PIN}", "@v7"))
    result = proposals(current, owner_refs=[], criticality=5, downstream_count=20)
    assert result[0]["revision"] == HEAD
    assert result[0]["source_digest"] == current["workflows"][PATH]["source_digest"]
    assert result[0]["owner_status"] == "unresolved"
    assert result[0]["requires_human_approval"] is True
    assert result[0]["authorizes_mutation"] is False
    assert result[0]["risk_vector"] == [2, 5, 20]


def test_review_metrics_no_quality_claim_and_pending_not_zero_latency():
    data = [{"id": 1, "requested_at": "2026-09-13T12:00:00Z", "first_review_at": "2026-09-13T13:00:00Z",
             "reviewer_ids": ["one", "one"], "changes_requested": 2},
            {"id": 2, "requested_at": "2026-09-13T12:00:00Z"}]
    result = review_metrics(data, observed_at=WHEN)
    assert result["median_first_review_seconds"] == 3600
    assert result["oldest_pending_seconds"] == 7200
    assert result["reviewer_participations"] == 1
    assert result["changes_requested"] == 2
    assert result["quality_inference"] == "not_measured"
    assert review_metrics([], observed_at=WHEN)["median_first_review_seconds"] is None


def test_review_metrics_reject_duplicate_and_bad_chronology():
    record = {"id": 1, "requested_at": "2026-09-13T12:00:00Z"}
    with pytest.raises(ValueError):
        review_metrics([record, copy.deepcopy(record)], observed_at=WHEN)
    with pytest.raises(ValueError):
        review_metrics([{**record, "first_review_at": "2026-09-13T11:00:00Z"}], observed_at=WHEN)


def test_cli_retrieval_coverage_exit_codes(tmp_path, capsys):
    source = tmp_path / "inventory.json"
    data = {"repository_id": 1, "revision": HEAD, "files": {}, "expected_paths": [PATH], "observed_at": WHEN}
    source.write_text(json.dumps(data))
    assert main([str(source)]) == 1
    assert json.loads(capsys.readouterr().out)["coverage"] == "partial"
    source.write_text('{"bad": "SYNTHETIC-PRIVATE"}')
    assert main([str(source)]) == 2
    assert "SYNTHETIC-PRIVATE" not in capsys.readouterr().out


@pytest.mark.parametrize("value", ["garbage", "true", "[]", "{contents: admin}"])
def test_invalid_permissions_are_not_clean(value):
    text = SAFE.replace("permissions:\n  contents: read", "permissions: " + value)
    with pytest.raises(ValueError):
        analyze_workflow(text)


@pytest.mark.parametrize("value", ["[]", "{}", "hello"])
def test_invalid_timeout_types(value):
    with pytest.raises(ValueError):
        analyze_workflow(SAFE.replace("timeout-minutes: 10", "timeout-minutes: " + value))
