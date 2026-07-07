"""Tests for ontology.relations — SPEC-002, PRIM-003 (Relation).

Unified relation layer: RelationType enum, Relation dataclass,
store adapters, and UnifiedRelationStore with cross-store queries.
"""


import pytest

from organvm_engine.ontology.relations import (
    Relation,
    RelationType,
    UnifiedRelationStore,
    relations_from_dependencies,
    relations_from_hierarchy,
    relations_from_lineage,
    relations_from_seed_graph,
)

# ---------------------------------------------------------------------------
# RelationType enum
# ---------------------------------------------------------------------------

class TestRelationType:
    def test_all_values_present(self):
        expected = {
            "CONTAINMENT", "LINEAGE", "DEPENDENCY", "DATA_FLOW",
            "SUBSCRIPTION", "NAMING", "INHERENCE", "PROMOTION_CONSTRAINT",
        }
        actual = {rt.value for rt in RelationType}
        assert actual == expected

    def test_string_enum(self):
        assert RelationType.DEPENDENCY == "DEPENDENCY"
        assert isinstance(RelationType.LINEAGE, str)

    def test_from_string(self):
        assert RelationType("DATA_FLOW") == RelationType.DATA_FLOW


# ---------------------------------------------------------------------------
# Relation dataclass
# ---------------------------------------------------------------------------

