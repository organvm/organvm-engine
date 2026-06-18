"""Tests for seed MCP tool functions (LIMEN-060).

Each tool returns a JSON-serializable dict. Tests build an isolated
workspace under tmp_path and pass an explicit ``orgs`` list so discovery
never touches the production workspace (blocked by conftest autouse).
"""

from __future__ import annotations

import json

import pytest

from organvm_engine.seed.mcp_tools import (
    seed_discover,
    seed_graph,
    seed_ownership,
    seed_validate,
)

ORGS = ["org-a", "org-b"]


def _write_seed(workspace, org: str, repo: str, body: str) -> None:
    repo_dir = workspace / org / repo
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "seed.yaml").write_text(body)


@pytest.fixture()
def workspace(tmp_path):
    """A two-org workspace: a producer, a consumer, and an invalid seed."""
    _write_seed(
        tmp_path,
        "org-a",
        "producer",
        """
schema_version: "1.0"
organ: I
repo: producer
org: org-a
produces:
  - type: theory
    description: "frameworks"
subscriptions:
  - event: governance.updated
    source: ORGAN-IV
    action: Check compliance
ownership:
  lead: alice
  collaborators:
    - handle: bob
      role: reviewer
      access: [read, write]
""".lstrip(),
    )
    _write_seed(
        tmp_path,
        "org-b",
        "consumer",
        """
schema_version: "1.0"
organ: II
repo: consumer
org: org-b
consumes:
  - type: theory
    source: org-a
""".lstrip(),
    )
    # Missing required fields -> validation failure
    _write_seed(
        tmp_path,
        "org-b",
        "broken",
        "organ: II\nrepo: broken\n",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# seed_discover
# ---------------------------------------------------------------------------


class TestSeedDiscover:
    def test_finds_all(self, workspace):
        result = seed_discover(workspace=str(workspace), orgs=ORGS)
        assert result["total"] == 3
        identities = {(s["org"], s["repo"]) for s in result["seeds"]}
        assert ("org-a", "producer") in identities
        assert ("org-b", "consumer") in identities

    def test_json_serializable(self, workspace):
        result = seed_discover(workspace=str(workspace), orgs=ORGS)
        assert isinstance(json.dumps(result), str)


# ---------------------------------------------------------------------------
# seed_validate
# ---------------------------------------------------------------------------


class TestSeedValidate:
    def test_reports_failures(self, workspace):
        result = seed_validate(workspace=str(workspace), orgs=ORGS)
        assert result["total"] == 3
        assert result["passed"] == 2
        assert result["failed"] == 1
        broken = [r for r in result["results"] if not r["passed"]]
        assert broken
        assert "schema_version" in broken[0]["missing"]

    def test_json_serializable(self, workspace):
        result = seed_validate(workspace=str(workspace), orgs=ORGS)
        assert isinstance(json.dumps(result), str)


# ---------------------------------------------------------------------------
# seed_graph
# ---------------------------------------------------------------------------


class TestSeedGraph:
    def test_produces_consumes_edge(self, workspace):
        result = seed_graph(workspace=str(workspace), orgs=ORGS)
        # producer --theory--> consumer
        assert result["edge_count"] >= 1
        edge = result["edges"][0]
        assert edge["source"] == "org-a/producer"
        assert edge["target"] == "org-b/consumer"
        assert edge["type"] == "theory"

    def test_nodes_present(self, workspace):
        result = seed_graph(workspace=str(workspace), orgs=ORGS)
        assert "org-a/producer" in result["nodes"]
        assert "org-b/consumer" in result["nodes"]

    def test_json_serializable(self, workspace):
        result = seed_graph(workspace=str(workspace), orgs=ORGS)
        assert isinstance(json.dumps(result), str)


# ---------------------------------------------------------------------------
# seed_ownership
# ---------------------------------------------------------------------------


class TestSeedOwnership:
    def test_with_ownership(self, workspace):
        result = seed_ownership("producer", workspace=str(workspace), orgs=ORGS)
        assert result["found"] is True
        assert result["has_ownership"] is True
        assert result["lead"] == "alice"
        assert result["collaborators"][0]["handle"] == "bob"

    def test_by_full_identity(self, workspace):
        result = seed_ownership("org-a/producer", workspace=str(workspace), orgs=ORGS)
        assert result["found"] is True

    def test_no_ownership_section(self, workspace):
        result = seed_ownership("consumer", workspace=str(workspace), orgs=ORGS)
        assert result["found"] is True
        assert result["has_ownership"] is False

    def test_not_found(self, workspace):
        result = seed_ownership("ghost", workspace=str(workspace), orgs=ORGS)
        assert result["found"] is False

    def test_empty_repo(self, workspace):
        result = seed_ownership("", workspace=str(workspace), orgs=ORGS)
        assert result["found"] is False
        assert "error" in result

    def test_json_serializable(self, workspace):
        result = seed_ownership("producer", workspace=str(workspace), orgs=ORGS)
        assert isinstance(json.dumps(result), str)
