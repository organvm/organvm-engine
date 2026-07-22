"""Tests for governance MCP tool functions (LIMEN-060).

Each tool returns a JSON-serializable dict. Tests use the registry and
governance-rules fixtures via explicit paths so they never resolve the
production data (blocked by conftest autouse).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from organvm_engine.governance.mcp_tools import (
    governance_audit,
    governance_check_deps,
    governance_dictums,
    governance_impact,
)

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY = str(FIXTURES / "registry-minimal.json")
RULES = str(FIXTURES / "governance-rules-test.json")


# ---------------------------------------------------------------------------
# governance_audit
# ---------------------------------------------------------------------------


class TestGovernanceAudit:
    def test_returns_severity_buckets(self):
        result = governance_audit(
            registry_path=REGISTRY, rules_path=RULES, check_dictums=False,
        )
        assert "passed" in result
        assert "critical" in result
        assert "warnings" in result
        assert "info" in result
        assert result["critical_count"] == len(result["critical"])

    def test_json_serializable(self):
        result = governance_audit(
            registry_path=REGISTRY, rules_path=RULES, check_dictums=False,
        )
        assert isinstance(json.dumps(result), str)


# ---------------------------------------------------------------------------
# governance_check_deps
# ---------------------------------------------------------------------------


class TestGovernanceCheckDeps:
    def test_clean_registry_passes(self):
        result = governance_check_deps(registry_path=REGISTRY)
        # registry-minimal has only valid downstream edges
        assert result["passed"] is True
        assert result["total_edges"] == 2
        assert result["missing_targets"] == []
        assert result["cycles"] == []

    def test_structure(self):
        result = governance_check_deps(registry_path=REGISTRY)
        for key in (
            "passed",
            "total_edges",
            "missing_targets",
            "self_deps",
            "back_edges",
            "cycles",
            "cross_organ",
            "violations",
        ):
            assert key in result

    def test_json_serializable(self):
        result = governance_check_deps(registry_path=REGISTRY)
        assert isinstance(json.dumps(result), str)


# ---------------------------------------------------------------------------
# governance_impact
# ---------------------------------------------------------------------------


class TestGovernanceImpact:
    def test_blast_radius(self):
        result = governance_impact("recursive-engine", registry_path=REGISTRY)
        assert result["source_repo"] == "recursive-engine"
        # ontological-framework and metasystem-master both depend on it
        assert "ontological-framework" in result["affected_repos"]
        assert "metasystem-master" in result["affected_repos"]
        assert result["affected_count"] >= 2

    def test_leaf_repo_no_impact(self):
        result = governance_impact("ontological-framework", registry_path=REGISTRY)
        assert result["affected_repos"] == []
        assert result["affected_count"] == 0

    def test_empty_repo_errors(self):
        result = governance_impact("", registry_path=REGISTRY)
        assert "error" in result

    def test_json_serializable(self):
        result = governance_impact("recursive-engine", registry_path=REGISTRY)
        assert isinstance(json.dumps(result), str)


# ---------------------------------------------------------------------------
# governance_dictums
# ---------------------------------------------------------------------------


class TestGovernanceDictums:
    def test_lists_axioms(self):
        result = governance_dictums(rules_path=RULES)
        assert result["total"] >= 1
        assert all("id" in d and "level" in d for d in result["dictums"])

    def test_filter_by_level(self):
        result = governance_dictums(level="axiom", rules_path=RULES)
        assert all(d["level"] == "axiom" for d in result["dictums"])

    def test_filter_by_id(self):
        result = governance_dictums(dictum_id="AX-1", rules_path=RULES)
        assert result["total"] == 1
        assert result["dictums"][0]["id"] == "AX-1"

    def test_unknown_id_empty(self):
        result = governance_dictums(dictum_id="AX-999", rules_path=RULES)
        assert result["total"] == 0

    def test_json_serializable(self):
        result = governance_dictums(rules_path=RULES)
        assert isinstance(json.dumps(result), str)
