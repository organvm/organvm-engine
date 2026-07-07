"""Tests for CLAUDE.md generator and sync (legacy module name).

These tests originally targeted organvm_engine.claudemd — now renamed to
organvm_engine.contextmd. See test_contextmd.py for comprehensive coverage.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from organvm_engine.contextmd.generator import (
    generate_organ_section,
    generate_repo_section,
    generate_workspace_section,
)
from organvm_engine.contextmd.sync import sync_repo


@pytest.fixture
def mock_registry():
    return {
        "organs": {
            "ORGAN-I": {
                "name": "Theory",
                "organization": "organvm-i-theoria",
                "repositories": [
                    {"name": "repo-a", "tier": "flagship", "promotion_status": "GRADUATED"},
                    {"name": "repo-b", "tier": "standard", "promotion_status": "LOCAL"},
                ],
            },
        },
    }


class TestGenerator:
    def test_generate_repo_section(self, mock_registry):
        seed = {"repo": "repo-a", "produces": [{"target": "repo-b", "artifact": "docs"}]}
        section = generate_repo_section("repo-a", "organvm-i-theoria", mock_registry, seed)
        assert "## System Context" in section
        assert "## System Library" in section
        assert "**Organ:** ORGAN-I" in section
        assert "Produces" in section
        assert "repo-b" in section

    def test_generate_organ_section(self, mock_registry):
        section = generate_organ_section("ORGAN-I", mock_registry, [])
        assert "## Organ Map" in section
        assert "2 repos" in section
        assert "1 flagship" in section

    def test_generate_workspace_section(self, mock_registry):
        section = generate_workspace_section(mock_registry, [])
        assert "## System Overview" in section
        assert "2 repos" in section
        assert "ORGAN-I" in section


class TestSync:
    @patch("organvm_engine.contextmd.sync._inject_section")
    def test_sync_repo(self, mock_inject, mock_registry):
        mock_inject.return_value = "updated"
        res = sync_repo(Path("/tmp"), "repo-a", "org", mock_registry)
        assert res["action"] == "updated"
        assert "CLAUDE.md" in res["path"]
