"""Tests for governance invariant validators (SPEC-003)."""

import json
from datetime import datetime, timezone

import pytest

from organvm_engine.governance.invariants import (
    InvariantResult,
    run_all_invariants,
    validate_constitutional_supremacy,
    validate_dag_invariant,
    validate_governance_reachability,
    validate_identity_persistence,
    validate_observability,
)
from organvm_engine.organ_config import FALLBACK_ORGAN_MAP

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_registry():
    """A minimal valid registry with all observability fields populated."""
    now_str = datetime.now(timezone.utc).isoformat()
    return {
        "organs": {
            "ORGAN-I": {
                "repositories": [
                    {
                        "name": "theory-core",
                        "org": "organvm-i-theoria",
                        "implementation_status": "ACTIVE",
                        "promotion_status": "PUBLIC_PROCESS",
                        "last_validated": now_str,
                        "code_files": 10,
                        "test_files": 5,
                        "dependencies": [],
                    },
                ],
            },
            "META-ORGANVM": {
                "repositories": [
                    {
                        "name": "organvm-engine",
                        "org": "meta-organvm",
                        "implementation_status": "ACTIVE",
                        "promotion_status": "PUBLIC_PROCESS",
                        "last_validated": now_str,
                        "code_files": 50,
                        "test_files": 20,
                        "dependencies": [],
                    },
                ],
            },
        },
    }


@pytest.fixture
def gov_rules_clean():
    """Governance rules with no axiom/dictum conflicts."""
    return {
        "version": "1.0",
        "dependency_rules": {
            "no_circular_dependencies": True,
            "no_back_edges": True,
        },
        "promotion_rules": {},
        "state_machine": {"transitions": {}},
        "audit_thresholds": {},
        "dictums": {
            "axioms": [
                {
                    "id": "AX-1",
                    "statement": "No circular dependencies allowed.",
                    "severity": "critical",
                    "enforcement": "automated",
                },
            ],
            "organ_dictums": {
                "ORGAN-III": [
                    {
                        "id": "OD-III-1",
                        "constraints": {"requires_ci": True},
                        "severity": "warning",
                    },
                ],
            },
        },
    }


# ---------------------------------------------------------------------------
# INV-000-001: DAG Invariant (delegates to dependency_graph)
# ---------------------------------------------------------------------------

class TestDagInvariant:
    def test_clean_dag_passes(self, clean_registry):
        valid, errors = validate_dag_invariant(clean_registry)
        assert valid
        assert errors == []

    def test_cycle_detected(self):
        registry = {
            "organs": {
                "ORGAN-IV": {
                    "repositories": [
                        {
                            "name": "a",
                            "org": "organvm-iv-taxis",
                            "dependencies": ["organvm-iv-taxis/b"],
                        },
                        {
                            "name": "b",
                            "org": "organvm-iv-taxis",
                            "dependencies": ["organvm-iv-taxis/a"],
                        },
                    ],
                },
            },
        }
        valid, errors = validate_dag_invariant(registry)
        assert not valid
        assert any("Cycle" in e for e in errors)

    def test_back_edge_detected(self):
        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {
                            "name": "theory",
                            "org": "organvm-i-theoria",
                            "dependencies": ["organvm-ii-poiesis/art"],
                        },
                    ],
                },
                "ORGAN-II": {
                    "repositories": [
                        {
                            "name": "art",
                            "org": "organvm-ii-poiesis",
                            "dependencies": [],
                        },
                    ],
                },
            },
        }
        valid, errors = validate_dag_invariant(registry)
        assert not valid
        assert any("Back-edge" in e for e in errors)


# ---------------------------------------------------------------------------
# INV-000-002: Governance Reachability
# ---------------------------------------------------------------------------

class TestGovernanceReachability:
    def test_all_reachable(self, clean_registry):
        valid, errors = validate_governance_reachability(
            clean_registry, FALLBACK_ORGAN_MAP,
        )
        assert valid
        assert errors == []

    def test_archived_ignored(self):
        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {
                            "name": "old-repo",
                            "org": "organvm-i-theoria",
                            "implementation_status": "ARCHIVED",
                            "dependencies": [],
                        },
                    ],
                },
            },
        }
        valid, errors = validate_governance_reachability(registry, FALLBACK_ORGAN_MAP)
        assert valid

    def test_empty_registry(self):
        registry = {"organs": {}}
        valid, errors = validate_governance_reachability(registry, FALLBACK_ORGAN_MAP)
        assert valid

    def test_connected_via_dependency(self):
        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {
                            "name": "a",
                            "org": "organvm-i-theoria",
                            "implementation_status": "ACTIVE",
                            "dependencies": ["organvm-i-theoria/b"],
                        },
                        {
                            "name": "b",
                            "org": "organvm-i-theoria",
                            "implementation_status": "ACTIVE",
                            "dependencies": [],
                        },
                    ],
                },
            },
        }
        valid, errors = validate_governance_reachability(registry, FALLBACK_ORGAN_MAP)
        assert valid


