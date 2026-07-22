"""Tests for the MCP tool wrappers over the five core organvm CLIs (LIMEN-060).

Every tool returns a JSON-serializable dict and is read-only. Registry-backed
tools run against the minimal fixture; seed tools run against a synthetic
workspace under tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from organvm_engine.mcp import (
    MCP_TOOLS,
    TOOLS_BY_NAME,
    call_tool,
    list_tools,
)
from organvm_engine.mcp import tools

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY = str(FIXTURES / "registry-minimal.json")
RULES = str(FIXTURES / "governance-rules-test.json")


def _assert_serializable(result: object) -> None:
    assert isinstance(json.dumps(result), str)


# ---------------------------------------------------------------------------
# manifest / dispatch layer
# ---------------------------------------------------------------------------


class TestManifest:
    def test_lists_all_five_clis(self):
        clis = {spec.cli for spec in MCP_TOOLS}
        assert clis == {"registry", "governance", "seed", "metrics", "dispatch"}

    def test_list_tools_serializable(self):
        manifest = list_tools()
        _assert_serializable(manifest)
        assert len(manifest) == len(MCP_TOOLS)
        for entry in manifest:
            assert set(entry) == {"name", "cli", "description"}

    def test_names_unique(self):
        names = [spec.name for spec in MCP_TOOLS]
        assert len(names) == len(set(names))
        assert set(names) == set(TOOLS_BY_NAME)

    def test_handlers_callable(self):
        for spec in MCP_TOOLS:
            assert callable(spec.handler)

    def test_call_tool_dispatches(self):
        result = call_tool("registry_stats", registry_path=REGISTRY)
        assert result["total_repos"] > 0

    def test_call_tool_unknown_name(self):
        result = call_tool("does_not_exist")
        assert "error" in result
        assert "does_not_exist" in result["error"]


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_show_found(self):
        result = tools.registry_show("recursive-engine", registry_path=REGISTRY)
        _assert_serializable(result)
        assert result["repo"]["name"] == "recursive-engine"
        assert result["organ"] == "ORGAN-I"

    def test_show_not_found(self):
        result = tools.registry_show("nope-not-here", registry_path=REGISTRY)
        assert "error" in result

    def test_list_all(self):
        result = tools.registry_list(registry_path=REGISTRY)
        _assert_serializable(result)
        assert result["total"] == len(result["repos"])
        assert result["total"] >= 3

    def test_list_filter_by_organ(self):
        result = tools.registry_list(organ="ORGAN-I", registry_path=REGISTRY)
        assert result["total"] >= 1
        assert all(r["organ"] == "ORGAN-I" for r in result["repos"])

    def test_list_filter_by_tier(self):
        result = tools.registry_list(tier="flagship", registry_path=REGISTRY)
        assert all(r["tier"] == "flagship" for r in result["repos"])

    def test_search_found(self):
        result = tools.registry_search("recursive", registry_path=REGISTRY)
        _assert_serializable(result)
        assert result["total"] >= 1
        names = {m["repo"]["name"] for m in result["matches"]}
        assert "recursive-engine" in names

    def test_search_empty_query(self):
        result = tools.registry_search("  ", registry_path=REGISTRY)
        assert "error" in result

    def test_stats(self):
        result = tools.registry_stats(registry_path=REGISTRY)
        _assert_serializable(result)
        assert "by_organ" in result
        assert result["total_repos"] > 0

    def test_deps_dependencies(self):
        result = tools.registry_deps("ontological-framework", registry_path=REGISTRY)
        _assert_serializable(result)
        assert "dependencies" in result
        assert "recursive-engine" in result["dependencies"]

    def test_deps_reverse(self):
        result = tools.registry_deps(
            "recursive-engine", reverse=True, registry_path=REGISTRY,
        )
        assert "dependents" in result
        assert "dependencies" not in result

    def test_deps_both(self):
        result = tools.registry_deps(
            "recursive-engine", both=True, registry_path=REGISTRY,
        )
        assert "dependencies" in result
        assert "dependents" in result

    def test_deps_unknown_repo(self):
        result = tools.registry_deps("ghost", registry_path=REGISTRY)
        assert "error" in result

    def test_validate(self):
        result = tools.registry_validate(registry_path=REGISTRY)
        _assert_serializable(result)
        assert "passed" in result
        assert isinstance(result["errors"], list)
        assert result["total_repos"] > 0


# ---------------------------------------------------------------------------
# governance
# ---------------------------------------------------------------------------


class TestGovernance:
    def test_audit(self):
        result = tools.governance_audit(registry_path=REGISTRY, rules_path=RULES)
        _assert_serializable(result)
        assert "passed" in result
        assert isinstance(result["critical"], list)
        assert isinstance(result["warnings"], list)
        assert isinstance(result["info"], list)

    def test_check_deps(self):
        result = tools.governance_check_deps(registry_path=REGISTRY)
        _assert_serializable(result)
        assert "passed" in result
        assert "total_edges" in result
        assert isinstance(result["cycles"], list)

    def test_impact(self):
        result = tools.governance_impact(
            "recursive-engine", registry_path=REGISTRY,
        )
        _assert_serializable(result)
        assert result["source_repo"] == "recursive-engine"
        assert "affected_repos" in result
        # ontological-framework and metasystem-master both depend on it
        assert "ontological-framework" in result["affected_repos"]
        assert result["affected_count"] == len(result["affected_repos"])


# ---------------------------------------------------------------------------
# seed
# ---------------------------------------------------------------------------


@pytest.fixture()
def seed_workspace(tmp_path):
    """A synthetic workspace with one valid and one invalid seed.yaml."""
    valid_dir = tmp_path / "organvm-i-theoria" / "recursive-engine"
    valid_dir.mkdir(parents=True)
    (valid_dir / "seed.yaml").write_text(
        'schema_version: "1.0"\norgan: I\nrepo: recursive-engine\n'
        "org: organvm-i-theoria\n",
    )

    bad_dir = tmp_path / "organvm-i-theoria" / "broken-repo"
    bad_dir.mkdir(parents=True)
    (bad_dir / "seed.yaml").write_text('repo: broken-repo\norg: organvm-i-theoria\n')

    return tmp_path


class TestSeed:
    def test_discover(self, seed_workspace):
        result = tools.seed_discover(workspace=str(seed_workspace))
        _assert_serializable(result)
        assert result["total"] == 2
        repos = {s["repo"] for s in result["seeds"]}
        assert repos == {"recursive-engine", "broken-repo"}

    def test_discover_empty(self, tmp_path):
        result = tools.seed_discover(workspace=str(tmp_path))
        assert result["total"] == 0
        assert result["seeds"] == []

    def test_validate(self, seed_workspace):
        result = tools.seed_validate(workspace=str(seed_workspace))
        _assert_serializable(result)
        assert result["total"] == 2
        assert result["passed"] == 1
        assert result["failed"] == 1
        bad = next(r for r in result["results"] if not r["passed"])
        assert "schema_version" in bad["missing"]
        assert "organ" in bad["missing"]

    def test_graph(self, seed_workspace):
        result = tools.seed_graph(workspace=str(seed_workspace))
        _assert_serializable(result)
        assert "nodes" in result
        assert "edges" in result
        assert result["edge_count"] == len(result["edges"])


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_calculate(self):
        result = tools.metrics_calculate(registry_path=REGISTRY)
        _assert_serializable(result)
        assert "total_repos" in result
        assert "total_organs" in result
        assert result["total_repos"] > 0

    def test_calculate_read_only(self, tmp_path):
        """Computing metrics must not write system-metrics.json."""
        before = set(tmp_path.iterdir())
        tools.metrics_calculate(registry_path=REGISTRY, workspace=str(tmp_path))
        assert set(tmp_path.iterdir()) == before


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_validate_invalid_type(self):
        result = tools.dispatch_validate(payload="not a dict")  # type: ignore[arg-type]
        assert result["valid"] is False
        assert result["errors"]

    def test_validate_returns_structure(self):
        result = tools.dispatch_validate(payload={})
        _assert_serializable(result)
        assert "valid" in result
        assert "errors" in result
        assert isinstance(result["errors"], list)
