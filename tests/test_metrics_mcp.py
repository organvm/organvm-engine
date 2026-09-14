"""Tests for metrics MCP tool functions (LIMEN-060).

The tools are read-only projections of ``organvm metrics`` — they never
write files. Tests use the registry fixture and a tmp workspace.
"""

from __future__ import annotations

import json
from pathlib import Path

from organvm_engine.metrics.mcp_tools import metrics_calculate, metrics_word_count

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY = str(FIXTURES / "registry-minimal.json")


# ---------------------------------------------------------------------------
# metrics_calculate
# ---------------------------------------------------------------------------


class TestMetricsCalculate:
    def test_core_counts(self):
        result = metrics_calculate(registry_path=REGISTRY)
        assert result["total_repos"] == 6
        assert result["active_repos"] == 6
        assert result["total_organs"] == 4
        assert result["operational_organs"] == 4

    def test_dependency_edges(self):
        result = metrics_calculate(registry_path=REGISTRY)
        assert result["dependency_edges"] == 2

    def test_ci_workflows(self):
        result = metrics_calculate(registry_path=REGISTRY)
        # only recursive-engine declares a ci_workflow in the fixture
        assert result["ci_workflows"] == 1

    def test_no_word_counts_without_workspace(self):
        result = metrics_calculate(registry_path=REGISTRY)
        assert "word_counts" not in result

    def test_word_counts_with_workspace(self, tmp_path):
        result = metrics_calculate(registry_path=REGISTRY, workspace=str(tmp_path))
        assert "word_counts" in result
        assert "code_files" in result

    def test_does_not_write_files(self, tmp_path):
        metrics_calculate(registry_path=REGISTRY, workspace=str(tmp_path))
        # the read-only tool must not emit system-metrics.json anywhere
        assert not (Path(REGISTRY).parent / "system-metrics.json").exists()
        assert list(tmp_path.iterdir()) == []

    def test_json_serializable(self):
        result = metrics_calculate(registry_path=REGISTRY)
        assert isinstance(json.dumps(result), str)


# ---------------------------------------------------------------------------
# metrics_word_count
# ---------------------------------------------------------------------------


class TestMetricsWordCount:
    def test_empty_workspace_zeroes(self, tmp_path):
        result = metrics_word_count(workspace=str(tmp_path))
        assert result["word_counts"]["total"] == 0
        assert result["total_words_numeric"] == 0

    def test_structure(self, tmp_path):
        result = metrics_word_count(workspace=str(tmp_path))
        for key in ("readmes", "essays", "corpus", "org_profiles", "total"):
            assert key in result["word_counts"]
        assert "total_words_short" in result

    def test_json_serializable(self, tmp_path):
        result = metrics_word_count(workspace=str(tmp_path))
        assert isinstance(json.dumps(result), str)
