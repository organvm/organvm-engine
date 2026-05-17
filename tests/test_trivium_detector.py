"""Tests for structural correspondence detection between organs."""

import json
from pathlib import Path

from organvm_engine.trivium.detector import (
    Correspondence,
    CorrespondenceType,
    detect_formation_correspondences,
    detect_functional_correspondences,
    detect_governance_correspondences,
    detect_maturity_correspondences,
    detect_naming_isomorphisms,
    detect_semantic_correspondences,
    detect_structural_correspondences,
    detect_technology_correspondences,
    scan_organ_pair,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "registry-trivium.json"


def _load_fixture() -> dict:
    with FIXTURE_PATH.open() as f:
        return json.load(f)


def test_correspondence_type_enum():
    assert len(CorrespondenceType) == 8


def test_correspondence_strength_range():
    c = Correspondence(
        correspondence_type=CorrespondenceType.NAMING,
        source_organ="a", target_organ="b",
        source_entity="x", target_entity="y",
        evidence="test", strength=0.5,
    )
    assert c.strength == 0.5


def test_correspondence_strength_validation():
    import pytest
    with pytest.raises(ValueError):
        Correspondence(
            correspondence_type=CorrespondenceType.NAMING,
            source_organ="a", target_organ="b",
            source_entity="x", target_entity="y",
            evidence="test", strength=1.5,
        )


def test_detect_naming_isomorphisms_empty():
    result = detect_naming_isomorphisms([], [])
    assert result == []


def test_detect_naming_isomorphisms_finds_parallel_repos():
    organ_a_repos = [
        {"name": "recursive-engine--generative-entity", "org": "org-a",
         "description": "Recursive computation"},
    ]
    organ_b_repos = [
        {"name": "recursive-tool--generative-util", "org": "org-b",
         "description": "Recursive tool for generation"},
    ]
    result = detect_naming_isomorphisms(organ_a_repos, organ_b_repos)
    assert len(result) >= 1
    assert any(c.correspondence_type == CorrespondenceType.NAMING for c in result)
    # "recursive" and "generative" should be shared stems
    assert any("recursive" in c.evidence for c in result)


def test_detect_naming_no_match():
    organ_a_repos = [
        {"name": "alpha-beta", "org": "org-a", "description": ""},
    ]
    organ_b_repos = [
        {"name": "gamma-delta", "org": "org-b", "description": ""},
    ]
    result = detect_naming_isomorphisms(organ_a_repos, organ_b_repos)
    assert result == []


def test_detect_structural_empty():
    result = detect_structural_correspondences([], [])
    assert result == []


def test_detect_structural_similar_counts():
    a = [{"org": "a", "tier": "standard"} for _ in range(3)]
    b = [{"org": "b", "tier": "standard"} for _ in range(3)]
    result = detect_structural_correspondences(a, b)
    assert len(result) >= 1
    assert any(c.correspondence_type == CorrespondenceType.STRUCTURAL for c in result)


def test_detect_functional_empty():
    result = detect_functional_correspondences([], [])
    assert result == []


def test_detect_functional_finds_dependency():
    a = [{"name": "upstream-lib", "org": "org-a"}]
    b = [{"name": "downstream-app", "org": "org-b",
          "dependencies": ["upstream-lib"]}]
    result = detect_functional_correspondences(a, b)
    assert len(result) == 1
    assert result[0].correspondence_type == CorrespondenceType.FUNCTIONAL
    assert result[0].strength == 0.9


def test_detect_semantic_empty():
    result = detect_semantic_correspondences([], [])
    assert result == []


def test_detect_semantic_shared_keywords():
    a = [{"name": "a", "org": "org-a",
          "description": "Recursive computation engine for generative entities"}]
    b = [{"name": "b", "org": "org-b",
          "description": "Recursive computation tool for generative utilities"}]
    result = detect_semantic_correspondences(a, b)
    assert len(result) >= 1
    assert any(c.correspondence_type == CorrespondenceType.SEMANTIC for c in result)


def test_scan_organ_pair_returns_report():
    report = scan_organ_pair("I", "III", registry_path=FIXTURE_PATH)
    assert "correspondences" in report
    assert "organ_a" in report
    assert report["organ_a"] == "I"
    assert "organ_b" in report
    assert report["organ_b"] == "III"
    assert isinstance(report["correspondences"], list)
    assert report["count"] >= 1


def test_scan_organ_pair_finds_naming():
    report = scan_organ_pair("I", "III", registry_path=FIXTURE_PATH)
    naming = [c for c in report["correspondences"] if c["type"] == "naming"]
    assert len(naming) >= 1


def test_scan_organ_pair_finds_functional():
    report = scan_organ_pair("I", "III", registry_path=FIXTURE_PATH)
    functional = [
        c for c in report["correspondences"] if c["type"] == "functional"
    ]
    assert len(functional) >= 1


def test_scan_organ_pair_no_registry():
    report = scan_organ_pair("I", "III")
    assert report["correspondences"] == []
    assert "No registry" in report["summary"]
    # Schema parity with success-case: every caller can sort/filter by these
    # without KeyError. Regression guard for the `organvm trivium scan --all`
    # crash that occurred when registry was unresolved.
    for key in ("organ_a", "organ_b", "by_type", "count", "avg_strength"):
        assert key in report, f"early-return missing key: {key}"
    assert report["count"] == 0
    assert report["avg_strength"] == 0.0
    assert report["by_type"] == {}


def test_scan_all_pairs_no_registry_sortable():
    from organvm_engine.trivium.detector import scan_all_pairs

    results = scan_all_pairs()
    assert len(results) == 28
    # Must not raise — this is the exact callsite that crashed in
    # cli/trivium.py:103 when avg_strength was missing from early-return.
    sorted(results, key=lambda x: -x["avg_strength"])


def test_scan_organ_pair_meta():
    report = scan_organ_pair("I", "META", registry_path=FIXTURE_PATH)
    assert report["organ_a"] == "I"
    assert report["organ_b"] == "META"


# Maturity correspondences


def test_detect_maturity_empty():
    result = detect_maturity_correspondences([], [])
    assert result == []


def test_detect_maturity_shared_statuses():
    a = [{"org": "a", "promotion_status": "GRADUATED"} for _ in range(3)]
    b = [{"org": "b", "promotion_status": "GRADUATED"} for _ in range(3)]
    result = detect_maturity_correspondences(a, b)
    assert len(result) >= 1
    assert result[0].correspondence_type == CorrespondenceType.MATURITY


def test_detect_maturity_different_statuses():
    a = [{"org": "a", "promotion_status": "LOCAL"} for _ in range(3)]
    b = [{"org": "b", "promotion_status": "GRADUATED"} for _ in range(3)]
    result = detect_maturity_correspondences(a, b)
    assert result == []


# Formation correspondences


def test_detect_formation_empty():
    result = detect_formation_correspondences([], [])
    assert result == []


def test_detect_formation_flagship_match():
    a = [{"name": "flagship-a", "org": "a", "tier": "flagship"}]
    b = [{"name": "flagship-b", "org": "b", "tier": "flagship"}]
    result = detect_formation_correspondences(a, b)
    assert len(result) == 1
    assert result[0].correspondence_type == CorrespondenceType.FORMATION
    assert result[0].strength == 0.7


def test_detect_formation_no_flagships():
    a = [{"name": "std-a", "org": "a", "tier": "standard"}]
    b = [{"name": "std-b", "org": "b", "tier": "standard"}]
    result = detect_formation_correspondences(a, b)
    assert result == []


# Technology correspondences


def test_detect_technology_empty():
    result = detect_technology_correspondences([], [])
    assert result == []


def test_detect_technology_shared_stack():
    a = [{"name": "api-server", "org": "a", "description": "FastAPI Python REST service"}]
    b = [{"name": "web-api", "org": "b", "description": "Python REST API with FastAPI"}]
    result = detect_technology_correspondences(a, b)
    assert len(result) >= 1
    assert result[0].correspondence_type == CorrespondenceType.TECHNOLOGY
    assert "python" in result[0].evidence.lower() or "fastapi" in result[0].evidence.lower()


def test_detect_technology_no_overlap():
    a = [{"name": "rust-engine", "org": "a", "description": "A Rust systems tool"}]
    b = [{"name": "js-app", "org": "b", "description": "A React frontend application"}]
    result = detect_technology_correspondences(a, b)
    assert result == []


# Governance correspondences


def test_detect_governance_empty():
    result = detect_governance_correspondences([], [])
    assert result == []


def test_detect_governance_similar_ci():
    a = [{"org": "a", "ci_workflow": True} for _ in range(3)]
    b = [{"org": "b", "ci_workflow": True} for _ in range(3)]
    result = detect_governance_correspondences(a, b)
    assert len(result) >= 1
    assert any(c.correspondence_type == CorrespondenceType.GOVERNANCE for c in result)


def test_detect_governance_similar_public():
    a = [{"org": "a", "public": True} for _ in range(5)]
    b = [{"org": "b", "public": True} for _ in range(5)]
    result = detect_governance_correspondences(a, b)
    assert any(
        c.correspondence_type == CorrespondenceType.GOVERNANCE
        and "public" in c.evidence.lower()
        for c in result
    )


def test_detect_governance_different_patterns():
    a = [{"org": "a", "ci_workflow": True, "public": True}]
    b = [{"org": "b", "ci_workflow": False, "public": False}]
    # Very different governance — should produce weak or no correspondences
    result = detect_governance_correspondences(a, b)
    # With only 1 repo each, ratios are 0% vs 100% — no match expected
    ci_matches = [c for c in result if "CI" in c.evidence or "ci" in c.evidence.lower()]
    for m in ci_matches:
        assert m.strength <= 0.5
