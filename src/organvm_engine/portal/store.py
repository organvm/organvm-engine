"""Engine access to the shared BIFRONS portal store.

The portal store (``~/.organvm/bifrons/portal.db``, override ``$BIFRONS_DB``) is
written by alchemia (intake tables) and organvm-engine (exchange tables). This
module owns the exchange-table DDL and provides readers over the intake tables
(``external_repo``, ``dossier``, ``exchange``) that alchemia populated.

The ``exchange`` DDL here MUST stay byte-identical to alchemia's copy — it is the
spine both halves share. Keep it minimal.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- shared spine DDL (MUST match alchemia's storage.EXCHANGE_DDL verbatim) --
EXCHANGE_DDL = """
CREATE TABLE IF NOT EXISTS exchange (
    exchange_id            TEXT PRIMARY KEY,
    external_repo_node_id  TEXT NOT NULL,
    external_repo          TEXT NOT NULL,
    state                  TEXT NOT NULL,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    data_json              TEXT NOT NULL DEFAULT '{}'
)
"""

# --- engine-owned exchange tables -------------------------------------------
_EXCHANGE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS resonance_edge (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        exchange_id    TEXT NOT NULL,
        external_node_id TEXT NOT NULL,
        external_repo  TEXT NOT NULL,
        internal_repo  TEXT NOT NULL,
        lens           TEXT NOT NULL,
        score          REAL NOT NULL,
        confidence     REAL DEFAULT 1.0,
        evidence_json  TEXT DEFAULT '[]',
        created_at     TEXT NOT NULL,
        UNIQUE(external_node_id, internal_repo, lens)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transmutation_proposal (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        exchange_id       TEXT NOT NULL,
        external_repo     TEXT NOT NULL,
        target_repo       TEXT NOT NULL,
        klass             TEXT NOT NULL,
        finding           TEXT DEFAULT '',
        proposed_change   TEXT DEFAULT '',
        license_decision  TEXT DEFAULT '',
        files_json        TEXT DEFAULT '[]',
        tests_json        TEXT DEFAULT '[]',
        status            TEXT DEFAULT 'proposed',
        created_at        TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS contribution_candidate (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        exchange_id        TEXT NOT NULL,
        external_repo      TEXT NOT NULL,
        kind               TEXT NOT NULL,
        rationale          TEXT DEFAULT '',
        contribution_score REAL DEFAULT 0.0,
        status             TEXT DEFAULT 'candidate',
        packet_json        TEXT DEFAULT '{}',
        created_at         TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS upstream_interaction (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        exchange_id     TEXT NOT NULL,
        external_repo   TEXT NOT NULL,
        kind            TEXT NOT NULL,
        number          INTEGER,
        url             TEXT DEFAULT '',
        state           TEXT DEFAULT '',
        review_decision TEXT DEFAULT '',
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backflow_signal (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        exchange_id   TEXT NOT NULL,
        external_repo TEXT NOT NULL,
        signal_type   TEXT NOT NULL,
        organ         TEXT NOT NULL,
        content       TEXT DEFAULT '',
        confidence    REAL DEFAULT 1.0,
        created_at    TEXT NOT NULL
    )
    """,
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_db_path() -> Path:
    env = os.environ.get("BIFRONS_DB")
    if env:
        return Path(env).expanduser()
    return Path("~/.organvm/bifrons/portal.db").expanduser()


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    db_path = Path(path).expanduser() if path else default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_exchange_schema(conn: sqlite3.Connection) -> None:
    """Create the engine-owned exchange tables + the shared exchange spine."""
    conn.execute(EXCHANGE_DDL)
    for ddl in _EXCHANGE_DDL:
        conn.execute(ddl)
    conn.commit()


