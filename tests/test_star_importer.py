"""BIFRONS star importer — dossiers -> resonance edges -> MAPPED + convergence."""

from __future__ import annotations

import json
import sqlite3

import pytest

from organvm_engine.network import ENGAGEMENT_FORMS
from organvm_engine.network.convergence import find_convergences
from organvm_engine.network.resonance import InternalRepo
from organvm_engine.network.star_importer import import_stars, mirror_entries_for_internal
from organvm_engine.portal import store


def _seed_portal(path, dossiers):
    """Create the alchemia-written tables and insert dossiers + exchange rows."""
    conn = sqlite3.connect(str(path))
    conn.execute(store.EXCHANGE_DDL)
    conn.execute(
        "CREATE TABLE dossier (id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT, "
        "full_name TEXT, level TEXT, schema_version TEXT, snapshot_ref TEXT, "
        "snapshot_at TEXT, doc_json TEXT, exchange_id TEXT, UNIQUE(node_id, level))",
    )
    for d in dossiers:
        ex_id = f"ex_{d['github_node_id']}"
        conn.execute(
            "INSERT INTO exchange(exchange_id, external_repo_node_id, external_repo, "
            "state, created_at, updated_at, data_json) VALUES(?,?,?,?,?,?, '{}')",
            (ex_id, d["github_node_id"], d["external_repo"], "STARRED",
             "2026-07-01T00:00:00Z", "2026-07-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO dossier(node_id, full_name, level, schema_version, "
            "snapshot_ref, snapshot_at, doc_json, exchange_id) VALUES(?,?,?,?,?,?,?,?)",
            (d["github_node_id"], d["external_repo"], "S1", "1.0",
             d.get("snapshot_ref", ""), "2026-07-01T00:00:00Z", json.dumps(d), ex_id),
        )
    conn.commit()
    conn.close()
    return path


def _dossier(node, full_name, *, lang="Rust", topics=None, desc=""):
    return {
        "external_repo": full_name,
        "github_node_id": node,
        "snapshot_ref": "abc1234def",
        "identity": {"description": desc, "topics": topics or [],
                     "primary_language": lang, "languages": {lang: 1.0}},
        "state": {"archived": False, "fork": False, "last_push_at": "2026-07-01T00:00:00Z"},
        "contracts": {"license": {"spdx": "MIT", "class": "permissive"},
                      "decision": "code-adaptation-with-attribution"},
    }


@pytest.fixture
def db(tmp_path):
    _seed_portal(tmp_path / "p.db", [
        _dossier("R_1", "astral-sh/ruff", lang="Rust",
                 topics=["python", "linter"], desc="fast python linter"),
        _dossier("R_2", "psf/black", lang="Python",
                 topics=["python", "formatter"], desc="python code formatter"),
    ])
    conn = store.connect(tmp_path / "p.db")
    yield conn
    conn.close()


INTERNAL = [
    InternalRepo("organvm-engine", languages={"Python", "Rust"},
                 topics={"linter"}, description="python quality control and linting"),
    InternalRepo("a-i--skills", languages={"Python"},
                 topics={"python", "formatter"}, description="python code formatting skills"),
]


def test_import_stars_writes_edges_and_maps_exchange(db):
    summary = import_stars(db, INTERNAL)
    assert summary.dossiers == 2
    assert summary.edges > 0
    assert summary.mapped == 2
    # Exchanges advanced to MAPPED with scores recorded.
    row = db.execute("SELECT state, data_json FROM exchange WHERE external_repo=?",
                     ("astral-sh/ruff",)).fetchone()
    assert row["state"] == "MAPPED"
    assert "absorption_score" in json.loads(row["data_json"])


def test_import_stars_is_idempotent(db):
    import_stars(db, INTERNAL)
    first = store.counts(db)["resonance_edge"]
    import_stars(db, INTERNAL)
    assert store.counts(db)["resonance_edge"] == first  # UNIQUE upsert, no dupes


def test_convergence_detects_multi_repo_stars(db):
    import_stars(db, INTERNAL)
    convs = find_convergences(db, min_repos=2)
    # ruff resonates with both internal repos (python+linter / python).
    names = {c.external_repo for c in convs}
    assert "astral-sh/ruff" in names


def test_mirror_entries_projection_feeds_network_map(db):
    import_stars(db, INTERNAL)
    mirrors = mirror_entries_for_internal(db, "organvm-engine")
    assert any(mirrors[lens] for lens in ("technical", "parallel", "kinship"))
    # Every projected MirrorEntry uses a canonical engagement form.
    for lens in mirrors.values():
        for entry in lens:
            assert set(entry.engagement) <= ENGAGEMENT_FORMS


def test_scanner_engagement_forms_are_canonical():
    # The watch->presence drift fix: scanner/discover emit only canonical forms.
    from pathlib import Path

    import organvm_engine.network as net
    net_dir = Path(net.__file__).parent
    for fname in ("scanner.py", "discover.py"):
        text = (net_dir / fname).read_text()
        assert '"watch"' not in text
        assert '"discussions"' not in text
