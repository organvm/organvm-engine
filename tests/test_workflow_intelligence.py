"""Static workflow counterexamples; no scripts in these fixtures are executed."""
import copy
import json

import pytest
import yaml

from organvm_engine.ci.workflow_intelligence import (
    MAX_BYTES,
    analyze_workflow,
    drift,
    inventory,
    main,
    proposals,
    review_metrics,
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


def test_push_commit_message_is_untrusted_shell_source():
    text = SAFE.replace("pytest tests/", "echo ${{ github.event.head_commit.message }}")
    assert "untrusted_run_expression" in codes(text)


@pytest.mark.parametrize("field", ["title", "body"])
def test_discussion_text_is_untrusted_shell_source(field):
    text = SAFE.replace("pytest tests/", f"echo ${{{{ github.event.discussion.{field} }}}}")
    assert "untrusted_run_expression" in codes(text)


@pytest.mark.parametrize("field", ["author.name", "author.email", "committer.name"])
def test_push_commit_identity_metadata_is_untrusted_shell_source(field):
    text = SAFE.replace("pytest tests/", f"echo ${{{{ github.event.head_commit.{field} }}}}")
    assert "untrusted_run_expression" in codes(text)


def test_push_commit_array_message_is_untrusted_shell_source():
    text = SAFE.replace("pytest tests/", "echo ${{ github.event.commits[0].message }}")
    assert "untrusted_run_expression" in codes(text)


@pytest.mark.parametrize("field", ["message", "author.name", "committer.email"])
def test_push_commit_array_wildcard_metadata_is_untrusted_shell_source(field):
    text = SAFE.replace(
        "pytest tests/",
        f"echo ${{{{ join(github.event.commits.*.{field}, ' ') }}}}",
    )
    assert "untrusted_run_expression" in codes(text)


def test_context_shaped_text_inside_expression_literal_is_not_untrusted():
    text = SAFE.replace("pytest tests/", "echo ${{ 'github.event.issue.title' }}")
    assert "untrusted_run_expression" not in codes(text)


@pytest.mark.parametrize("property_name", ["action", "pull_request.number"])
def test_safe_event_properties_are_not_whole_event_shell_sources(property_name):
    text = SAFE.replace("pytest tests/", f"echo ${{{{ github.event.{property_name} }}}}")
    assert "untrusted_run_expression" not in codes(text)


def test_snapshot_rejects_noncanonical_finding_severity():
    current = snapshot(SAFE.replace(f"@{PIN}", "@v7"))
    current["workflows"][PATH]["findings"][0]["severity"] = "info"
    with pytest.raises(ValueError, match="invalid finding"):
        proposals(current, owner_refs=[])


def test_snapshot_rejects_duplicate_findings():
    current = snapshot(SAFE.replace(f"@{PIN}", "@v7"))
    current["workflows"][PATH]["findings"] *= 2
    with pytest.raises(ValueError, match="duplicate finding"):
        proposals(current, owner_refs=[])


def test_privileged_target_head_checkout():
    text = SAFE.replace("[push, pull_request]", "pull_request_target")
    text = text.replace("      - run:", "        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n      - run:")
    assert "privileged_head_checkout" in codes(text)


def test_privileged_target_ignores_head_context_inside_expression_literal():
    text = SAFE.replace("[push, pull_request]", "pull_request_target")
    text = text.replace(
        "      - run:",
        "        with:\n          ref: ${{ 'github.event.pull_request.head.sha' }}\n      - run:",
    )
    assert "privileged_head_checkout" not in codes(text)


@pytest.mark.parametrize("expression", [
    "${{ github.event['pull_request'].head.sha }}",
    '${{ github.event["pull_request"].head.repo.full_name }}',
])
def test_privileged_target_bracket_notation_head_checkout(expression):
    text = SAFE.replace("[push, pull_request]", "pull_request_target")
    text = text.replace("      - run:", f"        with:\n          ref: {expression}\n      - run:")
    assert "privileged_head_checkout" in codes(text)


def test_privileged_target_synthetic_pull_ref_is_detected():
    text = SAFE.replace("[push, pull_request]", "pull_request_target")
    text = text.replace(
        "      - run:",
        "        with:\n          ref: refs/pull/${{ github.event.pull_request.number }}/head\n      - run:",
    )
    assert "privileged_head_checkout" in codes(text)


def test_privileged_target_top_level_event_number_synthetic_ref_is_detected():
    text = SAFE.replace("[push, pull_request]", "pull_request_target")
    text = text.replace(
        "      - run:",
        "        with:\n          ref: refs/pull/${{ github.event.number }}/head\n      - run:",
    )
    assert "privileged_head_checkout" in codes(text)


def test_privileged_target_format_built_synthetic_ref_is_detected():
    text = SAFE.replace("[push, pull_request]", "pull_request_target")
    text = text.replace(
        "      - run:",
        "        with:\n          ref: ${{ format('refs/pull/{0}/head', github.event.number) }}\n"
        "      - run:",
    )
    assert "privileged_head_checkout" in codes(text)


def test_privileged_target_format_ref_uses_numbered_argument_position():
    text = SAFE.replace("[push, pull_request]", "pull_request_target")
    text = text.replace(
        "      - run:",
        "        with:\n"
        "          ref: ${{ format('refs/pull/{0}/head', 'main', github.event.number) }}\n"
        "      - run:",
    )
    assert "privileged_head_checkout" not in codes(text)


def test_privileged_target_multi_placeholder_format_ref_is_detected():
    text = SAFE.replace("[push, pull_request]", "pull_request_target")
    text = text.replace(
        "      - run:",
        "        with:\n"
        "          ref: ${{ format('refs/pull/{0}/{1}', github.event.number, 'head') }}\n"
        "      - run:",
    )
    assert "privileged_head_checkout" in codes(text)


def test_privileged_target_format_ref_matches_placeholder_positions():
    text = SAFE.replace("[push, pull_request]", "pull_request_target")
    text = text.replace(
        "      - run:",
        "        with:\n"
        "          ref: ${{ format('refs/pull/{0}/{1}', 'head', github.event.number) }}\n"
        "      - run:",
    )
    assert "privileged_head_checkout" not in codes(text)


def test_privileged_target_github_head_ref_is_detected():
    text = SAFE.replace("[push, pull_request]", "pull_request_target")
    text = text.replace(
        "      - run:",
        "        with:\n          ref: ${{ github.head_ref }}\n      - run:",
    )
    assert "privileged_head_checkout" in codes(text)


def test_privileged_target_ignores_head_context_in_non_selector_input():
    text = SAFE.replace("[push, pull_request]", "pull_request_target")
    text = text.replace(
        "      - run:",
        "        with:\n"
        "          path: ${{ github.event.pull_request.head.ref }}\n"
        "      - run:",
    )
    assert "privileged_head_checkout" not in codes(text)


@pytest.mark.parametrize("expression", [
    "${{ github.event.pull_request.merge_commit_sha }}",
    "refs/pull/${{ github.event.pull_request.number }}/merge",
    "refs/pull/123/merge",
])
def test_privileged_target_merge_checkout_is_detected(expression):
    text = SAFE.replace("[push, pull_request]", "pull_request_target")
    text = text.replace("      - run:", f"        with:\n          ref: {expression}\n      - run:")
    assert "privileged_head_checkout" in codes(text)


def test_privileged_workflow_run_head_checkout_is_detected():
    text = SAFE.replace("on: [push, pull_request]", "on: workflow_run")
    text = text.replace(
        "      - run:",
        "        with:\n"
        "          ref: ${{ github.event.workflow_run.head_sha }}\n"
        "          repository: ${{ github.event.workflow_run.head_repository.full_name }}\n"
        "      - run:",
    )
    assert "privileged_head_checkout" in codes(text)


@pytest.mark.parametrize("missing", ["ref", "repository"])
def test_workflow_run_checkout_requires_both_untrusted_head_selectors(missing):
    settings = {
        "ref": "${{ github.event.workflow_run.head_sha }}",
        "repository": "${{ github.event.workflow_run.head_repository.full_name }}",
    }
    settings.pop(missing)
    rendered = "".join(f"          {key}: {value}\n" for key, value in settings.items())
    text = SAFE.replace("on: [push, pull_request]", "on: workflow_run")
    text = text.replace("      - run:", f"        with:\n{rendered}      - run:")
    assert "privileged_head_checkout" not in codes(text)


def test_untrusted_expression_in_env_is_not_shell_source():
    text = SAFE.replace("      - run: pytest tests/", "      - run: printf '%s' \"$TITLE\"\n        env:\n          TITLE: ${{ github.event.issue.title }}")
    assert "untrusted_run_expression" not in codes(text)


@pytest.mark.parametrize("expression", [
    "${{ github.event.pull_request['head']['sha'] }}",
    '${{ github.event["pull_request"]["head"]["repo"]["full_name"] }}',
])
def test_privileged_checkout_normalizes_every_bracket_segment(expression):
    text = SAFE.replace("on: [push, pull_request]", "on: pull_request_target")
    text = text.replace("      - run:", f"        with:\n          ref: {expression}\n      - run:")
    assert "privileged_head_checkout" in codes(text)


def test_untrusted_run_normalizes_every_bracket_segment():
    text = SAFE.replace("pytest tests/", "printf '%s' ${{ github.event['issue']['title'] }}")
    assert "untrusted_run_expression" in codes(text)


def test_whole_event_serialization_is_untrusted_shell_source():
    text = SAFE.replace("pytest tests/", "echo '${{ toJSON(github.event) }}'")
    assert "untrusted_run_expression" in codes(text)


def test_untrusted_run_parses_braces_inside_expression_string():
    text = SAFE.replace(
        "pytest tests/",
        "echo ${{ format('{0}', github.event.issue.title) }}",
    )
    assert "untrusted_run_expression" in codes(text)


def test_untrusted_run_parses_closing_delimiter_inside_expression_string():
    text = SAFE.replace(
        "pytest tests/",
        "echo ${{ format('}} {0}', github.event.issue.title) }}",
    )
    assert "untrusted_run_expression" in codes(text)


def test_untrusted_run_does_not_treat_backslash_as_expression_quote_escape():
    text = SAFE.replace(
        "pytest tests/",
        "echo ${{ format('{0}\\', github.event.issue.title) }}",
    )
    assert "untrusted_run_expression" in codes(text)


def test_head_ref_is_untrusted_generated_shell_source():
    assert "untrusted_run_expression" in codes(
        SAFE.replace("pytest tests/", "printf '%s' ${{ github.head_ref }}"),
    )


def test_local_actions_and_digest_containers_do_not_require_commit_pin():
    assert "mutable_action" not in codes(SAFE.replace(f"actions/checkout@{PIN}", "./.github/actions/check"))
    container = "docker://example/image@sha256:" + "b" * 64
    assert "mutable_action" not in codes(SAFE.replace(f"actions/checkout@{PIN}", container))


@pytest.mark.parametrize("reference", ["$/actions/check", "$/nested/action"])
def test_same_repository_dollar_actions_do_not_require_commit_pin(reference):
    assert "mutable_action" not in codes(SAFE.replace(f"actions/checkout@{PIN}", reference))


@pytest.mark.parametrize("reference", ["$/", "$/actions/check@main"])
def test_malformed_or_suffixed_dollar_actions_still_require_pin(reference):
    assert "mutable_action" in codes(SAFE.replace(f"actions/checkout@{PIN}", reference))


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


@pytest.mark.parametrize("content", [None, [], {}])
def test_inventory_rejects_non_string_workflow_contents(content):
    with pytest.raises(ValueError, match="workflow contents must be strings"):
        snapshot(files={PATH: content})


def test_inventory_rejects_non_mapping_files_before_iteration():
    with pytest.raises(ValueError, match="files mapping required"):
        snapshot(files=[])


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
    current = snapshot(files={}, revision="b" * 40)
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


def test_trigger_order_only_change_is_representation_only():
    reordered = snapshot(
        SAFE.replace("on: [push, pull_request]", "on: [pull_request, push]"),
        revision="b" * 40,
    )
    assert drift(snapshot(), reordered)["changes"][0]["kind"] == "representation_only"


def test_nested_trigger_type_order_change_is_representation_only():
    original = SAFE.replace(
        "on: [push, pull_request]",
        "on:\n  pull_request:\n    types: [opened, synchronize]",
    )
    reordered = original.replace(
        "types: [opened, synchronize]", "types: [synchronize, opened]",
    )
    assert drift(
        snapshot(original), snapshot(reordered, revision="b" * 40),
    )["changes"][0]["kind"] == "representation_only"


def test_drift_rejects_identity_and_time_mismatch():
    with pytest.raises(ValueError):
        drift(snapshot(), snapshot(repository_id=42))
    with pytest.raises(ValueError):
        drift(snapshot(), snapshot(observed_at="2026-09-12T14:00:00Z"))
    with pytest.raises(ValueError):
        snapshot(observed_at="2026-09-13T14:00:00")


def test_same_revision_allows_retrieval_state_recovery():
    unavailable = snapshot(files={})
    result = drift(unavailable, snapshot())
    assert result["changes"] == [{"path": PATH, "kind": "unavailable_comparison"}]


def test_same_revision_rejects_digest_change_across_analysis_status():
    invalid = snapshot("on: push\njobs: !unsafe anything")
    assert invalid["workflows"][PATH]["status"] == "invalid_or_unsupported"
    with pytest.raises(ValueError, match="content changed at unchanged revision"):
        drift(snapshot(), invalid)


def test_same_source_rejects_conflicting_analysis_status():
    previous = snapshot(revision="b" * 40)
    current = copy.deepcopy(previous)
    current["workflows"][PATH]["status"] = "invalid_or_unsupported"
    current["workflows"][PATH].pop("normalized_digest")
    current["workflows"][PATH].pop("job_count")
    current["workflows"][PATH].pop("triggers")
    current["workflows"][PATH].pop("transitive_coverage")
    current["workflows"][PATH].pop("reusable_references")
    current["workflows"][PATH]["findings"] = []
    current["analyzed_count"] = 0
    current["coverage"] = "partial"
    with pytest.raises(ValueError, match="inconsistent analysis status"):
        drift(previous, current)


@pytest.mark.parametrize(("field", "value"), [
    ("job_count", "1"),
    ("triggers", "push"),
    ("transitive_coverage", "complete"),
    ("reusable_references", "owner/repo/.github/workflows/ci.yml@main"),
])
def test_drift_rejects_malformed_analyzed_metadata(field, value):
    current = snapshot(revision="b" * 40)
    current["workflows"][PATH][field] = value
    with pytest.raises(ValueError, match="invalid analysis metadata"):
        drift(snapshot(), current)


def test_same_revision_rejects_conflicting_complete_enumeration():
    previous = snapshot()
    current = snapshot(
        files={".github/workflows/other.yml": SAFE},
        expected_paths=[".github/workflows/other.yml"],
    )
    with pytest.raises(ValueError, match="conflicting complete enumeration"):
        drift(previous, current)


def test_same_revision_rejects_extra_path_against_either_complete_enumeration():
    extra_path = ".github/workflows/other.yml"
    complete = snapshot()
    partial_with_extra = snapshot(
        files={PATH: SAFE, extra_path: SAFE},
        expected_paths=[PATH, extra_path],
        enumeration_complete=False,
    )
    with pytest.raises(ValueError, match="conflicting complete enumeration"):
        drift(complete, partial_with_extra)
    with pytest.raises(ValueError, match="conflicting complete enumeration"):
        drift(partial_with_extra, complete)


def test_same_revision_allows_partial_enumeration_to_omit_complete_paths():
    extra_path = ".github/workflows/other.yml"
    complete = snapshot(files={PATH: SAFE, extra_path: SAFE}, expected_paths=[PATH, extra_path])
    partial = snapshot(enumeration_complete=False)
    drift(complete, partial)
    drift(partial, complete)


def test_identical_source_rejects_conflicting_normalization():
    previous = snapshot(revision="b" * 40)
    current = snapshot()
    current["workflows"][PATH]["normalized_digest"] = "b" * 64
    with pytest.raises(ValueError, match="inconsistent analysis"):
        drift(previous, current)


def test_identical_source_rejects_conflicting_findings():
    previous = snapshot(revision="b" * 40)
    current = snapshot()
    current["workflows"][PATH]["findings"] = [
        analyze_workflow(SAFE.replace(f"@{PIN}", "@main"))["findings"][0],
    ]
    with pytest.raises(ValueError, match="inconsistent analysis"):
        drift(previous, current)


def test_remediations_bound_to_source_and_human_gate():
    current = snapshot(SAFE.replace(f"@{PIN}", "@v7"))
    result = proposals(current, owner_refs=[], criticality=5, downstream_count=20)
    assert result[0]["revision"] == HEAD
    assert result[0]["source_digest"] == current["workflows"][PATH]["source_digest"]
    assert result[0]["owner_status"] == "unresolved"
    assert result[0]["requires_human_approval"] is True
    assert result[0]["authorizes_mutation"] is False
    assert result[0]["risk_vector"] == [2, 5, 20]


def test_proposals_reject_invalid_snapshot_before_binding_source():
    current = snapshot(SAFE.replace(f"@{PIN}", "@v7"))
    current["revision"] = "main"
    with pytest.raises(ValueError, match="snapshot"):
        proposals(current, owner_refs=[])

    current = snapshot(SAFE.replace(f"@{PIN}", "@v7"))
    current["workflows"][PATH]["status"] = "unavailable"
    current["analyzed_count"] = 0
    current["coverage"] = "partial"
    with pytest.raises(ValueError, match="findings require analyzed source"):
        proposals(current, owner_refs=[])

    current = snapshot(SAFE.replace(f"@{PIN}", "@v7"))
    current["workflows"][PATH]["findings"][0]["repository_id"] = 99
    with pytest.raises(ValueError, match="invalid finding"):
        proposals(current, owner_refs=[])


@pytest.mark.parametrize("owners", ["team-a", 7, [""], ["team a"], [1]])
def test_proposals_reject_invalid_owner_reference_collections(owners):
    with pytest.raises(ValueError, match="owner references"):
        proposals(snapshot(SAFE.replace(f"@{PIN}", "@v7")), owner_refs=owners)


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


def test_pending_reviewers_are_not_observed_participants():
    result = review_metrics(
        [{"id": 1, "requested_at": "2026-09-13T12:00:00Z", "reviewer_ids": ["alice"]}],
        observed_at=WHEN,
    )
    assert result["reviewer_participations"] == 0
    assert result["largest_reviewer_share"] is None


def test_review_metrics_reject_duplicate_and_bad_chronology():
    record = {"id": 1, "requested_at": "2026-09-13T12:00:00Z"}
    with pytest.raises(ValueError):
        review_metrics([record, copy.deepcopy(record)], observed_at=WHEN)
    with pytest.raises(ValueError):
        review_metrics([{**record, "first_review_at": "2026-09-13T11:00:00Z"}], observed_at=WHEN)


@pytest.mark.parametrize("identity", [None, True, 0, -1, "1", 1.0])
def test_review_metrics_requires_positive_integer_identity(identity):
    with pytest.raises(ValueError, match="invalid identity"):
        review_metrics(
            [{"id": identity, "requested_at": "2026-09-13T12:00:00Z"}],
            observed_at=WHEN,
        )


@pytest.mark.parametrize("value", [0, ""])
def test_review_metrics_reject_present_invalid_review_timestamp(value):
    with pytest.raises(ValueError):
        review_metrics(
            [{"id": 1, "requested_at": "2026-09-13T12:00:00Z", "first_review_at": value}],
            observed_at=WHEN,
        )


def test_review_metrics_reject_rework_without_review_timestamp():
    with pytest.raises(ValueError, match="rework requires"):
        review_metrics(
            [{"id": 1, "requested_at": "2026-09-13T12:00:00Z", "changes_requested": 1}],
            observed_at=WHEN,
        )


@pytest.mark.parametrize("reviewer_ids", ["alice", 7, [""], ["alice/ops"], [1]])
def test_review_metrics_reject_invalid_reviewer_identity_collections(reviewer_ids):
    record = {"id": 1, "requested_at": "2026-09-13T12:00:00Z",
              "reviewer_ids": reviewer_ids}
    with pytest.raises(ValueError, match="reviewer identities"):
        review_metrics([record], observed_at=WHEN)


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
