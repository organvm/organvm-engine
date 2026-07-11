"""Compile the BIFRONS star corpus into ORGANVM network relationships.

Reads dossiers (written by alchemia) from the shared portal store, scores each
against the internal repos across the three lenses, records resonance edges, and
advances each exchange to MAPPED. This is the bridge from *absorption* (alchemia)
to *relationship* (the network mirror machinery).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from organvm_engine.network.resonance import (
    InternalRepo,
    ResonanceEdge,
    absorption_score,
    compute_resonance,
    contribution_score,
)
from organvm_engine.network.schema import MirrorEntry
from organvm_engine.portal import store
from organvm_engine.portal.state_machine import ExchangeState


@dataclass
class ImportSummary:
    dossiers: int = 0
    edges: int = 0
    mapped: int = 0
    unresolved: int = 0
    unresolved_repos: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "dossiers": self.dossiers,
            "edges": self.edges,
            "mapped": self.mapped,
            "unresolved": self.unresolved,
        }


def import_stars(
    conn: sqlite3.Connection,
    internal_repos: list[InternalRepo],
    *,
    level: str = "S1",
) -> ImportSummary:
    """Import all dossiers of ``level`` into resonance edges. Idempotent."""
    store.init_exchange_schema(conn)
    dossiers = store.list_dossiers(conn, level=level)
    summary = ImportSummary(dossiers=len(dossiers))

    for dossier in dossiers:
        exchange_id = dossier.get("_exchange_id", "")
        full_name = dossier.get("external_repo", "")
        node_id = dossier.get("github_node_id", "")
        edges = compute_resonance(dossier, internal_repos)

        if not edges:
            summary.unresolved += 1
            summary.unresolved_repos.append(full_name)
            continue

        for edge in edges:
            store.upsert_resonance_edge(
                conn,
                exchange_id=exchange_id,
                external_node_id=node_id,
                external_repo=full_name,
                internal_repo=edge.internal_repo,
                lens=edge.lens,
                score=edge.score,
                evidence=edge.evidence,
            )
            summary.edges += 1

        # Persist the two independent scores on the exchange and advance to MAPPED.
        if exchange_id:
            store.advance_exchange(
                conn, exchange_id, ExchangeState.MAPPED.value,
                data={
                    "absorption_score": absorption_score(dossier, edges),
                    "contribution_score": contribution_score(dossier),
                    "resonance_edges": len(edges),
                },
            )
        summary.mapped += 1

    conn.commit()
    return summary


def mirror_entries_for_internal(
    conn: sqlite3.Connection,
    internal_repo: str,
) -> dict[str, list[MirrorEntry]]:
    """Project recorded resonance edges into per-lens MirrorEntry lists.

    Feeds the existing network-map machinery (network-map.yaml) — the star
    importer feeds that machinery rather than duplicating it.
    """
    rows = conn.execute(
        "SELECT external_repo, lens, score, evidence_json FROM resonance_edge "
        "WHERE internal_repo=? ORDER BY score DESC",
        (internal_repo,),
    ).fetchall()
    out: dict[str, list[MirrorEntry]] = {"technical": [], "parallel": [], "kinship": []}
    import json
    for row in rows:
        lens = row["lens"]
        if lens not in out:
            continue
        evidence = json.loads(row["evidence_json"] or "[]")
        out[lens].append(MirrorEntry(
            project=row["external_repo"],
            platform="github",
            relevance="; ".join(evidence) or f"{lens} resonance {row['score']}",
            engagement=["presence"],
            url=f"https://github.com/{row['external_repo']}",
            tags=["bifrons-star", f"score:{row['score']}"],
        ))
    return out


def resonance_edges_as_relations(edges: list[ResonanceEdge]) -> list[str]:
    """Small helper: the lens relations implied by a set of edges."""
    return sorted({e.lens for e in edges})