# ---------------------------------------------------------------------------
# INV-000-003: Identity Persistence
# ---------------------------------------------------------------------------

class TestIdentityPersistence:
    def test_no_store_file_is_valid(self, tmp_path):
        valid, errors = validate_identity_persistence(tmp_path / "nonexistent.jsonl")
        assert valid
        assert errors == []

    def test_clean_store(self, tmp_path):
        store = tmp_path / "entities.jsonl"
        entries = [
            {"uid": "ent_001", "lifecycle_status": "active"},
            {"uid": "ent_002", "lifecycle_status": "active"},
            {"uid": "ent_003", "lifecycle_status": "active"},
        ]
        store.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        valid, errors = validate_identity_persistence(store)
        assert valid
        assert errors == []

    def test_deleted_uid_detected(self, tmp_path):
        store = tmp_path / "entities.jsonl"
        entries = [
            {"uid": "ent_001", "lifecycle_status": "active"},
            {"uid": "ent_002", "lifecycle_status": "deleted"},
        ]
        store.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        valid, errors = validate_identity_persistence(store)
        assert not valid
        assert any("ent_002" in e for e in errors)

    def test_malformed_json_reported(self, tmp_path):
        store = tmp_path / "entities.jsonl"
        store.write_text('{"uid": "ent_001"}\nNOT_JSON\n')
        valid, errors = validate_identity_persistence(store)
        assert not valid
        assert any("malformed" in e for e in errors)

    def test_empty_uids_ignored(self, tmp_path):
        store = tmp_path / "entities.jsonl"
        entries = [
            {"some_field": "value"},  # no uid
            {"uid": "ent_001", "lifecycle_status": "active"},
        ]
        store.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        valid, errors = validate_identity_persistence(store)
        assert valid


# ---------------------------------------------------------------------------
# INV-000-004: Constitutional Supremacy
# ---------------------------------------------------------------------------

class TestConstitutionalSupremacy:
    def test_no_conflict(self, gov_rules_clean):
        valid, errors = validate_constitutional_supremacy(gov_rules_clean)
        assert valid
        assert errors == []

    def test_no_dictums_is_valid(self):
        valid, errors = validate_constitutional_supremacy({"version": "1.0"})
        assert valid

    def test_organ_dictum_allows_forbidden(self):
        rules = {
            "dependency_rules": {
                "no_circular_dependencies": True,
            },
            "dictums": {
                "axioms": [],
                "organ_dictums": {
                    "ORGAN-III": [
                        {
                            "id": "OD-BAD",
                            "constraints": {"allow_circular_dependencies": True},
                            "severity": "warning",
                        },
                    ],
                },
            },
        }
        valid, errors = validate_constitutional_supremacy(rules)
        assert not valid
        assert any("OD-BAD" in e for e in errors)
        assert any("allow_circular_dependencies" in e for e in errors)

    def test_organ_dictum_disables_prohibition(self):
        rules = {
            "dependency_rules": {
                "no_back_edges": True,
            },
            "dictums": {
                "axioms": [],
                "organ_dictums": {
                    "ORGAN-II": [
                        {
                            "id": "OD-WRONG",
                            "constraints": {"no_back_edges": False},
                            "severity": "critical",
                        },
                    ],
                },
            },
        }
        valid, errors = validate_constitutional_supremacy(rules)
        assert not valid
        assert any("OD-WRONG" in e for e in errors)

    def test_unrelated_constraints_pass(self):
        rules = {
            "dependency_rules": {
                "no_circular_dependencies": True,
            },
            "dictums": {
                "axioms": [],
                "organ_dictums": {
                    "ORGAN-III": [
                        {
                            "id": "OD-OK",
                            "constraints": {"requires_ci": True},
                            "severity": "warning",
                        },
                    ],
                },
            },
        }
        valid, errors = validate_constitutional_supremacy(rules)
        assert valid


# ---------------------------------------------------------------------------
# INV-000-005: Observability
# ---------------------------------------------------------------------------

