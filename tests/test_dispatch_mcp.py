"""Tests for dispatch MCP tool functions (LIMEN-060).

Each tool returns a JSON-serializable dict. Routing tests build an
isolated workspace under tmp_path with an explicit ``orgs`` list so
discovery never touches the production workspace.
"""

from __future__ import annotations

import json

import pytest

from organvm_engine.dispatch.mcp_tools import (
    dispatch_create,
    dispatch_route,
    dispatch_validate,
)

ORGS = ["org-a"]


# ---------------------------------------------------------------------------
# dispatch_validate
# ---------------------------------------------------------------------------


class TestDispatchValidate:
    def test_valid_payload(self):
        payload = {
            "event": "theory.published",
            "source": {"organ": "ORGAN-I"},
            "target": {"organ": "ORGAN-II"},
            "payload": {"title": "x"},
        }
        result = dispatch_validate(payload)
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["contract_checked"] is False

    def test_missing_fields(self):
        result = dispatch_validate({"event": "no-dot"})
        assert result["valid"] is False
        assert any("dot" in e for e in result["errors"])
        assert any("source" in e for e in result["errors"])

    def test_non_dict_payload(self):
        result = dispatch_validate("not-a-dict")  # type: ignore[arg-type]
        assert result["valid"] is False

    def test_contract_check_flag(self):
        payload = {
            "event": "theory.published",
            "source": {"organ": "ORGAN-I"},
            "target": {"organ": "ORGAN-II"},
            "payload": {},
        }
        result = dispatch_validate(payload, check_contract=True)
        assert result["contract_checked"] is True
        assert "contract_found" in result

    def test_json_serializable(self):
        result = dispatch_validate({"event": "a.b"})
        assert isinstance(json.dumps(result), str)


# ---------------------------------------------------------------------------
# dispatch_create
# ---------------------------------------------------------------------------


class TestDispatchCreate:
    def test_builds_valid_payload(self):
        result = dispatch_create(
            event="theory.published",
            source_organ="ORGAN-I",
            target_organ="ORGAN-II",
            payload_data={"title": "x"},
        )
        assert result["created"] is True
        assert result["valid"] is True
        assert result["payload"]["event"] == "theory.published"
        assert "dispatch_id" in result["payload"]["metadata"]

    def test_missing_event(self):
        result = dispatch_create(event="", source_organ="ORGAN-I", target_organ="ORGAN-II")
        assert result["created"] is False
        assert "error" in result

    def test_missing_organs(self):
        result = dispatch_create(event="a.b", source_organ="", target_organ="ORGAN-II")
        assert result["created"] is False

    def test_optional_coordinates(self):
        result = dispatch_create(
            event="theory.published",
            source_organ="ORGAN-I",
            target_organ="ORGAN-II",
            source_org="organvm-i-theoria",
            source_repo="recursive-engine",
        )
        assert result["payload"]["source"]["org"] == "organvm-i-theoria"
        assert result["payload"]["source"]["repo"] == "recursive-engine"

    def test_json_serializable(self):
        result = dispatch_create(
            event="a.b", source_organ="ORGAN-I", target_organ="ORGAN-II",
        )
        assert isinstance(json.dumps(result), str)


# ---------------------------------------------------------------------------
# dispatch_route
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path):
    repo_dir = tmp_path / "org-a" / "subscriber"
    repo_dir.mkdir(parents=True)
    (repo_dir / "seed.yaml").write_text(
        """
schema_version: "1.0"
organ: I
repo: subscriber
org: org-a
subscriptions:
  - event: governance.updated
    source: ORGAN-IV
    action: Check compliance
""".lstrip(),
    )
    return tmp_path


class TestDispatchRoute:
    def test_matches_subscription(self, workspace):
        result = dispatch_route(
            event_type="governance.updated",
            source_organ="ORGAN-IV",
            workspace=str(workspace),
            orgs=ORGS,
        )
        assert result["match_count"] == 1
        assert result["matches"][0]["repo"] == "org-a/subscriber"
        assert result["matches"][0]["action"] == "Check compliance"

    def test_no_match(self, workspace):
        result = dispatch_route(
            event_type="nonexistent.event",
            source_organ="ORGAN-IV",
            workspace=str(workspace),
            orgs=ORGS,
        )
        assert result["match_count"] == 0

    def test_missing_args(self):
        result = dispatch_route(event_type="", source_organ="ORGAN-IV")
        assert "error" in result

    def test_contract_verification_fields(self, workspace):
        result = dispatch_route(
            event_type="governance.updated",
            source_organ="ORGAN-IV",
            payload_data={"foo": "bar"},
            workspace=str(workspace),
            orgs=ORGS,
        )
        assert "contract_found" in result
        assert "contract_verified" in result

    def test_json_serializable(self, workspace):
        result = dispatch_route(
            event_type="governance.updated",
            source_organ="ORGAN-IV",
            workspace=str(workspace),
            orgs=ORGS,
        )
        assert isinstance(json.dumps(result), str)
