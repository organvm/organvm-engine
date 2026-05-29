"""Tests for the omega scorecard module."""

import json

import pytest

from organvm_engine.omega.scorecard import (
    NetworkTestamentResult,
    _check_network_testament,
    analyze_soak_streak,
    diff_snapshots,
    evaluate,
    write_snapshot,
)


@pytest.fixture
def soak_dir(tmp_path):
    """Create a temporary soak-test directory with 8 days of data."""
    d = tmp_path / "soak-test"
    d.mkdir()
    for i in range(8):
        day = f"2026-02-{16 + i:02d}"
        snapshot = {
            "date": day,
            "validation": {
                "registry_pass": True,
                "dependency_pass": True,
            },
            "ci": {"total_checked": 77, "passing": 50, "failing": 25},
            "engagement": {"total_stars": 5, "total_forks": 3},
        }
        (d / f"daily-{day}.json").write_text(json.dumps(snapshot))
    return d


@pytest.fixture
def soak_dir_with_gap(tmp_path):
    """Soak dir with a gap on day 3."""
    d = tmp_path / "soak-test"
    d.mkdir()
    # Days: 16, 17, (gap 18), 19, 20, 21, 22, 23
    days = [16, 17, 19, 20, 21, 22, 23]
    for day_num in days:
        day = f"2026-02-{day_num:02d}"
        snapshot = {
            "date": day,
            "validation": {"registry_pass": True, "dependency_pass": True},
            "ci": {"total_checked": 77, "passing": 50, "failing": 25},
        }
        (d / f"daily-{day}.json").write_text(json.dumps(snapshot))
    return d


@pytest.fixture
def soak_dir_with_incident(tmp_path):
    """Soak dir with a critical incident."""
    d = tmp_path / "soak-test"
    d.mkdir()
    for i in range(3):
        day = f"2026-02-{16 + i:02d}"
        validation_pass = i != 1  # day 2 has an incident
        snapshot = {
            "date": day,
            "validation": {
                "registry_pass": validation_pass,
                "dependency_pass": True,
                **({"registry_issues": ["repo-x: duplicate entry"]} if not validation_pass else {}),
            },
            "ci": {"total_checked": 77, "passing": 50, "failing": 25},
        }
        (d / f"daily-{day}.json").write_text(json.dumps(snapshot))
    return d


@pytest.fixture
def registry():
    return {
        "version": "2.0",
        "organs": {
            "ORGAN-III": {
                "name": "Commerce",
                "launch_status": "OPERATIONAL",
                "repositories": [
                    {
                        "name": "product-app",
                        "org": "organvm-iii-ergon",
                        "implementation_status": "ACTIVE",
                        "public": True,
                        "description": "Test product",
                        "revenue_status": "pre-launch",
                    },
                ],
            },
        },
    }


@pytest.fixture
def registry_with_revenue():
    return {
        "version": "2.0",
        "organs": {
            "ORGAN-III": {
                "name": "Commerce",
                "launch_status": "OPERATIONAL",
                "repositories": [
                    {
                        "name": "product-app",
                        "org": "organvm-iii-ergon",
                        "implementation_status": "ACTIVE",
                        "public": True,
                        "description": "Test product",
                        "revenue_status": "live",
                    },
                ],
            },
        },
    }


class TestSoakStreak:
    def test_consecutive_streak(self, soak_dir):
        result = analyze_soak_streak(soak_dir)
        assert result.total_snapshots == 8
        assert result.streak_days == 8
        assert result.first_date == "2026-02-16"
        assert result.last_date == "2026-02-23"
        assert result.gaps == []
        assert result.critical_incidents == 0

    def test_streak_with_gap(self, soak_dir_with_gap):
        result = analyze_soak_streak(soak_dir_with_gap)
        assert result.total_snapshots == 7
        # Streak from latest back: 23,22,21,20,19 = 5 consecutive
        assert result.streak_days == 5
        assert "2026-02-18" in result.gaps

    def test_critical_incidents(self, soak_dir_with_incident):
        result = analyze_soak_streak(soak_dir_with_incident)
        assert result.critical_incidents == 1

    def test_empty_dir(self, tmp_path):
        empty = tmp_path / "empty-soak"
        empty.mkdir()
        result = analyze_soak_streak(empty)
        assert result.total_snapshots == 0
        assert result.streak_days == 0

    def test_nonexistent_dir(self, tmp_path):
        result = analyze_soak_streak(tmp_path / "nonexistent")
        assert result.total_snapshots == 0

    def test_days_remaining(self, soak_dir):
        result = analyze_soak_streak(soak_dir)
        assert result.days_remaining == 22  # 30 - 8

    def test_target_not_met_short_streak(self, soak_dir):
        result = analyze_soak_streak(soak_dir)
        assert not result.target_met

    def test_target_met_30_days(self, tmp_path):
        d = tmp_path / "soak-test"
        d.mkdir()
        for i in range(30):
            day = f"2026-02-{16 + i:02d}" if 16 + i <= 28 else f"2026-03-{16 + i - 28:02d}"
            snapshot = {
                "date": day,
                "validation": {"registry_pass": True, "dependency_pass": True},
            }
            (d / f"daily-{day}.json").write_text(json.dumps(snapshot))
        result = analyze_soak_streak(d)
        assert result.streak_days == 30
        assert result.target_met


