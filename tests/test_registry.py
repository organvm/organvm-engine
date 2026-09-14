"""Tests for the registry module."""

import json

import pytest

from organvm_engine.registry.loader import load_registry, save_registry
from organvm_engine.registry.query import (
    all_repos,
    build_dependency_maps,
    find_missing_dependency_targets,
    find_repo,
    get_repo_dependencies,
    get_repo_dependents,
    list_repos,
    resolve_organ_key,
    search_repos,
    sort_repo_results,
    summarize_registry,
)
from organvm_engine.registry.updater import update_repo
from organvm_engine.registry.validator import validate_registry


class TestLoader:
    def test_load_returns_dict(self, registry):
        assert isinstance(registry, dict)
        assert registry["version"] == "2.0"

    def test_load_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_registry("/nonexistent/path.json")

    @pytest.mark.parametrize(
        "payload,match",
        [
            ({"_redirect": "elsewhere"}, "compatibility redirect"),
            ({"organs": {}}, "non-empty organs"),
            ({"organs": {"ORGAN-I": {"repositories": []}}}, "zero repositories"),
        ],
    )
    def test_load_rejects_noncanonical_payloads(self, tmp_path, payload, match):
        path = tmp_path / "registry.json"
        path.write_text(json.dumps(payload))
        with pytest.raises(ValueError, match=match):
            load_registry(path)

    def test_save_to_explicit_path(self, registry, tmp_path):
        out = tmp_path / "out.json"
        save_registry(registry, out)
        reloaded = load_registry(out)
        assert reloaded["version"] == "2.0"

    def test_save_refuses_small_registry_to_production_path(self):
        """Guard against test fixture data overwriting production registry."""
        tiny = {
            "version": "2.0",
            "organs": {"ORGAN-I": {"name": "Theory", "repositories": [{"name": "repo-a"}]}},
        }
        with pytest.raises(ValueError, match="Refusing to write registry with only 1 repos"):
            save_registry(tiny)

    def test_save_allows_small_registry_to_explicit_path(self, tmp_path):
        """Small registries are fine when writing to an explicit non-production path."""
        tiny = {
            "version": "2.0",
            "organs": {"ORGAN-I": {"name": "Theory", "repositories": [{"name": "repo-a"}]}},
        }
        out = tmp_path / "test-registry.json"
        save_registry(tiny, out)
        assert out.exists()


class TestQuery:
    def test_find_repo_exists(self, registry):
        result = find_repo(registry, "recursive-engine")
        assert result is not None
        organ_key, repo = result
        assert organ_key == "ORGAN-I"
        assert repo["name"] == "recursive-engine"

    def test_find_repo_missing(self, registry):
        assert find_repo(registry, "nonexistent") is None

    def test_all_repos_yields_all(self, registry):
        repos = list(all_repos(registry))
        assert len(repos) == 6

    def test_list_repos_by_organ(self, registry):
        results = list_repos(registry, organ="ORGAN-I")
        assert len(results) == 2
        assert all(ok == "ORGAN-I" for ok, _ in results)

    def test_list_repos_by_organ_meta(self, registry):
        """META alias resolves to META-ORGANVM registry key."""
        results = list_repos(registry, organ="META")
        assert len(results) == 2
        assert all(ok == "META-ORGANVM" for ok, _ in results)

    def test_list_repos_by_organ_meta_full_key(self, registry):
        """Full registry key META-ORGANVM also works."""
        results = list_repos(registry, organ="META-ORGANVM")
        assert len(results) == 2

    def test_list_repos_by_organ_shorthand(self, registry):
        """Shorthand 'I' resolves to 'ORGAN-I'."""
        results = list_repos(registry, organ="I")
        assert len(results) == 2
        assert all(ok == "ORGAN-I" for ok, _ in results)

    def test_list_repos_by_tier(self, registry):
        flagships = list_repos(registry, tier="flagship")
        assert len(flagships) == 4

    def test_list_repos_public_only(self, registry):
        public = list_repos(registry, public_only=True)
        assert len(public) == 6  # all are public in fixture

    def test_list_repos_by_promotion_status(self, registry):
        public_process = list_repos(registry, promotion_status="PUBLIC_PROCESS")
        assert len(public_process) == 3
        assert all(r.get("promotion_status") == "PUBLIC_PROCESS" for _, r in public_process)

    def test_list_repos_by_promotion_status_local(self, registry):
        local = list_repos(registry, promotion_status="LOCAL")
        assert len(local) == 3
        assert all(r.get("promotion_status") == "LOCAL" for _, r in local)

    def test_list_repos_name_contains(self, registry):
        results = list_repos(registry, name_contains="framework")
        assert len(results) == 1
        assert results[0][1]["name"] == "ontological-framework"

    def test_list_repos_depends_on(self, registry):
        results = list_repos(registry, depends_on="recursive-engine")
        names = sorted(repo["name"] for _, repo in results)
        assert names == ["metasystem-master", "ontological-framework"]

    def test_list_repos_dependency_of(self, registry):
        results = list_repos(registry, dependency_of="ontological-framework")
        assert len(results) == 1
        assert results[0][1]["name"] == "recursive-engine"

    def test_list_repos_platinum_only(self, registry):
        results = list_repos(registry, platinum_only=True)
        assert len(results) == 1
        assert results[0][1]["name"] == "recursive-engine"

    def test_list_repos_archived_true(self, registry):
        data = json.loads(json.dumps(registry))
        data["organs"]["META-ORGANVM"]["repositories"][0]["archived"] = True
        archived = list_repos(data, archived=True)
        assert len(archived) == 1
        assert archived[0][1]["name"] == "organvm-engine"

    def test_list_repos_archived_false(self, registry):
        data = json.loads(json.dumps(registry))
        data["organs"]["META-ORGANVM"]["repositories"][0]["archived"] = True
        active = list_repos(data, archived=False)
        assert len(active) == 5
        assert all(not r.get("archived", False) for _, r in active)

    def test_search_repos_tokenized_query(self, registry):
        results = search_repos(registry, "governance engine")
        assert len(results) == 1
        assert results[0][1]["name"] == "organvm-engine"

    def test_search_repos_exact_with_field(self, registry):
        results = search_repos(registry, "organvm-i-theoria", fields=["org"], exact=True)
        names = sorted(repo["name"] for _, repo in results)
        assert names == ["ontological-framework", "recursive-engine"]

    def test_search_repos_limit(self, registry):
        results = search_repos(registry, "engine", limit=1)
        assert len(results) == 1

    def test_sort_repo_results(self, registry):
        results = list_repos(registry)
        sorted_results = sort_repo_results(results, field="organ", descending=True)
        assert sorted_results[0][0] == "ORGAN-III"
        assert sorted_results[-1][0] == "META-ORGANVM"