# --- readers over alchemia's intake tables ----------------------------------
def list_dossiers(conn: sqlite3.Connection, *, level: str = "S1") -> list[dict[str, Any]]:
    """Return parsed dossier docs (alchemia-written) at the given level."""
    try:
        rows = conn.execute(
            "SELECT node_id, full_name, doc_json, exchange_id FROM dossier WHERE level=?",
            (level,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for row in rows:
        doc = json.loads(row["doc_json"])
        doc["_exchange_id"] = row["exchange_id"]
        out.append(doc)
    return out


def get_dossier(conn: sqlite3.Connection, full_name: str, *, level: str = "S1") -> dict | None:
    try:
        row = conn.execute(
            "SELECT node_id, full_name, doc_json, exchange_id FROM dossier "
            "WHERE full_name=? AND level=?",
            (full_name, level),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    doc = json.loads(row["doc_json"])
    doc["_exchange_id"] = row["exchange_id"]
    return doc


def get_exchange(conn: sqlite3.Connection, exchange_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM exchange WHERE exchange_id=?", (exchange_id,),
    ).fetchone()


def exchange_for_repo(conn: sqlite3.Connection, full_name: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM exchange WHERE external_repo=? ORDER BY created_at DESC LIMIT 1",
        (full_name,),
    ).fetchone()


def advance_exchange(
    conn: sqlite3.Connection,
    exchange_id: str,
    state: str,
    *,
    data: dict | None = None,
) -> None:
    """Advance an exchange to a new state, merging optional data (engine writer)."""
    row = get_exchange(conn, exchange_id)
    merged: dict = {}
    if row is not None:
        try:
            merged = json.loads(row["data_json"] or "{}")
        except (ValueError, TypeError):
            merged = {}
    if data:
        merged.update(data)
    conn.execute(
        "UPDATE exchange SET state=?, updated_at=?, data_json=? WHERE exchange_id=?",
        (state, now_iso(), json.dumps(merged), exchange_id),
    )
    conn.commit()


# --- writers for engine-owned tables ----------------------------------------
def upsert_resonance_edge(
    conn: sqlite3.Connection,
    *,
    exchange_id: str,
    external_node_id: str,
    external_repo: str,
    internal_repo: str,
    lens: str,
    score: float,
    confidence: float = 1.0,
    evidence: list[str] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO resonance_edge(exchange_id, external_node_id, external_repo,
            internal_repo, lens, score, confidence, evidence_json, created_at)
        VALUES(?,?,?,?,?,?,?,?,?)
        ON CONFLICT(external_node_id, internal_repo, lens) DO UPDATE SET
            score=excluded.score, confidence=excluded.confidence,
            evidence_json=excluded.evidence_json
        """,
        (exchange_id, external_node_id, external_repo, internal_repo, lens, score,
         confidence, json.dumps(evidence or []), now_iso()),
    )


def insert_transmutation_proposal(conn: sqlite3.Connection, proposal: Any) -> int:
    cur = conn.execute(
        """
        INSERT INTO transmutation_proposal(exchange_id, external_repo, target_repo,
            klass, finding, proposed_change, license_decision, files_json,
            tests_json, status, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (proposal.exchange_id, proposal.external_repo, proposal.target_repo,
         proposal.klass, proposal.finding, proposal.proposed_change,
         proposal.license_decision, json.dumps(proposal.files_changed),
         json.dumps(proposal.tests_required), proposal.status, now_iso()),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def insert_contribution_candidate(conn: sqlite3.Connection, candidate: Any) -> int:
    cur = conn.execute(
        """
        INSERT INTO contribution_candidate(exchange_id, external_repo, kind,
            rationale, contribution_score, status, packet_json, created_at)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (candidate.exchange_id, candidate.external_repo, candidate.kind,
         candidate.rationale, candidate.contribution_score, candidate.status,
         json.dumps(candidate.packet), now_iso()),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def insert_backflow_signal(
    conn: sqlite3.Connection,
    *,
    exchange_id: str,
    external_repo: str,
    signal_type: str,
    organ: str,
    content: str,
    confidence: float = 1.0,
) -> None:
    conn.execute(
        "INSERT INTO backflow_signal(exchange_id, external_repo, signal_type, "
        "organ, content, confidence, created_at) VALUES(?,?,?,?,?,?,?)",
        (exchange_id, external_repo, signal_type, organ, content, confidence, now_iso()),
    )
    conn.commit()


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    out: dict[str, int] = {}
    for table in ("resonance_edge", "transmutation_proposal", "contribution_candidate",
                  "upstream_interaction", "backflow_signal"):
        try:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()  # noqa: S608
            out[table] = int(row["n"])
        except sqlite3.OperationalError:
            out[table] = 0
    return out