class TestRelation:
    def test_create_with_defaults(self):
        rel = Relation(
            source_uid="ent_repo_001",
            target_uid="ent_repo_002",
            relation_type=RelationType.DEPENDENCY,
        )
        assert rel.source_uid == "ent_repo_001"
        assert rel.target_uid == "ent_repo_002"
        assert rel.relation_type == RelationType.DEPENDENCY
        assert rel.metadata == {}
        assert rel.store_origin == ""
        assert rel.created_at  # not empty

    def test_create_with_metadata(self):
        meta = {"artifact_type": "json_schema"}
        rel = Relation(
            source_uid="a",
            target_uid="b",
            relation_type=RelationType.DATA_FLOW,
            metadata=meta,
            store_origin="seed",
        )
        assert rel.metadata == meta
        assert rel.store_origin == "seed"

    def test_frozen(self):
        rel = Relation(
            source_uid="a",
            target_uid="b",
            relation_type=RelationType.LINEAGE,
        )
        with pytest.raises(AttributeError):
            rel.source_uid = "c"  # type: ignore[misc]

    def test_to_dict(self):
        rel = Relation(
            source_uid="ent_001",
            target_uid="ent_002",
            relation_type=RelationType.CONTAINMENT,
            metadata={"depth": 1},
            created_at="2026-01-01T00:00:00+00:00",
            store_origin="lineage",
        )
        d = rel.to_dict()
        assert d["source_uid"] == "ent_001"
        assert d["target_uid"] == "ent_002"
        assert d["relation_type"] == "CONTAINMENT"
        assert d["metadata"] == {"depth": 1}
        assert d["created_at"] == "2026-01-01T00:00:00+00:00"
        assert d["store_origin"] == "lineage"

    def test_to_dict_roundtrip_keys(self):
        rel = Relation(
            source_uid="x",
            target_uid="y",
            relation_type=RelationType.NAMING,
        )
        d = rel.to_dict()
        expected_keys = {"source_uid", "target_uid", "relation_type", "metadata", "created_at", "store_origin"}
        assert set(d.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Adapter: relations_from_lineage
# ---------------------------------------------------------------------------

class TestRelationsFromLineage:
    def test_basic_conversion(self):
        records = [
            {
                "entity_id": "ent_001",
                "related_id": "ent_002",
                "lineage_type": "supersedes",
                "recorded_at": "2026-01-01T00:00:00+00:00",
                "metadata": {"reason": "merge"},
            },
        ]
        rels = relations_from_lineage(records)
        assert len(rels) == 1
        assert rels[0].source_uid == "ent_001"
        assert rels[0].target_uid == "ent_002"
        assert rels[0].relation_type == RelationType.LINEAGE
        assert rels[0].metadata["lineage_type"] == "supersedes"
        assert rels[0].store_origin == "lineage"

    def test_all_lineage_types_map(self):
        for lt in ("derived_from", "supersedes", "merged_into", "split_from"):
            records = [{"entity_id": "a", "related_id": "b", "lineage_type": lt}]
            rels = relations_from_lineage(records)
            assert rels[0].relation_type == RelationType.LINEAGE

    def test_empty_input(self):
        assert relations_from_lineage([]) == []

    def test_preserves_original_metadata(self):
        records = [
            {
                "entity_id": "a",
                "related_id": "b",
                "lineage_type": "derived_from",
                "metadata": {"custom": "value"},
            },
        ]
        rels = relations_from_lineage(records)
        assert rels[0].metadata["original_metadata"] == {"custom": "value"}


# ---------------------------------------------------------------------------
# Adapter: relations_from_seed_graph
# ---------------------------------------------------------------------------

class TestRelationsFromSeedGraph:
    def test_basic_conversion(self):
        edges = [
            ("meta-organvm/schema-definitions", "meta-organvm/organvm-engine", "json_schema"),
        ]
        rels = relations_from_seed_graph(edges)
        assert len(rels) == 1
        assert rels[0].source_uid == "meta-organvm/schema-definitions"
        assert rels[0].target_uid == "meta-organvm/organvm-engine"
        assert rels[0].relation_type == RelationType.DATA_FLOW
        assert rels[0].metadata == {"artifact_type": "json_schema"}
        assert rels[0].store_origin == "seed"

    def test_multiple_edges(self):
        edges = [
            ("a", "b", "type1"),
            ("c", "d", "type2"),
            ("a", "d", "type1"),
        ]
        rels = relations_from_seed_graph(edges)
        assert len(rels) == 3

    def test_empty_input(self):
        assert relations_from_seed_graph([]) == []


# ---------------------------------------------------------------------------
# Adapter: relations_from_dependencies
# ---------------------------------------------------------------------------

class TestRelationsFromDependencies:
    def test_basic_conversion(self):
        registry = {
            "organs": {
                "META-ORGANVM": {
                    "repositories": [
                        {
                            "org": "meta-organvm",
                            "name": "organvm-engine",
                            "dependencies": [
                                "meta-organvm/schema-definitions",
                                "meta-organvm/organvm-corpvs-testamentvm",
                            ],
                        },
                    ],
                },
            },
        }
        rels = relations_from_dependencies(registry)
        assert len(rels) == 2
        assert rels[0].source_uid == "meta-organvm/organvm-engine"
        assert rels[0].target_uid == "meta-organvm/schema-definitions"
        assert rels[0].relation_type == RelationType.DEPENDENCY
        assert rels[0].store_origin == "dependency"

    def test_empty_registry(self):
        assert relations_from_dependencies({"organs": {}}) == []

    def test_no_dependencies(self):
        registry = {
            "organs": {
                "X": {
                    "repositories": [
                        {"org": "x", "name": "repo1", "dependencies": []},
                    ],
                },
            },
        }
        assert relations_from_dependencies(registry) == []

    def test_missing_org_or_name_skipped(self):
        registry = {
            "organs": {
                "X": {
                    "repositories": [
                        {"org": "", "name": "repo1", "dependencies": ["a/b"]},
                        {"org": "x", "name": "", "dependencies": ["a/b"]},
                    ],
                },
            },
        }
        assert relations_from_dependencies(registry) == []


# ---------------------------------------------------------------------------
# Adapter: relations_from_hierarchy
# ---------------------------------------------------------------------------

class TestRelationsFromHierarchy:
    def test_basic_conversion(self):
        edges = [
            {
                "parent_id": "ent_organ_001",
                "child_id": "ent_repo_001",
                "valid_from": "2026-01-01T00:00:00+00:00",
            },
        ]
        rels = relations_from_hierarchy(edges)
        assert len(rels) == 1
        assert rels[0].source_uid == "ent_organ_001"
        assert rels[0].target_uid == "ent_repo_001"
        assert rels[0].relation_type == RelationType.CONTAINMENT
        assert rels[0].created_at == "2026-01-01T00:00:00+00:00"
        assert rels[0].store_origin == "lineage"

    def test_retired_edge_metadata(self):
        edges = [
            {
                "parent_id": "a",
                "child_id": "b",
                "valid_from": "2025-01-01T00:00:00+00:00",
                "valid_to": "2026-01-01T00:00:00+00:00",
            },
        ]
        rels = relations_from_hierarchy(edges)
        assert rels[0].metadata["valid_to"] == "2026-01-01T00:00:00+00:00"

    def test_empty_input(self):
        assert relations_from_hierarchy([]) == []


# ---------------------------------------------------------------------------
# UnifiedRelationStore — construction and loading
# ---------------------------------------------------------------------------

class TestUnifiedRelationStoreLoading:
    def test_empty_store(self):
        store = UnifiedRelationStore()
        assert store.count == 0
        assert store.all_relations == []

    def test_construct_with_relations(self):
        rels = [
            Relation("a", "b", RelationType.DEPENDENCY, store_origin="test"),
            Relation("c", "d", RelationType.LINEAGE, store_origin="test"),
        ]
        store = UnifiedRelationStore(rels)
        assert store.count == 2

    def test_load_lineage(self):
        store = UnifiedRelationStore()
        records = [
            {"entity_id": "e1", "related_id": "e2", "lineage_type": "supersedes"},
        ]
        added = store.load_lineage(records)
        assert added == 1
        assert store.count == 1

    def test_load_seed_graph(self):
        store = UnifiedRelationStore()
        edges = [("a", "b", "schema"), ("c", "d", "config")]
        added = store.load_seed_graph(edges)
        assert added == 2
        assert store.count == 2

    def test_load_dependencies(self):
        registry = {
            "organs": {
                "X": {
                    "repositories": [
                        {"org": "x", "name": "r", "dependencies": ["y/s"]},
                    ],
                },
            },
        }
        store = UnifiedRelationStore()
        added = store.load_dependencies(registry)
        assert added == 1

    def test_load_hierarchy(self):
        store = UnifiedRelationStore()
        edges = [{"parent_id": "p", "child_id": "c", "valid_from": "2026-01-01"}]
        added = store.load_hierarchy(edges)
        assert added == 1

    def test_add_single(self):
        store = UnifiedRelationStore()
        rel = Relation("a", "b", RelationType.NAMING)
        store.add(rel)
        assert store.count == 1

    def test_multiple_loads_accumulate(self):
        store = UnifiedRelationStore()
        store.load_lineage([
            {"entity_id": "a", "related_id": "b", "lineage_type": "derived_from"},
        ])
        store.load_seed_graph([("c", "d", "data")])
        assert store.count == 2


# ---------------------------------------------------------------------------
# UnifiedRelationStore — queries
# ---------------------------------------------------------------------------

def _build_test_store() -> UnifiedRelationStore:
    """Build a store with relations from all three sources for testing."""
    store = UnifiedRelationStore()

    # Lineage
    store.load_lineage([
        {"entity_id": "ent_001", "related_id": "ent_002", "lineage_type": "supersedes"},
        {"entity_id": "ent_003", "related_id": "ent_001", "lineage_type": "derived_from"},
    ])

    # Seed graph
    store.load_seed_graph([
        ("meta-organvm/schema-definitions", "meta-organvm/organvm-engine", "json_schema"),
        ("organvm-i-theoria/styx", "organvm-ii-poiesis/dromenon", "theory_model"),
    ])

    # Dependencies
    store.load_dependencies({
        "organs": {
            "META-ORGANVM": {
                "repositories": [
                    {
                        "org": "meta-organvm",
                        "name": "organvm-engine",
                        "dependencies": ["meta-organvm/schema-definitions"],
                    },
                    {
                        "org": "meta-organvm",
                        "name": "system-dashboard",
                        "dependencies": ["meta-organvm/organvm-engine"],
                    },
                ],
            },
        },
    })

    return store


class TestUnifiedRelationStoreQuery:
    def test_query_no_filters(self):
        store = _build_test_store()
        all_rels = store.query()
        assert len(all_rels) == 6

    def test_query_by_source(self):
        store = _build_test_store()
        rels = store.query(source="ent_001")
        assert len(rels) == 1
        assert rels[0].target_uid == "ent_002"

    def test_query_by_target(self):
        store = _build_test_store()
        rels = store.query(target="meta-organvm/organvm-engine")
        assert len(rels) == 2  # seed edge + dependency edge

    def test_query_by_rel_type(self):
        store = _build_test_store()
        rels = store.query(rel_type=RelationType.DATA_FLOW)
        assert len(rels) == 2
        for rel in rels:
            assert rel.relation_type == RelationType.DATA_FLOW

    def test_query_by_store_origin(self):
        store = _build_test_store()
        rels = store.query(store_origin="dependency")
        assert len(rels) == 2
        for rel in rels:
            assert rel.store_origin == "dependency"

    def test_query_combined_filters(self):
        store = _build_test_store()
        rels = store.query(
            source="meta-organvm/organvm-engine",
            rel_type=RelationType.DEPENDENCY,
        )
        assert len(rels) == 1
        assert rels[0].target_uid == "meta-organvm/schema-definitions"

    def test_query_no_match(self):
        store = _build_test_store()
        rels = store.query(source="nonexistent")
        assert rels == []


class TestUnifiedRelationStoreNeighbors:
    def test_neighbors_both(self):
        store = _build_test_store()
        rels = store.neighbors("meta-organvm/organvm-engine")
        # Incoming: seed edge, dependency edge. Outgoing: dependency edge.
        assert len(rels) == 3

    def test_neighbors_outgoing(self):
        store = _build_test_store()
        rels = store.neighbors("meta-organvm/organvm-engine", direction="outgoing")
        assert len(rels) == 1
        assert rels[0].relation_type == RelationType.DEPENDENCY

    def test_neighbors_incoming(self):
        store = _build_test_store()
        rels = store.neighbors("meta-organvm/organvm-engine", direction="incoming")
        assert len(rels) == 2

    def test_neighbors_with_type_filter(self):
        store = _build_test_store()
        rels = store.neighbors(
            "meta-organvm/organvm-engine",
            direction="both",
            rel_type=RelationType.DEPENDENCY,
        )
        assert len(rels) == 2  # one outgoing dep + one incoming dep


class TestUnifiedRelationStoreConvenience:
    def test_sources_of(self):
        store = _build_test_store()
        sources = store.sources_of("meta-organvm/organvm-engine")
        assert "meta-organvm/schema-definitions" in sources
        assert "meta-organvm/system-dashboard" in sources

    def test_targets_of(self):
        store = _build_test_store()
        targets = store.targets_of("meta-organvm/organvm-engine")
        assert "meta-organvm/schema-definitions" in targets

    def test_by_type(self):
        store = _build_test_store()
        lineage_rels = store.by_type(RelationType.LINEAGE)
        assert len(lineage_rels) == 2

    def test_store_summary(self):
        store = _build_test_store()
        summary = store.store_summary()
        assert summary["lineage"] == 2
        assert summary["seed"] == 2
        assert summary["dependency"] == 2

    def test_type_summary(self):
        store = _build_test_store()
        summary = store.type_summary()
        assert summary["LINEAGE"] == 2
        assert summary["DATA_FLOW"] == 2
        assert summary["DEPENDENCY"] == 2

    def test_snapshot(self):
        store = _build_test_store()
        snap = store.snapshot()
        assert len(snap) == 6
        assert all(isinstance(d, dict) for d in snap)
        assert all("relation_type" in d for d in snap)


# ---------------------------------------------------------------------------
# Package-level imports
# ---------------------------------------------------------------------------

class TestPackageExports:
    def test_import_from_ontology_package(self):
        from organvm_engine.ontology import Relation, RelationType, UnifiedRelationStore
        assert Relation is not None
        assert RelationType is not None
        assert UnifiedRelationStore is not None