class TestDependencyQueries:
    def test_build_dependency_maps(self, registry):
        outbound, inbound = build_dependency_maps(registry)
        assert outbound["ontological-framework"] == {"recursive-engine"}
        assert outbound["metasystem-master"] == {"recursive-engine"}
        assert inbound["recursive-engine"] == {"ontological-framework", "metasystem-master"}

    def test_get_repo_dependencies_direct(self, registry):
        deps = get_repo_dependencies(registry, "ontological-framework")
        assert deps == ["recursive-engine"]

    def test_get_repo_dependencies_transitive(self, registry):
        data = json.loads(json.dumps(registry))
        data["organs"]["ORGAN-III"]["repositories"][0]["dependencies"] = [
            "organvm-ii-poiesis/metasystem-master",
        ]
        deps = get_repo_dependencies(data, "product-app", transitive=True)
        assert deps == ["metasystem-master", "recursive-engine"]

    def test_get_repo_dependents_direct(self, registry):
        dependents = get_repo_dependents(registry, "recursive-engine")
        assert dependents == ["metasystem-master", "ontological-framework"]

    def test_get_repo_dependents_transitive(self, registry):
        data = json.loads(json.dumps(registry))
        data["organs"]["ORGAN-III"]["repositories"][0]["dependencies"] = [
            "organvm-ii-poiesis/metasystem-master",
        ]
        dependents = get_repo_dependents(data, "recursive-engine", transitive=True)
        assert dependents == ["metasystem-master", "ontological-framework", "product-app"]

    def test_get_repo_dependencies_missing_repo(self, registry):
        assert get_repo_dependencies(registry, "does-not-exist") == []

    def test_find_missing_dependency_targets(self, registry):
        data = json.loads(json.dumps(registry))
        data["organs"]["ORGAN-II"]["repositories"][0]["dependencies"] = [
            "organvm-i-theoria/recursive-engine",
            "organvm-vii-kerygma/nonexistent",
        ]
        missing = find_missing_dependency_targets(data)
        assert missing == {"metasystem-master": ["nonexistent"]}


class TestRegistrySummary:
    def test_summarize_registry_baseline(self, registry):
        summary = summarize_registry(registry)
        assert summary.total_repos == 6
        assert summary.organ_count == 4
        assert summary.public_repos == 6
        assert summary.private_repos == 0
        assert summary.platinum_repos == 1
        assert summary.archived_repos == 0
        assert summary.repos_with_dependencies == 2
        assert summary.dependency_edges == 2
        assert summary.by_tier == {"flagship": 4, "standard": 2}
        assert summary.by_promotion_status == {"LOCAL": 3, "PUBLIC_PROCESS": 3}

    def test_summarize_registry_private_and_archived(self, registry):
        data = json.loads(json.dumps(registry))
        data["organs"]["META-ORGANVM"]["repositories"][0]["public"] = False
        data["organs"]["META-ORGANVM"]["repositories"][0]["archived"] = True
        summary = summarize_registry(data)
        assert summary.public_repos == 5
        assert summary.private_repos == 1
        assert summary.archived_repos == 1


