"""Tests for registry MCP tool functions (LIMEN-060).

Each tool returns a JSON-serializable dict. Tests run against the
``registry-minimal.json`` fixture via an explicit ``registry_path`` so
they never touch the production registry (blocked by conftest autouse).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from organvm_engine.registry.mcp_tools import (
    registry_dependencies,
    registry_list,
    registry_search,
    registry_show,
    registry_stats,
)

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY = str(FIXTURES / "registry-minimal.json")


@pytest.fixture()
def reg() -> str:
    return REGISTRY


# ---------------------------------------------------------------------------
# registry_list
# ---------------------------------------------------------------------------


class TestRegistryList:
    def test_lists_all_repos(self, reg):
        result = registry_list(registry_path=reg)
        # registry-minimal has 6 repos across 4 organs
        assert result["total"] == 6
        assert result["matched"] == 6
        assert all("organ" in r and "name" in r for r in result["repos"])

    def test_json_serializable(self, reg):
        result = registry_list(registry_path=reg)
        assert isinstance(json.dumps(result), str)

    def test_filter_by_organ_alias(self, reg):
        result = registry_list(organ="META", registry_path=reg)
        assert result["total"] == 2
        assert {r["name"] for r in result["repos"]} == {
            "organvm-engine",
            "organvm-corpvs-testamentvm",
        }

    def test_filter_by_promotion_status(self, reg):
        result = registry_list(promotion_status="PUBLIC_PROCESS", registry_path=reg)
        names = {r["name"] for r in result["repos"]}
        assert "recursive-engine" in names
        assert "ontological-framework" not in names

    def test_filter_by_tier(self, reg):
        result = registry_list(tier="flagship", registry_path=reg)
        assert all(r.get("tier") == "flagship" for r in result["repos"])

    def test_platinum_only(self, reg):
        result = registry_list(platinum_only=True, registry_path=reg)
        assert result["total"] == 1
        assert result["repos"][0]["name"] == "recursive-engine"

    def test_limit_truncates_but_reports_matched(self, reg):
        result = registry_list(limit=2, registry_path=reg)
        assert result["total"] == 2
        assert result["matched"] == 6


# ---------------------------------------------------------------------------
# registry_show
# ---------------------------------------------------------------------------


class TestRegistryShow:
    def test_found(self, reg):
        result = registry_show("organvm-engine", registry_path=reg)
        assert result["found"] is True
        assert result["organ"] == "META-ORGANVM"
        assert result["repo"]["description"] == "Core governance engine"

    def test_not_found(self, reg):
        result = registry_show("does-not-exist", registry_path=reg)
        assert result["found"] is False
        assert result["name"] == "does-not-exist"

    def test_empty_name(self, reg):
        result = registry_show("", registry_path=reg)
        assert result["found"] is False
        assert "error" in result

    def test_json_serializable(self, reg):
        result = registry_show("organvm-engine", registry_path=reg)
        assert isinstance(json.dumps(result), str)


# ---------------------------------------------------------------------------
# registry_search
# ---------------------------------------------------------------------------


class TestRegistrySearch:
    def test_search_description(self, reg):
        result = registry_search("recursive", registry_path=reg)
        assert result["total"] >= 1
        assert any(r["name"] == "recursive-engine" for r in result["repos"])

    def test_empty_query(self, reg):
        result = registry_search("   ", registry_path=reg)
        assert result["total"] == 0
        assert result["repos"] == []

    def test_limit_respected(self, reg):
        result = registry_search("organvm", limit=1, fields=["org"], registry_path=reg)
        assert result["total"] <= 1

    def test_json_serializable(self, reg):
        result = registry_search("engine", registry_path=reg)
        assert isinstance(json.dumps(result), str)


# ---------------------------------------------------------------------------
# registry_stats
# ---------------------------------------------------------------------------


class TestRegistryStats:
    def test_totals(self, reg):
        result = registry_stats(registry_path=reg)
        assert result["total_repos"] == 6
        assert result["organ_count"] == 4
        assert result["platinum_repos"] == 1

    def test_by_organ_keys(self, reg):
        result = registry_stats(registry_path=reg)
        assert result["by_organ"]["META-ORGANVM"] == 2
        assert result["by_organ"]["ORGAN-I"] == 2

    def test_dependency_edges(self, reg):
        result = registry_stats(registry_path=reg)
        # ontological-framework -> recursive-engine, metasystem-master -> recursive-engine
        assert result["dependency_edges"] == 2
        assert result["repos_with_dependencies"] == 2

    def test_json_serializable(self, reg):
        result = registry_stats(registry_path=reg)
        assert isinstance(json.dumps(result), str)


# ---------------------------------------------------------------------------
# registry_dependencies
# ---------------------------------------------------------------------------


class TestRegistryDependencies:
    def test_outbound_direct(self, reg):
        result = registry_dependencies("ontological-framework", registry_path=reg)
        assert result["found"] is True
        assert result["direction"] == "out"
        assert result["results"] == ["recursive-engine"]

    def test_inbound_dependents(self, reg):
        result = registry_dependencies(
            "recursive-engine", direction="in", registry_path=reg,
        )
        assert result["found"] is True
        assert result["direction"] == "in"
        assert set(result["results"]) == {"ontological-framework", "metasystem-master"}

    def test_not_found(self, reg):
        result = registry_dependencies("ghost", registry_path=reg)
        assert result["found"] is False

    def test_invalid_direction(self, reg):
        result = registry_dependencies(
            "recursive-engine", direction="sideways", registry_path=reg,
        )
        assert "error" in result

    def test_empty_repo_name(self, reg):
        result = registry_dependencies("", registry_path=reg)
        assert result["found"] is False
        assert "error" in result

    def test_json_serializable(self, reg):
        result = registry_dependencies("recursive-engine", direction="in", registry_path=reg)
        assert isinstance(json.dumps(result), str)
