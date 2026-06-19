"""Tests for the network testament module.

Covers: schema, mapper, ledger, scanner, metrics, query, discover, synthesizer.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from organvm_engine.network import ENGAGEMENT_FORMS, MIRROR_LENSES, NETWORK_MAP_FILENAME
from organvm_engine.network.discover import (
    KINSHIP_COMMUNITIES,
    suggest_kinship_mirrors,
    suggest_parallel_mirrors,
)
from organvm_engine.network.ledger import (
    create_engagement,
    ledger_summary,
    log_engagement,
    read_ledger,
)
from organvm_engine.network.mapper import (
    merge_mirrors,
    read_network_map,
    validate_network_map,
    write_network_map,
)
from organvm_engine.network.metrics import (
    convergence_points,
    engagement_velocity,
    form_balance,
    lens_balance,
    mirror_coverage,
    network_density,
    network_reciprocity,
)
from organvm_engine.network.query import (
    blind_spots,
    engagement_targets,
    organ_density,
    repos_mirroring,
)
from organvm_engine.network.scanner import (
    scan_cargo_toml,
    scan_go_mod,
    scan_package_json,
    scan_pyproject,
    scan_repo_dependencies,
)
from organvm_engine.network.schema import EngagementEntry, MirrorEntry, NetworkMap
from organvm_engine.network.synthesizer import (
    _period_filter,
    synthesize_testament,
    write_testament,
)

# ─── Fixtures ───────────────────────────────────────────────────────────


def _make_mirror(project: str = "astral-sh/ruff", platform: str = "github",
                 relevance: str = "Linter", **kwargs) -> MirrorEntry:
    return MirrorEntry(project=project, platform=platform, relevance=relevance, **kwargs)


def _make_map(repo: str = "organvm-engine", organ: str = "META",
              technical: int = 1, parallel: int = 0, kinship: int = 0) -> NetworkMap:
    tech = [_make_mirror(f"tech-{i}", relevance=f"dep-{i}") for i in range(technical)]
    par = [_make_mirror(f"par-{i}", platform="github", relevance=f"parallel-{i}")
           for i in range(parallel)]
    kin = [_make_mirror(f"kin-{i}", platform="community", relevance=f"kinship-{i}")
           for i in range(kinship)]
    return NetworkMap(
        schema_version="1.0", repo=repo, organ=organ,
        technical=tech, parallel=par, kinship=kin,
    )


def _make_entry(
    repo: str = "organvm-engine",
    project: str = "astral-sh/ruff",
    lens: str = "technical",
    action_type: str = "contribution",
    detail: str = "Filed issue",
    timestamp: str | None = None,
    outcome: str | None = None,
) -> EngagementEntry:
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    return EngagementEntry(
        timestamp=ts, organvm_repo=repo, external_project=project,
        lens=lens, action_type=action_type, action_detail=detail,
        outcome=outcome,
    )


# ─── Constants ──────────────────────────────────────────────────────────


class TestConstants:
    def test_mirror_lenses_are_three(self):
        assert {"technical", "parallel", "kinship"} == MIRROR_LENSES

    def test_engagement_forms_are_four(self):
        assert {"presence", "contribution", "dialogue", "invitation"} == ENGAGEMENT_FORMS

    def test_filename_is_correct(self):
        assert NETWORK_MAP_FILENAME == "network-map.yaml"


# ─── Schema ─────────────────────────────────────────────────────────────


class TestMirrorEntry:
    def test_to_dict_minimal(self):
        m = MirrorEntry(project="foo/bar", platform="github", relevance="test")
        d = m.to_dict()
        assert d["project"] == "foo/bar"
        assert "url" not in d
        assert "tags" not in d

    def test_to_dict_full(self):
        m = MirrorEntry(
            project="foo/bar", platform="community", relevance="test",
            engagement=["watch"], url="https://example.com",
            tags=["a", "b"], notes="note",
        )
        d = m.to_dict()
        assert d["url"] == "https://example.com"
        assert d["tags"] == ["a", "b"]
        assert d["notes"] == "note"

    def test_roundtrip(self):
        m = _make_mirror(engagement=["watch", "issues"], tags=["python"])
        d = m.to_dict()
        m2 = MirrorEntry.from_dict(d)
        assert m2.project == m.project
        assert m2.engagement == m.engagement
        assert m2.tags == m.tags

    def test_from_dict_defaults(self):
        m = MirrorEntry.from_dict({"project": "x"})
        assert m.platform == "github"
        assert m.engagement == []
        assert m.url is None


class TestNetworkMap:
    def test_all_mirrors(self):
        nmap = _make_map(technical=2, parallel=1, kinship=3)
        assert len(nmap.all_mirrors) == 6

    def test_mirror_count(self):
        nmap = _make_map(technical=0, parallel=0, kinship=0)
        assert nmap.mirror_count == 0
        nmap2 = _make_map(technical=5)
        assert nmap2.mirror_count == 5

    def test_mirrors_by_lens(self):
        nmap = _make_map(technical=2, parallel=3)
        assert len(nmap.mirrors_by_lens("technical")) == 2
        assert len(nmap.mirrors_by_lens("parallel")) == 3
        assert len(nmap.mirrors_by_lens("kinship")) == 0

    def test_to_dict_structure(self):
        nmap = _make_map(technical=1, kinship=1)
        d = nmap.to_dict()
        assert "mirrors" in d
        assert "technical" in d["mirrors"]
        assert "parallel" in d["mirrors"]
        assert "kinship" in d["mirrors"]
        assert len(d["mirrors"]["technical"]) == 1
        assert len(d["mirrors"]["kinship"]) == 1

    def test_roundtrip(self):
        nmap = _make_map(repo="test-repo", organ="ORGAN-I", technical=2, parallel=1, kinship=1)
        d = nmap.to_dict()
        nmap2 = NetworkMap.from_dict(d)
        assert nmap2.repo == "test-repo"
        assert nmap2.organ == "ORGAN-I"
        assert len(nmap2.technical) == 2
        assert len(nmap2.parallel) == 1
        assert len(nmap2.kinship) == 1

    def test_from_dict_defaults(self):
        nmap = NetworkMap.from_dict({"repo": "x", "organ": "META"})
        assert nmap.schema_version == "1.0"
        assert nmap.technical == []
        assert nmap.last_scanned is None


class TestEngagementEntry:
    def test_to_dict_minimal(self):
        e = _make_entry()
        d = e.to_dict()
        assert "timestamp" in d
        assert "organvm_repo" in d
        assert "url" not in d

    def test_to_dict_full(self):
        e = _make_entry(outcome="merged")
        e.url = "https://github.com/x/y/pull/1"
        e.tags = ["upstream"]
        d = e.to_dict()
        assert d["outcome"] == "merged"
        assert d["url"] == "https://github.com/x/y/pull/1"
        assert d["tags"] == ["upstream"]

    def test_roundtrip(self):
        e = _make_entry(outcome="acknowledged")
        d = e.to_dict()
        e2 = EngagementEntry.from_dict(d)
        assert e2.organvm_repo == e.organvm_repo
        assert e2.outcome == "acknowledged"


# ─── Mapper ─────────────────────────────────────────────────────────────


class TestMapper:
    def test_write_and_read(self, tmp_path: Path):
        nmap = _make_map(technical=2, kinship=1)
        out = tmp_path / "network-map.yaml"
        write_network_map(nmap, out)
        loaded = read_network_map(out)
        assert loaded.repo == nmap.repo
        assert len(loaded.technical) == 2
        assert len(loaded.kinship) == 1

    def test_read_invalid_yaml(self, tmp_path: Path):
        bad = tmp_path / "network-map.yaml"
        bad.write_text("not: a: valid: [")
        with pytest.raises(yaml.YAMLError):
            read_network_map(bad)

    def test_read_non_mapping(self, tmp_path: Path):
        bad = tmp_path / "network-map.yaml"
        bad.write_text("- list\n- items\n")
        with pytest.raises(ValueError, match="not a YAML mapping"):
            read_network_map(bad)

    def test_write_creates_parent_dirs(self, tmp_path: Path):
        nmap = _make_map()
        out = tmp_path / "deep" / "nested" / "network-map.yaml"
        write_network_map(nmap, out)
        assert out.exists()

    def test_validate_valid(self):
        data = {
            "repo": "test", "organ": "META",
            "mirrors": {
                "technical": [{"project": "x", "platform": "github", "engagement": []}],
                "parallel": [], "kinship": [],
            },
        }
        assert validate_network_map(data) == []

    def test_validate_missing_fields(self):
        errors = validate_network_map({})
        assert any("repo" in e for e in errors)
        assert any("organ" in e for e in errors)

    def test_validate_bad_mirrors_type(self):
        errors = validate_network_map({"repo": "x", "organ": "M", "mirrors": "bad"})
        assert any("mapping" in e for e in errors)

    def test_validate_missing_project(self):
        data = {
            "repo": "x", "organ": "M",
            "mirrors": {"technical": [{"platform": "github"}], "parallel": [], "kinship": []},
        }
        errors = validate_network_map(data)
        assert any("project" in e for e in errors)

    def test_validate_missing_platform(self):
        data = {
            "repo": "x", "organ": "M",
            "mirrors": {"technical": [{"project": "x"}], "parallel": [], "kinship": []},
        }
        errors = validate_network_map(data)
        assert any("platform" in e for e in errors)

    def test_validate_bad_engagement_type(self):
        data = {
            "repo": "x", "organ": "M",
            "mirrors": {
                "technical": [{"project": "x", "platform": "g", "engagement": "bad"}],
                "parallel": [], "kinship": [],
            },
        }
        errors = validate_network_map(data)
        assert any("engagement" in e for e in errors)

    def test_merge_no_duplicates(self):
        existing = [_make_mirror("a/b"), _make_mirror("c/d")]
        discovered = [_make_mirror("c/d"), _make_mirror("e/f")]
        merged = merge_mirrors(existing, discovered)
        assert len(merged) == 3
        projects = [m.project for m in merged]
        assert "a/b" in projects
        assert "c/d" in projects
        assert "e/f" in projects

    def test_merge_existing_takes_precedence(self):
        existing = [MirrorEntry(project="a/b", platform="github",
                                relevance="Human curated", engagement=["contributions"])]
        discovered = [MirrorEntry(project="a/b", platform="github",
                                  relevance="Auto-discovered", engagement=["watch"])]
        merged = merge_mirrors(existing, discovered)
        assert len(merged) == 1
        assert merged[0].relevance == "Human curated"

    def test_discover_in_workspace(self, tmp_path: Path):
        from organvm_engine.network.mapper import discover_network_maps

        # Create workspace structure with network maps
        organ = tmp_path / "organ-x"
        repo = organ / "repo-a"
        repo.mkdir(parents=True)
        nmap = _make_map(repo="repo-a", organ="X", technical=1)
        write_network_map(nmap, repo / NETWORK_MAP_FILENAME)

        found = discover_network_maps(tmp_path)
        assert len(found) == 1
        assert found[0][1].repo == "repo-a"


# ─── Ledger ─────────────────────────────────────────────────────────────


class TestLedger:
    def test_log_and_read(self, tmp_path: Path):
        ledger = tmp_path / "ledger.jsonl"
        entry = _make_entry(detail="test action")
        log_engagement(entry, ledger)
        entries = read_ledger(ledger)
        assert len(entries) == 1
        assert entries[0].action_detail == "test action"

    def test_log_creates_dirs(self, tmp_path: Path):
        ledger = tmp_path / "deep" / "path" / "ledger.jsonl"
        entry = _make_entry()
        log_engagement(entry, ledger)
        assert ledger.exists()

    def test_log_appends(self, tmp_path: Path):
        ledger = tmp_path / "ledger.jsonl"
        log_engagement(_make_entry(detail="first"), ledger)
        log_engagement(_make_entry(detail="second"), ledger)
        entries = read_ledger(ledger)
        assert len(entries) == 2

    def test_read_nonexistent(self, tmp_path: Path):
        entries = read_ledger(tmp_path / "nope.jsonl")
        assert entries == []

    def test_read_with_malformed_lines(self, tmp_path: Path):
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_text("not json\n" + json.dumps(_make_entry().to_dict()) + "\n")
        entries = read_ledger(ledger)
        assert len(entries) == 1

    def test_filter_by_repo(self, tmp_path: Path):
        ledger = tmp_path / "ledger.jsonl"
        log_engagement(_make_entry(repo="a"), ledger)
        log_engagement(_make_entry(repo="b"), ledger)
        entries = read_ledger(ledger, repo="a")
        assert len(entries) == 1
        assert entries[0].organvm_repo == "a"

    def test_filter_by_lens(self, tmp_path: Path):
        ledger = tmp_path / "ledger.jsonl"
        log_engagement(_make_entry(lens="technical"), ledger)
        log_engagement(_make_entry(lens="kinship"), ledger)
        entries = read_ledger(ledger, lens="kinship")
        assert len(entries) == 1
        assert entries[0].lens == "kinship"

    def test_filter_by_action_type(self, tmp_path: Path):
        ledger = tmp_path / "ledger.jsonl"
        log_engagement(_make_entry(action_type="presence"), ledger)
        log_engagement(_make_entry(action_type="contribution"), ledger)
        entries = read_ledger(ledger, action_type="contribution")
        assert len(entries) == 1

    def test_filter_by_since(self, tmp_path: Path):
        ledger = tmp_path / "ledger.jsonl"
        old = _make_entry(timestamp="2020-01-01T00:00:00+00:00")
        new = _make_entry(timestamp="2026-03-20T00:00:00+00:00")
        log_engagement(old, ledger)
        log_engagement(new, ledger)
        entries = read_ledger(ledger, since="2025-01-01T00:00:00+00:00")
        assert len(entries) == 1

    def test_create_engagement_timestamp(self):
        entry = create_engagement(
            organvm_repo="x", external_project="y",
            lens="technical", action_type="presence",
            action_detail="test",
        )
        assert entry.timestamp  # non-empty
        assert "T" in entry.timestamp  # ISO format

    def test_ledger_summary_empty(self, tmp_path: Path):
        s = ledger_summary(tmp_path / "empty.jsonl")
        assert s["total_actions"] == 0
        assert s["unique_projects"] == 0

    def test_ledger_summary(self, tmp_path: Path):
        ledger = tmp_path / "ledger.jsonl"
        log_engagement(_make_entry(project="a", lens="technical", action_type="presence"), ledger)
        log_engagement(_make_entry(project="b", lens="kinship", action_type="dialogue"), ledger)
        log_engagement(_make_entry(project="a", lens="technical", action_type="contribution"), ledger)
        s = ledger_summary(ledger)
        assert s["total_actions"] == 3
        assert s["unique_projects"] == 2
        assert s["by_lens"]["technical"] == 2
        assert s["by_lens"]["kinship"] == 1


# ─── Scanner ────────────────────────────────────────────────────────────


class TestScanner:
    def test_scan_pyproject(self, tmp_path: Path):
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\ndependencies = [\n  "pyyaml>=6.0",\n  "click>=8.0",\n]\n',
        )
        mirrors = scan_pyproject(tmp_path)
        projects = {m.project for m in mirrors}
        assert "yaml/pyyaml" in projects
        assert "pallets/click" in projects

    def test_scan_pyproject_optional(self, tmp_path: Path):
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project.optional-dependencies]\ndev = [\n  "pytest>=7.0",\n  "ruff>=0.1",\n]\n',
        )
        mirrors = scan_pyproject(tmp_path)
        projects = {m.project for m in mirrors}
        assert "pytest-dev/pytest" in projects
        assert "astral-sh/ruff" in projects

    def test_scan_pyproject_missing(self, tmp_path: Path):
        assert scan_pyproject(tmp_path) == []

    def test_scan_package_json(self, tmp_path: Path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({
            "dependencies": {"react": "^18.0", "next": "^14.0"},
            "devDependencies": {"typescript": "^5.0"},
        }))
        mirrors = scan_package_json(tmp_path)
        projects = {m.project for m in mirrors}
        assert "facebook/react" in projects
        assert "vercel/next.js" in projects
        assert "microsoft/TypeScript" in projects

    def test_scan_package_json_missing(self, tmp_path: Path):
        assert scan_package_json(tmp_path) == []

    def test_scan_package_json_malformed(self, tmp_path: Path):
        pkg = tmp_path / "package.json"
        pkg.write_text("not json {")
        assert scan_package_json(tmp_path) == []

    def test_scan_go_mod(self, tmp_path: Path):
        go = tmp_path / "go.mod"
        go.write_text(
            "module example.com/mymod\n\ngo 1.21\n\n"
            "require (\n"
            "\tgithub.com/gorilla/mux v1.8.0\n"
            "\tgithub.com/gin-gonic/gin v1.9.0\n"
            ")\n",
        )
        mirrors = scan_go_mod(tmp_path)
        projects = {m.project for m in mirrors}
        assert "gorilla/mux" in projects
        assert "gin-gonic/gin" in projects

    def test_scan_go_mod_single_require(self, tmp_path: Path):
        go = tmp_path / "go.mod"
        go.write_text(
            "module example.com/mymod\n\n"
            "require github.com/gorilla/mux v1.8.0\n",
        )
        mirrors = scan_go_mod(tmp_path)
        assert len(mirrors) == 1
        assert mirrors[0].project == "gorilla/mux"

    def test_scan_go_mod_missing(self, tmp_path: Path):
        assert scan_go_mod(tmp_path) == []

    def test_scan_cargo_toml(self, tmp_path: Path):
        cargo = tmp_path / "Cargo.toml"
        cargo.write_text(
            "[package]\nname = \"myapp\"\n\n"
            "[dependencies]\ntokio = { version = \"1\", features = [\"full\"] }\n"
            "serde = \"1.0\"\n",
        )
        mirrors = scan_cargo_toml(tmp_path)
        projects = {m.project for m in mirrors}
        assert "tokio-rs/tokio" in projects
        assert "serde-rs/serde" in projects

    def test_scan_cargo_toml_missing(self, tmp_path: Path):
        assert scan_cargo_toml(tmp_path) == []

    def test_scan_repo_deduplicates(self, tmp_path: Path):
        # Both pyproject and package.json have overlapping deps (vitest)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = [\n  "pyyaml>=6.0",\n]\n',
        )
        (tmp_path / "package.json").write_text(json.dumps({
            "dependencies": {"react": "^18"},
        }))
        mirrors = scan_repo_dependencies(tmp_path)
        projects = [m.project for m in mirrors]
        assert len(projects) == len(set(projects))

    def test_scan_tags_auto_discovered(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = [\n  "ruff>=0.1",\n]\n',
        )
        mirrors = scan_pyproject(tmp_path)
        assert "auto-discovered" in mirrors[0].tags


# ─── Metrics ────────────────────────────────────────────────────────────


class TestMetrics:
    def test_network_density_zero(self):
        assert network_density([], 10) == 0.0

    def test_network_density_full(self):
        maps = [_make_map(technical=1), _make_map(technical=1)]
        assert network_density(maps, 2) == 1.0

    def test_network_density_partial(self):
        maps = [_make_map(technical=1), _make_map(technical=0)]
        assert network_density(maps, 4) == 0.25

    def test_network_density_zero_repos(self):
        assert network_density([], 0) == 0.0

    def test_mirror_coverage_empty(self):
        cov = mirror_coverage([])
        assert cov == {"technical": 0.0, "parallel": 0.0, "kinship": 0.0}

    def test_mirror_coverage_all_technical(self):
        maps = [_make_map(technical=2), _make_map(technical=1)]
        cov = mirror_coverage(maps)
        assert cov["technical"] == 1.0
        assert cov["parallel"] == 0.0

    def test_mirror_coverage_mixed(self):
        maps = [
            _make_map(technical=1, parallel=1, kinship=1),
            _make_map(technical=1, parallel=0, kinship=0),
        ]
        cov = mirror_coverage(maps)
        assert cov["technical"] == 1.0
        assert cov["parallel"] == 0.5
        assert cov["kinship"] == 0.5

    def test_engagement_velocity_empty(self):
        assert engagement_velocity([], 30) == 0.0

    def test_engagement_velocity(self):
        entries = [_make_entry() for _ in range(15)]
        assert engagement_velocity(entries, 30) == 0.5

    def test_engagement_velocity_zero_days(self):
        assert engagement_velocity([_make_entry()], 0) == 0.0

    def test_network_reciprocity_empty(self):
        assert network_reciprocity([]) == 0.0

    def test_network_reciprocity_full(self):
        entries = [_make_entry(outcome="merged"), _make_entry(outcome="acknowledged")]
        assert network_reciprocity(entries) == 1.0

    def test_network_reciprocity_partial(self):
        entries = [_make_entry(outcome="merged"), _make_entry()]
        assert network_reciprocity(entries) == 0.5

    def test_lens_balance_empty(self):
        b = lens_balance([])
        assert all(v == 0.0 for v in b.values())

    def test_lens_balance_uniform(self):
        entries = [
            _make_entry(lens="technical"),
            _make_entry(lens="parallel"),
            _make_entry(lens="kinship"),
        ]
        b = lens_balance(entries)
        assert abs(b["technical"] - 1 / 3) < 0.01

    def test_form_balance_empty(self):
        b = form_balance([])
        assert all(v == 0.0 for v in b.values())

    def test_form_balance(self):
        entries = [
            _make_entry(action_type="presence"),
            _make_entry(action_type="contribution"),
        ]
        b = form_balance(entries)
        assert b["presence"] == 0.5
        assert b["contribution"] == 0.5
        assert b["dialogue"] == 0.0

    def test_convergence_points_none(self):
        maps = [_make_map(repo="a", technical=1), _make_map(repo="b", technical=1)]
        # Different project names (tech-0 for both, but same project)
        # Actually they both have "tech-0", so they converge
        cp = convergence_points(maps)
        assert "tech-0" in cp
        assert len(cp["tech-0"]) == 2

    def test_convergence_points_no_overlap(self):
        m1 = NetworkMap(
            schema_version="1.0", repo="a", organ="X",
            technical=[_make_mirror("x/y")],
        )
        m2 = NetworkMap(
            schema_version="1.0", repo="b", organ="X",
            technical=[_make_mirror("p/q")],
        )
        cp = convergence_points([m1, m2])
        assert cp == {}


# ─── Query ──────────────────────────────────────────────────────────────


class TestQuery:
    def test_repos_mirroring(self):
        m1 = NetworkMap(
            schema_version="1.0", repo="a", organ="X",
            technical=[_make_mirror("shared/proj")],
        )
        m2 = NetworkMap(
            schema_version="1.0", repo="b", organ="X",
            technical=[_make_mirror("shared/proj"), _make_mirror("other/proj")],
        )
        result = repos_mirroring([m1, m2], "shared/proj")
        assert set(result) == {"a", "b"}

    def test_repos_mirroring_none(self):
        m1 = NetworkMap(
            schema_version="1.0", repo="a", organ="X",
            technical=[_make_mirror("x/y")],
        )
        assert repos_mirroring([m1], "not/found") == []

    def test_blind_spots(self):
        maps = [_make_map(repo="a", technical=1)]
        spots = blind_spots(maps, ["a", "b", "c"])
        assert "b" in spots
        assert "c" in spots
        assert "a" not in spots

    def test_blind_spots_empty_maps(self):
        maps = [_make_map(repo="a", technical=0)]
        spots = blind_spots(maps, ["a", "b"])
        assert "a" in spots  # has map but zero mirrors
        assert "b" in spots

    def test_organ_density(self):
        maps = [
            _make_map(repo="a", organ="META", technical=2, parallel=1, kinship=0),
            _make_map(repo="b", organ="META", technical=0, parallel=0, kinship=3),
            _make_map(repo="c", organ="ORGAN-I", technical=1, parallel=0, kinship=0),
        ]
        d = organ_density(maps)
        assert d["META"]["technical"] == 2
        assert d["META"]["parallel"] == 1
        assert d["META"]["kinship"] == 3
        assert d["META"]["total"] == 6
        assert d["ORGAN-I"]["total"] == 1

    def test_engagement_targets(self):
        m = NetworkMap(
            schema_version="1.0", repo="a", organ="X",
            technical=[_make_mirror("x/y")],
            parallel=[_make_mirror("p/q", platform="github", relevance="parallel")],
        )
        targets = engagement_targets([m])
        assert len(targets) == 2
        assert targets[0]["lens"] == "technical"
        assert targets[1]["lens"] == "parallel"

    def test_engagement_targets_filter_lens(self):
        m = NetworkMap(
            schema_version="1.0", repo="a", organ="X",
            technical=[_make_mirror("x/y")],
            kinship=[_make_mirror("k/l", platform="community", relevance="values")],
        )
        targets = engagement_targets([m], lens="kinship")
        assert len(targets) == 1
        assert targets[0]["lens"] == "kinship"


# ─── Discover ───────────────────────────────────────────────────────────


class TestDiscover:
    def test_suggest_parallel_by_tag(self):
        suggestions = suggest_parallel_mirrors(["mcp", "server"])
        assert any("modelcontextprotocol" in s.project for s in suggestions)

    def test_suggest_parallel_by_description(self):
        suggestions = suggest_parallel_mirrors([], repo_description="a generative art framework")
        assert any("generative-art" in s.tags for s in suggestions)

    def test_suggest_parallel_excludes_existing(self):
        suggestions = suggest_parallel_mirrors(
            ["mcp"],
            existing_projects={"modelcontextprotocol/servers"},
        )
        assert all(s.project != "modelcontextprotocol/servers" for s in suggestions)

    def test_suggest_parallel_empty(self):
        suggestions = suggest_parallel_mirrors(["totally-unrelated-xyz"])
        assert suggestions == []

    def test_suggest_kinship_by_tag(self):
        suggestions = suggest_kinship_mirrors(["creative-coding"])
        assert len(suggestions) > 0
        assert any("creative-coding" in s.tags for s in suggestions)

    def test_suggest_kinship_organ_ii(self):
        suggestions = suggest_kinship_mirrors([], organ="ORGAN-II")
        assert len(suggestions) > 0

    def test_suggest_kinship_organ_i(self):
        suggestions = suggest_kinship_mirrors([], organ="ORGAN-I")
        assert any(s.project == "tools-for-thought" for s in suggestions)

    def test_suggest_kinship_excludes_existing(self):
        suggestions = suggest_kinship_mirrors(
            ["creative-coding"],
            existing_projects={"creative-coding-community"},
        )
        assert all(s.project != "creative-coding-community" for s in suggestions)

    def test_suggest_kinship_deduplicates(self):
        suggestions = suggest_kinship_mirrors(
            ["creative-coding", "art-tech"],
            organ="ORGAN-II",
        )
        projects = [s.project for s in suggestions]
        assert len(projects) == len(set(projects))


# ─── Kinship community dataset integrity ──────────────────────────────────

# The eight organ short-keys used in the kinship dataset's "organs" field.
_ORGAN_KEYS = frozenset({"I", "II", "III", "IV", "V", "VI", "VII", "META"})

# Platforms whose entries point at an external destination and so need a URL.
_URL_REQUIRED_PLATFORMS = frozenset({"community", "forum", "wiki", "discord"})


class TestKinshipDataset:
    def test_no_duplicate_project_slugs(self):
        """Every kinship community has a unique project slug (dedup invariant)."""
        slugs = [c["project"] for c in KINSHIP_COMMUNITIES]
        assert len(slugs) == len(set(slugs))

    def test_no_duplicate_urls(self):
        """Distinct communities point at distinct destinations."""
        urls = [c["url"] for c in KINSHIP_COMMUNITIES if c.get("url")]
        assert len(urls) == len(set(urls))

    def test_required_fields_present(self):
        """Each entry carries the fields downstream code reads."""
        for c in KINSHIP_COMMUNITIES:
            assert c.get("project"), c
            assert c.get("platform"), c
            assert c.get("relevance"), c
            assert c.get("tags"), c
            assert c.get("organs"), c

    def test_organs_are_valid_keys(self):
        """Every organ reference resolves to a known organ short-key."""
        for c in KINSHIP_COMMUNITIES:
            assert set(c["organs"]) <= _ORGAN_KEYS, c["project"]

    def test_url_present_for_external_platforms(self):
        """Web-facing communities carry a URL so engagement is actionable."""
        for c in KINSHIP_COMMUNITIES:
            if c["platform"] in _URL_REQUIRED_PLATFORMS:
                assert c.get("url"), c["project"]

    def test_every_organ_has_kinship_coverage(self):
        """No organ is a kinship blind spot — each has multiple communities."""
        counts = {k: 0 for k in _ORGAN_KEYS}
        for c in KINSHIP_COMMUNITIES:
            for organ in c["organs"]:
                counts[organ] += 1
        for organ, n in counts.items():
            assert n >= 3, f"organ {organ} thin: {n} communities"


class TestKinshipR3:
    """R3 research round (LIMEN-070, issue #66) — community identification."""

    # A sampling of the projects introduced in the third research round,
    # spanning cross-organ commons and each organ's lens.
    _R3_PROJECTS = frozenset({
        "sustainoss", "permacomputing", "solid-project", "digital-gardeners",
        "lesswrong", "principia-cybernetica", "metagov",
        "openprocessing", "hydra-community", "nime",
        "tinyseed", "open-startups",
        "opentelemetry-community", "opengitops", "srecon",
        "humanities-commons", "pubpub",
        "exercism", "the-odin-project", "hack-club",
        "matrix-community", "nostr-community",
        "all-contributors", "software-freedom-conservancy",
        "apache-software-foundation",
    })

    def test_r3_communities_present(self):
        slugs = {c["project"] for c in KINSHIP_COMMUNITIES}
        missing = self._R3_PROJECTS - slugs
        assert not missing, f"missing R3 communities: {sorted(missing)}"

    def test_r3_communities_are_suggestable(self):
        """A tag introduced by R3 surfaces its community via discovery."""
        suggestions = suggest_kinship_mirrors(["gitops"])
        assert any(s.project == "opengitops" for s in suggestions)

    def test_r3_decentralization_tag_matches(self):
        """R3 broadened ORGAN-VII decentralization kinship."""
        suggestions = suggest_kinship_mirrors(["decentralization"])
        projects = {s.project for s in suggestions}
        assert {"matrix-community", "nostr-community"} <= projects


# ─── Synthesizer ────────────────────────────────────────────────────────


class TestSynthesizer:
    def test_period_filter_all_time(self):
        entries = [_make_entry(timestamp="2020-01-01T00:00:00+00:00")]
        assert _period_filter(entries, "all-time") == entries

    def test_period_filter_weekly(self):
        old = _make_entry(timestamp="2020-01-01T00:00:00+00:00")
        new = _make_entry(timestamp=datetime.now(timezone.utc).isoformat())
        result = _period_filter([old, new], "weekly")
        assert len(result) == 1

    def test_period_filter_monthly(self):
        old = _make_entry(timestamp="2020-01-01T00:00:00+00:00")
        new = _make_entry(timestamp=datetime.now(timezone.utc).isoformat())
        result = _period_filter([old, new], "monthly")
        assert len(result) == 1

    def test_synthesize_empty(self, tmp_path: Path):
        # Use a tmp_path ledger to avoid picking up real ledger entries
        empty_ledger = tmp_path / "empty-ledger.jsonl"
        content = synthesize_testament(
            tmp_path, ledger_path=empty_ledger, total_active_repos=10,
        )
        assert "Network Testament" in content
        assert "Mirror Coverage" in content
        assert "No engagement actions" in content

    def test_synthesize_with_data(self, tmp_path: Path):
        # Create a network map
        organ = tmp_path / "organ-x"
        repo = organ / "repo-a"
        repo.mkdir(parents=True)
        nmap = _make_map(repo="repo-a", organ="X", technical=2, parallel=1)
        write_network_map(nmap, repo / NETWORK_MAP_FILENAME)

        # Create a ledger
        ledger = tmp_path / "ledger.jsonl"
        log_engagement(_make_entry(lens="technical", action_type="contribution"), ledger)
        log_engagement(_make_entry(lens="kinship", action_type="dialogue", outcome="ack"), ledger)

        content = synthesize_testament(
            tmp_path, ledger_path=ledger, period="all-time", total_active_repos=5,
        )
        assert "20.0%" in content  # density: 1/5
        assert "Engagement" in content
        assert "2" in content  # 2 actions

    def test_write_testament(self, tmp_path: Path):
        content = "# Test Testament\n\nContent here."
        out = write_testament(content, tmp_path, "monthly")
        assert out.exists()
        assert out.read_text() == content
        assert "network-synthesis" in out.name

    def test_write_testament_creates_dir(self, tmp_path: Path):
        target = tmp_path / "deep" / "testament"
        out = write_testament("content", target)
        assert out.exists()

    def test_synthesize_with_convergences(self, tmp_path: Path):
        """Convergence points appear in synthesis when multiple repos share mirrors."""
        organ = tmp_path / "organ-x"
        for name in ("repo-a", "repo-b"):
            d = organ / name
            d.mkdir(parents=True)
            nmap = NetworkMap(
                schema_version="1.0", repo=name, organ="X",
                technical=[MirrorEntry(
                    project="shared/proj", platform="github",
                    relevance="shared dep",
                )],
            )
            write_network_map(nmap, d / NETWORK_MAP_FILENAME)

        empty_ledger = tmp_path / "empty.jsonl"
        content = synthesize_testament(
            tmp_path, ledger_path=empty_ledger, period="all-time",
            total_active_repos=2,
        )
        assert "Convergence" in content
        assert "shared/proj" in content


# ─── Additional edge cases ──────────────────────────────────────────


class TestScannerEdgeCases:
    def test_cargo_dev_dependencies(self, tmp_path: Path):
        cargo = tmp_path / "Cargo.toml"
        cargo.write_text(
            "[package]\nname = \"myapp\"\n\n"
            "[dev-dependencies]\nclap = \"4.0\"\n",
        )
        mirrors = scan_cargo_toml(tmp_path)
        projects = {m.project for m in mirrors}
        assert "clap-rs/clap" in projects

    def test_go_mod_non_github(self, tmp_path: Path):
        """Non-GitHub Go modules are skipped."""
        go = tmp_path / "go.mod"
        go.write_text(
            "module example.com/mymod\n\n"
            "require (\n"
            "\tgolang.org/x/text v0.3.0\n"
            ")\n",
        )
        mirrors = scan_go_mod(tmp_path)
        assert mirrors == []

    def test_scan_pyproject_no_known_deps(self, tmp_path: Path):
        """Dependencies not in KNOWN_REPOS produce no mirrors."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\ndependencies = [\n  "totally-unknown-package>=1.0",\n]\n',
        )
        mirrors = scan_pyproject(tmp_path)
        assert mirrors == []

    def test_package_json_scoped_packages(self, tmp_path: Path):
        """Scoped npm packages (@org/name) are handled."""
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({
            "dependencies": {"@tailwindcss/forms": "^0.5"},
        }))
        # @tailwindcss/forms -> cleaned to "tailwindcss-forms" which isn't in KNOWN_REPOS
        mirrors = scan_package_json(tmp_path)
        assert mirrors == []  # correct: scoped pkg not in mapping


class TestDiscoverEdgeCases:
    def test_suggest_parallel_empty_inputs(self):
        """Empty tags and empty description = no suggestions."""
        assert suggest_parallel_mirrors([], repo_description="") == []

    def test_suggest_kinship_no_matching_tags(self):
        """Unrelated tags produce no kinship suggestions."""
        suggestions = suggest_kinship_mirrors(["quantum-physics-simulation"])
        assert suggestions == []

    def test_suggest_parallel_multiple_domains(self):
        """Tags matching multiple domains produce combined suggestions."""
        suggestions = suggest_parallel_mirrors(["mcp", "generative", "art"])
        # Should get both MCP and generative-art suggestions
        projects = {s.project for s in suggestions}
        assert any("modelcontextprotocol" in p for p in projects)


class TestMapperEdgeCases:
    def test_discover_skips_malformed(self, tmp_path: Path):
        """discover_network_maps skips repos with malformed YAML."""
        organ = tmp_path / "organ-x"
        good = organ / "good-repo"
        bad = organ / "bad-repo"
        good.mkdir(parents=True)
        bad.mkdir(parents=True)

        nmap = _make_map(repo="good-repo", organ="X", technical=1)
        write_network_map(nmap, good / NETWORK_MAP_FILENAME)

        (bad / NETWORK_MAP_FILENAME).write_text("- this is a list not a map\n")

        from organvm_engine.network.mapper import discover_network_maps
        found = discover_network_maps(tmp_path)
        assert len(found) == 1
        assert found[0][1].repo == "good-repo"

    def test_validate_extra_lens_keys_ok(self):
        """Unknown keys in mirrors are not flagged (extensibility)."""
        data = {
            "repo": "x", "organ": "M",
            "mirrors": {
                "technical": [], "parallel": [], "kinship": [],
            },
        }
        errors = validate_network_map(data)
        assert errors == []

    def test_validate_non_list_lens(self):
        """Non-list lens value is caught."""
        data = {
            "repo": "x", "organ": "M",
            "mirrors": {"technical": "string", "parallel": [], "kinship": []},
        }
        errors = validate_network_map(data)
        assert any("must be a list" in e for e in errors)


class TestLedgerEdgeCases:
    def test_multiple_filters_combined(self, tmp_path: Path):
        """Filtering by repo + lens simultaneously."""
        ledger = tmp_path / "ledger.jsonl"
        log_engagement(_make_entry(repo="a", lens="technical"), ledger)
        log_engagement(_make_entry(repo="a", lens="kinship"), ledger)
        log_engagement(_make_entry(repo="b", lens="technical"), ledger)
        entries = read_ledger(ledger, repo="a", lens="technical")
        assert len(entries) == 1

    def test_ledger_summary_by_form(self, tmp_path: Path):
        """Summary correctly counts by action form."""
        ledger = tmp_path / "ledger.jsonl"
        log_engagement(_make_entry(action_type="presence"), ledger)
        log_engagement(_make_entry(action_type="presence"), ledger)
        log_engagement(_make_entry(action_type="dialogue"), ledger)
        s = ledger_summary(ledger)
        assert s["by_form"]["presence"] == 2
        assert s["by_form"]["dialogue"] == 1


class TestMetricsEdgeCases:
    def test_convergence_across_lenses(self):
        """Same project in different lenses of different repos converges."""
        m1 = NetworkMap(
            schema_version="1.0", repo="a", organ="X",
            technical=[_make_mirror("shared/p")],
        )
        m2 = NetworkMap(
            schema_version="1.0", repo="b", organ="X",
            kinship=[_make_mirror("shared/p", platform="community", relevance="values")],
        )
        cp = convergence_points([m1, m2])
        assert "shared/p" in cp
        assert set(cp["shared/p"]) == {"a", "b"}

    def test_lens_balance_ignores_unknown(self):
        """Entries with invalid lens values don't crash balance."""
        entries = [
            _make_entry(lens="technical"),
            _make_entry(lens="unknown_lens"),
        ]
        b = lens_balance(entries)
        assert b["technical"] == 0.5  # 1 of 2

    def test_form_balance_ignores_unknown(self):
        """Entries with invalid form values don't crash balance."""
        entries = [
            _make_entry(action_type="presence"),
            _make_entry(action_type="unknown_form"),
        ]
        b = form_balance(entries)
        assert b["presence"] == 0.5
