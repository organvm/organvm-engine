"""Tests for ontologia state snapshot bridge."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from organvm_engine.ontologia.snapshots import (
    _compare_system_snapshots,
    _prune_old_snapshots,
    compare_entity_snapshots,
    create_entity_snapshot,
    create_system_snapshot,
    detect_drift,
)

# A snapshot date safely inside the 30-day prune window (relative, never rots).
_RECENT = (date.today() - timedelta(days=5)).isoformat()


@pytest.fixture
def registry_file(tmp_path):
    registry = {
        "version": "2",
        "organs": {
            "ORGAN-I": {
                "name": "Theoria",
                "repositories": [
                    {
                        "name": "repo-alpha",
                        "promotion_status": "CANDIDATE",
                        "tier": "standard",
                        "public": True,
                        "ci_workflow": "ci.yml",
                        "platinum_status": True,
                        "implementation_status": "ACTIVE",
                        "last_validated": "2026-03-10T00:00:00Z",
                    },
                    {
                        "name": "repo-beta",
                        "promotion_status": "LOCAL",
                        "tier": "standard",
                        "public": False,
                        "ci_workflow": "",
                        "platinum_status": False,
                        "implementation_status": "STUB",
                        "last_validated": "",
                    },
                ],
            },
        },
    }
    path = tmp_path / "registry-v2.json"
    path.write_text(json.dumps(registry))
    return path


@pytest.fixture
def snapshots_dir(tmp_path):
    return tmp_path / "snapshots"


# ---------------------------------------------------------------------------
# Entity snapshot creation
# ---------------------------------------------------------------------------

class TestCreateEntitySnapshot:
    def test_basic_snapshot(self):
        repo = {
            "name": "test-repo",
            "promotion_status": "CANDIDATE",
            "tier": "standard",
        }
        snap = create_entity_snapshot("ent_001", repo)
        assert snap["entity_id"] == "ent_001"
        assert snap["properties"]["name"] == "test-repo"
        assert snap["properties"]["promotion_status"] == "CANDIDATE"
        assert "timestamp" in snap

    def test_with_metrics(self):
        repo = {"name": "test"}
        metrics = {"test_count": 50.0, "code_files": 20.0}
        snap = create_entity_snapshot("ent_002", repo, metric_values=metrics)
        assert snap["metric_values"]["test_count"] == 50.0


# ---------------------------------------------------------------------------
# System snapshot
# ---------------------------------------------------------------------------

class TestCreateSystemSnapshot:
    def test_creates_snapshot_file(self, registry_file, snapshots_dir):
        result = create_system_snapshot(registry_file, snapshots_dir)
        assert result["entity_count"] == 2
        assert Path(result["snapshot_path"]).is_file()

    def test_snapshot_contains_entities(self, registry_file, snapshots_dir):
        result = create_system_snapshot(registry_file, snapshots_dir)
        data = json.loads(Path(result["snapshot_path"]).read_text())
        assert "repo-alpha" in data["entities"]
        assert "repo-beta" in data["entities"]

    def test_invalid_registry(self, tmp_path, snapshots_dir):
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        result = create_system_snapshot(bad, snapshots_dir)
        assert "error" in result


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------

class TestDetectDrift:
    def test_first_snapshot_no_drift(self, registry_file, snapshots_dir):
        result = detect_drift(snapshots_dir, registry_file)
        # No snapshots dir yet, so it creates one
        assert result["has_drift"] is False

    def test_no_drift_same_data(self, registry_file, snapshots_dir):
        create_system_snapshot(registry_file, snapshots_dir)

        # Create a second snapshot with same data (different date)
        data = json.loads(list(snapshots_dir.glob("*.json"))[0].read_text())
        data["date"] = "2026-03-14"
        (snapshots_dir / "snapshot-2026-03-14.json").write_text(json.dumps(data))

        result = detect_drift(snapshots_dir)
        assert result["has_drift"] is False
        assert len(result["changed_entities"]) == 0

    def test_detects_property_change(self, registry_file, snapshots_dir):
        create_system_snapshot(registry_file, snapshots_dir)

        # Modify registry and create second snapshot
        reg = json.loads(registry_file.read_text())
        reg["organs"]["ORGAN-I"]["repositories"][0]["promotion_status"] = "PUBLIC_PROCESS"
        registry_file.write_text(json.dumps(reg))

        # Rename file to simulate earlier date (must be within 30-day prune window)
        old_file = list(snapshots_dir.glob("*.json"))[0]
        old_file.rename(snapshots_dir / f"snapshot-{_RECENT}.json")

        create_system_snapshot(registry_file, snapshots_dir)

        result = detect_drift(snapshots_dir)
        assert result["has_drift"] is True
        modified = [c for c in result["changed_entities"] if c["change"] == "modified"]
        assert any(c["entity_id"] == "repo-alpha" for c in modified)

    def test_detects_entity_added(self, registry_file, snapshots_dir):
        create_system_snapshot(registry_file, snapshots_dir)

        # Add a repo
        reg = json.loads(registry_file.read_text())
        reg["organs"]["ORGAN-I"]["repositories"].append({"name": "new-repo", "tier": "standard"})
        registry_file.write_text(json.dumps(reg))

        old_file = list(snapshots_dir.glob("*.json"))[0]
        old_file.rename(snapshots_dir / f"snapshot-{_RECENT}.json")

        create_system_snapshot(registry_file, snapshots_dir)

        result = detect_drift(snapshots_dir)
        assert result["has_drift"] is True
        added = [c for c in result["changed_entities"] if c["change"] == "added"]
        assert any(c["entity_id"] == "new-repo" for c in added)


# ---------------------------------------------------------------------------
# Compare entity snapshots
# ---------------------------------------------------------------------------

class TestCompareEntitySnapshots:
    def test_not_enough_snapshots(self, snapshots_dir):
        result = compare_entity_snapshots("test", snapshots_dir)
        assert "error" in result

    def test_entity_not_found(self, registry_file, snapshots_dir):
        create_system_snapshot(registry_file, snapshots_dir)
        # Copy to create second snapshot
        f = list(snapshots_dir.glob("*.json"))[0]
        data = json.loads(f.read_text())
        data["date"] = "2026-03-14"
        (snapshots_dir / "snapshot-2026-03-14.json").write_text(json.dumps(data))

        result = compare_entity_snapshots("nonexistent-entity", snapshots_dir)
        assert "error" in result


# ---------------------------------------------------------------------------
# Compare system snapshots helper
# ---------------------------------------------------------------------------

class TestCompareSystemSnapshots:
    def test_detects_added(self):
        prev = {"entities": {"a": {"properties": {}}}}
        curr = {"entities": {"a": {"properties": {}}, "b": {"properties": {}}}}
        changes = _compare_system_snapshots(prev, curr)
        added = [c for c in changes if c["change"] == "added"]
        assert len(added) == 1

    def test_detects_removed(self):
        prev = {"entities": {"a": {"properties": {}}, "b": {"properties": {}}}}
        curr = {"entities": {"a": {"properties": {}}}}
        changes = _compare_system_snapshots(prev, curr)
        removed = [c for c in changes if c["change"] == "removed"]
        assert len(removed) == 1

    def test_detects_modified(self):
        prev = {"entities": {"a": {"properties": {"x": 1}}}}
        curr = {"entities": {"a": {"properties": {"x": 2}}}}
        changes = _compare_system_snapshots(prev, curr)
        assert len(changes) == 1
        assert changes[0]["change"] == "modified"

    def test_no_changes(self):
        data = {"entities": {"a": {"properties": {"x": 1}}}}
        changes = _compare_system_snapshots(data, data)
        assert len(changes) == 0


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------

class TestPruneSnapshots:
    def test_removes_old_snapshots(self, snapshots_dir):
        snapshots_dir.mkdir(parents=True)
        (snapshots_dir / "snapshot-2024-01-01.json").write_text("{}")
        (snapshots_dir / f"snapshot-{_RECENT}.json").write_text("{}")

        removed = _prune_old_snapshots(snapshots_dir, keep_days=30)
        assert removed == 1
        assert not (snapshots_dir / "snapshot-2024-01-01.json").exists()
        assert (snapshots_dir / f"snapshot-{_RECENT}.json").exists()