class TestObservability:
    def test_fully_observable(self, clean_registry):
        valid, errors = validate_observability(clean_registry)
        assert valid
        assert errors == []

    def test_missing_promotion_status(self):
        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {
                            "name": "no-promo",
                            "org": "organvm-i-theoria",
                            "implementation_status": "ACTIVE",
                            "last_validated": "2026-03-15",
                            "code_files": 5,
                        },
                    ],
                },
            },
        }
        valid, errors = validate_observability(registry)
        assert not valid
        assert any("missing promotion_status" in e for e in errors)

    def test_missing_last_validated(self):
        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {
                            "name": "no-date",
                            "org": "organvm-i-theoria",
                            "implementation_status": "ACTIVE",
                            "promotion_status": "LOCAL",
                            "code_files": 5,
                        },
                    ],
                },
            },
        }
        valid, errors = validate_observability(registry)
        assert not valid
        assert any("missing last_validated" in e for e in errors)

    def test_stale_repo(self):
        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {
                            "name": "stale-one",
                            "org": "organvm-i-theoria",
                            "implementation_status": "ACTIVE",
                            "promotion_status": "LOCAL",
                            "last_validated": "2020-01-01",
                            "code_files": 5,
                        },
                    ],
                },
            },
        }
        valid, errors = validate_observability(registry)
        assert not valid
        assert any("stale" in e for e in errors)

    def test_no_metrics(self):
        registry = {
            "organs": {
                "META-ORGANVM": {
                    "repositories": [
                        {
                            "name": "no-metrics",
                            "org": "meta-organvm",
                            "implementation_status": "ACTIVE",
                            "promotion_status": "LOCAL",
                            "last_validated": "2026-03-15",
                        },
                    ],
                },
            },
        }
        valid, errors = validate_observability(registry)
        assert not valid
        assert any("no metrics" in e for e in errors)

    def test_archived_excluded(self):
        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {
                            "name": "archived-repo",
                            "org": "organvm-i-theoria",
                            "implementation_status": "ARCHIVED",
                        },
                    ],
                },
            },
        }
        valid, errors = validate_observability(registry)
        assert valid

    def test_malformed_date(self):
        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {
                            "name": "bad-date",
                            "org": "organvm-i-theoria",
                            "implementation_status": "ACTIVE",
                            "promotion_status": "LOCAL",
                            "last_validated": "not-a-date",
                            "code_files": 5,
                        },
                    ],
                },
            },
        }
        valid, errors = validate_observability(registry)
        assert not valid
        assert any("malformed" in e for e in errors)


# ---------------------------------------------------------------------------
# Consolidated runner
# ---------------------------------------------------------------------------

class TestRunAllInvariants:
    def test_all_pass(self, clean_registry, gov_rules_clean, tmp_path):
        store = tmp_path / "entities.jsonl"
        store.write_text('{"uid": "ent_001", "lifecycle_status": "active"}\n')

        result = run_all_invariants(
            registry=clean_registry,
            organ_config=FALLBACK_ORGAN_MAP,
            entity_store_path=store,
            governance_rules=gov_rules_clean,
        )
        assert isinstance(result, InvariantResult)
        assert result.passed
        assert len(result.all_errors) == 0
        assert "INV-000-001:dag" in result.results
        assert "INV-000-002:reachability" in result.results
        assert "INV-000-003:identity" in result.results
        assert "INV-000-004:supremacy" in result.results
        assert "INV-000-005:observability" in result.results

    def test_skips_optional_checks(self, clean_registry):
        result = run_all_invariants(
            registry=clean_registry,
            organ_config=FALLBACK_ORGAN_MAP,
        )
        # identity and supremacy skipped when paths/rules not provided
        assert "INV-000-003:identity" not in result.results
        assert "INV-000-004:supremacy" not in result.results
        # dag and reachability always run
        assert "INV-000-001:dag" in result.results
        assert "INV-000-002:reachability" in result.results

    def test_summary_output(self, clean_registry):
        result = run_all_invariants(
            registry=clean_registry,
            organ_config=FALLBACK_ORGAN_MAP,
        )
        summary = result.summary()
        assert "Invariant Report" in summary
        assert "PASS" in summary

    def test_failure_propagates(self):
        # Registry with a cycle
        registry = {
            "organs": {
                "ORGAN-IV": {
                    "repositories": [
                        {
                            "name": "a",
                            "org": "organvm-iv-taxis",
                            "dependencies": ["organvm-iv-taxis/b"],
                        },
                        {
                            "name": "b",
                            "org": "organvm-iv-taxis",
                            "dependencies": ["organvm-iv-taxis/a"],
                        },
                    ],
                },
            },
        }
        result = run_all_invariants(
            registry=registry,
            organ_config=FALLBACK_ORGAN_MAP,
        )
        assert not result.passed
        assert len(result.all_errors) > 0