class TestResolveOrganKey:
    def test_shorthand_to_full(self):
        assert resolve_organ_key("I") == "ORGAN-I"
        assert resolve_organ_key("VII") == "ORGAN-VII"

    def test_meta_alias(self):
        assert resolve_organ_key("META") == "META-ORGANVM"

    def test_passthrough_full_key(self):
        assert resolve_organ_key("ORGAN-I") == "ORGAN-I"
        assert resolve_organ_key("META-ORGANVM") == "META-ORGANVM"

    def test_unknown_passthrough(self):
        assert resolve_organ_key("UNKNOWN") == "UNKNOWN"


class TestValidator:
    def test_valid_registry_passes(self, registry):
        result = validate_registry(registry)
        assert result.passed
        assert result.total_repos == 6

    def test_missing_field_is_error(self):
        bad = {"organs": {"ORGAN-I": {"repositories": [{"name": "test"}]}}}
        result = validate_registry(bad)
        assert not result.passed
        assert any("missing required" in e for e in result.errors)

    def test_invalid_status_is_error(self):
        bad = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {
                            "name": "test",
                            "org": "organvm-i-theoria",
                            "implementation_status": "BOGUS",
                            "public": True,
                            "description": "Test repo",
                        },
                    ],
                },
            },
        }
        result = validate_registry(bad)
        assert not result.passed
        assert any("BOGUS" in e for e in result.errors)

    def test_back_edge_detected(self):
        bad = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {
                            "name": "theory-repo",
                            "org": "organvm-i-theoria",
                            "implementation_status": "ACTIVE",
                            "public": True,
                            "description": "Theory",
                            "dependencies": ["organvm-ii-poiesis/art-repo"],
                        },
                    ],
                },
                "ORGAN-II": {
                    "repositories": [
                        {
                            "name": "art-repo",
                            "org": "organvm-ii-poiesis",
                            "implementation_status": "ACTIVE",
                            "public": True,
                            "description": "Art",
                            "dependencies": [],
                        },
                    ],
                },
            },
        }
        result = validate_registry(bad)
        assert any("back-edge" in e for e in result.errors)


class TestUpdater:
    def test_update_valid_field(self, registry):
        ok, msg = update_repo(registry, "recursive-engine", "tier", "standard")
        assert ok
        _, repo = find_repo(registry, "recursive-engine")
        assert repo["tier"] == "standard"

    def test_update_invalid_status(self, registry):
        ok, msg = update_repo(registry, "recursive-engine", "implementation_status", "BOGUS")
        assert not ok

    def test_update_missing_repo(self, registry):
        ok, msg = update_repo(registry, "nonexistent", "tier", "standard")
        assert not ok

    def test_promotion_status_records_history(self, registry):
        """F-002: updating promotion_status appends to promotion_history."""
        ok, msg = update_repo(
            registry, "ontological-framework", "promotion_status", "CANDIDATE",
        )
        assert ok
        _, repo = find_repo(registry, "ontological-framework")
        history = repo.get("promotion_history", [])
        assert len(history) == 1
        assert history[0]["from_state"] == "LOCAL"
        assert history[0]["to_state"] == "CANDIDATE"
        assert "timestamp" in history[0]

    def test_promotion_history_accumulates(self, registry):
        """F-002: successive promotions append, not overwrite."""
        update_repo(registry, "ontological-framework", "promotion_status", "CANDIDATE")
        update_repo(registry, "ontological-framework", "promotion_status", "PUBLIC_PROCESS")
        _, repo = find_repo(registry, "ontological-framework")
        history = repo["promotion_history"]
        assert len(history) == 2
        assert history[0]["to_state"] == "CANDIDATE"
        assert history[1]["from_state"] == "CANDIDATE"
        assert history[1]["to_state"] == "PUBLIC_PROCESS"

    def test_promotion_history_includes_reason(self, registry):
        """F-002: reason is recorded when provided."""
        update_repo(
            registry, "ontological-framework", "promotion_status", "CANDIDATE",
            reason="passed CI checks",
        )
        _, repo = find_repo(registry, "ontological-framework")
        assert repo["promotion_history"][0]["reason"] == "passed CI checks"

    def test_promotion_history_omits_empty_reason(self, registry):
        """F-002: empty reason is not stored in the record."""
        update_repo(registry, "ontological-framework", "promotion_status", "CANDIDATE")
        _, repo = find_repo(registry, "ontological-framework")
        assert "reason" not in repo["promotion_history"][0]

    def test_no_history_for_non_promotion_fields(self, registry):
        """F-002: only promotion_status changes trigger history recording."""
        update_repo(registry, "recursive-engine", "tier", "standard")
        _, repo = find_repo(registry, "recursive-engine")
        assert "promotion_history" not in repo

    def test_no_history_when_value_unchanged(self, registry):
        """F-002: setting promotion_status to the same value is a no-op for history."""
        _, repo = find_repo(registry, "recursive-engine")
        current = repo["promotion_status"]
        update_repo(registry, "recursive-engine", "promotion_status", current)
        assert "promotion_history" not in repo
