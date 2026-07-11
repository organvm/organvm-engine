"""Resonance scoring for BIFRONS — map absorbed repos to ORGANVM repos.

Two independent scores, never collapsed into one number:

* absorption score  — how valuable the repo is as *material* for ORGANVM
* contribution score — whether ORGANVM can return legitimate value upstream

And three resonance lenses (mirroring the network mirror lenses): technical
dependency, domain parallel, philosophical kinship. Weights are initial
configurable heuristics whose values should evolve from actual outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Absorption score component weights (sum = 1.0 before penalties).
ABSORPTION_WEIGHTS = {
    "resonance": 0.25,
    "applicability": 0.20,
    "novelty": 0.15,
    "upstream_health": 0.15,
    "convergence": 0.10,
    "temporal": 0.10,
    "aesthetic": 0.05,
}

# Contribution score component weights (sum = 1.0 before penalties).
CONTRIBUTION_WEIGHTS = {
    "verified_friction": 0.25,
    "tractability": 0.20,
    "testability": 0.20,
    "receptivity": 0.15,
    "existing_evidence": 0.10,
    "strategic": 0.10,
}

# Minimum lens score for a resonance edge to be recorded.
DEFAULT_EDGE_THRESHOLD = 0.15

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "is",
    "fast", "simple", "tool", "library", "framework", "python", "rust", "js",
})


@dataclass
class InternalRepo:
    """A lightweight descriptor of an ORGANVM repo to map stars against."""

    name: str
    organ: str = ""
    languages: set[str] = field(default_factory=set)
    topics: set[str] = field(default_factory=set)
    description: str = ""


@dataclass
class ResonanceEdge:
    internal_repo: str
    lens: str
    score: float
    evidence: list[str] = field(default_factory=list)


def _words(text: str) -> set[str]:
    return {
        w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split()
        if len(w) > 2 and w not in _STOPWORDS
    }


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _dossier_languages(dossier: dict) -> set[str]:
    langs = set((dossier.get("identity", {}).get("languages") or {}).keys())
    primary = dossier.get("identity", {}).get("primary_language")
    if primary:
        langs.add(primary)
    return {lang_.lower() for lang_ in langs}


def compute_resonance(
    dossier: dict,
    internal_repos: list[InternalRepo],
    *,
    threshold: float = DEFAULT_EDGE_THRESHOLD,
) -> list[ResonanceEdge]:
    """Score a dossier against each internal repo across the three lenses."""
    ext_langs = _dossier_languages(dossier)
    ext_topics = {t.lower() for t in dossier.get("identity", {}).get("topics", [])}
    ext_words = _words(dossier.get("identity", {}).get("description", ""))

    edges: list[ResonanceEdge] = []
    for repo in internal_repos:
        # technical: shared languages
        lang_overlap = ext_langs & {lang_.lower() for lang_ in repo.languages}
        tech = _jaccard(ext_langs, {lang_.lower() for lang_ in repo.languages})
        if tech >= threshold:
            edges.append(ResonanceEdge(
                repo.name, "technical", round(tech, 3),
                [f"shared language: {', '.join(sorted(lang_overlap))}"] if lang_overlap else [],
            ))
        # parallel: shared topics
        topic_overlap = ext_topics & {t.lower() for t in repo.topics}
        par = _jaccard(ext_topics, {t.lower() for t in repo.topics})
        if par >= threshold:
            edges.append(ResonanceEdge(
                repo.name, "parallel", round(par, 3),
                [f"shared topics: {', '.join(sorted(topic_overlap))}"] if topic_overlap else [],
            ))
        # kinship: description word overlap
        kin = _jaccard(ext_words, _words(repo.description))
        if kin >= threshold:
            shared = ext_words & _words(repo.description)
            edges.append(ResonanceEdge(
                repo.name, "kinship", round(kin, 3),
                [f"shared concepts: {', '.join(sorted(shared))}"] if shared else [],
            ))
    return edges


def _upstream_health(dossier: dict) -> float:
    state = dossier.get("state", {})
    score = 1.0
    if state.get("archived"):
        score -= 0.6
    if state.get("fork"):
        score -= 0.2
    if not state.get("last_push_at"):
        score -= 0.2
    return max(0.0, min(1.0, score))


def absorption_score(dossier: dict, edges: list[ResonanceEdge]) -> float:
    """Weighted absorption score in [0, 1] (higher = more valuable material)."""
    resonance = max((e.score for e in edges), default=0.0)
    distinct_internal = {e.internal_repo for e in edges}
    applicability = min(1.0, len(distinct_internal) / 3.0)
    convergence = min(1.0, len(distinct_internal) / 5.0)
    topics = dossier.get("identity", {}).get("topics", [])
    novelty = min(1.0, 0.3 + 0.1 * len(topics))
    upstream = _upstream_health(dossier)
    temporal = 1.0 if dossier.get("state", {}).get("last_push_at") else 0.4
    aesthetic = 1.0 if dossier.get("identity", {}).get("description") else 0.2

    components = {
        "resonance": resonance,
        "applicability": applicability,
        "novelty": novelty,
        "upstream_health": upstream,
        "convergence": convergence,
        "temporal": temporal,
        "aesthetic": aesthetic,
    }
    base = sum(ABSORPTION_WEIGHTS[k] * v for k, v in components.items())

    # penalties
    contracts = dossier.get("contracts", {})
    license_class = contracts.get("license", {}).get("class", "unknown")
    penalty = 0.0
    if license_class in ("none", "unknown"):
        penalty += 0.05
    if dossier.get("state", {}).get("archived"):
        penalty += 0.15
    return round(max(0.0, min(1.0, base - penalty)), 3)


def contribution_score(
    dossier: dict,
    *,
    has_verified_friction: bool = False,
    tractability: float = 0.5,
    testability: float = 0.5,
    existing_evidence: bool = False,
) -> float:
    """Weighted contribution score in [0, 1] (can we return value upstream)."""
    contracts = dossier.get("contracts", {})
    # receptivity: has CONTRIBUTING + not requiring a CLA is more receptive.
    receptivity = 0.4
    if contracts.get("contributing"):
        receptivity += 0.3
    if contracts.get("cla_or_dco") in ("dco", "none"):
        receptivity += 0.2
    strategic = min(1.0, 0.4 + 0.1 * len(dossier.get("identity", {}).get("topics", [])))

    components = {
        "verified_friction": 1.0 if has_verified_friction else 0.0,
        "tractability": max(0.0, min(1.0, tractability)),
        "testability": max(0.0, min(1.0, testability)),
        "receptivity": min(1.0, receptivity),
        "existing_evidence": 1.0 if existing_evidence else 0.0,
        "strategic": strategic,
    }
    base = sum(CONTRIBUTION_WEIGHTS[k] * v for k, v in components.items())

    penalty = 0.0
    if dossier.get("state", {}).get("archived"):
        penalty += 0.3
    if contracts.get("cla_or_dco") == "cla":
        penalty += 0.1
    return round(max(0.0, min(1.0, base - penalty)), 3)
