"""Cross-organ convergence detection for BIFRONS.

A starred repository often resonates with several ORGANVM repositories through
different lenses — a convergence point. Surfacing these prevents forcing a star
into one organ and reveals where external material touches the system broadly.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass
class Convergence:
    external_repo: str
    internal_repos: list[str] = field(default_factory=list)
    lenses: list[str] = field(default_factory=list)
    max_score: float = 0.0

    def as_dict(self) -> dict:
        return {
            "external_repo": self.external_repo,
            "internal_repos": self.internal_repos,
            "lenses": self.lenses,
            "max_score": self.max_score,
            "breadth": len(self.internal_repos),
        }


def find_convergences(
    conn: sqlite3.Connection,
    *,
    min_repos: int = 2,
) -> list[Convergence]:
    """External repos resonating with >= ``min_repos`` distinct internal repos."""
    try:
        rows = conn.execute(
            "SELECT external_repo, internal_repo, lens, score FROM resonance_edge",
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    grouped: dict[str, Convergence] = {}
    repos_seen: dict[str, set] = {}
    lenses_seen: dict[str, set] = {}
    for row in rows:
        ext = row["external_repo"]
        conv = grouped.setdefault(ext, Convergence(external_repo=ext))
        repos_seen.setdefault(ext, set()).add(row["internal_repo"])
        lenses_seen.setdefault(ext, set()).add(row["lens"])
        conv.max_score = max(conv.max_score, row["score"])

    result: list[Convergence] = []
    for ext, conv in grouped.items():
        repos = sorted(repos_seen[ext])
        if len(repos) >= min_repos:
            conv.internal_repos = repos
            conv.lenses = sorted(lenses_seen[ext])
            result.append(conv)
    result.sort(key=lambda c: (len(c.internal_repos), c.max_score), reverse=True)
    return result


def convergence_report(conn: sqlite3.Connection, *, min_repos: int = 2) -> str:
    """Human-readable convergence summary."""
    convs = find_convergences(conn, min_repos=min_repos)
    if not convs:
        return "No cross-organ convergences found."
    lines = [f"{len(convs)} convergence point(s):"]
    for c in convs:
        lines.append(
            f"  {c.external_repo} -> {len(c.internal_repos)} repos "
            f"[{', '.join(c.lenses)}] (max {c.max_score})",
        )
    return "\n".join(lines)