class TestEvaluate:
    def test_returns_20_criteria(self, registry, soak_dir):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        assert len(scorecard.criteria) == 20
        assert scorecard.total == 20

    def test_criterion_6_always_met(self, registry, soak_dir):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        c6 = scorecard.criteria[5]  # 0-indexed
        assert c6.id == 6
        assert c6.status == "MET"

    def test_soak_in_progress(self, registry, soak_dir):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        c1 = scorecard.criteria[0]
        assert c1.status == "IN_PROGRESS"
        assert "8/30" in c1.value

    def test_soak_not_started(self, registry, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        scorecard = evaluate(registry=registry, soak_dir=empty)
        c1 = scorecard.criteria[0]
        assert c1.status == "NOT_MET"

    def test_product_quality_not_met(self, registry, soak_dir):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        c9 = scorecard.criteria[8]
        assert c9.id == 9
        assert c9.status == "NOT_MET"
        assert "stranger-ready" in c9.name

    def test_organic_discovery_in_progress(self, registry, soak_dir):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        c10 = scorecard.criteria[9]
        assert c10.id == 10
        assert c10.status == "IN_PROGRESS"
        assert "visitor" in c10.name

    def test_organic_revenue_is_criterion_18(self, registry, soak_dir):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        c18 = scorecard.criteria[17]
        assert c18.id == 18
        assert "organic revenue" in c18.name.lower()
        assert c18.horizon == "H5"

    def test_met_count(self, registry, soak_dir, tmp_path):
        # Pin workspace_root + corpus_dir to an empty tmp dir so the auto-evaluated
        # criteria (#19 network testament, #20 sigma-E) read controlled, empty
        # inputs instead of leaking the real filesystem — keeps the count hermetic.
        scorecard = evaluate(
            registry=registry,
            soak_dir=soak_dir,
            workspace_root=tmp_path,
            corpus_dir=tmp_path,
        )
        # Exactly the 5 _KNOWN_MET (#5, #6, #8, #13, #15); the auto criteria
        # (#1/#3/#17/#19/#20) are not MET with empty inputs.
        assert scorecard.met_count == 5

    def test_summary_output(self, registry, soak_dir):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        summary = scorecard.summary()
        assert f"{scorecard.met_count}/{scorecard.total} MET" in summary
        assert "Soak Test Streak" in summary
        assert "8/30" in summary

    def test_to_dict(self, registry, soak_dir):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        d = scorecard.to_dict()
        assert d["score"] == scorecard.met_count
        assert d["total"] == 20
        assert len(d["criteria"]) == 20
        assert "soak" in d
        assert d["soak"]["streak_days"] == 8

    def test_auto_criteria_identified(self, registry, soak_dir):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        auto_ids = {c.id for c in scorecard.criteria if c.auto}
        assert auto_ids == {1, 3, 17, 19, 20}


class TestWriteSnapshot:
    def test_writes_json_file(self, registry, soak_dir, tmp_path):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        path = write_snapshot(scorecard, corpus_dir=tmp_path)
        assert path.exists()
        assert path.name.startswith("omega-status-")
        assert path.suffix == ".json"

    def test_snapshot_content(self, registry, soak_dir, tmp_path):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        path = write_snapshot(scorecard, corpus_dir=tmp_path)
        data = json.loads(path.read_text())
        assert data["score"] == scorecard.met_count
        assert data["total"] == 20
        assert len(data["criteria"]) == 20

    def test_creates_omega_dir(self, registry, soak_dir, tmp_path):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        write_snapshot(scorecard, corpus_dir=tmp_path)
        assert (tmp_path / "data" / "omega").is_dir()

    def test_diff_no_previous(self, registry, soak_dir, tmp_path):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        changes = diff_snapshots(scorecard, corpus_dir=tmp_path)
        assert any("No previous" in c for c in changes)

    def test_diff_detects_change(self, registry, soak_dir, tmp_path):
        # Write a snapshot, then manually alter it to simulate a score change
        sc1 = evaluate(registry=registry, soak_dir=soak_dir)
        write_snapshot(sc1, corpus_dir=tmp_path)

        # Modify the saved snapshot to have a different score
        omega_dir = tmp_path / "data" / "omega"
        snap_files = sorted(omega_dir.glob("omega-status-*.json"))
        assert snap_files
        data = json.loads(snap_files[-1].read_text())
        data["score"] = data["score"] - 1  # pretend one fewer MET
        snap_files[-1].write_text(json.dumps(data))

        # Re-evaluate → score differs from saved snapshot
        sc2 = evaluate(registry=registry, soak_dir=soak_dir)
        changes = diff_snapshots(sc2, corpus_dir=tmp_path)
        assert any("Score changed" in c for c in changes)

    def test_diff_no_change(self, registry, soak_dir, tmp_path):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        write_snapshot(scorecard, corpus_dir=tmp_path)
        changes = diff_snapshots(scorecard, corpus_dir=tmp_path)
        assert any("No changes" in c for c in changes)


class TestNetworkTestament:
    def test_result_not_met_by_default(self):
        result = NetworkTestamentResult()
        assert not result.met
        assert result.density == 0.0
        assert result.velocity == 0.0
        assert result.milestones == 0

    def test_result_met_when_all_conditions_satisfied(self):
        result = NetworkTestamentResult(
            density=0.6, velocity=0.5, milestones=1,
            maps_found=10, total_mirrors=30, ledger_entries=15,
        )
        assert result.met

    def test_result_not_met_low_density(self):
        result = NetworkTestamentResult(density=0.3, velocity=0.5, milestones=1)
        assert not result.met

    def test_result_not_met_zero_velocity(self):
        result = NetworkTestamentResult(density=0.6, velocity=0.0, milestones=1)
        assert not result.met

    def test_result_not_met_no_milestones(self):
        result = NetworkTestamentResult(density=0.6, velocity=0.5, milestones=0)
        assert not result.met

    def test_check_empty_workspace(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        result = _check_network_testament(workspace_root=ws, corpus_dir=corpus)
        assert result.maps_found == 0
        assert result.density == 0.0
        assert result.milestones == 0

    def test_check_milestones_counted(self, tmp_path):
        corpus = tmp_path / "corpus"
        milestones_dir = corpus / "data" / "testament" / "milestones"
        milestones_dir.mkdir(parents=True)
        (milestones_dir / "first-mirror.md").write_text("# First mirror milestone")
        (milestones_dir / "engagement-started.json").write_text("{}")
        (milestones_dir / "not-a-milestone.txt").touch()  # wrong extension
        ws = tmp_path / "workspace"
        ws.mkdir()
        result = _check_network_testament(workspace_root=ws, corpus_dir=corpus)
        assert result.milestones == 2  # .md and .json count, .txt does not

    def test_criterion_19_in_evaluate(self, registry, soak_dir):
        scorecard = evaluate(registry=registry, soak_dir=soak_dir)
        c19 = scorecard.criteria[18]  # 0-indexed
        assert c19.id == 19
        assert "Network Testament" in c19.name
        assert c19.horizon == "H3"
        assert c19.auto is True
        assert "density=" in c19.value

    def test_criterion_19_status_reflects_data(self, registry, soak_dir, tmp_path, monkeypatch):
        # With empty workspace + corpus + no ledger, should be NOT_MET
        ws = tmp_path / "workspace"
        ws.mkdir()
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        # Block the ledger from reading real production data
        import organvm_engine.network.ledger as _ledger_mod
        monkeypatch.setattr(_ledger_mod, "DEFAULT_LEDGER_PATH", tmp_path / "empty-ledger.jsonl")
        scorecard = evaluate(
            registry=registry, soak_dir=soak_dir,
            workspace_root=ws, corpus_dir=corpus,
        )
        c19 = scorecard.criteria[18]
        assert c19.status == "NOT_MET"
